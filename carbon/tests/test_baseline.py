"""Baseline of the case: official table, the max(0, ...) clamp, parts and sub-polygons."""
from __future__ import annotations

import json

import pytest

from carbon import (
    BaselinePart,
    BaselineRow,
    baseline_stock,
    compute_baseline,
    load_baseline_table,
    notes,
    reasons,
)
from carbon.baseline import REFERENCE_YEAR
from carbon.parameters import REPO_ROOT

CO2_PER_C = 44 / 12
AOIS = ("RU_TVER_01", "RU_VOLOGDA_02", "RU_MORDOVIA_03", "RU_MORDOVIA_04")


@pytest.fixture(scope="module")
def table():
    return load_baseline_table()


def test_official_table_covers_every_area_for_2019_2029(table):
    assert set(table) == set(AOIS)
    for aoi in AOIS:
        rows = table[aoi]
        assert [row.year_start for row in rows] == list(range(2019, 2029))
        assert [row.year_end for row in rows] == list(range(2020, 2030))
        assert {row.pool for row in rows} == {"AGB"}


def test_official_table_matches_the_statement_formula(table):
    """g = (c̄2019 − c̄2015)/4 and c_base,y = max(0, c̄2019 + g × (y − 2019))."""
    for aoi in AOIS:
        for row in table[aoi]:
            rate = (row.reference_mean_2019_tc_ha - row.reference_mean_2015_tc_ha) / 4
            assert rate == pytest.approx(row.historical_rate_tc_ha_yr, abs=1e-8)
            for year, tabulated in (
                (row.year_start, row.stock_start_tc_ha),
                (row.year_end, row.stock_end_tc_ha),
            ):
                expected = baseline_stock(
                    reference_2019_tc_ha=row.reference_mean_2019_tc_ha,
                    rate_tc_ha_yr=rate,
                    year=year,
                )
                assert expected == pytest.approx(tabulated, abs=1e-8)
            assert row.delta_tc_ha == pytest.approx(
                row.stock_end_tc_ha - row.stock_start_tc_ha, abs=1e-8
            )
            assert row.clipped_at_zero is False


def test_clamp_is_applied_to_a_declining_trajectory():
    assert baseline_stock(reference_2019_tc_ha=10.0, rate_tc_ha_yr=-5.0, year=2024) == 0.0
    assert baseline_stock(reference_2019_tc_ha=10.0, rate_tc_ha_yr=-5.0, year=2020) == 5.0
    assert baseline_stock(reference_2019_tc_ha=10.0, rate_tc_ha_yr=-2.0, year=REFERENCE_YEAR) == 10.0


def test_tabulated_stock_below_zero_is_clamped_and_flagged():
    steep = {
        "UNIT_TEST_VECTOR": (
            BaselineRow(
                baseline_id="UNIT_TEST_VECTOR", aoi_id="UNIT_TEST_VECTOR",
                year_start=2019, year_end=2020, pool="AGB",
                reference_mean_2015_tc_ha=30.0, reference_mean_2019_tc_ha=10.0,
                historical_rate_tc_ha_yr=-5.0,
                stock_start_tc_ha=10.0, stock_end_tc_ha=5.0, delta_tc_ha=-5.0,
                clipped_at_zero=False,
            ),
            BaselineRow(
                baseline_id="UNIT_TEST_VECTOR", aoi_id="UNIT_TEST_VECTOR",
                year_start=2020, year_end=2021, pool="AGB",
                reference_mean_2015_tc_ha=30.0, reference_mean_2019_tc_ha=10.0,
                historical_rate_tc_ha_yr=-5.0,
                stock_start_tc_ha=5.0, stock_end_tc_ha=-1.0, delta_tc_ha=-5.0,
                clipped_at_zero=False,
            ),
        )
    }
    result = compute_baseline(
        [BaselinePart(aoi_id="UNIT_TEST_VECTOR", area_ha=100.0)],
        year_start=2019, year_end=2021, table=steep,
    )
    assert result.status == reasons.AVAILABLE
    part = result.parts[0]
    assert part.stock_end_tc_ha == 0.0
    assert part.clipped_at_zero is True
    assert part.delta_tc_ha == pytest.approx(-10.0)


def test_declining_baseline_is_reported_with_a_warning(table):
    result = compute_baseline(
        [BaselinePart(aoi_id="RU_MORDOVIA_03", area_ha=1000.0)],
        year_start=2019, year_end=2024, table=table,
    )
    assert result.delta_tc_ha == pytest.approx(-12.405113869, abs=1e-8)
    assert result.e_base_tco2e == pytest.approx(45485.41751966, abs=1e-6)
    assert result.e_base_tco2e > 0.0
    assert notes.BASELINE_DECLINING in {item.code for item in result.notes}
    assert notes.BASELINE_FIXED in {item.code for item in result.notes}


