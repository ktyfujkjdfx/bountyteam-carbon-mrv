"""The baseline projection to 2029: marked, separate, and unable to touch Q."""
from __future__ import annotations

import pytest

from carbon import BaselinePart, project_baseline, reasons
from carbon.baseline import baseline_stock, load_baseline_table
from carbon.parameters import DEFAULT_PARAMETERS
from carbon.projection import FORMULA, OBSERVED, SCENARIO_PROJECTION, SOURCE, STOCK_UNIT
from carbon.tests.conftest import ALL_REQUESTS, build_case


@pytest.fixture(scope="module")
def table():
    return load_baseline_table()


@pytest.fixture(scope="module")
def projection(table):
    return project_baseline(
        [BaselinePart("RU_MORDOVIA_03", 1000.0)],
        observed={2019: 60000.0, 2024: 40000.0},
        table=table,
    )


def test_the_projection_reaches_the_official_scenario_horizon(projection):
    assert projection.status == reasons.AVAILABLE
    assert projection.horizon_year == DEFAULT_PARAMETERS.scenario_end_year == 2029
    assert [point.year for point in projection.points] == list(range(2019, 2030))


def test_the_observed_years_stop_at_the_last_measured_one(projection):
    assert projection.last_observed_year == 2024
    assert [point.year for point in projection.observed] == list(range(2019, 2025))
    assert [point.year for point in projection.projected] == list(range(2025, 2030))
    assert {point.kind for point in projection.observed} == {OBSERVED}
    assert {point.kind for point in projection.projected} == {SCENARIO_PROJECTION}


def test_a_projected_year_carries_no_observed_value(projection):
    """A year nobody measured must be empty, not filled in with the assumption."""
    for point in projection.projected:
        assert point.observed_tc is None
        assert point.observed_tc_ha is None


def test_the_projection_follows_the_official_formula(projection, table):
    reference = table["RU_MORDOVIA_03"][0]
    for point in projection.points:
        expected = baseline_stock(
            reference_2019_tc_ha=reference.reference_mean_2019_tc_ha,
            rate_tc_ha_yr=reference.historical_rate_tc_ha_yr,
            year=point.year,
        )
        assert point.baseline_tc_ha == pytest.approx(expected, rel=1e-12)
        assert point.baseline_tc == pytest.approx(expected * 1000.0, rel=1e-12)


def test_the_result_states_its_value_unit_source_and_formula(projection):
    assert projection.stock_unit == STOCK_UNIT == "t C"
    assert projection.stock_unit_per_ha == "t C/ha"
    assert projection.source == SOURCE == "data/methodology/baseline.csv"
    assert "c̄_2019" in FORMULA and "max(0" in FORMULA
    assert projection.formula == FORMULA
    assert projection.method_version


def test_the_projection_is_labelled_as_a_methodological_scenario(projection):
    codes = {item.code for item in projection.notes}
    assert "BASELINE_PROJECTION" in codes
    text = next(item.text for item in projection.notes if item.code == "BASELINE_PROJECTION")
    assert "не прогноз будущей биомассы" in text
    assert "не прогноз рынка" in text
    assert "не влияет на Q" in text


def test_a_declining_trajectory_is_clamped_and_said_to_be_clamped(table):
    steep = project_baseline(
        [BaselinePart("RU_MORDOVIA_03", 1000.0)], horizon_year=2060, table=table
    )
    assert steep.status == reasons.AVAILABLE
    assert steep.points[-1].baseline_tc_ha == 0.0
    assert any(point.clipped_at_zero for point in steep.points)
    assert "PROJECTION_CLIPPED" in {item.code for item in steep.notes}


def test_a_growing_trajectory_keeps_growing_to_the_horizon(table):
    growing = project_baseline([BaselinePart("RU_TVER_01", 1000.0)], table=table)
    values = [point.baseline_tc_ha for point in growing.points]
    assert values == sorted(values)
    assert "PROJECTION_CLIPPED" not in {item.code for item in growing.notes}


def test_parts_of_several_areas_are_summed(table):
    combined = project_baseline(
        [BaselinePart("RU_TVER_01", 600.0), BaselinePart("RU_MORDOVIA_03", 400.0)],
        table=table,
    )
    assert combined.area_ha == pytest.approx(1000.0)
    separate = [
        project_baseline([BaselinePart("RU_TVER_01", 600.0)], table=table),
        project_baseline([BaselinePart("RU_MORDOVIA_03", 400.0)], table=table),
    ]
    for index, point in enumerate(combined.points):
        assert point.baseline_tc == pytest.approx(
            separate[0].points[index].baseline_tc + separate[1].points[index].baseline_tc
        )


@pytest.mark.parametrize(
    "parts, expected",
    [
        ([], reasons.MISSING_INPUT),
        ([BaselinePart("RU_TVER_01", 0.0)], reasons.NON_POSITIVE_AREA),
        ([BaselinePart("RU_UNKNOWN_09", 100.0)], reasons.BASELINE_UNKNOWN_AREA),
    ],
)
def test_an_unusable_request_gives_a_reason_not_a_line(parts, expected, table):
    result = project_baseline(parts, table=table)
    assert result.status == reasons.UNAVAILABLE
    assert result.unavailable_reason == expected
    assert result.points == ()


# -- the separation from Q -----------------------------------------------------------------


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_a_projected_value_never_reaches_the_units_of_the_period(request_id, areas, sample_requests):
    """Q is computed from the two dates of the request; the horizon cannot enter it."""
    request, inputs, analysis, _ = build_case(request_id, areas, sample_requests)
    projected = project_baseline(list(request.parts), table=load_baseline_table())
    assert projected.status == reasons.AVAILABLE
    assert projected.horizon_year == 2029
    assert analysis.request.year_end <= 2024
    # the units of the period use only E_base of that period
    assert analysis.units.e_base_tco2e == analysis.baseline.e_base_tco2e
    assert analysis.units.units == 0
    beyond = {point.baseline_tc for point in projected.points if point.year > request.year_end}
    assert analysis.units.e_base_tco2e not in beyond


def test_the_engine_exposes_the_projection_only_as_its_own_result():
    """Nothing in the unit calculation imports the projection."""
    import ast
    from pathlib import Path

    for name in ("units.py", "analysis.py", "baseline.py", "interval.py", "claim.py"):
        source = (Path(__file__).resolve().parents[1] / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "projection", name
            if isinstance(node, ast.Import):
                assert all("projection" not in alias.name for alias in node.names), name


def test_the_projection_is_deterministic(table):
    first = project_baseline([BaselinePart("RU_VOLOGDA_02", 500.0)], table=table)
    second = project_baseline([BaselinePart("RU_VOLOGDA_02", 500.0)], table=table)
    assert first == second
