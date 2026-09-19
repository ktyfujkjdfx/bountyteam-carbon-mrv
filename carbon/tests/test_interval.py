"""Stock difference and the scenario interval: dependence assumptions and sensitivity."""
from __future__ import annotations

import math

import pytest

from carbon import CellObservations, compute_interval, notes, reasons
from carbon.interval import FULL_SPATIAL_CORRELATION, INDEPENDENT_NATIVE_CELLS, INTERVAL_KIND

CF = 0.47
CO2_PER_C = 44 / 12


def uniform_cells(*, count: int, area_ha: float, sd: float, delta: float = 0.0):
    return CellObservations.from_sequences(
        area_ha=[area_ha] * count,
        agb_start=[100.0] * count,
        agb_end=[100.0 + delta] * count,
        sd_start=[sd] * count,
        sd_end=[sd] * count,
    )


def test_stock_difference_follows_the_statement():
    cells = uniform_cells(count=4, area_ha=25.0, sd=1.0, delta=4.0)
    result = compute_interval(cells, year_start=2019, year_end=2021)
    assert result.status == reasons.AVAILABLE
    assert result.area_ha == pytest.approx(100.0)
    assert result.stock_start_tc == pytest.approx(100.0 * 100.0 * CF)
    assert result.stock_end_tc == pytest.approx(100.0 * 104.0 * CF)
    assert result.delta_stock_tc == pytest.approx(188.0, abs=1e-9)
    assert result.e_proj_tco2e == pytest.approx(-188.0 * CO2_PER_C, abs=1e-9)
    assert result.e_per_ha_year_tco2e == pytest.approx(result.e_proj_tco2e / (100.0 * 2))
    assert result.interval_kind == INTERVAL_KIND
    assert notes.SCENARIO_INTERVAL in {item.code for item in result.notes}


def test_temporal_correlation_of_one_cancels_equal_standard_deviations():
    cells = uniform_cells(count=3, area_ha=10.0, sd=2.5)
    independent_time = compute_interval(cells, year_start=2019, year_end=2024, temporal_correlation=0.0)
    dependent_time = compute_interval(cells, year_start=2019, year_end=2024, temporal_correlation=1.0)
    assert independent_time.sd_tco2e > 0.0
    assert dependent_time.sd_tco2e == pytest.approx(0.0, abs=1e-12)
    assert dependent_time.lower_tco2e == pytest.approx(dependent_time.e_proj_tco2e)


def test_spatial_dependence_scales_the_interval_by_sqrt_n():
    count, area, sd = 16, 5.0, 3.0
    cells = uniform_cells(count=count, area_ha=area, sd=sd)
    result = compute_interval(cells, year_start=2019, year_end=2024)
    cell_weight = area * CF * CO2_PER_C
    cell_sd = sd * math.sqrt(2.0)  # rho_t = 0
    assert result.sd_tco2e == pytest.approx(math.sqrt(count) * cell_weight * cell_sd)

    variants = {variant.label: variant for variant in result.sensitivity}
    independent = variants[f"{INDEPENDENT_NATIVE_CELLS}_RHO_0"]
    dependent = variants[f"{FULL_SPATIAL_CORRELATION}_RHO_0"]
    assert dependent.sd_tco2e == pytest.approx(count * cell_weight * cell_sd)
    assert dependent.sd_tco2e / independent.sd_tco2e == pytest.approx(math.sqrt(count))


def test_mandatory_sensitivity_grid_is_always_present():
    cells = uniform_cells(count=5, area_ha=20.0, sd=1.5)
    result = compute_interval(cells, year_start=2019, year_end=2024)
    labels = [variant.label for variant in result.sensitivity]
    assert labels == [
        f"{INDEPENDENT_NATIVE_CELLS}_RHO_0",
        f"{INDEPENDENT_NATIVE_CELLS}_RHO_1",
        f"{FULL_SPATIAL_CORRELATION}_RHO_0",
        f"{FULL_SPATIAL_CORRELATION}_RHO_1",
    ]
    for variant in result.sensitivity:
        assert variant.half_width_tco2e >= 0.0
        assert variant.lower_tco2e <= result.e_proj_tco2e <= variant.upper_tco2e
    independent = next(v for v in result.sensitivity if v.label == f"{INDEPENDENT_NATIVE_CELLS}_RHO_0")
    dependent = next(v for v in result.sensitivity if v.label == f"{FULL_SPATIAL_CORRELATION}_RHO_0")
    assert dependent.sd_tco2e >= independent.sd_tco2e


def test_main_mode_is_independent_native_cells_and_is_recorded():
    cells = uniform_cells(count=4, area_ha=10.0, sd=2.0)
    result = compute_interval(cells, year_start=2019, year_end=2024, temporal_correlation=0.25)
    assert result.assumptions["spatial_dependence"] == INDEPENDENT_NATIVE_CELLS
    assert result.assumptions["temporal_correlation"] == 0.25
    assert result.assumptions["coverage_factor"] == 1.0
    assert result.assumptions["empirically_calibrated"] is False
    assert result.assumptions["grid"] == "native CCI cells"


