"""The decision: what the numbers mean, when there is no number, and when the answer is zero.

The distinction these tests defend is the one the whole tool rests on. "We could not tell"
and "we worked it out and it is zero" are different answers with different consequences,
and a screen that renders them the same way would be lying politely.
"""
from __future__ import annotations

import pytest

from backend.app.v2 import catalog

from .conftest import Harness

POSITIVE = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024}
NON_POSITIVE = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2022}
TOO_UNCERTAIN = {"aoi_id": "RU_MORDOVIA_03", "year_start": 2020, "year_end": 2022}
NO_DATA = {"aoi_id": "RU_MORDOVIA_04", "year_start": 2019, "year_end": 2024}


def sub_plot(**extra) -> dict:
    sample = next(item for item in catalog.sample_requests()
                  if item["request_id"] == "CHECK_TRANSFER_01")
    return {"geometry": sample["geometry"], "year_start": 2020, "year_end": 2024, **extra}


def result_of(harness: Harness, body: dict, key: str) -> dict:
    job = harness.analyse(body, key=key)
    assert job["job_state"] == "SUCCEEDED", job
    return job["result"]


# -- q above zero -------------------------------------------------------------------------
def test_a_positive_result_carries_the_whole_ledger(harness):
    units = result_of(harness, POSITIVE, "pos-key-00000001")["units"]
    assert units["status"] == "AVAILABLE"
    assert units["q"] > 0
    assert units["zero_reason"] is None and units["unavailable_reason"] is None
    for field in ("ebase_tco2e", "eproj_tco2e", "lk_tco2e", "h_tco2e", "r_tco2e", "ratio",
                  "unc", "radj_tco2e", "buffer_tco2e", "rounding_residual_tco2e"):
        assert units[field] is not None, field


def test_q_is_floor_of_radj_times_the_literal_share(harness):
    import math

    units = result_of(harness, POSITIVE, "floor-key-000001")["units"]
    assert units["q"] == math.floor(units["radj_tco2e"] * 0.85)


def test_the_rounding_residual_is_preserved_not_absorbed(harness):
    units = result_of(harness, POSITIVE, "residual-key-0001")["units"]
    residual = units["radj_tco2e"] - units["buffer_tco2e"] - units["q"]
    assert units["rounding_residual_tco2e"] == pytest.approx(residual, abs=1e-9)
    assert 0.0 <= units["rounding_residual_tco2e"] <= 1.0


def test_the_uncertainty_deduction_follows_the_allowance(harness):
    units = result_of(harness, POSITIVE, "unc-key-00000001")["units"]
    assert units["unc"] == pytest.approx(min(1.0, max(0.0, units["ratio"] - 0.10)), abs=1e-12)
    assert units["radj_tco2e"] == pytest.approx(units["r_tco2e"] * (1 - units["unc"]), abs=1e-9)


def test_scenario_values_use_the_three_prices_of_the_case(harness):
    result = result_of(harness, POSITIVE, "money-key-0000001")
    q, values = result["units"]["q"], result["scenario_values"]
    assert values["unit"] == "RUB"
    for name, price in zip(("low", "base", "high"), (500.0, 1500.0, 4000.0)):
        assert values[name]["price_rub"] == price
        assert values[name]["value_rub"] == pytest.approx(q * price)


# -- q equal to zero ----------------------------------------------------------------------
def test_a_non_positive_relative_result_is_zero_with_a_reason(harness):
    units = result_of(harness, NON_POSITIVE, "zero-key-00000001")["units"]
    assert units["status"] == "AVAILABLE"
    assert units["q"] == 0
    assert units["zero_reason"] == "NON_POSITIVE_RELATIVE_RESULT"
    assert units["unavailable_reason"] is None
    assert units["r_tco2e"] <= 0.0


def test_the_stop_rule_is_a_zero_not_a_missing_answer(harness):
    units = result_of(harness, TOO_UNCERTAIN, "stop-key-00000001")["units"]
    assert units["q"] == 0
    assert units["zero_reason"] == "UNCERTAINTY_TOO_HIGH"
    assert units["ratio"] >= 1.0
    assert units["r_tco2e"] > 0.0, "the stop rule only applies to a positive relative result"


