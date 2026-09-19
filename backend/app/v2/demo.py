"""A demonstration of issuing, transferring and retiring. It is not a registry.

Nothing in this module creates anything that exists. It shows what the lifecycle of a
unit would look like once there is a registry to put one in, and every response says so
in words a reader cannot miss.

    FINALIZED -> ISSUED_DEMO -> TRANSFERRED_DEMO -> RETIRED_DEMO

Four rules, each of which is the reason a step exists at all:

- **A verifier has to have finalized the passport first.** Issuing against a draft would
  be issuing against a number nobody accepted.
- **q = 0 and q = null forbid issuing.** Every real plot in the supplied data comes out
  at zero, so this is not a corner case; it is the normal case, and a demonstration that
  quietly issued zero units would be the one misleading thing in the whole tool.
- **Each role does its own step.** An owner issues, an investor accepts the transfer and
  retires. Nobody performs the whole lifecycle alone.
- **Every step is idempotent.** Repeating a transition returns the state that already
  exists rather than recording a second one.
"""
from __future__ import annotations

import logging
from typing import Any

from ..db import utc_now
from ..errors import conflict, forbidden, not_found
from . import auth, verification

log = logging.getLogger("backend.lens.demo")

ISSUED = "ISSUED_DEMO"
TRANSFERRED = "TRANSFERRED_DEMO"
RETIRED = "RETIRED_DEMO"
STATUSES = (ISSUED, TRANSFERRED, RETIRED)

TRANSITIONS: dict[str, tuple[str, ...]] = {
    ISSUED: (TRANSFERRED,),
    TRANSFERRED: (RETIRED,),
    RETIRED: (),
}

DEMONSTRATION_NOTE = (
    "Демонстрация жизненного цикла единицы. Это не официальный реестр: ничего не "
    "выпущено, не передано и не погашено в действительности, и эта запись не является "
    "подтверждением прав на углеродные единицы."
)


def _unit(conn: Any, request_id: str) -> Any:
    return conn.execute("SELECT * FROM lens_demo_units WHERE request_id = ?",
                        (request_id,)).fetchone()


def _events(conn: Any, request_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT occurred_at, from_status, to_status, user_id, note"
        " FROM lens_demo_events WHERE request_id = ? ORDER BY seq", (request_id,))
    return [dict(row) for row in rows]


def _record(conn: Any, request_id: str, *, from_status: str | None, to_status: str,
            user_id: str | None, note: str) -> None:
    conn.execute(
        "INSERT INTO lens_demo_events (request_id, occurred_at, from_status, to_status,"
        " user_id, note) VALUES (?, ?, ?, ?, ?, ?)",
        (request_id, utc_now(), from_status, to_status, user_id, note))


def _public(conn: Any, request_id: str, row: Any) -> dict:
    return {
        "request_id": request_id,
        "status": row["status"],
        "units": row["units"],
        "passport_hash": row["passport_hash"],
        "issued_by": row["issued_by"],
        "issued_at": row["issued_at"],
        "held_by": row["held_by"],
        "transferred_at": row["transferred_at"],
        "retired_by": row["retired_by"],
        "retired_at": row["retired_at"],
        "is_demonstration": True,
        "note": DEMONSTRATION_NOTE,
        "events": _events(conn, request_id),
    }


def _request(ctx: Any, request_id: str, who: auth.Principal) -> Any:
    with ctx.db.reader() as conn:
        row = conn.execute("SELECT * FROM lens_requests WHERE request_id = ?",
                           (request_id,)).fetchone()
    if row is None or not verification._visible(row, who):
        raise not_found("Request")
    return row


def view(ctx: Any, request_id: str, *, who: auth.Principal) -> dict:
    _request(ctx, request_id, who)
    with ctx.db.reader() as conn:
        row = _unit(conn, request_id)
        if row is None:
            raise not_found("Demonstration unit")
        return _public(conn, request_id, row)


