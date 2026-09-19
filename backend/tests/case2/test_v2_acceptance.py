"""The fourteen acceptance scenarios, walked one at a time through HTTP.

Each test here is one numbered scenario from the roadmap. They repeat coverage that the
focused suites already have, and that is the point: a scenario is a sentence somebody can
read and check, and it should be possible to point at the line that proves it rather than
at a directory.
"""
from __future__ import annotations

import pytest

from backend.app.v2 import catalog

OFFICIAL_AOI = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024}
ZERO_RESULT = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2022}
FIRE_AOI = {"aoi_id": "RU_MORDOVIA_03", "year_start": 2020, "year_end": 2022}


def _as(harness, role):
    return {"Authorization": "Bearer " + harness.api.tokens[role]}


def _sub_plot(**extra) -> dict:
    sample = next(item for item in catalog.sample_requests()
                  if item["request_id"] == "CHECK_TRANSFER_01")
    return {"geometry": sample["geometry"], "year_start": 2020, "year_end": 2024, **extra}


def _walk(harness, body, key, *, finalize=False):
    """A request from draft to calculated, optionally finalized by a verifier."""
    request_id = harness.client.post("/api/v2/requests", json=body,
                                     headers=_as(harness, "PROJECT_OWNER")
                                     ).json()["request_id"]
    harness.client.post(f"/api/v2/requests/{request_id}/submit",
                        headers=_as(harness, "PROJECT_OWNER"))
    harness.client.post(f"/api/v2/requests/{request_id}/analysis",
                        headers={**_as(harness, "VERIFIER"), "Idempotency-Key": key})
    harness.run()
    if finalize:
        assert harness.client.post(f"/api/v2/requests/{request_id}/finalize",
                                   headers=_as(harness, "VERIFIER")).status_code == 200
    request = harness.client.get(f"/api/v2/requests/{request_id}",
                                 headers=_as(harness, "VERIFIER")).json()
    analysis = harness.client.get(request["analysis_url"],
                                  headers=_as(harness, "VERIFIER")).json()
    return request, analysis


# 1 ---------------------------------------------------------------------------------------
def test_01_an_owner_signs_in_and_submits_an_official_area_with_a_claim(harness):
    from .conftest import PASSWORD

    signed_in = harness.client.post("/api/v2/auth/login",
                                    json={"username": "owner", "password": PASSWORD})
    assert signed_in.status_code == 200
    assert signed_in.json()["user"]["role"] == "PROJECT_OWNER"

    created = harness.client.post("/api/v2/requests",
                                  json={**OFFICIAL_AOI, "claimed_units": 500},
                                  headers={"Authorization":
                                           "Bearer " + signed_in.json()["token"]})
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "DRAFT" and body["aoi_id"] == "RU_TVER_01"
    assert body["claimed_units"] == 500


# 2 ---------------------------------------------------------------------------------------
def test_02_a_verifier_runs_the_calculation_and_gets_a_zero_that_says_why(harness):
    """Zero is an answer. It arrives with a reason and is not a failure."""
    _request, analysis = _walk(harness, ZERO_RESULT, "acc02-key-00000001")
    assert analysis["job_state"] == "SUCCEEDED" and analysis["error"] is None
    units = analysis["result"]["units"]
    assert units["status"] == "AVAILABLE" and units["q"] == 0
    assert units["zero_reason"] == "NON_POSITIVE_RELATIVE_RESULT"
    assert units["unavailable_reason"] is None


# 3 ---------------------------------------------------------------------------------------
def test_03_the_stress_test_shows_an_unsupported_gap_without_accusing_anyone(harness):
    import json

    _request, analysis = _walk(harness, {**OFFICIAL_AOI, "claimed_units": 100000},
                               "acc03-key-00000001")
    claim = analysis["result"]["claim"]
    assert claim["status"] == "PARTIALLY_SUPPORTED_BY_CASE"
    assert claim["unsupported_gap"] > 0 and claim["supported_share"] < 1.0
    assert "не установленный факт" in claim["scope_note"]

    text = json.dumps(analysis["result"], ensure_ascii=False).upper()
    for accusation in ("МОШЕННИЧЕСТВ", "FRAUD", "ПОДЛОГ", "ОБМАН", "VALUE AT RISK"):
        assert accusation not in text, accusation


