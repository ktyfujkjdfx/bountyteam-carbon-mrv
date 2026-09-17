"""Durable worker: verification jobs and chain operation reconciliation (sole runtime tx sender).

Operation lifecycle (public states only):
  QUEUED     intent persisted -> preflight -> nonce -> sign -> persist signed bytes + tx hash
             (still QUEUED) -> broadcast. Signing is an internal step of QUEUED.
  SUBMITTED  broadcast done. Poll receipt. No receipt = stays SUBMITTED (timeout never fails);
             if the node forgot the tx, the SAME stored bytes are rebroadcast (never a new nonce).
  CONFIRMED  receipt status 1 + expected decoded event matching the intent + readback at the
             receipt block matching the intent.
  FAILED     irrecoverable pre-broadcast error, or receipt status 0.
A status-1 receipt without the expected event, or with a readback mismatch, stays SUBMITTED
with an error for reconciliation: it is never reported CONFIRMED.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from .chain.base import BatchView, ChainReceipt, ChainUnavailable, ContractRevert, NonceConsumed
from .context import AppContext, audit, record_event, repo_path
from .contracts import ZERO_HASH
from .db import utc_now
from .evidence import EvidenceRejected
from .ingest import (call_from_intent, freeze_candidate, import_evidence, latest_verification, pending_freeze,
                     plan_freeze_intents)

log = logging.getLogger("backend.worker")
EXPECTED_EVENT = {"ISSUE": "Issued", "BUY": "Purchased", "TRANSFER": "Transferred", "FREEZE": "Frozen"}


class Worker:
    def __init__(self, ctx: AppContext, worker_id: str | None = None):
        self.ctx = ctx
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._recovered = False

    # -- lease: exactly one active worker serializes nonces ---------------------------------------
    def acquire_lease(self) -> bool:
        now = time.time()
        with self.ctx.db.transaction() as conn:
            row = conn.execute("SELECT worker_id, heartbeat_at FROM worker_leases WHERE lease='main'").fetchone()
            if row and row["worker_id"] != self.worker_id and now - row["heartbeat_at"] < self.ctx.settings.worker_lease_seconds:
                return False
            conn.execute("INSERT INTO worker_leases VALUES ('main', ?, ?) ON CONFLICT(lease) DO UPDATE SET "
                         "worker_id=excluded.worker_id, heartbeat_at=excluded.heartbeat_at", (self.worker_id, now))
        return True

    def recover(self) -> None:
        """After restart: interrupted jobs are re-queued (import is idempotent by evidence hash)."""
        with self.ctx.db.transaction() as conn:
            count = conn.execute("UPDATE verification_jobs SET state='QUEUED', updated_at=? WHERE state='RUNNING'",
                                 (utc_now(),)).rowcount
            if count:
                audit(conn, "JOBS_REQUEUED_AFTER_RESTART", None, count=count)
        self._recovered = True

    def tick(self) -> bool:
        """One full pass. Returns False if another worker holds the lease."""
        if not self.acquire_lease():
            return False
        if not self._recovered:
            self.recover()
        self.process_jobs()
        self.plan_freezes()
        self.process_operations()
        return True

    def run_forever(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.tick()
            except Exception:  # keep the durable loop alive; state is in the DB
                log.exception("worker tick failed")
            stop.wait(self.ctx.settings.worker_poll_seconds)

    # -- verification jobs --------------------------------------------------------------------------
    def process_jobs(self) -> None:
        with self.ctx.db.reader() as conn:
            jobs = conn.execute("SELECT job_id FROM verification_jobs WHERE state='QUEUED' ORDER BY created_at, rowid").fetchall()
        for job in jobs:
            self.run_job(job["job_id"])

    def run_job(self, job_id: str) -> None:
        with self.ctx.db.transaction() as conn:
            job = conn.execute("SELECT * FROM verification_jobs WHERE job_id=? AND state='QUEUED'", (job_id,)).fetchone()
            if job is None:
                return
            conn.execute("UPDATE verification_jobs SET state='RUNNING', attempts=attempts+1, updated_at=? WHERE job_id=?",
                         (utc_now(), job_id))
        try:
            evidence_path, bundle_root, mode = self._resolve_scenario(job)
            result = import_evidence(self.ctx, evidence_path.read_bytes(), bundle_root, computation_mode=mode,
                                     expected_plot_id=job["plot_id"])
        except EvidenceRejected as exc:
            self._finish_job(job_id, error={"code": "INVALID_EVIDENCE", "message": exc.message,
                                            "details": {"category": "EVIDENCE", **exc.details}})
            return
        except Exception as exc:  # no stack traces to clients
            log.exception("verification job failed")
            self._finish_job(job_id, error={"code": "JOB_ERROR", "message": "Verification job failed",
                                            "details": {"reason": type(exc).__name__}})
            return
        self._finish_job(job_id, verification_id=result.verification_id)

    def _finish_job(self, job_id: str, verification_id: str | None = None, error: dict | None = None) -> None:
        with self.ctx.db.transaction() as conn:
            if error is None:
                conn.execute("UPDATE verification_jobs SET state='SUCCEEDED', verification_id=?, updated_at=? "
                             "WHERE job_id=?", (verification_id, utc_now(), job_id))
            else:
                conn.execute("UPDATE verification_jobs SET state='FAILED', error_json=?, updated_at=? WHERE job_id=?",
                             (json.dumps(error), utc_now(), job_id))
                audit(conn, "VERIFICATION_JOB_FAILED", job_id, code=error["code"], message=error["message"])

    def _resolve_scenario(self, job) -> tuple[Path, Path, str]:
        scenario = self.ctx.scenarios["scenarios"][job["scenario_id"]]
        settings = self.ctx.settings
        if settings.rs_mode == "cached_bundle":
            evidence_path = repo_path(scenario["fixture"])
            return evidence_path, evidence_path.parent, "CACHED_REPLAY"
        output = Path(settings.rs_work_dir) / job["job_id"]
        if output.exists():
            shutil.rmtree(output)  # interrupted run: recompute from scratch
        output.parent.mkdir(parents=True, exist_ok=True)
        command = list(settings.rs_command or (sys.executable, "-m", "rs.verify"))
        command += ["--request", str(repo_path(scenario["rs_request"])), "--output", str(output)]
        completed = subprocess.run(command, cwd=repo_path("."), capture_output=True, text=True, timeout=1800)
        if completed.returncode != 0:
            raise EvidenceRejected("RS computation failed", {"exit_code": completed.returncode,
                                                             "stderr_tail": completed.stderr[-500:]})
        return output / "verification.json", output, "COMPUTED"

    # -- oracle freeze planning -----------------------------------------------------------------------
    def plan_freezes(self) -> None:
        with self.ctx.db.reader() as conn:
            plots = [r["plot_id"] for r in conn.execute("SELECT plot_id FROM plots")]
        for plot_id in plots:
            plan_freeze_intents(self.ctx, plot_id)

    # -- chain operations -----------------------------------------------------------------------------
    def process_operations(self) -> None:
        with self.ctx.db.reader() as conn:
            ops = conn.execute("SELECT operation_id FROM operations WHERE transaction_state IN ('QUEUED','SUBMITTED') "
                               "ORDER BY created_at, rowid").fetchall()
        for op in ops:
            self.step_operation(op["operation_id"])

    def _load(self, operation_id: str):
        with self.ctx.db.reader() as conn:
            return conn.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()

    def _set_error(self, operation_id: str, code: str, message: str, **details) -> None:
        with self.ctx.db.transaction() as conn:
            conn.execute("UPDATE operations SET error_json=?, attempts=attempts+1, updated_at=? WHERE operation_id=?",
                         (json.dumps({"code": code, "message": message, "details": details}), utc_now(), operation_id))

    def _fail(self, op, code: str, message: str, **details) -> None:
        with self.ctx.db.transaction() as conn:
            updated = conn.execute(
                "UPDATE operations SET transaction_state='FAILED', error_json=?, updated_at=? "
                "WHERE operation_id=? AND transaction_state IN ('QUEUED','SUBMITTED')",
                (json.dumps({"code": code, "message": message, "details": details}), utc_now(), op["operation_id"])).rowcount
            if updated:
                record_event(conn, plot_id=op["plot_id"], kind="TX_FAILED", operation_id=op["operation_id"],
                             tx_hash=op["tx_hash"], batch_id=op["batch_id"], dedupe_key="failed:" + op["operation_id"],
                             message=f"{op['kind']} failed: {code}")
                audit(conn, "OPERATION_FAILED", op["operation_id"], code=code, **details)

    def step_operation(self, operation_id: str) -> None:
        op = self._load(operation_id)
        if op is None or op["transaction_state"] not in ("QUEUED", "SUBMITTED"):
            return
        identity = self.ctx.chain.identity()
        if not identity.ok or identity.deployment is None:
            self._set_error(operation_id, "CHAIN_UNAVAILABLE" if (identity.reason or "").startswith("CHAIN_UNAVAILABLE")
                            else "DEPLOYMENT_MISMATCH", "Chain identity not verified; operation kept for reconciliation",
                            reason=(identity.reason or "").split(":")[0])
            return
        if identity.deployment.deployment_id != op["deployment_id"]:
            if op["transaction_state"] == "QUEUED" and self._signed(operation_id) is None:
                self._fail(op, "DEPLOYMENT_MISMATCH", "Intent belongs to a different deployment; never broadcast")
            else:
                self._set_error(operation_id, "DEPLOYMENT_CHANGED",
                                "Transaction was prepared for another deployment; manual reconciliation required")
            return
        try:
            if op["transaction_state"] == "QUEUED":
                self._advance_queued(op)
                op = self._load(operation_id)
            if op["transaction_state"] == "SUBMITTED":
                self._reconcile_submitted(op)
        except ChainUnavailable as exc:
            self._set_error(operation_id, "CHAIN_UNAVAILABLE", "Chain temporarily unavailable; will retry",
                            reason=str(exc)[:120])

    def _financial_gate_still_open(self, op) -> bool:
        """Re-check the API gate at signing time: accepted-but-unsent intents obey later decisions."""
        with self.ctx.db.reader() as conn:
            latest = latest_verification(conn, op["plot_id"])
            freeze = freeze_candidate(conn, op["plot_id"]) is not None or pending_freeze(conn, op["plot_id"])
        return latest is not None and latest["decision"] == "NO_RESTRICTION" and not freeze

    def _signed(self, operation_id: str):
        with self.ctx.db.reader() as conn:
            return conn.execute("SELECT * FROM operation_signed_transactions WHERE operation_id=?",
                                (operation_id,)).fetchone()

    def _advance_queued(self, op) -> None:
        signed = self._signed(op["operation_id"])
        if signed is None:
            if op["kind"] != "FREEZE" and not self._financial_gate_still_open(op):
                self._fail(op, "ACTION_NO_LONGER_ALLOWED",
                           "Backend decision changed or a freeze is pending before signing; no transaction was sent")
                return
            call = call_from_intent(json.loads(op["intent_json"]))
            try:
                self.ctx.chain.simulate(op["sender_role"], call)
            except ContractRevert as exc:
                self._fail(op, "CONTRACT_REVERT", "Preflight call reverted; no transaction was sent",
                           contract_error=exc.error_name)
                return
            with self.ctx.signer_lock:
                with self.ctx.db.reader() as conn:
                    local = conn.execute("SELECT MAX(nonce) AS n FROM operation_signed_transactions WHERE sender_address=?",
                                         (op["sender_address"],)).fetchone()["n"]
                nonce = max(self.ctx.chain.pending_nonce(op["sender_address"]), -1 if local is None else local + 1)
                try:
                    tx = self.ctx.chain.sign(op["sender_role"], call, nonce)
                except ContractRevert as exc:
                    self._fail(op, "CONTRACT_REVERT", "Gas estimation reverted; no transaction was sent",
                               contract_error=exc.error_name)
                    return
                if tx.sender.lower() != op["sender_address"].lower():
                    self._fail(op, "SIGNER_MISMATCH", "Signer address differs from the intent sender")
                    return
                with self.ctx.db.transaction() as conn:
                    conn.execute("INSERT INTO operation_signed_transactions VALUES (?,?,?,?,?,?)",
                                 (op["operation_id"], tx.sender, tx.nonce, tx.raw, tx.tx_hash, utc_now()))
                    conn.execute("UPDATE operations SET tx_hash=?, updated_at=? WHERE operation_id=?",
                                 (tx.tx_hash, utc_now(), op["operation_id"]))
                    audit(conn, "TRANSACTION_SIGNED", op["operation_id"], nonce=tx.nonce, tx_hash=tx.tx_hash)
            signed = self._signed(op["operation_id"])
        try:
            self.ctx.chain.broadcast(bytes(signed["raw_transaction"]), signed["tx_hash"])
        except NonceConsumed:
            if self.ctx.chain.receipt(signed["tx_hash"]) is None:
                self._fail(op, "NONCE_CONSUMED", "Stored nonce was consumed by another transaction; nothing re-signed")
                return
        with self.ctx.db.transaction() as conn:
            updated = conn.execute("UPDATE operations SET transaction_state='SUBMITTED', error_json=NULL, updated_at=? "
                                   "WHERE operation_id=? AND transaction_state='QUEUED'",
                                   (utc_now(), op["operation_id"])).rowcount
            if updated:
                record_event(conn, plot_id=op["plot_id"], kind="TX_SUBMITTED", operation_id=op["operation_id"],
                             tx_hash=signed["tx_hash"], batch_id=op["batch_id"],
                             dedupe_key="submitted:" + op["operation_id"],
                             message=f"{op['kind']} transaction broadcast; not yet confirmed")

    def _reconcile_submitted(self, op) -> None:
        receipt = self.ctx.chain.receipt(op["tx_hash"])
        if receipt is None:
            if not self.ctx.chain.transaction_known(op["tx_hash"]):
                signed = self._signed(op["operation_id"])
                try:
                    self.ctx.chain.broadcast(bytes(signed["raw_transaction"]), signed["tx_hash"])
                except NonceConsumed:
                    self._set_error(op["operation_id"], "RECONCILIATION_REQUIRED",
                                    "Transaction unknown and its nonce was consumed; not re-signed")
                    return
            self._set_error(op["operation_id"], "RECEIPT_PENDING", "No receipt yet; operation remains SUBMITTED")
            return
        if receipt.status != 1:
            self._fail(op, "TX_REVERTED", "Transaction receipt status 0", block_number=receipt.block_number)
            return
        intent = json.loads(op["intent_json"])
        event = self._expected_event(op, intent, receipt)
        if event is None:
            self._set_error(op["operation_id"], "EXPECTED_EVENT_MISSING",
                            "Receipt succeeded without the expected matching event; not confirmed",
                            expected=EXPECTED_EVENT[op["kind"]])
            return
        batch_id = str(event.args["batchId"])
        try:
            readback_ok = self._readback(op, intent, event, receipt)
        except ContractRevert as exc:
            readback_ok = False
            log.warning("readback reverted: %s", exc.error_name)
        if not readback_ok:
            self._set_error(op["operation_id"], "READBACK_MISMATCH",
                            "Contract readback does not match the transaction; not confirmed", block_number=receipt.block_number)
            return
        summary = {"transaction_hash": receipt.tx_hash, "block_number": str(receipt.block_number), "status": 1,
                   "event_names": [e.name for e in receipt.contract_events], "state_readback_ok": True}
        with self.ctx.db.transaction() as conn:
            updated = conn.execute(
                "UPDATE operations SET transaction_state='CONFIRMED', batch_id=?, receipt_json=?, decoded_event_json=?, "
                "error_json=NULL, updated_at=? WHERE operation_id=? AND transaction_state='SUBMITTED'",
                (batch_id, json.dumps(summary), json.dumps({"name": event.name, "args": event.args}), utc_now(),
                 op["operation_id"])).rowcount
            if not updated:
                return
            if op["kind"] == "ISSUE":
                conn.execute("INSERT OR IGNORE INTO batches VALUES (?,?,?,?,?,?,?,?)",
                             (op["deployment_id"], batch_id, op["plot_id"], op["issuance_key"], op["operation_id"],
                              str(event.args["seller"]).lower(), intent["seller_actor"], utc_now()))
            record_event(conn, plot_id=op["plot_id"], kind="TX_CONFIRMED", operation_id=op["operation_id"],
                         tx_hash=receipt.tx_hash, batch_id=batch_id, dedupe_key="confirmed:" + op["operation_id"],
                         message=f"{op['kind']} confirmed: receipt status 1, event {event.name}, readback verified")
            audit(conn, "OPERATION_CONFIRMED", op["operation_id"], block_number=receipt.block_number)

    @staticmethod
    def _expected_event(op, intent: dict, receipt: ChainReceipt):
        args = [a["value"] for a in intent["args"]]
        sender = op["sender_address"].lower()
        for event in receipt.contract_events:
            if event.name != EXPECTED_EVENT[op["kind"]]:
                continue
            e = event.args
            if op["kind"] == "ISSUE":
                ok = (e["issuanceKey"] == args[0] and str(e["seller"]).lower() == args[2].lower()
                      and int(e["amount"]) == int(args[3]) and e["evidenceHash"] == args[5])
            elif op["kind"] == "BUY":
                ok = (int(e["batchId"]) == int(args[0]) and str(e["buyer"]).lower() == sender
                      and int(e["amount"]) == int(args[1]) and int(e["paidWei"]) == int(intent["value_wei"]))
            elif op["kind"] == "TRANSFER":
                ok = (int(e["batchId"]) == int(args[0]) and str(e["from"]).lower() == sender
                      and str(e["to"]).lower() == args[1].lower() and int(e["amount"]) == int(args[2]))
            else:
                ok = (int(e["batchId"]) == int(args[0]) and e["evidenceHash"] == args[1] and e["decisionHash"] == args[2]
                      and int(e["observedAt"]) == int(args[3]) and int(e["reasonCode"]) == int(args[4]))
            if ok:
                return event
        return None

    def _readback(self, op, intent: dict, event, receipt: ChainReceipt) -> bool:
        """Read contract state at the receipt block (and the block before for balance deltas)."""
        chain, block = self.ctx.chain, receipt.block_number
        args = [a["value"] for a in intent["args"]]
        batch_id = int(event.args["batchId"])
        if op["kind"] == "ISSUE":
            view: BatchView = chain.get_batch(batch_id, block)
            return (view.plot_id == args[1] and view.issuance_key == args[0] and view.seller == args[2].lower()
                    and view.total_supply == int(args[3]) and view.unit_price_wei == int(args[4])
                    and view.evidence_hash == args[5] and view.credit_status == "ACTIVE"
                    and chain.balance_of(batch_id, args[2], block) == int(args[3]))
        if op["kind"] == "FREEZE":
            view = chain.get_batch(batch_id, block)
            return (view.credit_status == "FROZEN" and view.evidence_hash == args[1] and view.decision_hash == args[2]
                    and view.decision_hash != ZERO_HASH and view.last_observed_at == int(args[3]) and view.frozen_at > 0)
        amount = int(args[-1])
        if op["kind"] == "BUY":
            receiver, payer = op["sender_address"], intent["seller"]
        else:
            receiver, payer = args[1], op["sender_address"]
        before, after = block - 1, block
        return (chain.balance_of(batch_id, receiver, after) - chain.balance_of(batch_id, receiver, before) == amount
                and chain.balance_of(batch_id, payer, before) - chain.balance_of(batch_id, payer, after) == amount)


def start_worker_thread(ctx: AppContext) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()
    thread = threading.Thread(target=Worker(ctx).run_forever, args=(stop,), name="backend-worker", daemon=True)
    thread.start()
    return thread, stop
