"""The research grid over the official data: what the assumptions decide, and what they don't."""
from __future__ import annotations

import math

import pytest

from carbon import reasons, research_rows, research_table
from carbon.research import (
    BASELINE_FLAT_RESEARCH,
    BASELINE_OFFICIAL,
    DEFAULT_ASSUMPTIONS,
    decided_by_assumptions,
)
from carbon.tests.conftest import ALL_REQUESTS, OFFICIAL_AOIS, build_case


@pytest.fixture(scope="module")
def table(areas, sample_requests):
    cases = []
    for request_id in ALL_REQUESTS:
        request, inputs, _, _ = build_case(request_id, areas, sample_requests)
        cases.append((request, inputs.cells))
    return research_table(cases)


def official(rows, request_id=None):
    return [
        row for row in rows
        if row.baseline_variant == BASELINE_OFFICIAL
        and (request_id is None or row.request_id == request_id)
    ]


def test_the_grid_covers_every_request_baseline_and_assumption(table):
    assert len(table) == len(ALL_REQUESTS) * 2 * len(DEFAULT_ASSUMPTIONS)
    assert {row.request_id for row in table} == set(ALL_REQUESTS)
    assert {row.baseline_variant for row in table} == {BASELINE_OFFICIAL, BASELINE_FLAT_RESEARCH}


def test_on_the_supplied_data_no_official_request_earns_a_unit(table):
    """Reported plainly: against the official baseline every supplied area gives Q = 0."""
    rows = official(table)
    assert {row.units for row in rows} == {0}
    assert {row.status for row in rows} == {reasons.AVAILABLE}
    assert {row.zero_reason for row in rows} == {reasons.NON_POSITIVE_RELATIVE_RESULT}
    assert all(row.r_tco2e is not None and row.r_tco2e <= 0.0 for row in rows)


def test_a_zero_from_a_rule_is_not_an_unavailable_result(table):
    for row in official(table):
        assert row.unavailable_reason is None
        assert row.units == 0
        assert row.value_base_price_rub == 0.0


def test_the_official_answer_does_not_move_across_the_assumption_grid(table):
    """R ≤ 0 is decided before the interval matters, so the grid cannot change it."""
    assert decided_by_assumptions(table, baseline_variant=BASELINE_OFFICIAL) == ()


def test_the_research_baseline_is_where_an_assumption_decides_the_answer(table):
    """The control site is the case that must be reported, not quietly resolved."""
    decided = decided_by_assumptions(table, baseline_variant=BASELINE_FLAT_RESEARCH)
    assert decided == ("RU_TVER_01",)
    tver = [
        row for row in table
        if row.request_id == "RU_TVER_01" and row.baseline_variant == BASELINE_FLAT_RESEARCH
    ]
    answers = {(row.spatial_dependence, row.temporal_correlation): row.units for row in tver}
    assert answers[("INDEPENDENT_CELLS", 0.0)] == 0
    assert answers[("INDEPENDENT_CELLS", 1.0)] > 0
    assert answers[("FULLY_DEPENDENT_CELLS", 0.0)] == 0
    assert answers[("FULLY_DEPENDENT_CELLS", 1.0)] == 0


def test_the_research_baseline_never_produces_a_reported_result(table):
    for row in table:
        assert row.is_research_only == (row.baseline_variant != BASELINE_OFFICIAL)
    flat = [row for row in table if row.baseline_variant == BASELINE_FLAT_RESEARCH]
    assert all(row.e_base_tco2e == 0.0 for row in flat)
    # the official rows keep the official baseline whatever the research rows show
    assert all(row.e_base_tco2e != 0.0 for row in official(table))


