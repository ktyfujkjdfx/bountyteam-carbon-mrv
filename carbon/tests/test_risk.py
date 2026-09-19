"""Risks inform the reading of a result; they never take a second bite out of Q."""
from __future__ import annotations

import pytest

from carbon import reasons
from carbon.risk import (
    CALCULATION_UNCERTAINTY,
    DATA_QUALITY,
    FIRE,
    HIGH,
    LEVELS,
    LOW,
    MODERATE,
    RISK_KINDS,
    TREE_COVER_LOSS,
    UNKNOWN,
    Risk,
    RiskReport,
    assess_risks,
)
from carbon.tests.conftest import ALL_REQUESTS, build_case


@pytest.fixture(scope="module")
def measured():
    return assess_risks(
        period=(2019, 2024),
        fire_evidence={"detected": True, "basis": "гарь MODIS в пределах запроса",
                       "source": "MODIS MCD64A1"},
        cover_loss_fraction=0.18,
        optical_paired_fraction=0.35,
        uncertainty_share=0.12,
    )


def test_all_four_risks_are_always_present(measured):
    assert tuple(risk.kind for risk in measured.risks) == RISK_KINDS
    assert len(measured.risks) == 4


def test_every_risk_carries_the_full_contract(measured):
    for risk in measured.risks:
        assert risk.level in LEVELS
        assert risk.basis
        assert risk.interpretation
        assert risk.limitations
        assert risk.period == (2019, 2024)
        assert isinstance(risk.affects_units, bool)
    assert set(RiskReport().fields) >= {
        "kind", "level", "basis", "source", "period", "interpretation",
        "limitations", "affects_units", "already_applied",
    }


def test_no_risk_is_ever_deducted_twice(measured):
    """The invariant of the whole module."""
    assert measured.deducted_twice == ()
    for risk in measured.risks:
        if risk.affects_units:
            assert risk.already_applied, risk.kind


def test_only_the_calculation_uncertainty_touched_the_units(measured):
    assert measured.by_kind(CALCULATION_UNCERTAINTY).affects_units is True
    assert measured.by_kind(CALCULATION_UNCERTAINTY).already_applied is True
    for kind in (FIRE, TREE_COVER_LOSS, DATA_QUALITY):
        assert measured.by_kind(kind).affects_units is False


def test_the_uncertainty_entry_explains_that_it_already_applied(measured):
    risk = measured.by_kind(CALCULATION_UNCERTAINTY)
    assert "уже уменьшила результат" in risk.interpretation
    assert "двойным счётом" in risk.interpretation
    assert "не вероятность" in risk.limitations


def test_a_declared_risk_that_moves_q_without_having_applied_it_is_refused():
    with pytest.raises(ValueError, match="already been applied"):
        Risk(
            kind=FIRE, level=HIGH, basis="x", source=None, period=None,
            interpretation="x", limitations="x", affects_units=True,
        )


def test_the_report_states_that_risks_are_not_multiplied_into_the_units(measured):
    assert "не умножаются на число единиц" in RiskReport().note
    assert "двойн" in measured.by_kind(CALCULATION_UNCERTAINTY).interpretation


# -- absent evidence -----------------------------------------------------------------------


def test_nothing_measured_gives_unknown_not_low():
    """A fire nobody observed is not a fire that did not happen."""
    empty = assess_risks()
    assert {risk.level for risk in empty.risks} == {UNKNOWN}
    for risk in empty.risks:
        assert "не предоставлено" in risk.basis
        assert risk.source is None or risk.kind == CALCULATION_UNCERTAINTY
    assert empty.deducted_twice == ()


def test_an_unobserved_fire_is_unknown_and_an_observed_absence_is_low():
    assert assess_risks().by_kind(FIRE).level == UNKNOWN
    assert assess_risks(fire_evidence={"detected": False}).by_kind(FIRE).level == LOW
    assert assess_risks(fire_evidence={"detected": True}).by_kind(FIRE).level == HIGH


def test_the_fire_limitation_says_absence_is_not_proof():
    risk = assess_risks(fire_evidence={"detected": False}).by_kind(FIRE)
    assert "не означает, что пожара не было" in risk.limitations


@pytest.mark.parametrize(
    "fraction, expected", [(0.0, LOW), (0.01, LOW), (0.05, MODERATE), (0.5, HIGH)]
)
def test_cover_loss_levels_follow_the_measured_share(fraction, expected):
    assert assess_risks(cover_loss_fraction=fraction).by_kind(TREE_COVER_LOSS).level == expected


@pytest.mark.parametrize(
    "paired, expected", [(1.0, LOW), (0.9, LOW), (0.5, MODERATE), (0.1, HIGH)]
)
def test_data_quality_worsens_as_the_optical_pair_thins(paired, expected):
    assert assess_risks(optical_paired_fraction=paired).by_kind(DATA_QUALITY).level == expected


def test_poor_optical_quality_still_does_not_touch_the_units():
    risk = assess_risks(optical_paired_fraction=0.05).by_kind(DATA_QUALITY)
    assert risk.level == HIGH
    assert risk.affects_units is False
    assert "не уменьшает число единиц" in risk.interpretation


def test_an_unavailable_result_leaves_the_uncertainty_risk_unknown():
    report = assess_risks(uncertainty_share=0.4, units_status=reasons.UNAVAILABLE)
    risk = report.by_kind(CALCULATION_UNCERTAINTY)
    assert risk.level == UNKNOWN
    assert risk.affects_units is False


def test_the_stop_rule_case_has_no_uncertainty_share_to_report():
    """H/R >= 1 cuts the calculation off, so there is no UNC to describe."""
    report = assess_risks(uncertainty_share=None)
    assert report.by_kind(CALCULATION_UNCERTAINTY).level == UNKNOWN


# -- the module computes no probabilistic deduction -----------------------------------------


def test_the_module_never_multiplies_units_by_a_risk_factor():
    import ast
    from pathlib import Path

    tree = ast.parse(
        (Path(__file__).resolve().parents[1] / "risk.py").read_text(encoding="utf-8")
    )
    identifiers = {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for forbidden in ("probability", "p_risk", "units", "q"):
        assert forbidden not in identifiers, forbidden
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Mult)]


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_risks_never_change_the_answer_of_a_real_area(request_id, areas, sample_requests):
    _, _, analysis, _ = build_case(request_id, areas, sample_requests)
    before = analysis.units.units
    report = assess_risks(
        period=(analysis.request.year_start, analysis.request.year_end),
        fire_evidence={"detected": True},
        cover_loss_fraction=0.4,
        optical_paired_fraction=0.05,
        uncertainty_share=analysis.units.uncertainty_share,
        units_status=analysis.units.status,
    )
    assert report.deducted_twice == ()
    assert analysis.units.units == before == 0