def test_zero_units_still_carry_scenario_values_of_zero(harness):
    result = result_of(harness, NON_POSITIVE, "zeromoney-key-01")
    assert result["units"]["q"] == 0
    assert result["scenario_values"]["base"]["value_rub"] == 0.0


def test_a_zero_result_is_not_an_unavailable_result(harness):
    result = result_of(harness, NON_POSITIVE, "notnull-key-00001")
    assert result["calculation_status"] == "AVAILABLE"
    assert result["units"]["q"] == 0


# -- q is null ----------------------------------------------------------------------------
def test_an_unanswerable_contour_is_null_with_a_reason(harness):
    result = result_of(harness, NO_DATA, "null-key-00000001")
    units = result["units"]
    assert result["calculation_status"] == "UNAVAILABLE"
    assert units["q"] is None
    assert units["unavailable_reason"] == "RASTER_ANALYSIS_UNAVAILABLE"
    assert units["zero_reason"] is None


def test_partial_coverage_is_a_result_not_a_failed_job(harness):
    job = harness.analyse(sub_plot(), key="partial-key-00001")
    assert job["job_state"] == "SUCCEEDED"
    assert job["error"] is None
    result = job["result"]
    assert result["units"]["unavailable_reason"] == "INCOMPLETE_COVERAGE"
    assert result["units"]["q"] is None
    # The stock change survives; only the units do not.
    assert result["change"]["delta_carbon_tc"] is not None
    assert result["areas"]["missing_ha"] > 0.0
    # Missing area and the signed difference answer different questions.
    assert result["areas"]["area_difference_ha"] < 0.0


def test_no_money_is_attached_to_an_absent_answer(harness):
    values = result_of(harness, NO_DATA, "nomoney-key-00001")["scenario_values"]
    assert values["low"] is None and values["base"] is None and values["high"] is None


def test_null_and_zero_never_share_a_reason_code(harness):
    absent = result_of(harness, NO_DATA, "vocab-key-0000001")["units"]
    zero = result_of(harness, NON_POSITIVE, "vocab-key-0000002")["units"]
    assert set(absent["reason_codes"]).isdisjoint(zero["reason_codes"])
    assert absent["reason_codes"] and zero["reason_codes"]


# -- the coverage axes --------------------------------------------------------------------
def test_the_four_coverages_are_reported_separately(harness):
    coverage = result_of(harness, POSITIVE, "cov-key-00000001")["coverage"]
    assert set(coverage) == {"biomass_fraction", "uncertainty_fraction", "baseline_fraction",
                             "optical_paired_valid_fraction", "coverage_fraction_raw"}
    assert coverage["biomass_fraction"] == pytest.approx(1.0, abs=1e-6)
    # Every public share has its unclamped counterpart, so nothing is lost to the clamp.
    assert set(coverage["coverage_fraction_raw"]) == {
        "biomass", "uncertainty", "baseline", "optical_paired_valid"}
    for public, raw in (("biomass_fraction", "biomass"),
                        ("uncertainty_fraction", "uncertainty"),
                        ("baseline_fraction", "baseline"),
                        ("optical_paired_valid_fraction", "optical_paired_valid")):
        assert coverage[public] == pytest.approx(
            min(1.0, max(0.0, coverage["coverage_fraction_raw"][raw])))


def test_missing_optical_evidence_does_not_reduce_biomass_coverage(harness):
    result = result_of(harness, POSITIVE, "optical-key-000001")
    assert result["coverage"]["optical_paired_valid_fraction"] == 0.0
    assert result["coverage"]["biomass_fraction"] == pytest.approx(1.0, abs=1e-6)
    assert result["units"]["q"] > 0, "poor optics must not by itself remove the number"
    assert result["evidence_status"] == "INSUFFICIENT"


