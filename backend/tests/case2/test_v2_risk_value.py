"""Risks, the projection and money: three things that must stay outside the number.

Each of these is a place where a tool like this usually starts lying. A risk becomes a
score, a projection becomes a forecast, and a price becomes a valuation. The tests here
exist to keep all three next to q rather than inside it.
"""
from __future__ import annotations

import pytest

POSITIVE = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024}
FIRE_AREA = {"aoi_id": "RU_MORDOVIA_03", "year_start": 2020, "year_end": 2022}
NO_DATA = {"aoi_id": "RU_MORDOVIA_04", "year_start": 2019, "year_end": 2024}


def _as(harness, role):
    return {"Authorization": "Bearer " + harness.api.tokens[role]}


def _result(harness, body, key):
    job = harness.analyse(body, key=key)
    assert job["job_state"] == "SUCCEEDED", job
    return job


# -- risks --------------------------------------------------------------------------------
def test_every_result_reports_the_three_risks_separately(harness):
    risks = _result(harness, POSITIVE, "risk-key-00000001")["result"]["risks"]
    assert [item["code"] for item in risks] == ["FIRE", "FOREST_LOSS", "DATA_QUALITY"]
    for item in risks:
        assert set(item) == {"code", "observed", "basis", "source_ref", "note"}
        assert isinstance(item["basis"], dict)


def test_a_risk_carries_a_measured_basis_and_never_a_score(harness):
    """A number that sums a fire indication and a coverage fraction means nothing."""
    import json

    result = _result(harness, POSITIVE, "score-key-00000001")["result"]
    for item in result["risks"]:
        keys = json.dumps(item["basis"], ensure_ascii=False).lower()
        for forbidden in ("score", "probability", "rating", "index"):
            assert forbidden not in keys, (item["code"], forbidden)
    # The prose may deny a probability; the data may not offer one.
    assert any("не является вероятностью" in item["note"] for item in result["risks"])


def test_a_risk_never_changes_q(harness):
    """The whole point of keeping risk beside the calculation rather than inside it."""
    result = _result(harness, POSITIVE, "riskq-key-0000001")["result"]
    assert result["units"]["q"] is not None
    for item in result["risks"]:
        assert "Q" in item["note"] or "не входит" in item["note"]
    # Nothing in the ledger refers to a risk at all.
    assert "risk" not in str(result["units"]).lower()


def test_the_fire_risk_quotes_the_supplied_event_when_there_is_one(harness):
    result = _result(harness, FIRE_AREA, "fire-key-00000001")["result"]
    fire = next(item for item in result["risks"] if item["code"] == "FIRE")
    if not fire["observed"]:
        pytest.skip("this vector has no analysed parent, so no event is attached")
    assert fire["source_ref"] == "MODIS_MCD64A1_061"
    assert fire["basis"]["date_min_product"] and fire["basis"]["date_max_product"]
    assert fire["basis"]["date_uncertainty_days_max"] >= \
        fire["basis"]["date_uncertainty_days_min"]
    assert 0.0 <= fire["basis"]["burned_share"] <= 1.0


def test_nothing_found_is_not_reported_as_an_established_absence(harness):
    result = _result(harness, POSITIVE, "absent-key-0000001")["result"]
    fire = next(item for item in result["risks"] if item["code"] == "FIRE")
    if fire["observed"]:
        pytest.skip("this vector does carry a fire event")
    assert fire["basis"] == {} and fire["source_ref"] is None
    assert "отсутств" in fire["note"] or "не" in fire["note"]


def test_data_quality_is_always_reported_because_it_is_always_knowable(harness):
    result = _result(harness, NO_DATA, "quality-key-000001")["result"]
    quality = next(item for item in result["risks"] if item["code"] == "DATA_QUALITY")
    assert quality["observed"] is True
    assert quality["basis"]["evidence_status"] == result["evidence_status"]
    assert quality["basis"]["biomass_fraction"] == result["coverage"]["biomass_fraction"]


# -- the projection -------------------------------------------------------------------------
def test_facts_and_projected_years_are_different_kinds_of_point(harness):
    projection = _result(harness, POSITIVE, "proj-key-00000001")["result"]["projection"]
    assert projection["status"] == "AVAILABLE"
    assert projection["horizon_year"] == 2029
    kinds = {point["series_kind"] for point in projection["points"]}
    assert kinds == {"FACT", "PROJECTION"}
    facts = [point["year"] for point in projection["points"]
             if point["series_kind"] == "FACT"]
    projected = [point["year"] for point in projection["points"]
                 if point["series_kind"] == "PROJECTION"]
    # They do not interleave: everything measured comes before everything projected.
    assert max(facts) < min(projected)
    assert max(projected) == 2029


def test_the_projection_never_produces_units(harness):
    """Nothing in the supplied data supports a statement about future units."""
    projection = _result(harness, POSITIVE, "projq-key-0000001")["result"]["projection"]
    assert projection["q_projection"] is None
    assert projection["q_projection_note"]
    assert "не строится" in projection["q_projection_note"]


