"""Units of the case: official vectors, rule boundaries, Q = null vs Q = 0, rounding."""
from __future__ import annotations

import math

import pytest

from carbon import (
    BaselinePart,
    BaselineRow,
    CellObservations,
    Coverage,
    compute_baseline,
    compute_interval,
    compute_units,
    notes,
    reasons,
)
from carbon.units import UNIT_SHARE

CO2_PER_C = 44 / 12


def units_for(*, r: float, h: float, **overrides):
    """Vector with a chosen R and H: Eproj = 0, so R = Ebase and H = max(−L, U)."""
    arguments = dict(
        e_proj_tco2e=0.0,
        e_base_tco2e=r,
        lower_tco2e=-h,
        upper_tco2e=h,
        area_ha=100.0,
        year_start=2019,
        year_end=2020,
    )
    arguments.update(overrides)
    return compute_units(**arguments)


def test_official_example_gives_395_units():
    """Постановка задачи, с. 6: R=517, H=103.4, UNC=0.10, Radj=465.3, B=69.795, Q=395."""
    e_proj = -188.0 * CO2_PER_C
    result = compute_units(
        e_proj_tco2e=e_proj,
        e_base_tco2e=-47.0 * CO2_PER_C,
        lower_tco2e=e_proj - 103.4,
        upper_tco2e=e_proj + 103.4,
        area_ha=100.0,
        year_start=2019,
        year_end=2020,
    )
    assert result.status == reasons.AVAILABLE
    assert result.e_proj_tco2e == pytest.approx(-689.333333, abs=1e-6)
    assert result.e_base_tco2e == pytest.approx(-172.333333, abs=1e-6)
    assert result.r_tco2e == pytest.approx(517.0, abs=1e-9)
    assert result.h_tco2e == pytest.approx(103.4, abs=1e-12)
    assert result.ratio == pytest.approx(0.20, abs=1e-12)
    assert result.uncertainty_share == pytest.approx(0.10, abs=1e-12)
    assert result.r_adj_tco2e == pytest.approx(465.3, abs=1e-9)
    assert result.buffer_tco2e == pytest.approx(69.795, abs=1e-9)
    assert result.units == 395
    assert result.rounding_residual_tco2e == pytest.approx(0.505, abs=1e-9)
    assert result.zero_reason is None


def test_official_example_through_interval_and_baseline():
    """The same vector assembled from per-cell data and a baseline table."""
    cell_sd = 0.6 / math.sqrt(2.0)  # one cell, rho_t = 0 -> sd(Δb) = 0.6 t/ha
    cells = CellObservations.from_sequences(
        area_ha=[100.0], agb_start=[100.0], agb_end=[104.0],
        sd_start=[cell_sd], sd_end=[cell_sd],
    )
    interval = compute_interval(cells, year_start=2019, year_end=2020)
    assert interval.mean_start_tc_ha == pytest.approx(47.0)
    assert interval.mean_end_tc_ha == pytest.approx(48.88)
    assert interval.delta_stock_tc == pytest.approx(188.0, abs=1e-9)
    assert interval.e_proj_tco2e == pytest.approx(-689.333333, abs=1e-6)
    assert interval.e_per_ha_year_tco2e == pytest.approx(-6.893333, abs=1e-6)
    assert interval.upper_tco2e - interval.e_proj_tco2e == pytest.approx(103.4, abs=1e-9)

    table = {
        "UNIT_TEST_VECTOR": (
            BaselineRow(
                baseline_id="UNIT_TEST_VECTOR", aoi_id="UNIT_TEST_VECTOR",
                year_start=2019, year_end=2020, pool="AGB",
                reference_mean_2015_tc_ha=45.12, reference_mean_2019_tc_ha=47.0,
                historical_rate_tc_ha_yr=0.47,
                stock_start_tc_ha=47.0, stock_end_tc_ha=47.47, delta_tc_ha=0.47,
                clipped_at_zero=False,
            ),
        )
    }
    baseline = compute_baseline(
        [BaselinePart(aoi_id="UNIT_TEST_VECTOR", area_ha=100.0)],
        year_start=2019, year_end=2020, table=table,
    )
    assert baseline.e_base_tco2e == pytest.approx(-172.333333, abs=1e-6)

    result = compute_units(
        e_proj_tco2e=interval.e_proj_tco2e,
        e_base_tco2e=baseline.e_base_tco2e,
        lower_tco2e=interval.lower_tco2e,
        upper_tco2e=interval.upper_tco2e,
        area_ha=interval.area_ha,
        year_start=2019,
        year_end=2020,
        coverage=Coverage(biomass=1.0, baseline=1.0),
    )
    assert result.units == 395


