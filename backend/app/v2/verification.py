"""The verification request: what a person works with, from a draft to a passport.

An analysis is a calculation. A request is the thing somebody is responsible for, and
the two are deliberately separate rows: the calculation is immutable once published, the
request moves through states, and neither can quietly rewrite the other.

    DRAFT -> SUBMITTED -> ANALYSING -> CALCULATED -> FINALIZED

Two rules hold the whole workflow up:

- **Nothing advances on its own.** A failed run returns the request to SUBMITTED so it
  can be tried again. An analysis that honestly could not produce a number still reaches
  CALCULATED, because the calculation did finish; what it must never do is arrive at
  FINALIZED without a verifier putting it there.
- **Finalizing changes no number.** It records that a named person accepted a particular
  passport content hash at a particular time. Recalculating later produces a new
  passport and leaves the pinned one exactly as it was.
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from ..contracts import loads_json
from ..db import utc_now
from ..errors import conflict, forbidden, not_found
from . import auth, catalog, geometry
from .adapters.carbon import POOL, UNIT

log = logging.getLogger("backend.lens.verification")

DRAFT = "DRAFT"
SUBMITTED = "SUBMITTED"
ANALYSING = "ANALYSING"
CALCULATED = "CALCULATED"
FINALIZED = "FINALIZED"
STATUSES = (DRAFT, SUBMITTED, ANALYSING, CALCULATED, FINALIZED)

# Which move is allowed from where. A move that is not here does not happen, and the
# answer is 409 rather than a silently ignored request.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    DRAFT: (SUBMITTED,),
    SUBMITTED: (ANALYSING,),
    # A run that fails goes back to SUBMITTED; a run that finishes reaches CALCULATED.
    ANALYSING: (CALCULATED, SUBMITTED),
    # Recalculating a request that was already calculated is allowed and expected.
    CALCULATED: (FINALIZED, ANALYSING),
    # A finalized request is the end of this request's life. A new verification of the
    # same contour is a new request, so that a pinned passport is never reopened.
    FINALIZED: (),
}


def new_request_id() -> str:
    return "vr-" + secrets.token_hex(8)


def _row(conn: Any, request_id: str) -> Any:
    return conn.execute("SELECT * FROM lens_requests WHERE request_id = ?",
                        (request_id,)).fetchone()


def _events(conn: Any, request_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT occurred_at, from_status, to_status, user_id, note"
        " FROM lens_request_events WHERE request_id = ? ORDER BY seq", (request_id,))
    return [dict(row) for row in rows]


def _record(conn: Any, request_id: str, *, from_status: str | None, to_status: str,
            user_id: str | None, note: str) -> None:
    conn.execute(
        "INSERT INTO lens_request_events (request_id, occurred_at, from_status,"
        " to_status, user_id, note) VALUES (?, ?, ?, ?, ?, ?)",
        (request_id, utc_now(), from_status, to_status, user_id, note))


def _require_transition(current: str, target: str) -> None:
    if target not in TRANSITIONS[current]:
        raise conflict("INVALID_TRANSITION",
                       f"Заявка в состоянии {current} не может перейти в {target}.",
                       from_status=current, to_status=target)


# -- reading ---------------------------------------------------------------------------
def view(ctx: Any, request_id: str, *, who: auth.Principal) -> dict:
    with ctx.db.reader() as conn:
        row = _row(conn, request_id)
        if row is None or not _visible(row, who):
            # 404 rather than 403, so probing identifiers cannot reveal which exist.
            raise not_found("Request")
        return _public(conn, row, ctx)


def listing(ctx: Any, *, who: auth.Principal) -> dict:
    """The requests this role may see.

    An owner sees their own. A verifier sees all of them, because reviewing them is the
    job. An investor sees only the finalized ones: a draft is not a finding.
    """
    with ctx.db.reader() as conn:
        rows = conn.execute(
            "SELECT * FROM lens_requests ORDER BY created_at DESC, request_id").fetchall()
        return {"requests": [_public(conn, row, ctx) for row in rows
                             if _visible(row, who)]}


def _visible(row: Any, who: auth.Principal) -> bool:
    if auth.allows(who, "analysis.read.any"):
        return True
    if row["owner_id"] == who.user_id:
        return True
    return row["status"] == FINALIZED and auth.allows(who, "analysis.read.finalized")


def _public(conn: Any, row: Any, ctx: Any) -> dict:
    owner = conn.execute(
        "SELECT user_id, username, display_name, role FROM lens_users WHERE user_id = ?",
        (row["owner_id"],)).fetchone()
    analysis_id = row["analysis_id"]
    return {
        "request_id": row["request_id"],
        "status": row["status"],
        "owner": dict(owner) if owner else {
            "user_id": row["owner_id"], "username": "unknown",
            "display_name": "unknown", "role": "PROJECT_OWNER"},
        "aoi_id": row["aoi_id"],
        "geometry": loads_json(row["geometry_json"]),
        "geometry_hash": row["geometry_hash"],
        "area_ha": row["area_ha"],
        "year_start": row["year_start"],
        "year_end": row["year_end"],
        "claimed_units": row["claimed_units"],
        "claim_pool": row["claim_pool"],
        "claim_unit": row["claim_unit"],
        "analysis_id": analysis_id,
        "analysis_url": f"/api/v2/analyses/{analysis_id}" if analysis_id else None,
        "passport_hash": row["passport_hash"],
        "finalized_by": row["finalized_by"],
        "finalized_at": row["finalized_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "events": _events(conn, row["request_id"]),
    }


# -- writing ---------------------------------------------------------------------------
def create(ctx: Any, *, who: auth.Principal, body: dict) -> dict:
    """A new draft. Nothing is calculated yet and no worker is involved."""
    aoi_id = body.get("aoi_id")
    raw = body.get("geometry")
    if raw is None and aoi_id is None:
        from ..errors import invalid

        raise invalid("VALIDATION_ERROR", "Either geometry or aoi_id is required")
    if raw is None:
        area = catalog.area(aoi_id)
        if area is None:
            raise not_found("Area")
        raw = area.geometry
    year_start, year_end = geometry.validate_years(body["year_start"], body["year_end"])
    geom, area_ha = geometry.validate(raw)
    claimed = body.get("claimed_units")

    request_id = new_request_id()
    now = utc_now()
    with ctx.db.transaction() as conn:
        conn.execute(
            "INSERT INTO lens_requests (request_id, owner_id, status, aoi_id,"
            " geometry_json, geometry_hash, area_ha, year_start, year_end, claimed_units,"
            " claim_pool, claim_unit, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (request_id, who.user_id, DRAFT, aoi_id,
             json.dumps(geometry.canonical_geometry(geom), ensure_ascii=False,
                        sort_keys=True),
             geometry.geometry_hash(geom), area_ha, year_start, year_end,
             float(claimed) if claimed is not None else None, POOL, UNIT, now, now))
        _record(conn, request_id, from_status=None, to_status=DRAFT,
                user_id=who.user_id, note="Заявка создана как черновик.")
        auth.audit(ctx, who.user_id, who.role, "REQUEST_CREATED", request_id, conn=conn)
        return _public(conn, _row(conn, request_id), ctx)


def update_claim(ctx: Any, request_id: str, *, who: auth.Principal, body: dict) -> dict:
    """Change the stated volume while the request is still a draft.

    The contour and the period are not editable. A claim compared against a different
    scope is not a comparison, so changing those is a different request.
    """
    claimed = body.get("claimed_units")
    with ctx.db.transaction() as conn:
        row = _row(conn, request_id)
        if row is None or not _visible(row, who):
            raise not_found("Request")
        if row["owner_id"] != who.user_id:
            raise forbidden("Изменить черновик может только его владелец.")
        if row["status"] != DRAFT:
            raise conflict("INVALID_TRANSITION",
                           "Заявленный объём можно изменить только в черновике.",
                           from_status=row["status"])
        conn.execute(
            "UPDATE lens_requests SET claimed_units = ?, updated_at = ?"
            " WHERE request_id = ?",
            (float(claimed) if claimed is not None else None, utc_now(), request_id))
        auth.audit(ctx, who.user_id, who.role, "REQUEST_UPDATED", request_id, conn=conn,
                   claimed_units=claimed)
        return _public(conn, _row(conn, request_id), ctx)


def submit(ctx: Any, request_id: str, *, who: auth.Principal) -> dict:
    auth.require(who, "request.submit")
    with ctx.db.transaction() as conn:
        row = _row(conn, request_id)
        if row is None or not _visible(row, who):
            raise not_found("Request")
        if row["owner_id"] != who.user_id:
            raise forbidden("Подать заявку может только её владелец.")
        _require_transition(row["status"], SUBMITTED)
        _move(conn, row, SUBMITTED, who.user_id, "Заявка подана на проверку.")
        auth.audit(ctx, who.user_id, who.role, "REQUEST_SUBMITTED", request_id, conn=conn)
        return _public(conn, _row(conn, request_id), ctx)


def _move(conn: Any, row: Any, target: str, user_id: str | None, note: str,
          **columns: Any) -> None:
    assignments = ", ".join(f"{name} = ?" for name in columns)
    sql = "UPDATE lens_requests SET status = ?, updated_at = ?"
    values: list[Any] = [target, utc_now()]
    if assignments:
        sql += ", " + assignments
        values.extend(columns.values())
    sql += " WHERE request_id = ?"
    values.append(row["request_id"])
    conn.execute(sql, values)
    _record(conn, row["request_id"], from_status=row["status"], to_status=target,
            user_id=user_id, note=note)


def start_analysis(ctx: Any, request_id: str, *, who: auth.Principal,
                   queue: Any) -> tuple[dict, str]:
    """Move to ANALYSING and queue the calculation this request describes.

    `queue` is called with the analysis body and returns the accepted analysis id. It is
    passed in rather than imported so that this module stays about the workflow and the
    service stays the only place that knows how an analysis is submitted.
    """
    with ctx.db.reader() as conn:
        row = _row(conn, request_id)
        if row is None or not _visible(row, who):
            raise not_found("Request")
    auth.require(who, "analysis.run")
    _require_transition(row["status"], ANALYSING)

    analysis_id = queue({
        "geometry": loads_json(row["geometry_json"]),
        "aoi_id": row["aoi_id"],
        "year_start": row["year_start"],
        "year_end": row["year_end"],
        "claimed_units": row["claimed_units"],
        "claim_origin": "USER_INPUT" if row["claimed_units"] is not None else None,
        "include_optical": True,
    })
    with ctx.db.transaction() as conn:
        current = _row(conn, request_id)
        _require_transition(current["status"], ANALYSING)
        _move(conn, current, ANALYSING, who.user_id,
              "Расчёт поставлен в очередь.", analysis_id=analysis_id)
        auth.audit(ctx, who.user_id, who.role, "ANALYSIS_STARTED", request_id,
                   conn=conn, analysis_id=analysis_id)
        return _public(conn, _row(conn, request_id), ctx), analysis_id


def on_analysis_finished(ctx: Any, analysis_id: str, *, succeeded: bool) -> None:
    """Advance, or step back, when a worker finishes.

    Called by the worker rather than by a request. A run that failed returns the request
    to SUBMITTED so somebody can try again; nothing here can reach FINALIZED, because
    only a verifier puts it there.
    """
    with ctx.db.transaction() as conn:
        row = conn.execute("SELECT * FROM lens_requests WHERE analysis_id = ?",
                           (analysis_id,)).fetchone()
        if row is None or row["status"] != ANALYSING:
            return
        if succeeded:
            _move(conn, row, CALCULATED, None,
                  "Расчёт завершён. Результат готов к проверке.")
        else:
            _move(conn, row, SUBMITTED, None,
                  "Расчёт не удалось выполнить; заявка возвращена к подаче.")


def finalize(ctx: Any, request_id: str, *, who: auth.Principal,
             passport_of: Any) -> dict:
    """A verifier pins this passport version. No number changes.

    `passport_of` returns the stored passport of an analysis. Finalizing records its
    content hash, the person and the time; it does not touch the analysis, which is
    immutable once published.
    """
    auth.require(who, "passport.finalize")
    with ctx.db.reader() as conn:
        row = _row(conn, request_id)
    if row is None:
        raise not_found("Request")
    _require_transition(row["status"], FINALIZED)
    if not row["analysis_id"]:
        raise conflict("NO_CALCULATION", "У заявки нет завершённого расчёта.")

    passport = passport_of(row["analysis_id"])
    if passport is None:
        raise conflict("NO_CALCULATION", "Расчёт заявки ещё не опубликован.")

    now = utc_now()
    with ctx.db.transaction() as conn:
        current = _row(conn, request_id)
        _require_transition(current["status"], FINALIZED)
        _move(conn, current, FINALIZED, who.user_id,
              "Паспорт финализирован проверяющим. Значения расчёта не изменялись.",
              passport_hash=passport["content_hash"], finalized_by=who.user_id,
              finalized_at=now)
        auth.audit(ctx, who.user_id, who.role, "PASSPORT_FINALIZED", request_id,
                   conn=conn, analysis_id=current["analysis_id"],
                   content_hash=passport["content_hash"])
        return _public(conn, _row(conn, request_id), ctx)


def owner_of(ctx: Any, analysis_id: str) -> str | None:
    """Who is responsible for the request this analysis was run for.

    An analysis records the person who *started* it, and starting one belongs to the
    verifier, so that column never names the owner. Asking it who owns the work answers
    "the verifier" for every request and closes an owner out of their own calculation
    until somebody finalizes it. The request row is where responsibility lives.

    An analysis nobody requested — the direct `/analyses` path — has no owner here, and
    the caller falls back to the actor rather than inventing one.
    """
    with ctx.db.reader() as conn:
        row = conn.execute(
            "SELECT owner_id FROM lens_requests WHERE analysis_id = ?",
            (analysis_id,)).fetchone()
    return row["owner_id"] if row else None


# -- the passport status an analysis is served with ------------------------------------
def finalization_of(ctx: Any, analysis_id: str) -> dict | None:
    """The finalization pinned to this analysis, if a verifier made one.

    The stored result is immutable and always says DRAFT, because that is what it was
    when it was computed. A finalization is a separate record, and the passport status
    an API response carries is derived from it at read time.
    """
    with ctx.db.reader() as conn:
        row = conn.execute(
            "SELECT passport_hash, finalized_by, finalized_at FROM lens_requests"
            " WHERE analysis_id = ? AND status = ?", (analysis_id, FINALIZED)).fetchone()
    return dict(row) if row else None


def apply_passport_status(ctx: Any, analysis_id: str, result: dict) -> dict:
    """Overlay the finalized status onto a stored result, without rewriting it.

    The overlay is outside the content hash by construction: the passport block is not
    part of `content_view`, so finalizing changes no hash and a finalized result still
    verifies against the same bytes it was published with.
    """
    if not result:
        return result
    record = finalization_of(ctx, analysis_id)
    if record is None or record["passport_hash"] != result["passport"]["content_hash"]:
        return result
    passport = dict(result["passport"])
    passport["status"] = FINALIZED
    passport["finalized_at"] = record["finalized_at"]
    return {**result, "passport": passport}