def test_evidence_status_and_calculation_status_move_independently(harness):
    result = result_of(harness, POSITIVE, "indep-key-0000001")
    assert result["calculation_status"] == "AVAILABLE"
    assert result["evidence_status"] in ("INSUFFICIENT", "REVIEW_REQUIRED")
    assert result["evidence"]["warnings"], "an insufficient evidence status must say why"


# -- areas and the sub-plot baseline ------------------------------------------------------
def test_the_requested_area_is_the_geodesic_area_of_the_contour(harness):
    result = result_of(harness, POSITIVE, "area-key-00000001")
    registered = catalog.area("RU_TVER_01").area_ha
    assert result["areas"]["requested_ha"] == pytest.approx(registered, rel=1e-3)


def test_a_sub_plot_uses_the_parent_baseline_on_its_own_area(harness):
    result = result_of(harness, sub_plot(), "subplot-key-00001")
    parts = result["areas"]["parent_parts"]
    assert [part["aoi_id"] for part in parts] == ["RU_VOLOGDA_02"]
    assert result["areas"]["requested_ha"] == pytest.approx(808.85, rel=1e-3)
    assert sum(part["area_ha"] for part in parts) < result["areas"]["requested_ha"]


def test_parent_parts_do_not_double_count_hectares(harness):
    result = result_of(harness, POSITIVE, "double-key-0000001")
    total = sum(part["area_ha"] for part in result["areas"]["parent_parts"])
    assert total == pytest.approx(result["areas"]["calculated_ha"], rel=1e-9)


# -- claim comparability ------------------------------------------------------------------
def test_no_claim_means_not_provided(harness):
    claim = result_of(harness, POSITIVE, "noclaim-key-00001")["claim"]
    assert claim["status"] == "NOT_PROVIDED"
    assert claim["claimed_units"] is None and claim["unsupported_gap"] is None


def test_a_claim_below_the_result_is_supported(harness):
    result = result_of(harness, {**POSITIVE, "claimed_units": 10}, "under-key-0000001")
    claim = result["claim"]
    assert claim["status"] == "SUPPORTED_BY_CASE"
    assert claim["unsupported_gap"] == 0.0
    assert claim["supported_share"] == 1.0


def test_a_claim_above_the_result_is_partially_supported(harness):
    result = result_of(harness, {**POSITIVE, "claimed_units": 100000},
                       "over-key-00000001")
    claim, q = result["claim"], result["units"]["q"]
    assert claim["status"] == "PARTIALLY_SUPPORTED_BY_CASE"
    assert claim["unsupported_gap"] == pytest.approx(100000 - q)
    assert claim["supported_share"] == pytest.approx(q / 100000)
    assert claim["scenario_gap_values"]["base"]["value_rub"] == pytest.approx(
        (100000 - q) * 1500.0)


def test_a_claim_against_zero_units_is_not_supported(harness):
    result = result_of(harness, {**NON_POSITIVE, "claimed_units": 500},
                       "zeroclaim-key-001")
    claim = result["claim"]
    assert claim["status"] == "NOT_SUPPORTED_BY_CASE"
    assert claim["unsupported_gap"] == 500.0


def test_a_claim_against_a_null_result_is_unassessable(harness):
    result = result_of(harness, sub_plot(claimed_units=500), "nullclaim-key-01")
    claim = result["claim"]
    assert claim["status"] == "UNASSESSABLE"
    assert claim["unsupported_gap"] is None
    assert claim["scenario_gap_values"] is None


def test_a_claim_about_another_period_is_not_comparable(harness):
    scope = {"geometry_hash": "0x" + "1" * 64, "year_start": 2019, "year_end": 2020,
             "pool": "AGB", "unit": "tCO2e"}
    result = result_of(harness, {**POSITIVE, "claimed_units": 500, "claim_scope": scope},
                       "scope-key-00000001")
    claim = result["claim"]
    assert claim["status"] == "NOT_COMPARABLE"
    assert claim["comparable"] is False
    assert set(claim["mismatch_reasons"]) >= {"GEOMETRY_MISMATCH", "PERIOD_MISMATCH"}
    assert claim["unsupported_gap"] is None


