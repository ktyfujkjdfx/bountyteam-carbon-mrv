"""SQLite persistence with ordered, recorded migrations. The DB is the durable queue."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "initial P0 schema", """
CREATE TABLE plots (
    plot_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    geometry_json TEXT NOT NULL,
    geometry_hash TEXT NOT NULL,
    area_ha REAL NOT NULL CHECK (area_ha > 0),
    dataset_kind TEXT NOT NULL CHECK (dataset_kind IN ('REAL','SYNTHETIC')),
    created_at TEXT NOT NULL
);

CREATE TABLE verification_jobs (
    job_id TEXT PRIMARY KEY,
    plot_id TEXT NOT NULL REFERENCES plots(plot_id),
    scenario_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')),
    verification_id TEXT REFERENCES verifications(verification_id),
    error_json TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK ((state = 'SUCCEEDED') = (verification_id IS NOT NULL)),
    CHECK ((state = 'FAILED') = (error_json IS NOT NULL))
);
CREATE INDEX verification_jobs_pending ON verification_jobs(state, created_at);

CREATE TABLE verifications (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    verification_id TEXT NOT NULL UNIQUE,
    plot_id TEXT NOT NULL REFERENCES plots(plot_id),
    geometry_hash TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    canonical_bytes BLOB NOT NULL,
    observed_at TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    outcome TEXT NOT NULL,
    evidence_quality TEXT NOT NULL,
    evidence_quality_score INTEGER,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    decision_record_json TEXT NOT NULL,
    decision_hash TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    observation_mode TEXT NOT NULL,
    computation_mode TEXT NOT NULL CHECK (computation_mode IN ('COMPUTED','CACHED_REPLAY')),
    UNIQUE (plot_id, geometry_hash, evidence_hash)
);
CREATE INDEX verifications_plot_latest ON verifications(plot_id, observed_at, seq);

-- Canonical evidence and hashes are write-once.
CREATE TRIGGER verifications_immutable BEFORE UPDATE ON verifications
BEGIN SELECT RAISE(ABORT, 'verification records are immutable'); END;

-- Allowlist for GET /artifacts/{id}: only manifest entries whose bytes were hash-verified at import.
CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    media_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    storage_name TEXT NOT NULL
);

CREATE TABLE verification_artifacts (
    verification_id TEXT NOT NULL REFERENCES verifications(verification_id),
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    PRIMARY KEY (verification_id, artifact_id)
);

CREATE TABLE idempotency_keys (
    actor TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_status INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (actor, operation, idempotency_key)
);

CREATE TABLE operations (
    operation_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('ISSUE','BUY','TRANSFER','FREEZE')),
    transaction_state TEXT NOT NULL CHECK (transaction_state IN ('QUEUED','SUBMITTED','CONFIRMED','FAILED')),
    plot_id TEXT NOT NULL REFERENCES plots(plot_id),
    deployment_id TEXT NOT NULL,
    batch_id TEXT,
    verification_id TEXT REFERENCES verifications(verification_id),
    issuance_key TEXT,
    sender_role TEXT NOT NULL CHECK (sender_role IN ('issuer','buyer','recipient','oracle')),
    sender_address TEXT NOT NULL,
    intent_json TEXT NOT NULL,
    tx_hash TEXT,
    receipt_json TEXT,
    decoded_event_json TEXT,
    error_json TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (transaction_state IN ('QUEUED','FAILED') OR tx_hash IS NOT NULL),
    CHECK ((transaction_state = 'CONFIRMED') = (receipt_json IS NOT NULL))
);
CREATE INDEX operations_pending ON operations(transaction_state, created_at);
-- At most one live or confirmed freeze per on-chain batch: FROZEN -> FROZEN never sends a second freeze.
CREATE UNIQUE INDEX operations_one_freeze_per_batch ON operations(deployment_id, batch_id)
    WHERE kind = 'FREEZE' AND transaction_state IN ('QUEUED','SUBMITTED','CONFIRMED');
-- A single-use demo authorization produces at most one live or confirmed issuance.
CREATE UNIQUE INDEX operations_one_issue_per_key ON operations(issuance_key)
    WHERE kind = 'ISSUE' AND transaction_state IN ('QUEUED','SUBMITTED','CONFIRMED');

-- Signed transaction material: restricted, never selected by API read paths.
CREATE TABLE operation_signed_transactions (
    operation_id TEXT PRIMARY KEY REFERENCES operations(operation_id),
    sender_address TEXT NOT NULL,
    nonce INTEGER NOT NULL,
    raw_transaction BLOB NOT NULL,
    tx_hash TEXT NOT NULL UNIQUE,
    signed_at TEXT NOT NULL,
    UNIQUE (sender_address, nonce)
);
CREATE TRIGGER signed_transactions_immutable BEFORE UPDATE ON operation_signed_transactions
BEGIN SELECT RAISE(ABORT, 'signed transactions are immutable'); END;

CREATE TABLE batches (
    deployment_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    plot_id TEXT NOT NULL REFERENCES plots(plot_id),
    issuance_key TEXT NOT NULL,
    issue_operation_id TEXT NOT NULL REFERENCES operations(operation_id),
    seller_address TEXT NOT NULL,
    seller_actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (deployment_id, batch_id)
);

CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    occurred_at TEXT NOT NULL,
    plot_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('VERIFICATION','DECISION','TX_SUBMITTED','TX_CONFIRMED','TX_FAILED')),
    verification_id TEXT,
    operation_id TEXT,
    tx_hash TEXT,
    batch_id TEXT,
    message TEXT NOT NULL,
    dedupe_key TEXT UNIQUE
);
CREATE INDEX events_plot ON events(plot_id, seq);

CREATE TABLE audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    category TEXT NOT NULL,
    subject TEXT,
    detail_json TEXT NOT NULL
);

CREATE TABLE worker_leases (
    lease TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    heartbeat_at REAL NOT NULL
);
"""),
    (2, "carbon lens v2 analyses", """
-- /api/v2 lives in its own tables. The v1 schema above is not read, written or
-- reinterpreted by the Lens code; a P0 credit state is not a passport status.
CREATE TABLE lens_analyses (
    analysis_id TEXT PRIMARY KEY,
    job_state TEXT NOT NULL CHECK (job_state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')),
    actor TEXT NOT NULL,
    request_json TEXT NOT NULL,
    geometry_hash TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    year_start INTEGER NOT NULL,
    year_end INTEGER NOT NULL,
    -- Comparison scope: two analyses may be compared only when this key matches.
    scope_key TEXT NOT NULL,
    result_json TEXT,
    content_hash TEXT,
    report_hash TEXT,
    units_q INTEGER,
    error_json TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK ((job_state = 'SUCCEEDED') = (result_json IS NOT NULL)),
    CHECK ((job_state = 'FAILED') = (error_json IS NOT NULL))
);
CREATE INDEX lens_analyses_pending ON lens_analyses(job_state, created_at);
CREATE INDEX lens_analyses_scope ON lens_analyses(scope_key, created_at);

-- Once a result is published it is the passport. A worker that wakes up late and
-- finds the job finished must not overwrite it.
CREATE TRIGGER lens_analyses_result_immutable BEFORE UPDATE ON lens_analyses
WHEN OLD.result_json IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a published analysis result is immutable'); END;

-- Allowlist for GET /analyses/{id}/artifacts/{id}: only files whose bytes were
-- hash-verified when they were stored.
CREATE TABLE lens_artifacts (
    analysis_id TEXT NOT NULL REFERENCES lens_analyses(analysis_id),
    artifact_id TEXT NOT NULL,
    role TEXT NOT NULL,
    media_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    storage_name TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    PRIMARY KEY (analysis_id, artifact_id)
);

CREATE TABLE lens_reports (
    analysis_id TEXT PRIMARY KEY REFERENCES lens_analyses(analysis_id),
    report_hash TEXT NOT NULL,
    json_bytes BLOB NOT NULL,
    html_bytes BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER lens_reports_immutable BEFORE UPDATE ON lens_reports
BEGIN SELECT RAISE(ABORT, 'a stored passport is immutable'); END;

CREATE TABLE lens_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('ANALYSIS_QUEUED','ANALYSIS_COMPLETED',
        'ANALYSIS_FAILED','EVIDENCE_REVIEW_REQUIRED','PASSPORT_SUPERSEDED',
        'PASSPORT_TAMPER_DETECTED')),
    message TEXT NOT NULL,
    dedupe_key TEXT UNIQUE
);
CREATE INDEX lens_events_analysis ON lens_events(analysis_id, seq);
"""),
    (3, "carbon lens roles, sessions and audit", """
-- Who may do what. The role lives here and is read from the session on every
-- request; it is never taken from anything the client sends.
CREATE TABLE lens_users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('PROJECT_OWNER','VERIFIER','INVESTOR')),
    -- scrypt$n$r$p$salt$hash. The password itself is never stored or logged.
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    disabled_at TEXT
);

-- Only the hash of a session token is stored, so a copy of this database does
-- not hand anyone a working session.
CREATE TABLE lens_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES lens_users(user_id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX lens_sessions_user ON lens_sessions(user_id, expires_at);

-- Failed sign-ins, for rate limiting. Successful ones are not kept here.
CREATE TABLE lens_login_failures (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE,
    occurred_at TEXT NOT NULL
);
CREATE INDEX lens_login_failures_window ON lens_login_failures(username, occurred_at);

-- What people did. Deliberately outside the scientific content hash: who read a
-- report cannot change what the report says.
CREATE TABLE lens_audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    user_id TEXT,
    role TEXT,
    action TEXT NOT NULL,
    subject TEXT,
    details_json TEXT NOT NULL
);
CREATE INDEX lens_audit_user ON lens_audit(user_id, seq);
CREATE INDEX lens_audit_subject ON lens_audit(subject, seq);
"""),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=FULL")
    return conn


def migrate(path: Path) -> list[int]:
    """Apply pending migrations in order; returns applied versions."""
    conn = connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, "
                     "description TEXT NOT NULL, applied_at TEXT NOT NULL)")
        done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        applied = []
        for version, description, sql in MIGRATIONS:
            if version in done:
                continue
            record = "INSERT INTO schema_migrations VALUES ({}, '{}', '{}');".format(
                int(version), description.replace("'", "''"), utc_now())
            try:
                conn.executescript("BEGIN IMMEDIATE;\n" + sql + "\n" + record + "\nCOMMIT;")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            applied.append(version)
        return applied
    finally:
        conn.close()


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        return connect(self.path)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Serializable write transaction (BEGIN IMMEDIATE)."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    @contextmanager
    def reader(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()