def test_fully_dependent_main_mode_can_be_requested_for_sensitivity():
    cells = uniform_cells(count=9, area_ha=11.0, sd=1.0)
    independent = compute_interval(cells, year_start=2019, year_end=2024)
    dependent = compute_interval(
        cells, year_start=2019, year_end=2024, spatial_dependence=FULL_SPATIAL_CORRELATION
    )
    assert dependent.sd_tco2e > independent.sd_tco2e
    assert dependent.assumptions["spatial_dependence"] == FULL_SPATIAL_CORRELATION


def test_errors_are_weighted_by_area_not_divided_by_sqrt_n():
    one_cell = uniform_cells(count=1, area_ha=100.0, sd=2.0)
    many_cells = uniform_cells(count=100, area_ha=1.0, sd=2.0)
    single = compute_interval(one_cell, year_start=2019, year_end=2024)
    split = compute_interval(many_cells, year_start=2019, year_end=2024)
    assert single.area_ha == pytest.approx(split.area_ha)
    assert split.sd_tco2e == pytest.approx(single.sd_tco2e / math.sqrt(100))
    dependent = compute_interval(
        many_cells, year_start=2019, year_end=2024, spatial_dependence=FULL_SPATIAL_CORRELATION
    )
    assert dependent.sd_tco2e == pytest.approx(single.sd_tco2e)


def test_coverage_factor_widens_the_scenario_interval():
    cells = uniform_cells(count=4, area_ha=10.0, sd=1.0)
    narrow = compute_interval(cells, year_start=2019, year_end=2024, coverage_factor=1.0)
    wide = compute_interval(cells, year_start=2019, year_end=2024, coverage_factor=2.0)
    assert wide.upper_tco2e - wide.e_proj_tco2e == pytest.approx(
        2.0 * (narrow.upper_tco2e - narrow.e_proj_tco2e)
    )


@pytest.mark.parametrize(
    "broken, expected",
    [
        ({"agb_end": [float("nan"), 1.0]}, reasons.NON_FINITE_INPUT),
        ({"sd_start": [float("inf"), 1.0]}, reasons.NON_FINITE_INPUT),
        ({"sd_end": [-1.0, 1.0]}, reasons.INVALID_UNCERTAINTY_INPUT),
        ({"area_ha": [0.0, 0.0]}, reasons.NON_POSITIVE_AREA),
        ({"area_ha": [-5.0, 5.0]}, reasons.NON_POSITIVE_AREA),
    ],
)
def test_unusable_cells_make_the_result_unavailable(broken, expected):
    payload = dict(
        area_ha=[10.0, 10.0], agb_start=[100.0, 90.0], agb_end=[95.0, 85.0],
        sd_start=[1.0, 1.0], sd_end=[1.0, 1.0],
    )
    payload.update(broken)
    result = compute_interval(
        CellObservations.from_sequences(**payload), year_start=2019, year_end=2024
    )
    assert result.status == reasons.UNAVAILABLE
    assert result.unavailable_reason == expected
    assert result.e_proj_tco2e is None
    assert result.sensitivity == ()


@pytest.mark.parametrize("years", [(2024, 2019), (2021, 2021)])
def test_period_must_be_positive(years):
    cells = uniform_cells(count=2, area_ha=10.0, sd=1.0)
    result = compute_interval(cells, year_start=years[0], year_end=years[1])
    assert result.status == reasons.UNAVAILABLE
    assert result.unavailable_reason == reasons.NON_POSITIVE_PERIOD


def test_nan_is_never_silently_replaced_by_zero():
    cells = CellObservations.from_sequences(
        area_ha=[10.0, 10.0], agb_start=[100.0, float("nan")], agb_end=[100.0, 100.0],
        sd_start=[1.0, 1.0], sd_end=[1.0, 1.0],
    )
    result = compute_interval(cells, year_start=2019, year_end=2024)
    assert result.status == reasons.UNAVAILABLE
    assert result.stock_start_tc is None


@pytest.mark.parametrize("correlation", [-1.5, 1.5, float("nan")])
def test_temporal_correlation_outside_the_valid_range_is_a_contract_error(correlation):
    cells = uniform_cells(count=2, area_ha=10.0, sd=1.0)
    with pytest.raises(ValueError):
        compute_interval(cells, year_start=2019, year_end=2024, temporal_correlation=correlation)


def test_cell_payload_shape_is_validated():
    with pytest.raises(ValueError):
        CellObservations.from_sequences(
            area_ha=[1.0, 2.0], agb_start=[1.0], agb_end=[1.0], sd_start=[1.0], sd_end=[1.0]
        )
    with pytest.raises(ValueError):
        CellObservations.from_sequences(
            area_ha=[], agb_start=[], agb_end=[], sd_start=[], sd_end=[]
        )


def test_replay_is_deterministic():
    cells = uniform_cells(count=7, area_ha=13.0, sd=2.0, delta=-3.0)
    first = compute_interval(cells, year_start=2019, year_end=2024, temporal_correlation=0.3)
    second = compute_interval(cells, year_start=2019, year_end=2024, temporal_correlation=0.3)
    assert first == second
