"""CONTRACT_FIXTURE mock ledger with the frozen CarbonCreditRegistry semantics.

It is NOT a blockchain and never an on-chain proof: it exists so the API, worker,
idempotency and reconciliation logic can be exercised without Anvil. It still goes
through the same sign -> broadcast -> receipt -> event -> readback pipeline, so a
mock operation can only become CONFIRMED on the same evidence rules as a real one.
Settings refuse this adapter in LOCAL_DEMO mode.

State lives in a separate SQLite file to survive backend restarts. Failure injection
(`hold_mining`, `omit_events`, `corrupt_readback`, `drop_broadcasts`) exists for tests.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from ..contracts import ZERO_HASH, canonical, sha256_hex
from .base import (CREDIT_STATUS, BatchView, ChainReceipt, ChainUnavailable, ContractCall, ContractRevert,
                   DecodedEvent, Deployment, IdentityStatus, NonceConsumed, SignedTransaction)

RAW_PREFIX = b"BOUNTYTEAM-MOCK-TX-V1:"
MOCK_CHAIN_ID = "0"
MOCK_CONTRACT = "0x00000000000000000000000000000000000000c0"
ROLES = ("owner", "issuer", "oracle", "buyer", "recipient")
ZERO_ADDRESS = "0x" + "0" * 40


def mock_address(role: str) -> str:
    return "0x" + hashlib.sha256(("bountyteam-mock-account:" + role).encode()).hexdigest()[:40]


def _hex(value: Any) -> Any:
    return "0x" + value.hex() if isinstance(value, (bytes, bytearray)) else value


class MockChainAdapter:
    kind = "mock"

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS txs (tx_hash TEXT PRIMARY KEY, raw BLOB NOT NULL, sender TEXT NOT NULL,
                    nonce INTEGER NOT NULL, status TEXT NOT NULL, block_number INTEGER, receipt_status INTEGER,
                    events_json TEXT);
                CREATE TABLE IF NOT EXISTS blocks (number INTEGER PRIMARY KEY, timestamp INTEGER NOT NULL,
                    state_json TEXT NOT NULL);
            """)
            if conn.execute("SELECT 1 FROM meta WHERE key='deployment'").fetchone() is None:
                roles = {role: mock_address(role) for role in ROLES}
                deployment = {"deployment_id": str(uuid.uuid4()), "chain_id": MOCK_CHAIN_ID,
                              "contract_address": MOCK_CONTRACT,
                              "contract_code_hash": sha256_hex(b"BOUNTYTEAM-MOCK-REGISTRY"),
                              "abi_sha256": "MOCK", "roles": roles}
                state = {"batches": {}, "balances": {}, "issuance_keys": [], "next_batch_id": 1,
                         "proceeds": {}, "nonces": {}, "issuers": [roles["issuer"]], "oracles": [roles["oracle"]]}
                controls = {"hold_mining": False, "omit_events": 0, "corrupt_readback": False,
                            "drop_broadcasts": 0, "available": True}
                conn.execute("INSERT INTO meta VALUES ('deployment', ?)", (json.dumps(deployment),))
                conn.execute("INSERT INTO meta VALUES ('controls', ?)", (json.dumps(controls),))
                conn.execute("INSERT INTO blocks VALUES (0, ?, ?)", (int(time.time()), json.dumps(state)))

    # -- storage helpers -------------------------------------------------------------------------
    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            yield conn
        finally:
            conn.close()

    def _meta(self, conn: sqlite3.Connection, key: str) -> dict:
        return json.loads(conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()[0])

    def controls(self) -> dict:
        with self._conn() as conn:
            return self._meta(conn, "controls")

    def set_controls(self, **changes: Any) -> None:
        with self._lock, self._conn() as conn:
            controls = self._meta(conn, "controls")
            controls.update(changes)
            conn.execute("UPDATE meta SET value=? WHERE key='controls'", (json.dumps(controls),))

    def _check_available(self, conn: sqlite3.Connection) -> None:
        if not self._meta(conn, "controls").get("available", True):
            raise ChainUnavailable("CHAIN_UNAVAILABLE: mock chain unavailable (injected)")

    def _state(self, conn: sqlite3.Connection, block: int | None = None) -> tuple[int, dict]:
        if block is None:
            row = conn.execute("SELECT number, state_json FROM blocks ORDER BY number DESC LIMIT 1").fetchone()
        else:
            row = conn.execute("SELECT number, state_json FROM blocks WHERE number=?", (block,)).fetchone()
            if row is None:
                raise ChainUnavailable("unknown block")
        return row[0], json.loads(row[1])

    # -- identity --------------------------------------------------------------------------------
    def identity(self) -> IdentityStatus:
        with self._conn() as conn:
            try:
                self._check_available(conn)
            except ChainUnavailable as exc:
                return IdentityStatus(False, None, str(exc))
            d = self._meta(conn, "deployment")
        return IdentityStatus(True, Deployment(**d))

    def signer_address(self, role: str) -> str:
        return mock_address(role)

    def pending_nonce(self, address: str) -> int:
        with self._conn() as conn:
            self._check_available(conn)
            row = conn.execute("SELECT MAX(nonce) FROM txs WHERE sender=? AND status IN ('pending','mined')",
                               (address.lower(),)).fetchone()
            return 0 if row[0] is None else row[0] + 1

    def mined_nonce(self, address: str) -> int:
        with self._conn() as conn:
            self._check_available(conn)
            _, state = self._state(conn)
            return state["nonces"].get(address.lower(), 0)

    # -- transactions ----------------------------------------------------------------------------
    def simulate(self, sender_role: str, call: ContractCall) -> None:
        with self._conn() as conn:
            self._check_available(conn)
            number, state = self._state(conn)
            _apply(copy.deepcopy(state), mock_address(sender_role), call.function,
                   [_hex(a) for a in call.args], call.value_wei, int(time.time()))

    def sign(self, sender_role: str, call: ContractCall, nonce: int) -> SignedTransaction:
        sender = mock_address(sender_role)
        payload = {"chain_id": MOCK_CHAIN_ID, "to": MOCK_CONTRACT, "from": sender, "nonce": nonce,
                   "function": call.function, "args": [_hex(a) for a in call.args], "value": str(call.value_wei)}
        raw = RAW_PREFIX + canonical(payload)
        return SignedTransaction(raw=raw, tx_hash=sha256_hex(raw), nonce=nonce, sender=sender)

    def broadcast(self, raw: bytes, tx_hash: str) -> None:
        if not raw.startswith(RAW_PREFIX) or sha256_hex(raw) != tx_hash:
            raise ValueError("Not a mock transaction")
        tx = json.loads(raw[len(RAW_PREFIX):])
        with self._lock, self._conn() as conn:
            self._check_available(conn)
            controls = self._meta(conn, "controls")
            if controls.get("drop_broadcasts", 0) > 0:
                controls["drop_broadcasts"] -= 1
                conn.execute("UPDATE meta SET value=? WHERE key='controls'", (json.dumps(controls),))
                raise ChainUnavailable("mock broadcast dropped (injected)")
            if conn.execute("SELECT 1 FROM txs WHERE tx_hash=?", (tx_hash,)).fetchone():
                return  # already known: idempotent rebroadcast of the same bytes
            expected = self.pending_nonce(tx["from"])
            if tx["nonce"] < expected:
                raise NonceConsumed(f"nonce {tx['nonce']} already used")
            if tx["nonce"] > expected:
                raise ChainUnavailable("nonce gap; earlier transaction not yet known")
            conn.execute("INSERT INTO txs (tx_hash, raw, sender, nonce, status) VALUES (?,?,?,?, 'pending')",
                         (tx_hash, raw, tx["from"], tx["nonce"]))
            if not controls.get("hold_mining"):
                self._mine(conn)

    def mine(self) -> None:
        with self._lock, self._conn() as conn:
            self._mine(conn)

    def _mine(self, conn: sqlite3.Connection) -> None:
        controls = self._meta(conn, "controls")
        pending = conn.execute("SELECT tx_hash, raw FROM txs WHERE status='pending' ORDER BY rowid").fetchall()
        for tx_hash, raw in pending:
            number, state = self._state(conn)
            tx = json.loads(bytes(raw)[len(RAW_PREFIX):])
            block, now = number + 1, int(time.time())
            working = copy.deepcopy(state)
            try:
                events = _apply(working, tx["from"], tx["function"], tx["args"], int(tx["value"]), now)
                status = 1
            except ContractRevert:
                working = copy.deepcopy(state)
                events, status = [], 0
            working["nonces"][tx["from"]] = tx["nonce"] + 1
            if status == 1 and controls.get("omit_events", 0) > 0:
                controls["omit_events"] -= 1
                events = []
            conn.execute("INSERT INTO blocks VALUES (?,?,?)", (block, now, json.dumps(working)))
            conn.execute("UPDATE txs SET status='mined', block_number=?, receipt_status=?, events_json=? "
                         "WHERE tx_hash=?", (block, status, json.dumps(events), tx_hash))
        conn.execute("UPDATE meta SET value=? WHERE key='controls'", (json.dumps(controls),))

    def transaction_known(self, tx_hash: str) -> bool:
        with self._conn() as conn:
            self._check_available(conn)
            return conn.execute("SELECT 1 FROM txs WHERE tx_hash=?", (tx_hash,)).fetchone() is not None

    def receipt(self, tx_hash: str) -> ChainReceipt | None:
        with self._conn() as conn:
            self._check_available(conn)
            row = conn.execute("SELECT status, block_number, receipt_status, events_json FROM txs WHERE tx_hash=?",
                               (tx_hash,)).fetchone()
        if row is None or row[0] != "mined":
            return None
        events = [DecodedEvent(e["name"], e["args"]) for e in json.loads(row[3])]
        return ChainReceipt(tx_hash=tx_hash, block_number=row[1], status=row[2], contract_events=events)

    # -- views -----------------------------------------------------------------------------------
    def get_batch(self, batch_id: int, block: int | None = None) -> BatchView:
        with self._conn() as conn:
            self._check_available(conn)
            _, state = self._state(conn, block)
            corrupt = self._meta(conn, "controls").get("corrupt_readback")
        batch = state["batches"].get(str(batch_id))
        if batch is None:
            raise ContractRevert("UnknownBatch")
        view = BatchView(**{**batch, "credit_status": CREDIT_STATUS[batch["credit_status"]]})
        if corrupt:
            view = BatchView(**{**view.__dict__, "evidence_hash": "0x" + "ee" * 32})
        return view

    def balance_of(self, batch_id: int, address: str, block: int | None = None) -> int:
        with self._conn() as conn:
            self._check_available(conn)
            _, state = self._state(conn, block)
        if str(batch_id) not in state["batches"]:
            raise ContractRevert("UnknownBatch")
        return int(state["balances"].get(str(batch_id), {}).get(address.lower(), 0))