def test_a_claim_about_another_pool_is_not_comparable(harness):
    scope = {"geometry_hash": "0x" + "1" * 64, "year_start": 2019, "year_end": 2024,
             "pool": "WHOLE_ECOSYSTEM", "unit": "tCO2e"}
    result = result_of(harness, {**POSITIVE, "claimed_units": 500, "claim_scope": scope},
                       "pool-key-00000001")
    assert "POOL_MISMATCH" in result["claim"]["mismatch_reasons"]


def test_a_claim_is_labelled_as_an_input_not_as_a_finding(harness):
    result = result_of(harness, {**POSITIVE, "claimed_units": 42, "claim_origin": "DEMO_INPUT"},
                       "label-key-00000001")
    assert result["claim"]["origin"] == "DEMO_INPUT"
    assert "ввод" in result["claim"]["scope_note"]


def test_a_claim_never_moves_the_calculated_number(harness):
    without = result_of(harness, POSITIVE, "move-key-00000001")
    with_claim = result_of(harness, {**POSITIVE, "claimed_units": 1},
                           "move-key-00000002")
    assert without["units"] == with_claim["units"]
    assert without["change"] == with_claim["change"]


# -- the language the result is allowed to use --------------------------------------------
def test_the_result_never_calls_a_gap_a_loss_or_a_verdict(harness):
    import json

    result = result_of(harness, {**POSITIVE, "claimed_units": 100000},
                       "language-key-00001")
    text = json.dumps(result, ensure_ascii=False).upper()
    for forbidden in ("INVESTABLE", "МОШЕННИЧЕСТВ", "ОДОБРЕНО К ПОКУПКЕ", "VALUE AT RISK"):
        assert forbidden not in text, forbidden
    # The word may appear only where the result denies the promise, never where it makes it.
    for index in range(len(text)):
        if text.startswith("ГАРАНТИРОВАН", index):
            assert text[max(0, index - 3):index] == "НЕ ", text[index - 40:index + 40]


def test_every_result_states_the_pool_and_the_sign(harness):
    change = result_of(harness, POSITIVE, "sign-key-00000001")["change"]
    assert change["pool"] == "AGB"
    assert change["sign_convention"] == "POSITIVE_E_MEANS_POOL_LOSS"


def test_every_result_carries_its_limitations_and_sources(harness):
    result = result_of(harness, POSITIVE, "limits-key-000001")
    assert len(result["limitations"]) >= 4
    assert all({"code", "message"} == set(item) for item in result["limitations"])
    assert any("надземная" in item["message"] for item in result["limitations"])
    assert {"CCI_V7", "IPCC_FOREST_2006", "CASE_RULES_V1"} <= {
        item["source_id"] for item in result["sources"]}
    assert all(item["attribution"] for item in result["sources"])


def test_a_replayed_vector_is_labelled_on_the_wire(harness):
    result = result_of(harness, POSITIVE, "fixture-key-00001")
    assert result["fixture"]["kind"] == "UNIT_TEST_VECTOR"
    assert result["run"]["dataset_origin"] == "STUB_FIXTURE"
    assert any("заглушк" in item["message"] or "замены" in item["message"]
               for item in result["limitations"])


# -- a claim of zero ----------------------------------------------------------------------
def test_a_claim_of_zero_is_not_applicable_rather_than_supported(harness):
    """Nothing positive was stated, so nothing was supported.

    Reporting a zero claim as SUPPORTED_BY_CASE would let an empty statement inherit the
    vocabulary of a confirmed one, which is exactly the confusion the status axis exists
    to prevent.
    """
    claim = result_of(harness, {**POSITIVE, "claimed_units": 0}, "zeroclaim-key-002")["claim"]
    assert claim["status"] == "NOT_APPLICABLE"
    assert claim["mismatch_reasons"] == ["NO_POSITIVE_CLAIM"]
    assert claim["supported_share"] is None
    assert claim["unsupported_gap"] == 0.0
    assert claim["comparable"] is False
    assert claim["scenario_gap_values"] is None


