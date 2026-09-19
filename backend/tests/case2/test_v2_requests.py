"""The verification request: who moves it, what may not move on its own, and finalizing.

The distinction these tests defend is that a calculation and a responsibility are
different things. A worker produces numbers; a verifier accepts them. Nothing in between
may close the gap by itself, and accepting them may not change any of them.
"""
from __future__ import annotations

import pytest

from backend.app.v2 import verification

BODY = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024, "claimed_units": 500}
NO_DATA = {"aoi_id": "RU_MORDOVIA_04", "year_start": 2019, "year_end": 2024}


def _as(harness, role):
    return {"Authorization": "Bearer " + harness.api.tokens[role]}


def _create(harness, body=None, role="PROJECT_OWNER"):
    response = harness.client.post("/api/v2/requests", json=body or BODY,
                                   headers=_as(harness, role))
    assert response.status_code == 201, response.text
    return response.json()


def _post(harness, path, role, key=None, **kwargs):
    headers = _as(harness, role)
    if key:
        headers["Idempotency-Key"] = key
    return harness.client.post("/api/v2" + path, headers=headers, **kwargs)


def _through_to_calculated(harness, body=None, key="req-key-00000001"):
    request = _create(harness, body)
    request_id = request["request_id"]
    assert _post(harness, f"/requests/{request_id}/submit", "PROJECT_OWNER").status_code == 200
    started = _post(harness, f"/requests/{request_id}/analysis", "VERIFIER", key=key)
    assert started.status_code == 202, started.text
    harness.run()
    return harness.client.get(f"/api/v2/requests/{request_id}",
                              headers=_as(harness, "VERIFIER")).json()


# -- the shape of a request ---------------------------------------------------------------
def test_a_new_request_is_a_draft_with_nothing_calculated(harness):
    request = _create(harness)
    assert request["status"] == "DRAFT"
    assert request["analysis_id"] is None and request["analysis_url"] is None
    assert request["passport_hash"] is None
    assert request["finalized_by"] is None and request["finalized_at"] is None
    assert request["claim_pool"] and request["claim_unit"]
    assert request["area_ha"] > 0 and request["geometry_hash"].startswith("0x")
    assert [event["to_status"] for event in request["events"]] == ["DRAFT"]


def test_the_request_measures_its_contour_the_same_way_the_analysis_does(harness):
    request = _create(harness)
    measured = harness.client.post(
        "/api/v2/areas/measure", json={"geometry": request["geometry"]},
        headers=_as(harness, "PROJECT_OWNER")).json()
    assert measured["area_ha"] == pytest.approx(request["area_ha"])
    assert measured["geometry_hash"] == request["geometry_hash"]


def test_an_investor_may_not_open_a_request(harness):
    assert harness.client.post("/api/v2/requests", json=BODY,
                               headers=_as(harness, "INVESTOR")).status_code == 403


def test_only_an_owner_may_create_and_submit_a_request(harness):
    assert harness.client.post("/api/v2/requests", json=BODY,
                               headers=_as(harness, "VERIFIER")).status_code == 403
    request = _create(harness)
    assert _post(harness, f"/requests/{request['request_id']}/submit",
                 "VERIFIER").status_code == 403
    assert _post(harness, f"/requests/{request['request_id']}/submit",
                 "PROJECT_OWNER").status_code == 200


def test_only_a_verifier_may_start_request_analysis(harness):
    request = _create(harness)
    request_id = request["request_id"]
    assert _post(harness, f"/requests/{request_id}/submit",
                 "PROJECT_OWNER").status_code == 200
    assert _post(harness, f"/requests/{request_id}/analysis", "PROJECT_OWNER",
                 key="owner-cannot-run").status_code == 403
    assert _post(harness, f"/requests/{request_id}/analysis", "INVESTOR",
                 key="investor-cannot-run").status_code in (403, 404)
    assert _post(harness, f"/requests/{request_id}/analysis", "VERIFIER",
                 key="verifier-can-run").status_code == 202