def issue(ctx: Any, request_id: str, *, who: auth.Principal,
          units_of: Any) -> dict:
    """An owner issues, once a verifier has finalized and only for a positive q."""
    request = _request(ctx, request_id, who)
    if request["owner_id"] != who.user_id:
        raise forbidden("Выпустить демонстрационные единицы может владелец заявки.")
    if request["status"] != verification.FINALIZED:
        raise conflict("NOT_FINALIZED",
                       "Демонстрационный выпуск возможен только после финализации "
                       "паспорта проверяющим.", status=request["status"])

    with ctx.db.reader() as conn:
        existing = _unit(conn, request_id)
        if existing is not None:
            # Idempotent: a repeated issue returns what already exists.
            return _public(conn, request_id, existing)

    units = units_of(request["analysis_id"])
    if units is None or units <= 0:
        # Every real plot in the supplied data comes out at zero. A demonstration that
        # quietly issued zero units would be the one misleading thing in the tool.
        raise conflict(
            "NO_POSITIVE_UNITS",
            "Расчёт не даёт положительного числа единиц, поэтому демонстрационный "
            "выпуск невозможен. Это не ошибка системы, а результат расчёта.",
            q=units)

    now = utc_now()
    with ctx.db.transaction() as conn:
        if _unit(conn, request_id) is not None:
            return _public(conn, request_id, _unit(conn, request_id))
        conn.execute(
            "INSERT INTO lens_demo_units (request_id, status, units, passport_hash,"
            " issued_by, issued_at) VALUES (?, ?, ?, ?, ?, ?)",
            (request_id, ISSUED, int(units), request["passport_hash"], who.user_id, now))
        _record(conn, request_id, from_status=None, to_status=ISSUED,
                user_id=who.user_id,
                note="Демонстрационный выпуск по финализированному паспорту.")
        auth.audit(ctx, who.user_id, who.role, "DEMO_LIFECYCLE", request_id, conn=conn,
                   transition=ISSUED, units=int(units))
        return _public(conn, request_id, _unit(conn, request_id))


def accept_transfer(ctx: Any, request_id: str, *, who: auth.Principal) -> dict:
    """An investor accepts the transfer. Nobody performs the whole lifecycle alone."""
    _request(ctx, request_id, who)
    if who.role != "INVESTOR":
        raise forbidden("Принять передачу может инвестор.")
    with ctx.db.transaction() as conn:
        row = _unit(conn, request_id)
        if row is None:
            raise not_found("Demonstration unit")
        if row["status"] == TRANSFERRED and row["held_by"] == who.user_id:
            return _public(conn, request_id, row)
        if TRANSFERRED not in TRANSITIONS[row["status"]]:
            raise conflict("INVALID_TRANSITION",
                           f"Из состояния {row['status']} передача невозможна.",
                           from_status=row["status"])
        conn.execute(
            "UPDATE lens_demo_units SET status = ?, held_by = ?, transferred_at = ?"
            " WHERE request_id = ?", (TRANSFERRED, who.user_id, utc_now(), request_id))
        _record(conn, request_id, from_status=row["status"], to_status=TRANSFERRED,
                user_id=who.user_id, note="Демонстрационная передача принята инвестором.")
        auth.audit(ctx, who.user_id, who.role, "DEMO_LIFECYCLE", request_id, conn=conn,
                   transition=TRANSFERRED)
        return _public(conn, request_id, _unit(conn, request_id))


def retire(ctx: Any, request_id: str, *, who: auth.Principal) -> dict:
    """The holder retires. After this there is nothing further to demonstrate."""
    _request(ctx, request_id, who)
    with ctx.db.transaction() as conn:
        row = _unit(conn, request_id)
        if row is None:
            raise not_found("Demonstration unit")
        if row["status"] == RETIRED and row["retired_by"] == who.user_id:
            return _public(conn, request_id, row)
        if RETIRED not in TRANSITIONS[row["status"]]:
            raise conflict("INVALID_TRANSITION",
                           f"Из состояния {row['status']} погашение невозможно.",
                           from_status=row["status"])
        if row["held_by"] != who.user_id:
            raise forbidden("Погасить демонстрационные единицы может их держатель.")
        conn.execute(
            "UPDATE lens_demo_units SET status = ?, retired_by = ?, retired_at = ?"
            " WHERE request_id = ?", (RETIRED, who.user_id, utc_now(), request_id))
        _record(conn, request_id, from_status=row["status"], to_status=RETIRED,
                user_id=who.user_id, note="Демонстрационное погашение держателем.")
        auth.audit(ctx, who.user_id, who.role, "DEMO_LIFECYCLE", request_id, conn=conn,
                   transition=RETIRED)
        return _public(conn, request_id, _unit(conn, request_id))