def test_a_claim_of_zero_is_not_applicable_even_without_a_number(harness):
    """The rule holds on the degraded path too, where there is no q to compare with."""
    claim = result_of(harness, sub_plot(claimed_units=0), "zeroclaim-key-003")["claim"]
    assert claim["status"] == "NOT_APPLICABLE"
    assert claim["supported_share"] is None and claim["unsupported_gap"] == 0.0


# -- coverage arithmetic that lands outside [0, 1] ----------------------------------------
def test_a_raw_coverage_above_one_is_clamped_in_public_and_preserved_raw():
    """Geodesic areas are not additive over a partition, so the sum can exceed the whole.

    The public share must stay a share, and the arithmetic must still be visible: a
    reader who sees 1.0 needs to be able to find out it was 1.000000113.
    """
    from backend.app.v2.assemble import coverage_block

    raster = {"coverage": {
        "requested_ha": 1000.0, "calculated_ha": 1000.000113, "missing_ha": 0.0,
        "complete": True,
        "biomass": {"area_ha": 1000.000113, "fraction": 1.000000113},
        "biomass_sd": {"area_ha": 1000.000113, "fraction": 1.000000113},
        "optical_paired": {"area_ha": 0.0, "fraction": 0.0}}}
    block = coverage_block(raster, {"area_ha": 1000.000113})

    assert block["biomass_fraction"] == 1.0
    assert block["uncertainty_fraction"] == 1.0
    assert block["coverage_fraction_raw"]["biomass"] == pytest.approx(1.000000113)
    assert block["coverage_fraction_raw"]["uncertainty"] == pytest.approx(1.000000113)
    assert block["coverage_fraction_raw"]["baseline"] > 1.0


def test_the_signed_area_difference_and_the_missing_area_are_different_questions():
    from backend.app.v2.assemble import areas_block

    raster = {"coverage": {"requested_ha": 1000.0, "calculated_ha": 1000.000113,
                           "missing_ha": 0.0, "complete": True},
              "request": {"parents": ["RU_TVER_01"]}}
    areas = areas_block(raster, {"features": []})
    assert areas["missing_ha"] == 0.0
    assert areas["area_difference_ha"] == pytest.approx(0.000113, abs=1e-9)


# -- warnings a machine can act on --------------------------------------------------------
def test_every_warning_carries_a_code_a_severity_and_a_message(harness):
    result = result_of(harness, POSITIVE, "warncode-key-00001")
    warnings = result["evidence"]["warnings"]
    assert warnings, "an incomplete evidence status must say why"
    for item in warnings:
        assert set(item) == {"code", "severity", "message", "details"}
        assert item["severity"] in ("INFO", "WARNING", "BLOCKING")
        assert item["code"] == item["code"].upper() and " " not in item["code"]
        assert isinstance(item["details"], dict)
    # Warnings are about this run; limitations always hold. They stay apart.
    assert {item["code"] for item in warnings}.isdisjoint(
        {item["code"] for item in result["limitations"]})


def test_a_degraded_result_names_its_blocking_reason_as_a_code(harness):
    result = result_of(harness, NO_DATA, "warnblock-key-0001")
    blocking = [item for item in result["evidence"]["warnings"]
                if item["severity"] == "BLOCKING"]
    assert blocking, "a result with no numbers must carry a blocking warning"
    assert blocking[0]["code"] == result["units"]["unavailable_reason"]


# -- zones must be drawable ---------------------------------------------------------------
def test_published_zones_always_point_at_the_file_that_holds_their_geometry(harness):
    """A zone a map cannot draw is a row in a table, not evidence."""
    result = result_of(harness, TOO_UNCERTAIN, "zonegeom-key-00001")
    if not result["zones"]:
        pytest.skip("the replay vector for this contour carries no change zones")
    artifacts = {item["artifact_id"] for item in result["artifacts"]}
    for zone in result["zones"]:
        assert zone["artifact_ref"] is not None, zone["zone_id"]
        assert zone["artifact_ref"] in artifacts