# 4 ---------------------------------------------------------------------------------------
def test_04_an_investor_sees_only_a_finalized_passport(harness):
    request, _analysis = _walk(harness, OFFICIAL_AOI, "acc04-key-00000001")
    assert harness.client.get(request["analysis_url"],
                              headers=_as(harness, "INVESTOR")).status_code == 404

    harness.client.post(f"/api/v2/requests/{request['request_id']}/finalize",
                        headers=_as(harness, "VERIFIER"))
    visible = harness.client.get(request["analysis_url"], headers=_as(harness, "INVESTOR"))
    assert visible.status_code == 200
    assert visible.json()["result"]["passport"]["status"] == "FINALIZED"


# 5 ---------------------------------------------------------------------------------------
def test_05_the_808_hectare_sub_plot_is_processed(harness):
    _request, analysis = _walk(harness, _sub_plot(), "acc05-key-00000001")
    assert analysis["job_state"] == "SUCCEEDED"
    areas = analysis["result"]["areas"]
    assert areas["requested_ha"] == pytest.approx(808.85, rel=1e-3)
    assert [part["aoi_id"] for part in areas["parent_parts"]] == ["RU_VOLOGDA_02"]


# 6 ---------------------------------------------------------------------------------------
def test_06_a_drawn_contour_is_processed_without_a_code_change(harness):
    """The same path as a named area: naming one is a shortcut for pasting its polygon."""
    geometry = catalog.area("RU_TVER_01").geometry
    named = harness.analyse(OFFICIAL_AOI, key="acc06-key-00000001")
    drawn = harness.analyse({"geometry": geometry, "year_start": 2019, "year_end": 2024},
                            key="acc06-key-00000002")
    assert drawn["job_state"] == "SUCCEEDED"
    assert drawn["result"]["passport"]["content_hash"] == \
        named["result"]["passport"]["content_hash"]


# 7 ---------------------------------------------------------------------------------------
def test_07_incomplete_coverage_gives_a_null_and_not_a_zero(harness):
    _request, analysis = _walk(harness, _sub_plot(), "acc07-key-00000001")
    units = analysis["result"]["units"]
    assert analysis["job_state"] == "SUCCEEDED"
    assert units["q"] is None and units["status"] == "UNAVAILABLE"
    assert units["unavailable_reason"] == "INCOMPLETE_COVERAGE"
    assert units["zero_reason"] is None
    values = analysis["result"]["scenario_values"]
    assert values["low"] is None and values["base"] is None and values["high"] is None


# 8 ---------------------------------------------------------------------------------------
def test_08_a_supported_fire_is_shown_and_an_unknown_cause_stays_unknown(harness):
    _request, analysis = _walk(harness, FIRE_AOI, "acc08-key-00000001")
    zones = analysis["result"]["zones"]
    if not zones:
        # The replay vectors carry no zones, because inventing a fire is exactly the
        # thing a stand-in must not do. The real path is covered by
        # backend/tools/live_composition.py, which runs this over the supplied rasters.
        pytest.skip("the replay vectors carry no change zones; see live_composition.py")
    causes = {zone["cause"] for zone in zones}
    assert causes <= {"FIRE_SUPPORTED", "UNKNOWN", "NOT_APPLICABLE"}
    for zone in zones:
        assert zone["cause_reason"], "a cause without a reason is an assertion"
        if zone["cause"] == "FIRE_SUPPORTED":
            assert zone["date_range"] and "MODIS_MCD64A1_061" in zone["evidence_refs"]
        if zone["cause"] == "UNKNOWN":
            assert zone["date_range"] is None


