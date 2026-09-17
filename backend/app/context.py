"""Wiring of settings, DB, policy, config and chain adapter shared by API, worker and CLI tools."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .chain.base import ChainAdapter
from .chain.factory import build_chain_adapter
from .config import REPO_ROOT, Settings
from .contracts import read_json
from .db import Database, migrate, utc_now
from .policy import Policy


@dataclass
class AppContext:
    settings: Settings
    db: Database
    policy: Policy
    chain: ChainAdapter
    scenarios: dict
    authorizations: dict[str, dict]
    signer_lock: threading.Lock = field(default_factory=threading.Lock)


def create_context(settings: Settings, chain: ChainAdapter | None = None) -> AppContext:
    migrate(settings.db_path)
    scenarios = read_json(settings.scenarios_path)
    authorizations = {a["demo_authorization_id"]: a
                      for a in read_json(settings.authorizations_path)["authorizations"]}
    return AppContext(settings=settings, db=Database(settings.db_path), policy=Policy.load(settings.policy_path),
                      chain=chain or build_chain_adapter(settings), scenarios=scenarios,
                      authorizations=authorizations)


def repo_path(configured: str):
    """Resolve a server-config path: relative paths must stay in the repo; absolute paths are explicit operator config."""
    if Path(configured).is_absolute():
        return Path(configured).resolve()
    path = (REPO_ROOT / configured).resolve()
    if not path.is_relative_to(REPO_ROOT):
        raise ValueError("Configured path escapes repository: " + configured)
    return path


def epoch_to_utc(value: int) -> str:
    return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_to_epoch(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


def record_event(conn: sqlite3.Connection, *, plot_id: str, kind: str, message: str,
                 verification_id: str | None = None, operation_id: str | None = None,
                 tx_hash: str | None = None, batch_id: str | None = None, dedupe_key: str | None = None) -> None:
    """Append to the unified public journal; dedupe_key makes retries/reconciliation idempotent."""
    conn.execute(
        "INSERT OR IGNORE INTO events (event_id, occurred_at, plot_id, kind, verification_id, operation_id, "
        "tx_hash, batch_id, message, dedupe_key) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), utc_now(), plot_id, kind, verification_id, operation_id, tx_hash, batch_id,
         message, dedupe_key))


def audit(conn: sqlite3.Connection, category: str, subject: str | None, **detail) -> None:
    """Internal audit trail (not public API); never store secrets or signed bytes here."""
    conn.execute("INSERT INTO audit_log (occurred_at, category, subject, detail_json) VALUES (?,?,?,?)",
                 (utc_now(), category, subject, json.dumps(detail, sort_keys=True, default=str)))
