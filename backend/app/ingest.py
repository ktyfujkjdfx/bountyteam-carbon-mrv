"""Evidence import: validate -> JCS -> SHA-256 -> policy -> decision record -> immutable storage.

Also plans oracle freeze intents. Planning is idempotent and safe to repeat on every
worker tick: a batch gets at most one freeze operation, never one for a batch that is
not ACTIVE on chain (FROZEN -> FROZEN sends nothing), and never one bound to evidence
older than the batch's last on-chain observation.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .chain.base import ChainUnavailable, ContractCall, ContractRevert
from .context import AppContext, audit, record_event, utc_to_epoch
from .contracts import ZERO_HASH, canonical, digest, loads_json, sha256_hex
from .db import utc_now
from .evidence import EvidenceRejected, Limits, safe_path, validate_evidence, validate_geometry

LIVE_STATES = ("QUEUED", "SUBMITTED", "CONFIRMED")


@dataclass(frozen=True)
class ImportResult:
    verification_id: str
    created: bool
    evidence_hash: str
    decision: str
    reason: str
    decision_hash: str


def register_plot(ctx: AppContext, plot: dict) -> bool:
    """Seed one approved plot. Returns True if inserted; refuses to silently change geometry."""
    geometry = plot["geometry"]
    validate_geometry(geometry)
    if digest(geometry) != plot["geometry_hash"]:
        raise EvidenceRejected("Plot geometry_hash does not match JCS SHA-256 of geometry")
    with ctx.db.transaction() as conn:
        row = conn.execute("SELECT geometry_hash FROM plots WHERE plot_id=?", (plot["plot_id"],)).fetchone()
        if row is not None:
            if row["geometry_hash"] != plot["geometry_hash"]:
                raise EvidenceRejected("Plot already registered with a different geometry version")
            return False
        conn.execute("INSERT INTO plots VALUES (?,?,?,?,?,?,?)",
                     (plot["plot_id"], plot["name"], json.dumps(geometry), plot["geometry_hash"],
                      float(plot["area_ha"]), plot.get("dataset_kind", "SYNTHETIC"), utc_now()))
        audit(conn, "PLOT_REGISTERED", plot["plot_id"], geometry_hash=plot["geometry_hash"])
    return True


def _store_artifact(ctx: AppContext, bundle_root: Path, artifact: dict) -> str:
    """Copy hash-verified bytes into the content-addressed store; re-verify to close TOCTOU gaps."""
    data = safe_path(bundle_root, artifact["relative_path"]).read_bytes()
    if len(data) != artifact["size_bytes"] or sha256_hex(data) != artifact["sha256"]:
        raise EvidenceRejected("Artifact changed during import", {"artifact_id": artifact["artifact_id"]})
    name = artifact["sha256"][2:] + ".bin"
    store = Path(ctx.settings.artifact_store)
    store.mkdir(parents=True, exist_ok=True)
    target = store / name
    if not target.exists():
        fd, tmp = tempfile.mkstemp(dir=store)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    return name


def _public_artifact_id(conn: sqlite3.Connection, artifact: dict) -> str:
    """Public /artifacts/{id} key.

    RS artifact_id values are unique within one bundle only; real runs reuse ids such as
    "preview_before". The evidence id is kept when free or bound to identical bytes;
    otherwise a deterministic content-namespaced id is published. Consumers use the
    Verification.artifacts[].url and match evidence entries by role/sha256.
    """
    candidates = (artifact["artifact_id"], f"{artifact['artifact_id'][:80]}.{artifact['sha256'][2:14]}")
    for candidate in candidates:
        row = conn.execute("SELECT sha256 FROM artifacts WHERE artifact_id=?", (candidate,)).fetchone()
        if row is None or row["sha256"] == artifact["sha256"]:
            return candidate
    raise EvidenceRejected("Artifact id collision with different bytes", {"artifact_id": artifact["artifact_id"]})


def import_evidence(ctx: AppContext, evidence_source: bytes | dict, bundle_root: Path, *,
                    computation_mode: str, expected_plot_id: str | None = None) -> ImportResult:
    """Accept one RS evidence bundle or raise EvidenceRejected (no decision, no transaction)."""
    if isinstance(evidence_source, (bytes, bytearray)):
        try:
            evidence = loads_json(bytes(evidence_source).decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise EvidenceRejected("Corrupt evidence JSON", {"reason": type(exc).__name__}) from None
    else:
        evidence = evidence_source
    if not isinstance(evidence, dict) or not isinstance(evidence.get("plot_id"), str):
        raise EvidenceRejected("Evidence must be an object with plot_id")
    plot_id = evidence["plot_id"]
    if expected_plot_id is not None and plot_id != expected_plot_id:
        raise EvidenceRejected("Evidence plot_id does not match the requested plot",
                               {"expected": expected_plot_id, "received": plot_id})
    with ctx.db.reader() as conn:
        plot = conn.execute("SELECT * FROM plots WHERE plot_id=?", (plot_id,)).fetchone()
    if plot is None:
        raise EvidenceRejected("Evidence refers to an unregistered plot", {"plot_id": plot_id})

    limits = Limits(ctx.settings.max_artifact_bytes, ctx.settings.max_bundle_bytes)
    result = validate_evidence(evidence, ctx.policy, bundle_root=Path(bundle_root),
                               geometry=json.loads(plot["geometry_json"]), limits=limits)
    canonical_bytes = canonical(evidence)
    evidence_hash = sha256_hex(canonical_bytes)
    observed_at = evidence["observation"]["after"]["acquired_at"]
    # Historical replay: the decision is made as of the observation time of this evidence.
    record = ctx.policy.decision_record(evidence, evidence_hash, replay_as_of=observed_at)
    decision_hash = digest(record)
    stored = {a["artifact_id"]: _store_artifact(ctx, Path(bundle_root), a) for a in evidence["artifacts"]}

    with ctx.db.transaction() as conn:
        existing = conn.execute(
            "SELECT verification_id, decision, reason, decision_hash FROM verifications "
            "WHERE plot_id=? AND geometry_hash=? AND evidence_hash=?",
            (plot_id, plot["geometry_hash"], evidence_hash)).fetchone()
        if existing is not None:
            audit(conn, "EVIDENCE_DUPLICATE", existing["verification_id"], evidence_hash=evidence_hash)
            return ImportResult(existing["verification_id"], False, evidence_hash, existing["decision"],
                                existing["reason"], existing["decision_hash"])
        public_ids = {a["artifact_id"]: _public_artifact_id(conn, a) for a in evidence["artifacts"]}
        verification_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO verifications (verification_id, plot_id, geometry_hash, evidence_hash, canonical_bytes, "
            "observed_at, processed_at, outcome, evidence_quality, evidence_quality_score, decision, reason, "
            "decision_record_json, decision_hash, policy_version, observation_mode, computation_mode) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (verification_id, plot_id, plot["geometry_hash"], evidence_hash, canonical_bytes, observed_at,
             utc_now(), evidence["outcome"], result["evidence_quality"], result["evidence_quality_score"],
             result["decision"], result["reason"], json.dumps(record), decision_hash, ctx.policy.version,
             "HISTORICAL_REPLAY", computation_mode))
        for artifact in evidence["artifacts"]:
            public_id = public_ids[artifact["artifact_id"]]
            conn.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?,?)",
                         (public_id, artifact["role"], artifact["media_type"], artifact["sha256"],
                          artifact["size_bytes"], stored[artifact["artifact_id"]]))
            conn.execute("INSERT INTO verification_artifacts VALUES (?,?)", (verification_id, public_id))
        label = f"{evidence['dataset_kind']}/{computation_mode}"
        record_event(conn, plot_id=plot_id, kind="VERIFICATION", verification_id=verification_id,
                     dedupe_key="verification:" + verification_id,
                     message=f"Evidence accepted ({label}): outcome {evidence['outcome']}, "
                             f"quality {result['evidence_quality']}, evidence_hash {evidence_hash}")
        record_event(conn, plot_id=plot_id, kind="DECISION", verification_id=verification_id,
                     dedupe_key="decision:" + verification_id,
                     message=f"Backend policy {ctx.policy.version} decision {result['decision']} "
                             f"({result['reason']}); not an on-chain state")
        audit(conn, "EVIDENCE_ACCEPTED", verification_id, evidence_hash=evidence_hash, decision_hash=decision_hash)
    return ImportResult(verification_id, True, evidence_hash, result["decision"], result["reason"], decision_hash)


def latest_verification(conn: sqlite3.Connection, plot_id: str) -> sqlite3.Row | None:
    """Newest observation wins; an older observation imported later never replaces it."""
    return conn.execute("SELECT * FROM verifications WHERE plot_id=? ORDER BY observed_at DESC, seq DESC LIMIT 1",
                        (plot_id,)).fetchone()


def pending_freeze(conn: sqlite3.Connection, plot_id: str) -> bool:
    return conn.execute("SELECT 1 FROM operations WHERE plot_id=? AND kind='FREEZE' AND "
                        "transaction_state IN ('QUEUED','SUBMITTED') LIMIT 1", (plot_id,)).fetchone() is not None


def freeze_candidate(conn: sqlite3.Connection, plot_id: str) -> sqlite3.Row | None:
    """FREEZE_REQUESTED evidence not superseded by a strictly newer observation.

    Only newer observations supersede older ones; another report for the same observation
    time (e.g. an INSUFFICIENT_DATA re-run) cannot cancel a freeze decision.
    """
    return conn.execute(
        "SELECT * FROM verifications WHERE plot_id=? AND decision='FREEZE_REQUESTED' AND observed_at = "
        "(SELECT MAX(observed_at) FROM verifications WHERE plot_id=?) ORDER BY seq DESC LIMIT 1",
        (plot_id, plot_id)).fetchone()


def plan_freeze_intents(ctx: AppContext, plot_id: str) -> list[str]:
    """Create durable FREEZE intents for ACTIVE batches for a non-superseded FREEZE_REQUESTED decision."""
    with ctx.db.reader() as conn:
        latest = freeze_candidate(conn, plot_id)
    if latest is None:
        return []
    identity = ctx.chain.identity()
    if not identity.ok or identity.deployment is None:
        return []
    deployment_id = identity.deployment.deployment_id
    with ctx.db.reader() as conn:
        batches = conn.execute("SELECT batch_id FROM batches WHERE deployment_id=? AND plot_id=? ORDER BY batch_id",
                               (deployment_id, plot_id)).fetchall()
    created = []
    observed_epoch = utc_to_epoch(latest["observed_at"])
    for row in batches:
        batch_id = row["batch_id"]
        with ctx.db.reader() as conn:
            live = conn.execute("SELECT 1 FROM operations WHERE kind='FREEZE' AND deployment_id=? AND batch_id=? AND "
                                "(transaction_state IN ('QUEUED','SUBMITTED','CONFIRMED') OR verification_id=?)",
                                (deployment_id, batch_id, latest["verification_id"])).fetchone()
        if live:
            continue
        try:
            view = ctx.chain.get_batch(int(batch_id))
        except (ChainUnavailable, ContractRevert):
            continue
        with ctx.db.transaction() as conn:
            if view.credit_status != "ACTIVE":
                audit(conn, "FREEZE_NOT_SENT_BATCH_NOT_ACTIVE", batch_id, credit_status=view.credit_status,
                      verification_id=latest["verification_id"])
                continue
            if observed_epoch < view.last_observed_at:
                audit(conn, "FREEZE_NOT_SENT_STALE_OBSERVATION", batch_id, verification_id=latest["verification_id"])
                continue
            if latest["evidence_hash"] == ZERO_HASH or latest["decision_hash"] == ZERO_HASH:
                continue
            intent = {
                "function": "freeze",
                "args": [{"type": "uint", "value": batch_id},
                         {"type": "bytes32", "value": latest["evidence_hash"]},
                         {"type": "bytes32", "value": latest["decision_hash"]},
                         {"type": "uint", "value": str(observed_epoch)},
                         {"type": "uint", "value": str(ctx.policy.fire_reversal_reason_code)}],
                "value_wei": "0",
            }
            operation_id = str(uuid.uuid4())
            try:
                conn.execute(
                    "INSERT INTO operations (operation_id, kind, transaction_state, plot_id, deployment_id, batch_id, "
                    "verification_id, sender_role, sender_address, intent_json, created_at, updated_at) "
                    "VALUES (?, 'FREEZE', 'QUEUED', ?,?,?,?, 'oracle', ?,?,?,?)",
                    (operation_id, plot_id, deployment_id, batch_id, latest["verification_id"],
                     ctx.chain.signer_address("oracle"), json.dumps(intent), utc_now(), utc_now()))
            except sqlite3.IntegrityError:
                continue  # a concurrent planner already queued the single allowed freeze
            audit(conn, "FREEZE_INTENT_QUEUED", operation_id, batch_id=batch_id,
                  verification_id=latest["verification_id"])
            created.append(operation_id)
    return created


def call_from_intent(intent: dict) -> ContractCall:
    args = []
    for arg in intent["args"]:
        if arg["type"] == "bytes32":
            args.append(bytes.fromhex(arg["value"][2:]))
        elif arg["type"] == "uint":
            args.append(int(arg["value"]))
        else:
            args.append(arg["value"])
    return ContractCall(intent["function"], tuple(args), int(intent["value_wei"]))
