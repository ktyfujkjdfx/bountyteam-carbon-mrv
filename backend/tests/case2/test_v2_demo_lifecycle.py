"""The demonstration lifecycle: what it refuses, and that it never pretends to be real.

The most important test in this file is the one where nothing happens. Every real plot in
the supplied data comes out at q = 0, so a lifecycle that issued anyway would be the one
genuinely misleading thing in the tool.
"""
from __future__ import annotations

import pytest

from backend.app.v2 import demo

POSITIVE = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024}
ZERO_UNITS = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2022}
NO_UNITS = {"aoi_id": "RU_MORDOVIA_04", "year_start": 2019, "year_end": 2024}


def _as(harness, role):
    return {"Authorization": "Bearer " + harness.api.tokens[role]}


def _post(harness, path, role):
    return harness.client.post("/api/v2" + path, headers=_as(harness, role))


def _finalized(harness, body=POSITIVE, key="demo-key-00000001"):
    """A request taken all the way to a verifier-finalized passport."""
    request_id = harness.client.post("/api/v2/requests", json=body,
                                     headers=_as(harness, "PROJECT_OWNER")
                                     ).json()["request_id"]
    _post(harness, f"/requests/{request_id}/submit", "PROJECT_OWNER")
    started = harness.client.post(
        f"/api/v2/requests/{request_id}/analysis",
        headers={**_as(harness, "VERIFIER"), "Idempotency-Key": key})
    assert started.status_code == 202, started.text
    harness.run()
    assert _post(harness, f"/requests/{request_id}/finalize",
                 "VERIFIER").status_code == 200
    return request_id


# -- what it refuses ----------------------------------------------------------------------
def test_a_zero_result_cannot_be_issued(harness):
    """Not a corner case. This is what every real plot in the supplied data does."""
    request_id = _finalized(harness, ZERO_UNITS, key="demozero-key-0001")
    response = _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER")
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "NO_POSITIVE_UNITS"
    assert body["error"]["details"]["q"] == 0
    assert "не ошибка системы" in body["error"]["message"]


def test_a_result_with_no_number_cannot_be_issued_either(harness):
    request_id = _finalized(harness, NO_UNITS, key="demonull-key-0001")
    response = _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER")
    assert response.status_code == 409
    assert response.json()["error"]["details"]["q"] is None


def test_a_draft_passport_cannot_be_issued_against(harness):
    """Issuing against a number nobody accepted is issuing against nothing."""
    request_id = harness.client.post("/api/v2/requests", json=POSITIVE,
                                     headers=_as(harness, "PROJECT_OWNER")
                                     ).json()["request_id"]
    _post(harness, f"/requests/{request_id}/submit", "PROJECT_OWNER")
    harness.client.post(f"/api/v2/requests/{request_id}/analysis",
                        headers={**_as(harness, "VERIFIER"),
                                 "Idempotency-Key": "demodraft-key-001"})
    harness.run()
    response = _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_FINALIZED"


# -- the lifecycle itself -----------------------------------------------------------------
def test_each_role_performs_its_own_step(harness):
    """Nobody walks the whole lifecycle alone."""
    request_id = _finalized(harness, key="demoroles-key-001")

    assert _post(harness, f"/requests/{request_id}/demo/issue",
                 "VERIFIER").status_code == 403
    assert _post(harness, f"/requests/{request_id}/demo/issue",
                 "INVESTOR").status_code in (403, 404)
    issued = _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER")
    assert issued.status_code == 201 and issued.json()["status"] == "ISSUED_DEMO"

    assert _post(harness, f"/requests/{request_id}/demo/transfer",
                 "PROJECT_OWNER").status_code == 403
    transferred = _post(harness, f"/requests/{request_id}/demo/transfer", "INVESTOR")
    assert transferred.status_code == 200
    assert transferred.json()["status"] == "TRANSFERRED_DEMO"
    assert transferred.json()["held_by"] == harness.users["INVESTOR"]["user_id"]

    assert _post(harness, f"/requests/{request_id}/demo/retire",
                 "PROJECT_OWNER").status_code == 403
    retired = _post(harness, f"/requests/{request_id}/demo/retire", "INVESTOR")
    assert retired.status_code == 200 and retired.json()["status"] == "RETIRED_DEMO"


def test_the_quantity_comes_from_the_passport_and_not_from_the_caller(harness):
    request_id = _finalized(harness, key="demoqty-key-00001")
    unit = _post(harness, f"/requests/{request_id}/demo/issue",
                 "PROJECT_OWNER").json()
    request = harness.client.get(f"/api/v2/requests/{request_id}",
                                 headers=_as(harness, "VERIFIER")).json()
    analysis = harness.client.get(request["analysis_url"],
                                  headers=_as(harness, "VERIFIER")).json()
    assert unit["units"] == analysis["result"]["units"]["q"]
    assert unit["passport_hash"] == request["passport_hash"]


