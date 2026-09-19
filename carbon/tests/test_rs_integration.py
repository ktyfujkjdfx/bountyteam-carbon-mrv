"""The reviewed RS boundary: valid cells, separate SD coverage, raw shares, hard errors.

Every test here corresponds to a blocker raised in the Trust consumer review of the RS and
Backend pull requests. They are written so that the flattering failure — the one where
missing data makes Q larger — cannot pass.
"""
from __future__ import annotations

import copy
import math

import pytest

from carbon import Coverage, RsPayloadError, analyse, compute_units, from_fixture, from_rs_payload
from carbon.rs_adapter import (
    CANONICAL_E_TOLERANCE,
    COVERAGE_TOLERANCE_HA,
    RS_ANALYSIS_SCHEMA,
    agrees_with_declared_e,
    guard_production_input,
    read_cells,
)
from carbon.tests.conftest import ALL_REQUESTS, FIXTURE_DIR, build_case, load_json


def fixture(request_id: str) -> dict:
    return load_json(FIXTURE_DIR / f"cells_{request_id}.json")


def rs_payload(*, cells, requested=100.0, calculated=100.0, e_tco2e=None) -> dict:
    return {
        "schema": RS_ANALYSIS_SCHEMA,
        "request": {"area_ha": requested, "year_start": 2019, "year_end": 2024,
                    "years": [2019, 2024], "parents": ["RU_TVER_01"]},
        "stock_change": {"e_tco2e": e_tco2e},
        "coverage": {
            "requested_ha": requested, "calculated_ha": calculated,
            "missing_ha": max(0.0, requested - calculated),
            "complete": requested - calculated <= COVERAGE_TOLERANCE_HA,
            "biomass": {"area_ha": calculated,
                        "fraction": calculated / requested if requested else 0.0},
            "biomass_sd": {"area_ha": calculated,
                           "fraction": calculated / requested if requested else 0.0},
            "optical_paired": {"area_ha": 0.0, "fraction": 0.0},
        },
        "timeline": [],
        "optical": None,
        "sources": [],
    }


def cell(weight, *, valid=True, sd=(10.0, 12.0), agb=(100.0, 90.0), parent="RU_TVER_01"):
    return {
        "type": "Feature", "geometry": None,
        "properties": {
            "cell_id": f"c{weight}", "parent_aoi_id": parent, "weight_ha": weight,
            "agb_t_ha": {"2019": agb[0], "2024": agb[1]},
            "agb_sd_t_ha": {"2019": sd[0], "2024": sd[1]},
            "valid": valid,
        },
    }


def layer(*cells) -> dict:
    return {"type": "FeatureCollection", "features": list(cells)}


# -- the fixtures now speak the RS contract ------------------------------------------------


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_every_fixture_is_written_in_the_rs_shape(request_id):
    """The tests must exercise the path a real RS payload takes, not a private one."""
    payload = fixture(request_id)
    assert payload["cells"]["type"] == "FeatureCollection"
    first = payload["cells"]["features"][0]["properties"]
    assert set(first) >= {"weight_ha", "agb_t_ha", "agb_sd_t_ha", "valid", "parent_aoi_id"}
    assert payload["coverage"]["biomass_sd"]["fraction"] > 0
    assert payload["stock_change"]["e_tco2e"] is not None


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_the_same_reader_accepts_the_fixture_and_a_real_payload(request_id):
    payload = fixture(request_id)
    through_fixture = from_fixture(payload)
    as_if_real = dict(payload, schema=RS_ANALYSIS_SCHEMA)
    through_rs = from_rs_payload(as_if_real, payload["cells"])
    assert through_fixture.cells.count == through_rs.cells.count
    assert through_fixture.coverage.uncertainty == through_rs.coverage.uncertainty
    assert through_fixture.input_status != through_rs.input_status


# -- valid flag ----------------------------------------------------------------------------


def test_an_invalid_cell_is_excluded_from_the_sum():
    observations, parents, excluded, sd_weight = read_cells(
        layer(cell(10.0), cell(5.0, valid=False), cell(7.0)),
        year_start=2019, year_end=2024,
    )
    assert observations.count == 2
    assert list(observations.area_ha) == [10.0, 7.0]
    assert excluded == 1
    assert parents == {"RU_TVER_01": 17.0}
    assert sd_weight == 17.0


def test_a_layer_of_only_invalid_cells_is_an_error_not_an_empty_result():
    with pytest.raises(RsPayloadError, match="excluded as invalid"):
        read_cells(layer(cell(10.0, valid=False)), year_start=2019, year_end=2024)


def test_excluded_cells_are_reported_in_the_analysis(areas, sample_requests):
    payload = fixture("RU_TVER_01")
    broken = copy.deepcopy(payload)
    for feature in broken["cells"]["features"][:100]:
        feature["properties"]["valid"] = False
    inputs = from_fixture(broken)
    assert inputs.excluded_cells == 100
    # the declared area still claims full cover, but the cells that ran do not
    assert inputs.coverage.biomass < 1.0
    assert inputs.coverage.uncertainty < 1.0
    assert inputs.coverage.baseline < 1.0