def test_growing_baseline_has_no_decline_warning(table):
    result = compute_baseline(
        [BaselinePart(aoi_id="RU_TVER_01", area_ha=1000.0)],
        year_start=2019, year_end=2024, table=table,
    )
    assert result.delta_tc_ha == pytest.approx(1.718748896, abs=1e-8)
    assert result.e_base_tco2e == pytest.approx(-6302.07928533, abs=1e-6)
    assert notes.BASELINE_DECLINING not in {item.code for item in result.notes}


def test_subpolygon_uses_the_parent_trajectory_and_its_own_area(table):
    """CHECK_TRANSFER_01: 808.85 ha inside RU_VOLOGDA_02, 2020–2024."""
    request = json.loads(
        (REPO_ROOT / "data" / "sample_requests.geojson").read_text(encoding="utf-8")
    )["features"][0]["properties"]
    area_ha = request["area_ha"]
    assert (request["request_id"], request["parent_aoi_id"]) == (
        "CHECK_TRANSFER_01", "RU_VOLOGDA_02",
    )

    result = compute_baseline(
        [BaselinePart(aoi_id=request["parent_aoi_id"], area_ha=area_ha)],
        year_start=request["year_start"], year_end=request["year_end"], table=table,
    )
    reference = table["RU_VOLOGDA_02"][0]
    expected_start = baseline_stock(
        reference_2019_tc_ha=reference.reference_mean_2019_tc_ha,
        rate_tc_ha_yr=reference.historical_rate_tc_ha_yr,
        year=request["year_start"],
    )
    expected_end = baseline_stock(
        reference_2019_tc_ha=reference.reference_mean_2019_tc_ha,
        rate_tc_ha_yr=reference.historical_rate_tc_ha_yr,
        year=request["year_end"],
    )
    part = result.parts[0]
    assert part.stock_start_tc_ha == pytest.approx(expected_start, abs=1e-8)
    assert part.stock_end_tc_ha == pytest.approx(expected_end, abs=1e-8)
    # the table path and the formula path agree to the 9 decimals stored in the CSV
    assert part.delta_tc == pytest.approx(area_ha * (expected_end - expected_start), rel=1e-8)
    assert result.e_base_tco2e == pytest.approx(
        -area_ha * (expected_end - expected_start) * CO2_PER_C, rel=1e-8
    )
    assert result.area_ha == pytest.approx(area_ha)


def test_parts_of_several_areas_are_summed(table):
    parts = [
        BaselinePart(aoi_id="RU_TVER_01", area_ha=600.0),
        BaselinePart(aoi_id="RU_MORDOVIA_03", area_ha=400.0),
    ]
    result = compute_baseline(parts, year_start=2019, year_end=2024, table=table)
    assert len(result.parts) == 2
    assert result.area_ha == pytest.approx(1000.0)
    expected_delta = sum(part.delta_tc for part in result.parts)
    assert result.delta_tc == pytest.approx(expected_delta)
    assert result.e_base_tco2e == pytest.approx(-expected_delta * CO2_PER_C)
    assert result.delta_tc_ha == pytest.approx(expected_delta / 1000.0)


@pytest.mark.parametrize(
    "parts, years, expected",
    [
        ([], (2019, 2024), reasons.MISSING_INPUT),
        ([BaselinePart("RU_TVER_01", 100.0)], (2024, 2019), reasons.NON_POSITIVE_PERIOD),
        ([BaselinePart("RU_TVER_01", 100.0)], (2021, 2021), reasons.NON_POSITIVE_PERIOD),
        ([BaselinePart("RU_TVER_01", 0.0)], (2019, 2024), reasons.NON_POSITIVE_AREA),
        ([BaselinePart("RU_TVER_01", float("nan"))], (2019, 2024), reasons.NON_FINITE_INPUT),
        ([BaselinePart("RU_UNKNOWN_09", 100.0)], (2019, 2024), reasons.BASELINE_UNKNOWN_AREA),
        ([BaselinePart("RU_TVER_01", 100.0)], (2019, 2030), reasons.BASELINE_OUT_OF_COVERAGE),
        ([BaselinePart("RU_TVER_01", 100.0)], (2018, 2024), reasons.BASELINE_OUT_OF_COVERAGE),
    ],
)
def test_unusable_requests_make_the_baseline_unavailable(parts, years, expected, table):
    result = compute_baseline(parts, year_start=years[0], year_end=years[1], table=table)
    assert result.status == reasons.UNAVAILABLE
    assert result.unavailable_reason == expected
    assert result.e_base_tco2e is None
    assert result.parts == ()