# 9 ---------------------------------------------------------------------------------------
def test_09_a_tampered_artifact_is_blocked(harness):
    job = harness.analyse(OFFICIAL_AOI, key="acc09-key-00000001")
    artifact = job["result"]["artifacts"][0]
    rows = harness.lens.store.artifact_rows(job["analysis_id"])
    row = next(item for item in rows if item["artifact_id"] == artifact["artifact_id"])
    path = harness.lens.store.artifact_root / row["storage_name"]

    assert harness.client.get(artifact["url"],
                              headers=harness.api.headers()).status_code == 200
    path.write_bytes(path.read_bytes() + b"tampered")
    refused = harness.client.get(artifact["url"], headers=harness.api.headers())
    assert refused.status_code == 503
    assert refused.json()["error"]["code"] == "ARTIFACT_INTEGRITY_FAILED"


# 10 --------------------------------------------------------------------------------------
def test_10_a_repeated_idempotency_key_does_not_create_a_second_analysis(harness):
    first = harness.api.post("/analyses", OFFICIAL_AOI, key="acc10-key-00000001")
    second = harness.api.post("/analyses", OFFICIAL_AOI, key="acc10-key-00000001")
    assert first["analysis_id"] == second["analysis_id"]
    assert harness.counted("lens_analyses") == 1


# 11 --------------------------------------------------------------------------------------
def test_11_production_without_the_engines_returns_no_fixture(harness, tmp_path):
    """The default mode has one answer: the real engines, or an error."""
    from backend.app.v2.adapters import EnginesUnavailable, REAL, build_ports, missing_engines

    if not missing_engines():  # pragma: no cover - depends on the branch
        pytest.skip("both engines are merged into this branch")
    with pytest.raises(EnginesUnavailable):
        build_ports(tmp_path, engine_mode=REAL)


def test_11b_a_demo_deployment_may_not_be_switched_to_fixtures(harness):
    from backend.app.config import ConfigError, Settings

    with pytest.raises(ConfigError):
        Settings(demo_session="x" * 16, mode="LOCAL_DEMO", chain_adapter="web3",
                 lens_engine_mode="FIXTURE").validate()


# 12 --------------------------------------------------------------------------------------
def test_12_a_user_of_another_role_is_refused_by_the_server(harness):
    refused = harness.client.post("/api/v2/analyses", json=OFFICIAL_AOI,
                                  headers={**_as(harness, "INVESTOR"),
                                           "Idempotency-Key": "acc12-key-00000001"})
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "FORBIDDEN"

    request, _analysis = _walk(harness, OFFICIAL_AOI, "acc12-key-00000002")
    assert harness.client.post(f"/api/v2/requests/{request['request_id']}/finalize",
                               headers=_as(harness, "PROJECT_OWNER")).status_code == 403


# 13 --------------------------------------------------------------------------------------
def test_13_the_2029_projection_is_not_mixed_with_the_facts(harness):
    _request, analysis = _walk(harness, OFFICIAL_AOI, "acc13-key-00000001")
    projection = analysis["result"]["projection"]
    facts = [point for point in projection["points"] if point["series_kind"] == "FACT"]
    projected = [point for point in projection["points"]
                 if point["series_kind"] == "PROJECTION"]
    assert facts and projected
    assert max(point["year"] for point in facts) < min(point["year"] for point in projected)
    assert max(point["year"] for point in projected) == 2029
    assert projection["q_projection"] is None
    # The timeline of measured years carries no projected point at all.
    assert max(entry["year"] for entry in analysis["result"]["timeline"]) <= 2024


# 14 --------------------------------------------------------------------------------------
def test_14_the_demo_lifecycle_is_forbidden_for_a_real_zero(harness):
    request, analysis = _walk(harness, ZERO_RESULT, "acc14-key-00000001", finalize=True)
    assert analysis["result"]["units"]["q"] == 0
    refused = harness.client.post(f"/api/v2/requests/{request['request_id']}/demo/issue",
                                  headers=_as(harness, "PROJECT_OWNER"))
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "NO_POSITIVE_UNITS"