def test_the_projection_does_not_move_the_current_answer(harness):
    result = _result(harness, POSITIVE, "projmove-key-00001")["result"]
    assert result["units"]["q"] > 0
    years_in_units = str(result["units"])
    assert "2029" not in years_in_units
    # The ledger runs over the requested period, not over the horizon.
    assert result["change"]["year_end"] == 2024


def test_the_projection_continues_the_baseline_at_its_own_rate(harness):
    projection = _result(harness, POSITIVE, "projrate-key-00001")["result"]["projection"]
    points = [point for point in projection["points"]
              if point["baseline_carbon_tc_ha"] is not None]
    steps = [points[index + 1]["baseline_carbon_tc_ha"]
             - points[index]["baseline_carbon_tc_ha"]
             for index in range(len(points) - 1)]
    assert steps, "the baseline should have a trajectory to continue"
    assert all(step == pytest.approx(steps[0], abs=1e-6) for step in steps), \
        "a projected point must sit on the line the engine drew, not on a new one"


def test_no_baseline_means_no_projection_rather_than_a_guess(harness):
    from backend.app.v2.assemble import projection_block

    projection = projection_block(
        {"status": "UNAVAILABLE", "unavailable_reason": "BASELINE_UNKNOWN_AREA",
         "curve_tc_ha": {}}, [{"year": 2019}])
    assert projection["status"] == "UNAVAILABLE"
    assert projection["unavailable_reason"] == "BASELINE_UNKNOWN_AREA"
    assert projection["points"] == []


# -- scenario value -------------------------------------------------------------------------
def test_the_official_prices_are_q_times_the_parameter_table(harness):
    job = _result(harness, POSITIVE, "value-key-0000001")
    body = harness.api.get(f"/analyses/{job['analysis_id']}/value", "ValueScenarios")
    q = job["result"]["units"]["q"]
    assert body["q"] == q
    assert [item["price_rub"] for item in body["scenarios"]] == [500.0, 1500.0, 4000.0]
    for item in body["scenarios"]:
        assert item["origin"] == "CASE_PARAMETER"
        assert item["value_rub"] == pytest.approx(q * item["price_rub"])


def test_a_price_the_caller_supplies_is_labelled_as_theirs(harness):
    job = _result(harness, POSITIVE, "userprice-key-0001")
    body = harness.api.get(f"/analyses/{job['analysis_id']}/value?price_rub=1234.5",
                           "ValueScenarios")
    user = [item for item in body["scenarios"] if item["origin"] == "USER_SCENARIO"]
    assert len(user) == 1
    assert user[0]["price_rub"] == 1234.5
    assert user[0]["value_rub"] == pytest.approx(body["q"] * 1234.5)


def test_a_supplied_price_cannot_reach_the_passport(harness):
    """A stated price must never be able to change a hash."""
    job = _result(harness, POSITIVE, "pricehash-key-0001")
    before = job["result"]["passport"]["content_hash"]
    harness.api.get(f"/analyses/{job['analysis_id']}/value?price_rub=999999",
                    "ValueScenarios")
    again = harness.api.get(f"/analyses/{job['analysis_id']}", "Analysis")
    assert again["result"]["passport"]["content_hash"] == before
    # The stored result knows only the three prices of the case.
    values = again["result"]["scenario_values"]
    assert {key for key in values if key in ("low", "base", "high")} == {"low", "base",
                                                                         "high"}
    assert all(values[key]["price_rub"] in (500.0, 1500.0, 4000.0)
               for key in ("low", "base", "high"))


def test_no_money_is_attached_to_an_answer_that_does_not_exist(harness):
    job = _result(harness, NO_DATA, "nomoney-key-000001")
    assert job["result"]["units"]["q"] is None
    body = harness.api.get(f"/analyses/{job['analysis_id']}/value?price_rub=1000",
                           "ValueScenarios")
    assert body["q"] is None
    assert all(item["value_rub"] is None for item in body["scenarios"])


def test_a_negative_price_is_refused(harness):
    job = _result(harness, POSITIVE, "negprice-key-00001")
    response = harness.client.get(
        f"/api/v2/analyses/{job['analysis_id']}/value?price_rub=-5",
        headers=_as(harness, "VERIFIER"))
    assert response.status_code == 422


def test_the_value_document_refuses_the_vocabulary_of_a_forecast(harness):
    job = _result(harness, POSITIVE, "vocab-key-0000001")
    body = harness.api.get(f"/analyses/{job['analysis_id']}/value", "ValueScenarios")
    assert "не рыночная котировка" in body["note"]
    assert "не прогноз выручки" in body["note"]
    assert "USER_SCENARIO" in body["note"]


def test_the_value_route_follows_the_same_visibility_rule(harness):
    job = _result(harness, POSITIVE, "valrole-key-000001")
    response = harness.client.get(f"/api/v2/analyses/{job['analysis_id']}/value",
                                  headers=_as(harness, "INVESTOR"))
    assert response.status_code == 404
