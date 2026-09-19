"""Durable storage for Lens analyses, artifacts and passports.

The database is the queue, exactly as it is for P0: a restart re-queues interrupted work
and loses nothing, because nothing about a job lives only in a process. A published result
is immutable at the schema level, so a worker that wakes up after its job was finished by
someone else cannot overwrite a passport that has already been handed out.

Artifact bytes are stored under their own digest and verified again on the way out. The
store only ever hands back a file whose bytes still hash to what was recorded.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

from ..context import AppContext
from ..contracts import loads_json, sha256_hex
from ..db import utc_now
from ..errors import ApiError, not_found, unavailable

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def scope_key(*, geometry_hash: str, year_start: int, year_end: int, pool: str,
              method_version: str) -> str:
    """Two analyses are comparable only when every part of this key matches."""
    return f"{geometry_hash}|{year_start}|{year_end}|{pool}|{method_version}"


def new_id() -> str:
    return str(uuid.uuid4())


def record_event(conn: sqlite3.Connection, *, analysis_id: str, kind: str, message: str,
                 dedupe_key: str | None = None) -> None:
    conn.execute("INSERT OR IGNORE INTO lens_events (occurred_at, analysis_id, kind, message, "
                 "dedupe_key) VALUES (?,?,?,?,?)",
                 (utc_now(), analysis_id, kind, message, dedupe_key))


class LensStore:
    def __init__(self, ctx: AppContext, artifact_root: Path):
        self.ctx = ctx
        self.artifact_root = Path(artifact_root)

    # -- analyses ---------------------------------------------------------------------
    def queue(self, conn: sqlite3.Connection, *, analysis_id: str, actor: str, request: dict,
              geometry_hash: str, input_hash: str, year_start: int, year_end: int,
              scope: str) -> dict:
        now = utc_now()
        conn.execute(
            "INSERT INTO lens_analyses (analysis_id, job_state, actor, request_json, "
            "geometry_hash, input_hash, year_start, year_end, scope_key, created_at, updated_at) "
            "VALUES (?,'QUEUED',?,?,?,?,?,?,?,?,?)",
            (analysis_id, actor, json.dumps(request, ensure_ascii=False, sort_keys=True),
             geometry_hash, input_hash, year_start, year_end, scope, now, now))
        record_event(conn, analysis_id=analysis_id, kind="ANALYSIS_QUEUED",
                     message="Анализ поставлен в очередь.",
                     dedupe_key=f"queued:{analysis_id}")
        return {"analysis_id": analysis_id, "job_state": "QUEUED", "created_at": now}

    def get(self, analysis_id: str) -> sqlite3.Row | None:
        with self.ctx.db.reader() as conn:
            return conn.execute("SELECT * FROM lens_analyses WHERE analysis_id=?",
                                (analysis_id,)).fetchone()

    def require(self, analysis_id: str) -> sqlite3.Row:
        row = self.get(analysis_id)
        if row is None:
            raise not_found("Analysis")
        return row

    def pending(self) -> list[str]:
        with self.ctx.db.reader() as conn:
            return [row["analysis_id"] for row in conn.execute(
                "SELECT analysis_id FROM lens_analyses WHERE job_state='QUEUED' "
                "ORDER BY created_at, rowid")]

    def claim(self, analysis_id: str) -> sqlite3.Row | None:
        """Move one queued analysis to RUNNING; returns None if someone else took it."""
        with self.ctx.db.transaction() as conn:
            row = conn.execute("SELECT * FROM lens_analyses WHERE analysis_id=? AND "
                               "job_state='QUEUED'", (analysis_id,)).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE lens_analyses SET job_state='RUNNING', attempts=attempts+1, "
                         "updated_at=? WHERE analysis_id=?", (utc_now(), analysis_id))
            return row

    def requeue_interrupted(self) -> int:
        with self.ctx.db.transaction() as conn:
            return conn.execute(
                "UPDATE lens_analyses SET job_state='QUEUED', updated_at=? "
                "WHERE job_state='RUNNING' AND result_json IS NULL", (utc_now(),)).rowcount

    def previous(self, scope: str, *, before_id: str) -> dict | None:
        """The most recent published result in the same comparison scope."""
        with self.ctx.db.reader() as conn:
            row = conn.execute(
                "SELECT content_hash, units_q FROM lens_analyses WHERE scope_key=? "
                "AND job_state='SUCCEEDED' AND analysis_id<>? ORDER BY created_at DESC, rowid "
                "DESC LIMIT 1", (scope, before_id)).fetchone()
        if row is None:
            return None
        return {"content_hash": row["content_hash"], "q": row["units_q"]}

    def publish(self, analysis_id: str, result: dict, report: tuple[dict, str],
                artifacts: Iterable[dict]) -> bool:
        """Commit result, artifact rows and passport atomically. False if already published."""
        document, html = report
        with self.ctx.db.transaction() as conn:
            row = conn.execute("SELECT job_state, result_json FROM lens_analyses "
                               "WHERE analysis_id=?", (analysis_id,)).fetchone()
            if row is None or row["result_json"] is not None:
                return False
            for artifact in artifacts:
                conn.execute(
                    "INSERT OR REPLACE INTO lens_artifacts (analysis_id, artifact_id, role, "
                    "media_type, sha256, size_bytes, storage_name, metadata_json) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (analysis_id, artifact["artifact_id"], artifact["role"],
                     artifact["media_type"], artifact["sha256"], artifact["size_bytes"],
                     artifact["storage_name"],
                     json.dumps(artifact["metadata"], ensure_ascii=False, sort_keys=True)))
            conn.execute(
                "INSERT INTO lens_reports (analysis_id, report_hash, json_bytes, html_bytes, "
                "created_at) VALUES (?,?,?,?,?)",
                (analysis_id, result["passport"]["report_hash"],
                 json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8"),
                 html.encode("utf-8"), utc_now()))
            conn.execute(
                "UPDATE lens_analyses SET job_state='SUCCEEDED', result_json=?, content_hash=?, "
                "report_hash=?, units_q=?, updated_at=? WHERE analysis_id=?",
                (json.dumps(result, ensure_ascii=False, sort_keys=True),
                 result["passport"]["content_hash"], result["passport"]["report_hash"],
                 result["units"]["q"], utc_now(), analysis_id))
            record_event(conn, analysis_id=analysis_id, kind="ANALYSIS_COMPLETED",
                         message=_completion_message(result),
                         dedupe_key=f"completed:{analysis_id}")
            if result["evidence_status"] == "REVIEW_REQUIRED":
                record_event(conn, analysis_id=analysis_id, kind="EVIDENCE_REVIEW_REQUIRED",
                             message="Объяснение изменения требует проверки.",
                             dedupe_key=f"evidence:{analysis_id}")
            if result["passport"]["previous_hash"]:
                record_event(conn, analysis_id=analysis_id, kind="PASSPORT_SUPERSEDED",
                             message=result["passport"]["comparison_note"],
                             dedupe_key=f"superseded:{analysis_id}")
        return True

    def fail(self, analysis_id: str, error: dict) -> None:
        with self.ctx.db.transaction() as conn:
            row = conn.execute("SELECT result_json FROM lens_analyses WHERE analysis_id=?",
                               (analysis_id,)).fetchone()
            if row is None or row["result_json"] is not None:
                return
            conn.execute("UPDATE lens_analyses SET job_state='FAILED', error_json=?, "
                         "updated_at=? WHERE analysis_id=?",
                         (json.dumps(error, ensure_ascii=False, sort_keys=True), utc_now(),
                          analysis_id))
            record_event(conn, analysis_id=analysis_id, kind="ANALYSIS_FAILED",
                         message=error.get("message", "Анализ не выполнен."),
                         dedupe_key=f"failed:{analysis_id}")

    def result(self, analysis_id: str) -> dict | None:
        row = self.require(analysis_id)
        return loads_json(row["result_json"]) if row["result_json"] else None

    def events(self, analysis_id: str, limit: int = 50) -> list[dict]:
        with self.ctx.db.reader() as conn:
            rows = conn.execute("SELECT occurred_at, kind, message FROM lens_events "
                                "WHERE analysis_id=? ORDER BY seq LIMIT ?",
                                (analysis_id, limit)).fetchall()
        return [dict(row) for row in rows]

    # -- artifacts --------------------------------------------------------------------
    def store_artifact(self, data: bytes, *, expected_sha256: str | None = None) -> str:
        """Write bytes under their own digest; refuse anything that does not match."""
        if len(data) > MAX_ARTIFACT_BYTES:
            raise unavailable("ARTIFACT_TOO_LARGE", "Artifact exceeds the configured limit")
        digest_hex = sha256_hex(data)
        if expected_sha256 and expected_sha256 != digest_hex:
            raise unavailable("ARTIFACT_INTEGRITY_FAILED",
                              "Artifact bytes changed between production and storage")
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        name = digest_hex[2:] + ".bin"
        path = self.artifact_root / name
        if not path.exists():
            temporary = path.with_suffix(".part")
            temporary.write_bytes(data)
            temporary.replace(path)
        return name

    def artifact(self, analysis_id: str, artifact_id: str) -> tuple[bytes, str]:
        with self.ctx.db.reader() as conn:
            row = conn.execute("SELECT * FROM lens_artifacts WHERE analysis_id=? AND "
                               "artifact_id=?", (analysis_id, artifact_id)).fetchone()
        if row is None:
            raise not_found("Artifact")
        path = self.artifact_root / row["storage_name"]
        # The stored name is a digest this process wrote; it can never contain a separator,
        # but the check stays so a corrupted row cannot become a path traversal.
        if not _inside(self.artifact_root, path):
            raise unavailable("ARTIFACT_UNAVAILABLE", "Stored artifact is not addressable")
        try:
            data = path.read_bytes()
        except OSError:
            raise unavailable("ARTIFACT_UNAVAILABLE", "Stored artifact is missing") from None
        if len(data) != row["size_bytes"] or sha256_hex(data) != row["sha256"]:
            raise ApiError(503, "ARTIFACT_INTEGRITY_FAILED",
                           "Stored artifact failed its hash check")
        return data, row["media_type"]

    def artifact_rows(self, analysis_id: str) -> list[dict]:
        with self.ctx.db.reader() as conn:
            rows = conn.execute("SELECT * FROM lens_artifacts WHERE analysis_id=? "
                                "ORDER BY artifact_id", (analysis_id,)).fetchall()
        return [dict(row) for row in rows]

    # -- reports ----------------------------------------------------------------------
    def report(self, analysis_id: str) -> tuple[dict, bytes] | None:
        with self.ctx.db.reader() as conn:
            row = conn.execute("SELECT report_hash, json_bytes, html_bytes FROM lens_reports "
                               "WHERE analysis_id=?", (analysis_id,)).fetchone()
        if row is None:
            return None
        return loads_json(bytes(row["json_bytes"])), bytes(row["html_bytes"])


def _inside(root: Path, candidate: Path) -> bool:
    try:
        return candidate.resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False


def _completion_message(result: dict) -> str:
    units = result["units"]
    if units["status"] == "UNAVAILABLE":
        return f"Анализ завершён; единицы не рассчитаны ({units['unavailable_reason']})."
    if units["q"] == 0:
        return f"Анализ завершён; расчёт даёт 0 единиц ({units['zero_reason']})."
    return f"Анализ завершён; расчёт даёт {units['q']} потенциальных единиц."


def artifact_record(*, artifact_id: str, role: str, media_type: str, sha256: str,
                    size_bytes: int, storage_name: str, metadata: dict) -> dict[str, Any]:
    return {"artifact_id": artifact_id, "role": role, "media_type": media_type,
            "sha256": sha256, "size_bytes": size_bytes, "storage_name": storage_name,
            "metadata": metadata}