def _apply(state: dict, sender: str, function: str, args: list, value: int, now: int) -> list[dict]:
    """Execute one call against the frozen interface rules; raise ContractRevert on violation."""
    sender = sender.lower()

    def batch_of(batch_id: Any) -> dict:
        batch = state["batches"].get(str(int(batch_id)))
        if batch is None:
            raise ContractRevert("UnknownBatch")
        return batch

    def require_active(batch: dict) -> None:
        if batch["credit_status"] != 0:
            raise ContractRevert("BatchNotActive")

    if value and function != "buy":
        raise ContractRevert("IncorrectPayment")
    if function == "issue":
        key, plot_id, seller, amount, price, evidence_hash, observed_at = args
        if sender not in state["issuers"]:
            raise ContractRevert("Unauthorized")
        if not plot_id:
            raise ContractRevert("InvalidPlot")
        if seller.lower() == ZERO_ADDRESS:
            raise ContractRevert("InvalidAddress")
        if int(amount) <= 0 or int(price) <= 0:
            raise ContractRevert("InvalidAmount")
        if evidence_hash == ZERO_HASH or key == ZERO_HASH:
            raise ContractRevert("InvalidEvidence")
        if key in state["issuance_keys"]:
            raise ContractRevert("DuplicateIssuance")
        if int(observed_at) > now:
            raise ContractRevert("StaleObservation")
        batch_id = state["next_batch_id"]
        state["next_batch_id"] += 1
        state["issuance_keys"].append(key)
        state["batches"][str(batch_id)] = {
            "plot_id": plot_id, "issuance_key": key, "seller": seller.lower(), "total_supply": int(amount),
            "credit_status": 0, "unit_price_wei": int(price), "evidence_hash": evidence_hash,
            "decision_hash": ZERO_HASH, "issued_at": now, "frozen_at": 0, "last_observed_at": int(observed_at)}
        state["balances"][str(batch_id)] = {seller.lower(): int(amount)}
        return [{"name": "Issued", "args": {"batchId": batch_id, "issuanceKey": key, "seller": seller.lower(),
                                             "amount": int(amount), "evidenceHash": evidence_hash}}]
    if function == "buy":
        batch_id, amount = int(args[0]), int(args[1])
        batch = batch_of(batch_id)
        require_active(batch)
        if amount <= 0:
            raise ContractRevert("InvalidAmount")
        if sender == batch["seller"]:
            raise ContractRevert("InvalidAddress")
        balances = state["balances"][str(batch_id)]
        if balances.get(batch["seller"], 0) < amount:
            raise ContractRevert("InsufficientBalance")
        if value != amount * batch["unit_price_wei"]:
            raise ContractRevert("IncorrectPayment")
        balances[batch["seller"]] -= amount
        balances[sender] = balances.get(sender, 0) + amount
        state["proceeds"][batch["seller"]] = state["proceeds"].get(batch["seller"], 0) + value
        return [{"name": "Purchased", "args": {"batchId": batch_id, "buyer": sender, "amount": amount,
                                                "paidWei": value}}]
    if function == "transfer":
        batch_id, to, amount = int(args[0]), args[1].lower(), int(args[2])
        batch = batch_of(batch_id)
        require_active(batch)
        if amount <= 0:
            raise ContractRevert("InvalidAmount")
        if to == ZERO_ADDRESS or to == sender:
            raise ContractRevert("InvalidAddress")
        balances = state["balances"][str(batch_id)]
        if balances.get(sender, 0) < amount:
            raise ContractRevert("InsufficientBalance")
        balances[sender] -= amount
        balances[to] = balances.get(to, 0) + amount
        return [{"name": "Transferred", "args": {"batchId": batch_id, "from": sender, "to": to, "amount": amount}}]
    if function == "freeze":
        batch_id, evidence_hash, decision_hash, observed_at, reason = args
        if sender not in state["oracles"]:
            raise ContractRevert("Unauthorized")
        batch = batch_of(batch_id)
        require_active(batch)
        if evidence_hash == ZERO_HASH or decision_hash == ZERO_HASH:
            raise ContractRevert("InvalidEvidence")
        if int(reason) != 1:
            raise ContractRevert("InvalidReason")
        if int(observed_at) < batch["last_observed_at"] or int(observed_at) > now:
            raise ContractRevert("StaleObservation")
        batch.update(credit_status=1, evidence_hash=evidence_hash, decision_hash=decision_hash,
                     frozen_at=now, last_observed_at=int(observed_at))
        return [{"name": "Frozen", "args": {"batchId": int(batch_id), "evidenceHash": evidence_hash,
                                             "decisionHash": decision_hash, "observedAt": int(observed_at),
                                             "reasonCode": int(reason)}}]
    raise ContractRevert("UnknownFunction")