def test_second_official_vector_gives_5525_units():
    """R=7000, H=1200 -> UNC=1/14, Radj=6500, Q=5525."""
    result = units_for(r=7000.0, h=1200.0)
    assert result.ratio == pytest.approx(1200 / 7000, abs=1e-15)
    assert result.uncertainty_share == pytest.approx(0.07142857142857, abs=1e-12)
    assert result.r_adj_tco2e == pytest.approx(6500.0, abs=1e-9)
    assert result.units == 5525


def test_allowance_boundary_at_ratio_010_deducts_nothing():
    result = units_for(r=1000.0, h=100.0)
    assert result.ratio == pytest.approx(0.10, abs=1e-15)
    assert result.uncertainty_share == 0.0
    assert result.r_adj_tco2e == pytest.approx(1000.0, abs=1e-12)
    assert result.units == 850
    assert result.buffer_tco2e == pytest.approx(150.0, abs=1e-12)
    assert result.rounding_residual_tco2e == pytest.approx(0.0, abs=1e-12)


def test_just_above_the_allowance_starts_deducting():
    result = units_for(r=1000.0, h=100.1)
    assert result.uncertainty_share > 0.0
    assert result.units == 849


def test_stop_rule_at_ratio_one_gives_zero_units_without_an_unc_of_09():
    result = units_for(r=1000.0, h=1000.0)
    assert result.status == reasons.AVAILABLE
    assert result.units == 0
    assert result.zero_reason == reasons.UNCERTAINTY_TOO_HIGH
    assert result.ratio == pytest.approx(1.0, abs=1e-15)
    assert result.uncertainty_share is None
    assert result.r_adj_tco2e is None
    assert result.buffer_tco2e is None
    assert notes.STOP_RULE_APPLIED in {item.code for item in result.notes}


def test_stop_rule_is_a_cliff_not_a_slope():
    below = units_for(r=1000.0, h=999.0)
    above = units_for(r=1000.0, h=1000.0 + 1e-9)
    assert below.units == 85
    assert above.units == 0
    assert above.zero_reason == reasons.UNCERTAINTY_TOO_HIGH


@pytest.mark.parametrize("relative", [-1000.0, 0.0])
def test_non_positive_relative_result_gives_zero_units_and_no_ratio(relative):
    result = units_for(r=relative, h=10.0)
    assert result.status == reasons.AVAILABLE
    assert result.units == 0
    assert result.zero_reason == reasons.NON_POSITIVE_RELATIVE_RESULT
    assert result.ratio is None
    assert result.r_adj_tco2e is None


def test_result_below_one_unit_is_zero_with_its_own_reason():
    result = units_for(r=1.0, h=0.0)
    assert result.units == 0
    assert result.zero_reason == reasons.ROUNDED_TO_ZERO
    assert result.r_adj_tco2e == pytest.approx(1.0)
    assert notes.ROUNDED_BELOW_ONE_UNIT in {item.code for item in result.notes}


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"e_proj_tco2e": None}, reasons.MISSING_INPUT),
        ({"e_base_tco2e": None}, reasons.MISSING_INPUT),
        ({"lower_tco2e": None}, reasons.MISSING_INPUT),
        ({"area_ha": None}, reasons.MISSING_INPUT),
        ({"e_proj_tco2e": float("nan")}, reasons.NON_FINITE_INPUT),
        ({"e_base_tco2e": float("inf")}, reasons.NON_FINITE_INPUT),
        ({"upper_tco2e": float("nan")}, reasons.NON_FINITE_INPUT),
        ({"area_ha": 0.0}, reasons.NON_POSITIVE_AREA),
        ({"area_ha": -1.0}, reasons.NON_POSITIVE_AREA),
        ({"year_end": 2019}, reasons.NON_POSITIVE_PERIOD),
        ({"year_end": 2018}, reasons.NON_POSITIVE_PERIOD),
        ({"lower_tco2e": 10.0, "upper_tco2e": 20.0}, reasons.INVALID_INTERVAL),
        ({"coverage": Coverage(biomass=0.8, baseline=1.0)}, reasons.INCOMPLETE_COVERAGE),
        ({"coverage": Coverage(biomass=1.0, baseline=0.999)}, reasons.INCOMPLETE_COVERAGE),
    ],
)
def test_missing_or_unusable_input_gives_null_units_not_zero(overrides, expected):
    result = units_for(r=1000.0, h=100.0, **overrides)
    assert result.status == reasons.UNAVAILABLE
    assert result.unavailable_reason == expected
    assert result.units is None
    assert result.zero_reason is None
    assert result.scenario_values == ()