def test_full_spatial_dependence_widens_the_interval_by_the_square_root_of_the_cell_count(table):
    for request_id in ALL_REQUESTS:
        rows = {
            (row.spatial_dependence, row.temporal_correlation): row
            for row in official(table, request_id)
        }
        independent = rows[("INDEPENDENT_CELLS", 0.0)]
        dependent = rows[("FULLY_DEPENDENT_CELLS", 0.0)]
        assert dependent.sd_tco2e > independent.sd_tco2e
        # equal-sized cells with similar deviations give roughly sqrt(N)
        assert 1.0 < dependent.sd_tco2e / independent.sd_tco2e < math.sqrt(3400)


def test_perfect_temporal_correlation_narrows_the_interval(table):
    """var(Δb) = s0² + s1² − 2ρ s0 s1 collapses towards (s0 − s1)² as ρ → 1."""
    for request_id in ALL_REQUESTS:
        rows = {
            (row.spatial_dependence, row.temporal_correlation): row
            for row in official(table, request_id)
        }
        assert rows[("INDEPENDENT_CELLS", 1.0)].sd_tco2e < rows[("INDEPENDENT_CELLS", 0.0)].sd_tco2e


def test_the_estimate_itself_is_untouched_by_the_interval_assumptions(table):
    """Assumptions move the interval, never the stock difference."""
    for request_id in ALL_REQUESTS:
        estimates = {row.e_proj_tco2e for row in table if row.request_id == request_id}
        assert len(estimates) == 1


def test_a_disturbed_area_loses_more_carbon_than_the_control_area(table):
    """Mordovia burned, Tver did not; the sign of E has to show it."""
    estimate = {
        row.request_id: row.e_proj_tco2e for row in official(table)
    }
    assert estimate["RU_TVER_01"] < 0.0, "the control site accumulated stock"
    for disturbed in ("RU_VOLOGDA_02", "RU_MORDOVIA_03", "RU_MORDOVIA_04"):
        assert estimate[disturbed] > 0.0, f"{disturbed} lost stock"
    assert estimate["RU_MORDOVIA_03"] > estimate["RU_MORDOVIA_04"] > estimate["RU_VOLOGDA_02"]


def test_a_declining_baseline_does_not_by_itself_create_a_result(table):
    """Mordovia-03 has the steepest declining baseline and still earns nothing."""
    mordovia = official(table, "RU_MORDOVIA_03")[0]
    assert mordovia.e_base_tco2e > 0.0, "a declining baseline emits, so E_base is positive"
    assert mordovia.r_tco2e < 0.0
    assert mordovia.units == 0


def test_the_subpolygon_is_consistent_with_its_parent_area(table, areas, sample_requests):
    child = official(table, "CHECK_TRANSFER_01")[0]
    parent = official(table, "RU_VOLOGDA_02")[0]
    ratio = float(sample_requests["CHECK_TRANSFER_01"]["properties"]["area_ha"]) / float(
        areas["RU_VOLOGDA_02"]["area_ha"]
    )
    assert 0.0 < ratio < 1.0
    # the child covers a different period, so only the sign and the order of magnitude
    # are comparable; both must still point the same way
    assert child.e_proj_tco2e > 0.0 and parent.e_proj_tco2e > 0.0
    assert child.units == parent.units == 0


def test_the_grid_is_reproducible(areas, sample_requests):
    request, inputs, _, _ = build_case("RU_MORDOVIA_04", areas, sample_requests)
    first = research_rows(request, inputs.cells)
    second = research_rows(request, inputs.cells)
    assert first == second


def test_an_unknown_baseline_variant_is_refused(areas, sample_requests):
    request, inputs, _, _ = build_case("RU_TVER_01", areas, sample_requests)
    with pytest.raises(ValueError, match="unknown baseline variant"):
        research_rows(request, inputs.cells, baseline_variants=("MADE_UP",))


@pytest.mark.parametrize("request_id", OFFICIAL_AOIS)
def test_every_official_area_is_present_with_both_baselines(table, request_id):
    variants = {row.baseline_variant for row in table if row.request_id == request_id}
    assert variants == {BASELINE_OFFICIAL, BASELINE_FLAT_RESEARCH}