# -- the uncertainty input -----------------------------------------------------------------


def test_a_missing_deviation_is_an_error_never_a_zero():
    """Defaulting a missing SD to zero narrows the interval and raises Q."""
    hollow = layer(cell(10.0))
    hollow["features"][0]["properties"]["agb_sd_t_ha"] = {"2019": 10.0}
    with pytest.raises(RsPayloadError, match="2024"):
        read_cells(hollow, year_start=2019, year_end=2024)


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), "0", "x", True, []])
def test_an_unusable_deviation_is_an_error(bad):
    hollow = layer(cell(10.0))
    hollow["features"][0]["properties"]["agb_sd_t_ha"]["2024"] = bad
    with pytest.raises(RsPayloadError):
        read_cells(hollow, year_start=2019, year_end=2024)


def test_a_negative_deviation_is_refused():
    hollow = layer(cell(10.0, sd=(10.0, -1.0)))
    with pytest.raises(RsPayloadError, match="negative"):
        read_cells(hollow, year_start=2019, year_end=2024)


def test_partial_uncertainty_coverage_makes_q_null():
    """Method freeze: incomplete mandatory numeric coverage gives Q = null, not Q = 0."""
    result = compute_units(
        e_proj_tco2e=0.0, e_base_tco2e=1000.0, lower_tco2e=-50.0, upper_tco2e=50.0,
        area_ha=100.0, year_start=2019, year_end=2024,
        coverage=Coverage(biomass=1.0, baseline=1.0, uncertainty=0.9),
    )
    assert result.units is None
    assert result.status == "UNAVAILABLE"
    assert result.unavailable_reason == "INCOMPLETE_COVERAGE"


def test_complete_uncertainty_coverage_lets_the_calculation_run():
    result = compute_units(
        e_proj_tco2e=0.0, e_base_tco2e=1000.0, lower_tco2e=-50.0, upper_tco2e=50.0,
        area_ha=100.0, year_start=2019, year_end=2024,
        coverage=Coverage(biomass=1.0, baseline=1.0, uncertainty=1.0),
    )
    # R = 1000, H = 50, H/R = 0.05 is below the 0.10 allowance, so UNC = 0
    assert result.units == 850


def test_unreported_uncertainty_coverage_is_recorded_rather_than_assumed():
    result = compute_units(
        e_proj_tco2e=0.0, e_base_tco2e=1000.0, lower_tco2e=-50.0, upper_tco2e=50.0,
        area_ha=100.0, year_start=2019, year_end=2024,
        coverage=Coverage(biomass=1.0, baseline=1.0),
    )
    assert "UNCERTAINTY_COVERAGE_NOT_REPORTED" in {item.code for item in result.notes}


def test_the_adapter_measures_uncertainty_coverage_from_the_cells():
    inputs = from_rs_payload(
        rs_payload(cells=None, requested=20.0, calculated=20.0),
        layer(cell(10.0), cell(10.0)),
    )
    assert inputs.coverage.uncertainty == 1.0
    assert inputs.coverage_raw["uncertainty"].raw == pytest.approx(1.0)


# -- raw and public coverage ---------------------------------------------------------------


def test_a_raw_share_above_one_is_kept_and_the_public_share_is_clamped():
    """Geodesic area is not additive over a partition, so a raw share can exceed 1."""
    inputs = from_rs_payload(
        rs_payload(cells=None, requested=100.0, calculated=100.0000003),
        layer(cell(100.0000003)),
    )
    raw = inputs.coverage_raw["biomass"]
    assert raw.raw > 1.0
    assert raw.public == 1.0
    assert raw.clamped is True
    assert inputs.coverage.biomass == 1.0


def test_a_shortfall_inside_the_agreed_tolerance_is_still_complete():
    inputs = from_rs_payload(
        rs_payload(cells=None, requested=100.0, calculated=100.0 - COVERAGE_TOLERANCE_HA / 2),
        layer(cell(100.0 - COVERAGE_TOLERANCE_HA / 2)),
    )
    assert inputs.coverage.biomass == 1.0
    assert inputs.area.complete is True


def test_a_shortfall_beyond_the_tolerance_is_incomplete():
    inputs = from_rs_payload(
        rs_payload(cells=None, requested=100.0, calculated=99.0),
        layer(cell(99.0)),
    )
    assert inputs.coverage.biomass < 1.0
    assert inputs.area.complete is False
    assert inputs.area.missing_ha == pytest.approx(1.0)


# -- baseline coverage ---------------------------------------------------------------------