def test_zero_units_and_null_units_are_distinguishable():
    zero = units_for(r=-5.0, h=1.0)
    null = units_for(r=1000.0, h=100.0, e_base_tco2e=None)
    assert (zero.status, zero.units, zero.zero_reason) == (
        reasons.AVAILABLE, 0, reasons.NON_POSITIVE_RELATIVE_RESULT,
    )
    assert (null.status, null.units, null.unavailable_reason) == (
        reasons.UNAVAILABLE, None, reasons.MISSING_INPUT,
    )
    assert zero.unavailable_reason is None
    assert null.zero_reason is None


def test_full_coverage_is_accepted():
    result = units_for(r=1000.0, h=100.0, coverage=Coverage(biomass=1.0, baseline=1.0))
    assert result.status == reasons.AVAILABLE
    assert result.units == 850


def test_coverage_outside_the_unit_interval_is_a_contract_error():
    with pytest.raises(ValueError):
        units_for(r=1000.0, h=100.0, coverage=Coverage(biomass=1.2, baseline=1.0))


def test_floor_order_follows_the_statement():
    """Q = floor(Radj × 0.85); floor(Radj − B) disagrees on about 4.6% of boundary values."""
    r_adj = 31 / 0.85  # 36.470588235294116
    result = units_for(r=r_adj, h=0.0)
    assert result.uncertainty_share == 0.0
    assert result.r_adj_tco2e == r_adj
    assert result.units == math.floor(r_adj * UNIT_SHARE) == 30
    assert math.floor(r_adj * (1 - 0.15)) == 30  # (1 - 0.15) is the same double as 0.85
    assert math.floor(r_adj - r_adj * 0.15) == 31  # the subtraction order is the trap


def test_floor_order_disagreement_is_systematic():
    disagreements = sum(
        1 for n in range(1, 20001)
        if math.floor((n / 0.85) * UNIT_SHARE) != math.floor((n / 0.85) - (n / 0.85) * 0.15)
    )
    assert disagreements > 500
    for n in range(1, 2001):
        r_adj = n / 0.85
        assert units_for(r=r_adj, h=0.0).units == math.floor(r_adj * UNIT_SHARE)


@pytest.mark.parametrize("relative", [1.0, 36.470588235294116, 517.0, 1000.0, 7000.0, 123456.789])
@pytest.mark.parametrize("ratio", [0.0, 0.1, 0.35, 0.9])
def test_waterfall_residual_closes_the_balance(relative, ratio):
    result = units_for(r=relative, h=relative * ratio)
    assert result.status == reasons.AVAILABLE
    residual = result.rounding_residual_tco2e
    assert 0.0 <= residual <= 1.0
    assert result.r_adj_tco2e == pytest.approx(
        result.buffer_tco2e + result.units + residual, rel=1e-12
    )
    assert result.uncertainty_deduction_tco2e == pytest.approx(
        result.r_tco2e - result.r_adj_tco2e, rel=1e-12, abs=1e-12
    )


def test_rounding_residual_reaches_a_whole_unit_where_the_floor_orders_disagree():
    """A consequence of the statement order: the residual bar can be a full unit, not a fraction."""
    result = units_for(r=31 / 0.85, h=0.0)
    assert result.rounding_residual_tco2e == 1.0
    assert result.units == 30
    worst = max(
        units_for(r=n / 0.85, h=0.0).rounding_residual_tco2e for n in range(1, 2001)
    )
    assert worst == 1.0


def test_declining_baseline_carries_a_methodological_warning():
    """RU_MORDOVIA_03 scale: the area loses carbon and still beats a falling baseline."""
    result = compute_units(
        e_proj_tco2e=5000.0,
        e_base_tco2e=45485.418,
        lower_tco2e=4000.0,
        upper_tco2e=6000.0,
        area_ha=1000.0,
        year_start=2019,
        year_end=2024,
    )
    codes = {item.code for item in result.notes}
    assert result.units > 0
    assert notes.RESULT_FROM_DECLINING_BASELINE in codes
    assert notes.CASE_UNITS in codes


def test_growing_baseline_has_no_declining_baseline_warning():
    result = units_for(r=1000.0, h=100.0, e_base_tco2e=1000.0, e_proj_tco2e=0.0)
    assert notes.RESULT_FROM_DECLINING_BASELINE not in {item.code for item in result.notes}


def test_scenario_values_use_case_prices():
    result = units_for(r=1000.0, h=100.0)
    assert [value.price_rub for value in result.scenario_values] == [500.0, 1500.0, 4000.0]
    assert [value.value_rub for value in result.scenario_values] == [
        850 * 500.0, 850 * 1500.0, 850 * 4000.0,
    ]


def test_results_are_deterministic():
    first = units_for(r=517.0, h=103.4)
    second = units_for(r=517.0, h=103.4)
    assert first == second