# -- the draft claim ----------------------------------------------------------------------
def test_an_owner_may_change_the_stated_volume_while_it_is_a_draft(harness):
    request = _create(harness)
    response = harness.client.patch(f"/api/v2/requests/{request['request_id']}",
                                    json={"claimed_units": 42},
                                    headers=_as(harness, "PROJECT_OWNER"))
    assert response.status_code == 200
    assert response.json()["claimed_units"] == 42


def test_a_verifier_may_not_edit_somebody_elses_claim(harness):
    """A stated volume is the owner's statement. A reviewer who could edit it is not a
    reviewer of anything."""
    request = _create(harness)
    response = harness.client.patch(f"/api/v2/requests/{request['request_id']}",
                                    json={"claimed_units": 1},
                                    headers=_as(harness, "VERIFIER"))
    assert response.status_code == 403


def test_the_claim_is_frozen_once_the_request_is_submitted(harness):
    request = _create(harness)
    _post(harness, f"/requests/{request['request_id']}/submit", "PROJECT_OWNER")
    response = harness.client.patch(f"/api/v2/requests/{request['request_id']}",
                                    json={"claimed_units": 1},
                                    headers=_as(harness, "PROJECT_OWNER"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"


def test_the_contour_and_the_period_are_not_editable_at_all(harness):
    """Comparing a claim against a different scope is not a comparison."""
    request = _create(harness)
    response = harness.client.patch(
        f"/api/v2/requests/{request['request_id']}",
        json={"claimed_units": 1, "year_end": 2022}, headers=_as(harness, "PROJECT_OWNER"))
    assert response.status_code == 422


# -- the states ---------------------------------------------------------------------------
def test_the_request_walks_the_states_in_order(harness):
    request = _create(harness)
    request_id = request["request_id"]
    assert _post(harness, f"/requests/{request_id}/submit",
                 "PROJECT_OWNER").json()["status"] == "SUBMITTED"
    started = _post(harness, f"/requests/{request_id}/analysis", "VERIFIER",
                    key="walk-key-00000001")
    assert started.json()["status"] == "ANALYSING"
    assert started.json()["analysis_id"]
    harness.run()
    after = harness.client.get(f"/api/v2/requests/{request_id}",
                               headers=_as(harness, "VERIFIER")).json()
    assert after["status"] == "CALCULATED"
    assert [event["to_status"] for event in after["events"]] == [
        "DRAFT", "SUBMITTED", "ANALYSING", "CALCULATED"]


def test_a_state_cannot_be_skipped(harness):
    request = _create(harness)
    request_id = request["request_id"]
    # Analysing a draft that was never submitted.
    assert _post(harness, f"/requests/{request_id}/analysis", "VERIFIER",
                 key="skip-key-00000001").status_code == 409
    # Finalizing something that was never calculated.
    assert _post(harness, f"/requests/{request_id}/finalize", "VERIFIER").status_code == 409


def test_a_failed_run_returns_the_request_to_submitted_and_never_advances(harness):
    """Errors and missing data must not turn into a finalized passport."""
    request = _create(harness)
    request_id = request["request_id"]
    _post(harness, f"/requests/{request_id}/submit", "PROJECT_OWNER")
    _post(harness, f"/requests/{request_id}/analysis", "VERIFIER", key="fail-key-00000001")

    class Broken:
        name = "broken"

        def analyse(self, request):
            raise RuntimeError("the raster core exploded")

    harness.lens.ports.__dict__["raster"] = Broken()
    harness.run()

    after = harness.client.get(f"/api/v2/requests/{request_id}",
                               headers=_as(harness, "VERIFIER")).json()
    assert after["status"] == "SUBMITTED"
    assert after["passport_hash"] is None
    assert after["events"][-1]["to_status"] == "SUBMITTED"


def test_a_result_with_no_number_still_reaches_calculated(harness):
    """The calculation finished and honestly says it could not tell. That is a result."""
    request = _through_to_calculated(harness, NO_DATA, key="nodata-key-000001")
    assert request["status"] == "CALCULATED"
    analysis = harness.client.get(request["analysis_url"],
                                  headers=_as(harness, "VERIFIER")).json()
    assert analysis["result"]["units"]["q"] is None


# -- finalizing ---------------------------------------------------------------------------
def test_only_a_verifier_finalizes(harness):
    request = _through_to_calculated(harness, key="final-key-00000001")
    request_id = request["request_id"]
    assert _post(harness, f"/requests/{request_id}/finalize",
                 "PROJECT_OWNER").status_code == 403
    assert _post(harness, f"/requests/{request_id}/finalize",
                 "INVESTOR").status_code == 403
    assert _post(harness, f"/requests/{request_id}/finalize",
                 "VERIFIER").status_code == 200


def test_finalizing_pins_a_passport_and_changes_no_number(harness):
    request = _through_to_calculated(harness, key="pin-key-000000001")
    before = harness.client.get(request["analysis_url"],
                                headers=_as(harness, "VERIFIER")).json()["result"]

    finalized = _post(harness, f"/requests/{request['request_id']}/finalize",
                      "VERIFIER").json()
    assert finalized["status"] == "FINALIZED"
    assert finalized["passport_hash"] == before["passport"]["content_hash"]
    assert finalized["finalized_by"] == harness.users["VERIFIER"]["user_id"]
    assert finalized["finalized_at"]

    after = harness.client.get(request["analysis_url"],
                               headers=_as(harness, "VERIFIER")).json()["result"]
    for block in ("units", "change", "uncertainty", "baseline", "claim", "scenario_values"):
        assert after[block] == before[block], block
    assert after["passport"]["content_hash"] == before["passport"]["content_hash"]


def test_finalizing_moves_the_passport_status_and_only_that(harness):
    request = _through_to_calculated(harness, key="status-key-0000001")
    analysis_url = request["analysis_url"]
    before = harness.client.get(analysis_url, headers=_as(harness, "VERIFIER")).json()
    assert before["result"]["passport"]["status"] == "DRAFT"
    assert before["result"]["passport"]["finalized_at"] is None

    _post(harness, f"/requests/{request['request_id']}/finalize", "VERIFIER")
    after = harness.client.get(analysis_url, headers=_as(harness, "VERIFIER")).json()
    assert after["result"]["passport"]["status"] == "FINALIZED"
    assert after["result"]["passport"]["finalized_at"]
    # The anchor is a different axis and did not move with it.
    proof = harness.client.get(f"{analysis_url}/proof",
                               headers=_as(harness, "VERIFIER")).json()
    assert proof["passport"]["status"] == "FINALIZED"
    assert proof["anchor"]["status"] == "NOT_REQUESTED"


def test_a_finalized_request_cannot_be_finalized_again(harness):
    request = _through_to_calculated(harness, key="twice-key-00000001")
    assert _post(harness, f"/requests/{request['request_id']}/finalize",
                 "VERIFIER").status_code == 200
    again = _post(harness, f"/requests/{request['request_id']}/finalize", "VERIFIER")
    assert again.status_code == 409


def test_finalizing_is_recorded_against_the_person_who_did_it(harness):
    from backend.app.v2 import auth

    request = _through_to_calculated(harness, key="audit-key-00000001")
    _post(harness, f"/requests/{request['request_id']}/finalize", "VERIFIER")
    rows = auth.audit_trail(harness.ctx, subject=request["request_id"])
    finalized = [row for row in rows if row["action"] == "PASSPORT_FINALIZED"]
    assert finalized and finalized[0]["role"] == "VERIFIER"
    assert finalized[0]["user_id"] == harness.users["VERIFIER"]["user_id"]


# -- who sees what ------------------------------------------------------------------------
def test_an_investor_sees_a_request_only_once_it_is_finalized(harness):
    request = _through_to_calculated(harness, key="see-key-000000001")
    request_id = request["request_id"]
    assert harness.client.get(f"/api/v2/requests/{request_id}",
                              headers=_as(harness, "INVESTOR")).status_code == 404
    assert harness.client.get("/api/v2/requests",
                              headers=_as(harness, "INVESTOR")).json()["requests"] == []

    _post(harness, f"/requests/{request_id}/finalize", "VERIFIER")
    assert harness.client.get(f"/api/v2/requests/{request_id}",
                              headers=_as(harness, "INVESTOR")).status_code == 200
    listed = harness.client.get("/api/v2/requests",
                                headers=_as(harness, "INVESTOR")).json()["requests"]
    assert [item["request_id"] for item in listed] == [request_id]


def test_an_investor_may_read_the_analysis_behind_a_finalized_request(harness):
    request = _through_to_calculated(harness, key="invread-key-00001")
    _post(harness, f"/requests/{request['request_id']}/finalize", "VERIFIER")
    response = harness.client.get(request["analysis_url"], headers=_as(harness, "INVESTOR"))
    assert response.status_code == 200
    assert response.json()["result"]["passport"]["status"] == "FINALIZED"


def test_an_owner_sees_only_their_own_requests(harness):
    from backend.app.v2 import auth

    mine = _create(harness)
    other = auth.create_user(harness.ctx, username="owner2", password="test-password-1234",
                             role="PROJECT_OWNER")
    token = harness.client.post("/api/v2/auth/login",
                                json={"username": "owner2",
                                      "password": "test-password-1234"}).json()["token"]
    theirs = harness.client.post("/api/v2/requests", json=BODY,
                                 headers={"Authorization": "Bearer " + token}).json()

    listed = harness.client.get("/api/v2/requests",
                                headers=_as(harness, "PROJECT_OWNER")).json()["requests"]
    assert [item["request_id"] for item in listed] == [mine["request_id"]]
    assert harness.client.get(f"/api/v2/requests/{theirs['request_id']}",
                              headers=_as(harness, "PROJECT_OWNER")).status_code == 404
    assert other.role == "PROJECT_OWNER"


def test_a_verifier_sees_every_request(harness):
    first = _create(harness)
    second = _create(harness, {**BODY, "year_end": 2022})
    listed = harness.client.get("/api/v2/requests",
                                headers=_as(harness, "VERIFIER")).json()["requests"]
    assert {item["request_id"] for item in listed} == {first["request_id"],
                                                       second["request_id"]}


# -- the state machine itself -------------------------------------------------------------
def test_the_transition_table_names_only_real_states():
    assert set(verification.TRANSITIONS) == set(verification.STATUSES)
    for source, targets in verification.TRANSITIONS.items():
        assert set(targets) <= set(verification.STATUSES), source
    # Nothing leads out of FINALIZED: a pinned passport is never reopened.
    assert verification.TRANSITIONS[verification.FINALIZED] == ()


def test_no_state_but_a_verifier_reaches_finalized():
    reachable = {target for targets in verification.TRANSITIONS.values()
                 for target in targets}
    assert verification.FINALIZED in reachable
    assert verification.TRANSITIONS[verification.CALCULATED] == ("FINALIZED", "ANALYSING")
    # And a run finishing cannot: the only automatic moves are to CALCULATED or back.
    assert verification.FINALIZED not in verification.TRANSITIONS[verification.ANALYSING]


def test_the_history_cannot_be_rewritten(harness):
    import sqlite3

    request = _create(harness)
    with pytest.raises(sqlite3.IntegrityError):
        with harness.ctx.db.transaction() as conn:
            conn.execute("UPDATE lens_request_events SET to_status = 'FINALIZED'"
                         " WHERE request_id = ?", (request["request_id"],))