def test_every_step_is_idempotent(harness):
    request_id = _finalized(harness, key="demoidem-key-0001")
    first = _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER").json()
    again = _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER").json()
    assert again["issued_at"] == first["issued_at"]
    assert len(again["events"]) == len(first["events"]) == 1

    _post(harness, f"/requests/{request_id}/demo/transfer", "INVESTOR")
    repeated = _post(harness, f"/requests/{request_id}/demo/transfer", "INVESTOR").json()
    assert len([e for e in repeated["events"] if e["to_status"] == "TRANSFERRED_DEMO"]) == 1

    _post(harness, f"/requests/{request_id}/demo/retire", "INVESTOR")
    final = _post(harness, f"/requests/{request_id}/demo/retire", "INVESTOR").json()
    assert final["status"] == "RETIRED_DEMO"
    assert len([e for e in final["events"] if e["to_status"] == "RETIRED_DEMO"]) == 1


def test_a_step_cannot_be_skipped(harness):
    request_id = _finalized(harness, key="demoskip-key-0001")
    _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER")
    # Retiring something nobody has accepted yet.
    refused = _post(harness, f"/requests/{request_id}/demo/retire", "INVESTOR")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "INVALID_TRANSITION"


def test_nothing_follows_a_retirement(harness):
    request_id = _finalized(harness, key="demoend-key-00001")
    _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER")
    _post(harness, f"/requests/{request_id}/demo/transfer", "INVESTOR")
    _post(harness, f"/requests/{request_id}/demo/retire", "INVESTOR")
    assert demo.TRANSITIONS[demo.RETIRED] == ()


# -- it never pretends to be real ----------------------------------------------------------
def test_every_answer_says_it_is_a_demonstration(harness):
    request_id = _finalized(harness, key="demosays-key-0001")
    unit = _post(harness, f"/requests/{request_id}/demo/issue",
                 "PROJECT_OWNER").json()
    assert unit["is_demonstration"] is True
    assert "не официальный реестр" in unit["note"]
    assert "не является подтверждением прав" in unit["note"]
    assert all(status.endswith("_DEMO") for status in demo.STATUSES)


def test_the_demonstration_is_in_its_own_tables_and_touches_no_p0_credit(harness):
    request_id = _finalized(harness, key="demotable-key-001")
    _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER")
    with harness.ctx.db.reader() as conn:
        names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        assert {"lens_demo_units", "lens_demo_events"} <= names
        # The P0 tables are untouched by any of this: a demonstration unit is not a
        # credit, and nothing here writes into the frozen schema.
        for table in ("verification_jobs", "verifications", "operations", "batches"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_the_demonstration_changes_no_number_in_the_passport(harness):
    request_id = _finalized(harness, key="demohash-key-0001")
    request = harness.client.get(f"/api/v2/requests/{request_id}",
                                 headers=_as(harness, "VERIFIER")).json()
    before = harness.client.get(request["analysis_url"],
                                headers=_as(harness, "VERIFIER")).json()["result"]

    _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER")
    _post(harness, f"/requests/{request_id}/demo/transfer", "INVESTOR")
    _post(harness, f"/requests/{request_id}/demo/retire", "INVESTOR")

    after = harness.client.get(request["analysis_url"],
                               headers=_as(harness, "VERIFIER")).json()["result"]
    assert after == before


def test_the_lifecycle_is_recorded_for_every_step(harness):
    from backend.app.v2 import auth

    request_id = _finalized(harness, key="demoaudit-key-001")
    _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER")
    _post(harness, f"/requests/{request_id}/demo/transfer", "INVESTOR")
    _post(harness, f"/requests/{request_id}/demo/retire", "INVESTOR")

    rows = [row for row in auth.audit_trail(harness.ctx, subject=request_id)
            if row["action"] == "DEMO_LIFECYCLE"]
    assert len(rows) == 3
    assert {row["role"] for row in rows} == {"PROJECT_OWNER", "INVESTOR"}


def test_the_history_cannot_be_rewritten(harness):
    import sqlite3

    request_id = _finalized(harness, key="demorewrite-key-1")
    _post(harness, f"/requests/{request_id}/demo/issue", "PROJECT_OWNER")
    with pytest.raises(sqlite3.IntegrityError):
        with harness.ctx.db.transaction() as conn:
            conn.execute("UPDATE lens_demo_events SET to_status = 'RETIRED_DEMO'"
                         " WHERE request_id = ?", (request_id,))