def test_baseline_coverage_is_measured_not_assumed_to_be_one():
    """A cell with no named parent cannot be spoken for by the baseline table."""
    orphan = layer(cell(60.0), cell(40.0, parent=None))
    inputs = from_rs_payload(rs_payload(cells=None, requested=100.0, calculated=100.0), orphan)
    assert inputs.coverage.baseline == pytest.approx(0.6)
    assert inputs.parent_weights_ha == (("RU_TVER_01", 60.0),)


def test_incomplete_baseline_coverage_makes_q_null(areas, sample_requests):
    payload = fixture("RU_TVER_01")
    orphaned = copy.deepcopy(payload)
    for feature in orphaned["cells"]["features"][:500]:
        feature["properties"]["parent_aoi_id"] = None
    inputs = from_fixture(orphaned)
    assert inputs.coverage.baseline < 1.0
    result = compute_units(
        e_proj_tco2e=0.0, e_base_tco2e=1000.0, lower_tco2e=-10.0, upper_tco2e=10.0,
        area_ha=inputs.area.calculated_ha, year_start=2019, year_end=2024,
        coverage=inputs.coverage,
    )
    assert result.units is None
    assert result.unavailable_reason == "INCOMPLETE_COVERAGE"


# -- non-finite input ----------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), float("-inf"), "x"])
def test_a_non_finite_weight_is_an_explicit_adapter_error(bad):
    hollow = layer(cell(10.0))
    hollow["features"][0]["properties"]["weight_ha"] = bad
    with pytest.raises(RsPayloadError, match="finite number"):
        read_cells(hollow, year_start=2019, year_end=2024)


@pytest.mark.parametrize("field", ["requested_ha", "calculated_ha"])
def test_a_non_finite_coverage_number_is_an_explicit_adapter_error(field):
    payload = rs_payload(cells=None)
    payload["coverage"][field] = float("nan")
    with pytest.raises(RsPayloadError, match="finite number"):
        from_rs_payload(payload, layer(cell(10.0)))


def test_a_non_positive_requested_area_is_refused():
    payload = rs_payload(cells=None, requested=0.0, calculated=0.0)
    with pytest.raises(RsPayloadError, match="requested_ha must be positive"):
        from_rs_payload(payload, layer(cell(10.0)))


# -- the canonical stock difference --------------------------------------------------------


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_the_engine_agrees_with_the_declared_stock_difference(request_id, areas, sample_requests):
    """RS owns E; recomputing it from the cells is a cross-check within a declared tolerance."""
    _, inputs, analysis, _ = build_case(request_id, areas, sample_requests)
    assert inputs.declared_e_tco2e is not None
    assert agrees_with_declared_e(inputs, analysis.interval.e_proj_tco2e) is True
    assert analysis.declared_e_agrees is True
    scale = max(abs(inputs.declared_e_tco2e), abs(analysis.interval.e_proj_tco2e), 1.0)
    assert abs(inputs.declared_e_tco2e - analysis.interval.e_proj_tco2e) <= (
        CANONICAL_E_TOLERANCE * scale
    )


def test_a_disagreement_with_the_declared_value_is_reported_not_averaged(areas, sample_requests):
    request, inputs, _, _ = build_case("RU_TVER_01", areas, sample_requests)
    analysis = analyse(
        request, inputs.cells, coverage=inputs.coverage, area=inputs.area,
        input_status=inputs.input_status, declared_e_tco2e=1.0,
    )
    assert analysis.declared_e_agrees is False
    assert "CANONICAL_E_DISAGREES" in {item.code for item in analysis.notes}
    # the reported value stays the engine's own; nothing is blended
    assert analysis.interval.e_proj_tco2e != 1.0


# -- the provisional set is a test input ---------------------------------------------------


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_a_provisional_input_cannot_reach_a_published_result(request_id):
    inputs = from_fixture(fixture(request_id))
    assert inputs.is_provisional is True
    with pytest.raises(RsPayloadError, match="test input"):
        guard_production_input(inputs)


def test_a_real_payload_passes_the_production_guard():
    inputs = from_rs_payload(rs_payload(cells=None, requested=10.0, calculated=10.0),
                             layer(cell(10.0)))
    assert inputs.is_provisional is False
    guard_production_input(inputs)


# -- the official areas still earn nothing -------------------------------------------------


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_the_official_areas_still_give_zero_units(request_id, areas, sample_requests):
    """Method freeze: the real result of every supplied area stays Q = 0."""
    _, _, analysis, _ = build_case(request_id, areas, sample_requests)
    assert analysis.units.status == "AVAILABLE"
    assert analysis.units.units == 0
    assert analysis.units.zero_reason == "NON_POSITIVE_RELATIVE_RESULT"
    assert analysis.coverage.biomass == 1.0
    assert analysis.coverage.uncertainty == 1.0
    assert analysis.coverage.baseline == 1.0
    assert math.isfinite(analysis.interval.e_proj_tco2e)
