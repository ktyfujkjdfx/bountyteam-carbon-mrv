"""Claim comparison: comparability first, then arithmetic against Q."""
from __future__ import annotations

import pytest

from carbon import AnalysisContext, ClaimInput, compare_claim, notes, reasons

ANALYSIS = AnalysisContext(
    geometry_hash="0xabc", year_start=2019, year_end=2024, pool="AGB", unit="tCO2e"
)


def claim(**overrides) -> ClaimInput:
    payload = dict(
        claimed_units=1000.0,
        source=reasons.CLAIM_SOURCE_USER,
        geometry_hash="0xabc",
        year_start=2019,
        year_end=2024,
        pool="AGB",
        unit="tCO2e",
    )
    payload.update(overrides)
    return ClaimInput(**payload)


def test_absent_claim_is_not_provided():
    result = compare_claim(None, analysis=ANALYSIS, units=500)
    assert result.status == reasons.CLAIM_NOT_PROVIDED
    assert result.gap_units is None
    assert result.supported_share is None
    assert result.gap_values == ()


def test_claim_at_or_below_q_is_supported():
    result = compare_claim(claim(claimed_units=400.0), analysis=ANALYSIS, units=500)
    assert result.status == reasons.CLAIM_SUPPORTED
    assert result.gap_units == 0.0
    assert result.supported_share == 1.0
    assert [value.value_rub for value in result.gap_values] == [0.0, 0.0, 0.0]


def test_equal_claim_is_supported():
    result = compare_claim(claim(claimed_units=500.0), analysis=ANALYSIS, units=500)
    assert result.status == reasons.CLAIM_SUPPORTED
    assert result.supported_share == 1.0


def test_claim_above_q_is_partially_supported_and_priced_as_a_scenario():
    result = compare_claim(claim(claimed_units=1000.0), analysis=ANALYSIS, units=400)
    assert result.status == reasons.CLAIM_PARTIALLY_SUPPORTED
    assert result.gap_units == 600.0
    assert result.supported_share == pytest.approx(0.4)
    assert [value.price_rub for value in result.gap_values] == [500.0, 1500.0, 4000.0]
    assert [value.value_rub for value in result.gap_values] == [
        600 * 500.0, 600 * 1500.0, 600 * 4000.0,
    ]
    codes = {item.code for item in result.notes}
    assert notes.CLAIM_INPUT_LABEL in codes
    assert notes.CLAIM_GAP_SCENARIO in codes


def test_zero_q_against_a_positive_claim_is_not_supported():
    result = compare_claim(claim(claimed_units=250.0), analysis=ANALYSIS, units=0)
    assert result.status == reasons.CLAIM_NOT_SUPPORTED
    assert result.gap_units == 250.0
    assert result.supported_share == 0.0


def test_zero_claim_has_no_supported_share():
    result = compare_claim(claim(claimed_units=0.0), analysis=ANALYSIS, units=10)
    assert result.status == reasons.CLAIM_SUPPORTED
    assert result.gap_units == 0.0
    assert result.supported_share is None
    assert notes.CLAIM_ZERO in {item.code for item in result.notes}


def test_null_q_makes_the_claim_unassessable():
    result = compare_claim(claim(), analysis=ANALYSIS, units=None)
    assert result.status == reasons.CLAIM_UNASSESSABLE
    assert result.gap_units is None
    assert result.supported_share is None
    assert result.gap_values == ()


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf"), None])
def test_unusable_claim_values_are_not_comparable(value):
    result = compare_claim(claim(claimed_units=value), analysis=ANALYSIS, units=500)
    assert result.status == reasons.CLAIM_NOT_COMPARABLE
    assert reasons.INVALID_CLAIM_VALUE in result.mismatch_reasons
    assert result.gap_units is None


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"geometry_hash": "0xother"}, reasons.GEOMETRY_MISMATCH),
        ({"year_start": 2020}, reasons.PERIOD_MISMATCH),
        ({"year_end": 2023}, reasons.PERIOD_MISMATCH),
        ({"pool": "AGB+BGB"}, reasons.POOL_MISMATCH),
        ({"unit": "tC"}, reasons.UNIT_MISMATCH),
    ],
)
def test_mismatched_claims_are_not_comparable(overrides, expected):
    result = compare_claim(claim(**overrides), analysis=ANALYSIS, units=500)
    assert result.status == reasons.CLAIM_NOT_COMPARABLE
    assert expected in result.mismatch_reasons
    assert result.gap_units is None
    assert result.supported_share is None


def test_comparability_is_checked_before_q():
    result = compare_claim(claim(pool="SOIL"), analysis=ANALYSIS, units=None)
    assert result.status == reasons.CLAIM_NOT_COMPARABLE


def test_demo_source_is_accepted_and_labelled():
    result = compare_claim(
        claim(source=reasons.CLAIM_SOURCE_DEMO), analysis=ANALYSIS, units=1200
    )
    assert result.source == reasons.CLAIM_SOURCE_DEMO
    assert notes.CLAIM_INPUT_LABEL in {item.code for item in result.notes}


def test_unknown_claim_source_is_a_contract_error():
    with pytest.raises(ValueError):
        compare_claim(claim(source="REGISTRY"), analysis=ANALYSIS, units=10)


def test_claim_never_changes_the_calculated_units():
    low = compare_claim(claim(claimed_units=1.0), analysis=ANALYSIS, units=500)
    high = compare_claim(claim(claimed_units=10_000.0), analysis=ANALYSIS, units=500)
    assert low.units == high.units == 500
