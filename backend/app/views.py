"""Response builders for /api/v1 read endpoints (shapes from contracts/openapi.yaml)."""
from __future__ import annotations

import base64
import json
import sqlite3
import time
from pathlib import Path

from .chain.base import ChainUnavailable, ContractRevert
from .context import AppContext, epoch_to_utc
from .contracts import canonical, digest, loads_json, sha256_hex
from .db import utc_now
from .errors import ApiError, invalid, not_found, unavailable
from .ingest import latest_verification, pending_freeze
from .policy import action_flags


def _plot_row(conn: sqlite3.Connection, plot_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM plots WHERE plot_id=?", (plot_id,)).fetchone()
    if row is None:
        raise not_found("Plot")
    return row


def health(ctx: AppContext) -> dict:
    db, worker = "DOWN", "DOWN"
    try:
        with ctx.db.reader() as conn:
            conn.execute("SELECT 1").fetchone()
            db = "UP"
            lease = conn.execute("SELECT heartbeat_at FROM worker_leases WHERE lease='main'").fetchone()
            if lease and time.time() - lease["heartbeat_at"] < ctx.settings.worker_lease_seconds:
                worker = "UP"
    except sqlite3.Error:
        pass
    try:
        identity = ctx.chain.identity()
    except Exception:
        identity = None
    ok = bool(identity and identity.ok and identity.deployment)
    return {"api": "UP", "db": db, "worker": worker, "chain": "UP" if ok else "DOWN",
            "deployment_id": identity.deployment.deployment_id if ok else None, "mode": ctx.settings.mode}


def _summary(conn: sqlite3.Connection, plot: sqlite3.Row) -> dict:
    latest = latest_verification(conn, plot["plot_id"])
    return {"plot_id": plot["plot_id"], "name": plot["name"],
            "latest_verification_id": latest["verification_id"] if latest else None,
            "evidence_quality": latest["evidence_quality"] if latest else None,
            "latest_decision": latest["decision"] if latest else None}


def plots(ctx: AppContext) -> dict:
    with ctx.db.reader() as conn:
        return {"items": [_summary(conn, p) for p in conn.execute("SELECT * FROM plots ORDER BY plot_id")]}


def _authorization_available(ctx: AppContext, conn: sqlite3.Connection, plot_id: str, actor: str,
                             deployment_id: str) -> bool:
    for auth in ctx.authorizations.values():
        if auth["plot_id"] != plot_id or auth["issuer_actor"] != actor:
            continue
        key = digest({"plot_id": plot_id, "demo_authorization_id": auth["demo_authorization_id"],
                      "deployment_id": deployment_id})
        used = conn.execute("SELECT 1 FROM operations WHERE kind='ISSUE' AND issuance_key=? AND "
                            "transaction_state IN ('QUEUED','SUBMITTED','CONFIRMED')", (key,)).fetchone()
        if not used:
            return True
    return False


def plot(ctx: AppContext, plot_id: str, actor: str) -> dict:
    with ctx.db.reader() as conn:
        row = _plot_row(conn, plot_id)
        body = _summary(conn, row)
        latest = latest_verification(conn, plot_id)
        freeze_pending = pending_freeze(conn, plot_id)
    body.update(geometry=json.loads(row["geometry_json"]), geometry_hash=row["geometry_hash"], area_ha=row["area_ha"])
    flags = {"can_issue": False, "can_buy": False, "can_transfer_backend": False}
    reason = None
    identity = ctx.chain.identity()
    if latest is None:
        reason = "No accepted verification yet"
    elif not identity.ok or identity.deployment is None:
        reason = "Chain deployment not verified; financial actions unavailable"
    else:
        deployment_id = identity.deployment.deployment_id
        with ctx.db.reader() as conn:
            batch = conn.execute("SELECT * FROM batches WHERE deployment_id=? AND plot_id=? ORDER BY batch_id LIMIT 1",
                                 (deployment_id, plot_id)).fetchone()
            authorized = _authorization_available(ctx, conn, plot_id, actor, deployment_id)
        credit_status = None
        if batch is not None:
            try:
                credit_status = ctx.chain.get_batch(int(batch["batch_id"])).credit_status
            except (ChainUnavailable, ContractRevert):
                reason = "Chain readback unavailable; financial actions unavailable"
        if reason is None:
            flags = action_flags(credit_status, latest["decision"], is_latest=True, demo_authorized=authorized,
                                 pending_freeze=freeze_pending)
            if batch is not None and actor == batch["seller_actor"]:
                flags["can_buy"] = False
            if freeze_pending:
                reason = "Freeze requested; waiting for on-chain confirmation"
            elif credit_status == "FROZEN":
                reason = "Batch is FROZEN on chain"
            elif latest["decision"] != "NO_RESTRICTION":
                reason = f"Latest decision is {latest['decision']} ({latest['reason']})"
            elif not any(flags.values()):
                reason = "No action available for this demo actor"
    body.update(flags, action_block_reason=reason)
    return body


def _verification_row(conn: sqlite3.Connection, verification_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM verifications WHERE verification_id=?", (verification_id,)).fetchone()
    if row is None:
        raise not_found("Verification")
    return row


def verification(ctx: AppContext, verification_id: str) -> dict:
    with ctx.db.reader() as conn:
        row = _verification_row(conn, verification_id)
        latest = latest_verification(conn, row["plot_id"])
        links = conn.execute("SELECT a.* FROM verification_artifacts va JOIN artifacts a USING (artifact_id) "
                             "WHERE va.verification_id=? ORDER BY a.artifact_id", (verification_id,)).fetchall()
    return {
        "verification_id": row["verification_id"],
        "evidence": loads_json(bytes(row["canonical_bytes"]).decode("utf-8")),
        "evidence_hash": row["evidence_hash"],
        "evidence_quality": row["evidence_quality"],
        "evidence_quality_score": row["evidence_quality_score"],
        "decision": row["decision"],
        "reason": row["reason"],
        "decision_record": json.loads(row["decision_record_json"]),
        "decision_hash": row["decision_hash"],
        "is_latest": latest["verification_id"] == verification_id,
        "processed_at": row["processed_at"],
        "observation_mode": row["observation_mode"],
        "computation_mode": row["computation_mode"],
        "artifacts": [{"artifact_id": a["artifact_id"], "role": a["role"], "url": "/api/v1/artifacts/" + a["artifact_id"],
                       "sha256": a["sha256"], "media_type": a["media_type"]} for a in links],
    }


def canonical_bytes(ctx: AppContext, verification_id: str) -> bytes:
    with ctx.db.reader() as conn:
        return bytes(_verification_row(conn, verification_id)["canonical_bytes"])


def proof(ctx: AppContext, verification_id: str) -> dict:
    with ctx.db.reader() as conn:
        row = _verification_row(conn, verification_id)
        confirmed = conn.execute("SELECT kind, batch_id, tx_hash, decoded_event_json FROM operations WHERE plot_id=? "
                                 "AND kind IN ('ISSUE','FREEZE') AND transaction_state='CONFIRMED' ORDER BY created_at",
                                 (row["plot_id"],)).fetchall()
    stored = bytes(row["canonical_bytes"])
    recomputed = sha256_hex(stored)
    record = json.loads(row["decision_record_json"])
    integrity_ok = (recomputed == row["evidence_hash"]
                    and canonical(loads_json(stored.decode("utf-8"))) == stored
                    and digest(record) == row["decision_hash"]
                    and record["evidence_hash"] == row["evidence_hash"])
    anchors = []
    for op in confirmed:
        event = json.loads(op["decoded_event_json"])
        # Anchor only where the confirmed event itself carries THIS evidence hash; an older
        # anchor is never attributed to newer evidence.
        if event["args"].get("evidenceHash") != row["evidence_hash"]:
            continue
        anchors.append({"event_name": event["name"], "batch_id": str(event["args"]["batchId"]),
                        "tx_hash": op["tx_hash"], "evidence_hash": event["args"]["evidenceHash"],
                        "decision_hash": event["args"].get("decisionHash") if event["name"] == "Frozen" else None,
                        "confirmed": True})
    return {"evidence_hash": row["evidence_hash"], "recomputed_hash": recomputed, "decision_hash": row["decision_hash"],
            "canonical_url": f"/api/v1/verifications/{verification_id}/canonical", "anchors": anchors,
            "integrity_ok": integrity_ok}


def history(ctx: AppContext, plot_id: str) -> dict:
    with ctx.db.reader() as conn:
        _plot_row(conn, plot_id)
        latest = latest_verification(conn, plot_id)
        rows = conn.execute("SELECT * FROM verifications WHERE plot_id=? ORDER BY observed_at, seq", (plot_id,)).fetchall()
    return {"items": [{"verification_id": r["verification_id"], "observed_at": r["observed_at"],
                       "processed_at": r["processed_at"], "outcome": r["outcome"],
                       "evidence_quality": r["evidence_quality"], "decision": r["decision"],
                       "is_latest": r["verification_id"] == latest["verification_id"]} for r in rows]}


def credits(ctx: AppContext, plot_id: str, actor: str) -> dict:
    with ctx.db.reader() as conn:
        _plot_row(conn, plot_id)
        latest = latest_verification(conn, plot_id)
        freeze_pending = pending_freeze(conn, plot_id)
    identity = ctx.chain.identity()
    if not identity.ok or identity.deployment is None:
        raise unavailable("CHAIN_UNAVAILABLE", "Credits require verified chain readback; none is shown unverified",
                          reason=(identity.reason or "").split(":")[0])
    with ctx.db.reader() as conn:
        batches = conn.execute("SELECT * FROM batches WHERE deployment_id=? AND plot_id=? ORDER BY CAST(batch_id AS INTEGER)",
                               (identity.deployment.deployment_id, plot_id)).fetchall()
    items = []
    actor_address = ctx.chain.signer_address(actor)
    checked_at = utc_now()
    for batch in batches:
        try:
            view = ctx.chain.get_batch(int(batch["batch_id"]))
            seller_balance = ctx.chain.balance_of(int(batch["batch_id"]), view.seller)
            actor_balance = ctx.chain.balance_of(int(batch["batch_id"]), actor_address)
        except (ChainUnavailable, ContractRevert):
            raise unavailable("CHAIN_UNAVAILABLE", "Chain readback failed") from None
        flags = action_flags(view.credit_status, latest["decision"] if latest else None, is_latest=latest is not None,
                             demo_authorized=False, pending_freeze=freeze_pending)
        items.append({
            "batch_id": batch["batch_id"], "plot_id": plot_id, "seller": view.seller, "actor": actor,
            "total_supply": str(view.total_supply), "seller_balance": str(seller_balance),
            "actor_balance": str(actor_balance), "unit_price_wei": str(view.unit_price_wei),
            "credit_status": view.credit_status, "evidence_hash": view.evidence_hash,
            "decision_hash": view.decision_hash, "issued_at": epoch_to_utc(view.issued_at),
            "frozen_at": epoch_to_utc(view.frozen_at) if view.frozen_at else None,
            "last_observed_at": epoch_to_utc(view.last_observed_at), "chain_state_checked_at": checked_at,
            "can_buy": flags["can_buy"] and actor != batch["seller_actor"],
            "can_transfer_backend": flags["can_transfer_backend"] and actor_balance > 0,
        })
    return {"items": items}


def job(ctx: AppContext, job_id: str) -> dict:
    with ctx.db.reader() as conn:
        row = conn.execute("SELECT * FROM verification_jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        raise not_found("Job")
    return {"job_id": row["job_id"], "state": row["state"], "verification_id": row["verification_id"],
            "error": json.loads(row["error_json"]) if row["error_json"] else None}


def operation(ctx: AppContext, operation_id: str) -> dict:
    with ctx.db.reader() as conn:
        row = conn.execute("SELECT operation_id, kind, transaction_state, tx_hash, batch_id, error_json, receipt_json "
                           "FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
    if row is None:
        raise not_found("Operation")
    confirmed = row["transaction_state"] == "CONFIRMED"
    return {"operation_id": row["operation_id"], "kind": row["kind"], "transaction_state": row["transaction_state"],
            "tx_hash": row["tx_hash"], "batch_id": row["batch_id"],
            "error": None if confirmed or not row["error_json"] else json.loads(row["error_json"]),
            "receipt": json.loads(row["receipt_json"]) if confirmed else None}


def _cursor(seq: int) -> str:
    return base64.urlsafe_b64encode(f"seq:{seq}".encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        if not raw.startswith("seq:"):
            raise ValueError
        return int(raw[4:])
    except (ValueError, UnicodeDecodeError):
        raise invalid("VALIDATION_ERROR", "Invalid cursor") from None


def events(ctx: AppContext, plot_id: str, cursor: str | None, limit: int) -> dict:
    after = _decode_cursor(cursor) if cursor else 0
    with ctx.db.reader() as conn:
        _plot_row(conn, plot_id)
        rows = conn.execute("SELECT * FROM events WHERE plot_id=? AND seq>? ORDER BY seq LIMIT ?",
                            (plot_id, after, limit + 1)).fetchall()
    page = rows[:limit]
    return {"items": [{"event_id": r["event_id"], "occurred_at": r["occurred_at"], "plot_id": r["plot_id"],
                       "kind": r["kind"], "verification_id": r["verification_id"], "operation_id": r["operation_id"],
                       "tx_hash": r["tx_hash"], "batch_id": r["batch_id"], "message": r["message"]} for r in page],
            "next_cursor": _cursor(page[-1]["seq"]) if len(rows) > limit else None}


def artifact(ctx: AppContext, artifact_id: str) -> tuple[bytes, str]:
    with ctx.db.reader() as conn:
        row = conn.execute("SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
    if row is None:
        raise not_found("Artifact")
    path = Path(ctx.settings.artifact_store) / row["storage_name"]
    try:
        data = path.read_bytes()
    except OSError:
        raise unavailable("ARTIFACT_UNAVAILABLE", "Stored artifact is missing") from None
    if sha256_hex(data) != row["sha256"] or len(data) != row["size_bytes"]:
        raise ApiError(503, "ARTIFACT_INTEGRITY_FAILED", "Stored artifact failed its hash check")
    return data, row["media_type"]
