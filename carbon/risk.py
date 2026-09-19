"""Due-diligence risks, stated for interpretation and never deducted a second time.

Four risks are reported: fire, loss of tree cover, data quality and the uncertainty of the
calculation. Each carries its level or `UNKNOWN`, what it rests on, where that came from,
the period it speaks about, what it changes for a reader, whether it already moved Q, and
what it cannot tell.

Two rules decide the whole design.

First, a risk is never multiplied into the result. `Q × (1 − p_risk)` looks rigorous and is
not: the case gives no probability for any of these risks, so the factor would be invented,
and the buffer and the uncertainty deduction have already taken their share of the same
result. Every risk here reports `affects_units = False`, except the uncertainty of the
calculation, which reports `already_applied = True` — it moved Q once, through UNC, and
must not move it again.

Second, absent evidence is `UNKNOWN`, not `LOW`. A fire that nobody observed is not a fire
that did not happen, and the difference matters more than a tidy dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import reasons

# Risks this role knows how to describe.
FIRE = "FIRE"
TREE_COVER_LOSS = "TREE_COVER_LOSS"
DATA_QUALITY = "DATA_QUALITY"
CALCULATION_UNCERTAINTY = "CALCULATION_UNCERTAINTY"
RISK_KINDS = (FIRE, TREE_COVER_LOSS, DATA_QUALITY, CALCULATION_UNCERTAINTY)

# Levels. UNKNOWN is a real answer and the default one.
UNKNOWN = "UNKNOWN"
LOW = "LOW"
MODERATE = "MODERATE"
HIGH = "HIGH"
LEVELS = (UNKNOWN, LOW, MODERATE, HIGH)

NO_EVIDENCE = "Наблюдений, на которых можно было бы основать оценку, не предоставлено."


@dataclass(frozen=True)
class Risk:
    kind: str
    level: str
    basis: str
    source: str | None
    period: tuple[int, int] | None
    interpretation: str
    limitations: str
    affects_units: bool = False
    already_applied: bool = False

    def __post_init__(self) -> None:
        if self.kind not in RISK_KINDS:
            raise ValueError(f"risk kind must be one of {RISK_KINDS}")
        if self.level not in LEVELS:
            raise ValueError(f"risk level must be one of {LEVELS}")
        if self.affects_units and not self.already_applied:
            raise ValueError(
                "a risk may only be marked as affecting the units when the deduction has "
                "already been applied by the rules of the case"
            )


@dataclass(frozen=True)
class RiskReport:
    risks: tuple[Risk, ...] = ()
    note: str = (
        "Риски описывают интерпретацию результата. Они не умножаются на число единиц: "
        "официальной методики вероятностного вычета кейс не задаёт, а вычет за "
        "неопределённость и резерв уже применены."
    )
    fields: tuple[str, ...] = field(default=(
        "kind", "level", "basis", "source", "period", "interpretation",
        "limitations", "affects_units", "already_applied",
    ))

    def by_kind(self, kind: str) -> Risk | None:
        return next((risk for risk in self.risks if risk.kind == kind), None)

    @property
    def deducted_twice(self) -> tuple[Risk, ...]:
        """Risks that would double-count. It must always be empty."""
        return tuple(
            risk for risk in self.risks if risk.affects_units and not risk.already_applied
        )


def _level_from_fraction(fraction: float | None, *, low: float, high: float) -> str:
    if fraction is None:
        return UNKNOWN
    if fraction >= high:
        return HIGH
    if fraction >= low:
        return MODERATE
    return LOW


def assess_risks(
    *,
    period: tuple[int, int] | None = None,
    fire_evidence: dict[str, object] | None = None,
    cover_loss_fraction: float | None = None,
    optical_paired_fraction: float | None = None,
    uncertainty_share: float | None = None,
    units_status: str = reasons.AVAILABLE,
) -> RiskReport:
    """Describe the four risks from what was actually measured upstream.

    Every input is optional, and a missing one produces `UNKNOWN` with the reason stated.
    Nothing here changes Q; the uncertainty entry only reports the deduction Q already
    carries, so that a reader does not apply it twice.
    """
    risks: list[Risk] = []

    observed_fire = None if fire_evidence is None else fire_evidence.get("detected")
    risks.append(Risk(
        kind=FIRE,
        level=UNKNOWN if observed_fire is None else (HIGH if observed_fire else LOW),
        basis=NO_EVIDENCE if fire_evidence is None else str(
            fire_evidence.get("basis", "наблюдения поставщика растровых данных")
        ),
        source=None if fire_evidence is None else str(fire_evidence.get("source", "")) or None,
        period=period,
        interpretation=(
            "Пожар объясняет потерю запаса, но сам по себе не меняет число единиц: "
            "потеря уже учтена в изменении запаса."
        ),
        limitations=(
            "Отсутствие наблюдённого пожара не означает, что пожара не было. "
            "Причина изменения устанавливается отдельно от факта изменения."
        ),
    ))

    risks.append(Risk(
        kind=TREE_COVER_LOSS,
        level=_level_from_fraction(cover_loss_fraction, low=0.02, high=0.10),
        basis=NO_EVIDENCE if cover_loss_fraction is None else (
            f"доля площади с потерей древесного покрова: {cover_loss_fraction:.4f}"
        ),
        source=None if cover_loss_fraction is None else "GFC (по данным поставщика)",
        period=period,
        interpretation=(
            "Потеря покрова показывает, где изменился участок. Она не вычитается "
            "повторно: то же изменение уже отражено в запасе биомассы."
        ),
        limitations=(
            "Потеря древесного покрова и потеря запаса углерода — разные величины, "
            "измеренные разными продуктами."
        ),
    ))

    # An optical gap is an evidence problem, not a reason to reduce a modelled stock.
    risks.append(Risk(
        kind=DATA_QUALITY,
        level=UNKNOWN if optical_paired_fraction is None else _level_from_fraction(
            1.0 - optical_paired_fraction, low=0.3, high=0.6
        ),
        basis=NO_EVIDENCE if optical_paired_fraction is None else (
            f"доля площади с парой пригодных оптических наблюдений: "
            f"{optical_paired_fraction:.4f}"
        ),
        source=None if optical_paired_fraction is None else "Sentinel-2 L2A, маска SCL",
        period=period,
        interpretation=(
            "Низкое оптическое качество ослабляет наглядность свидетельств и не "
            "уменьшает число единиц: облачность снимка не меняет модельную оценку запаса."
        ),
        limitations=(
            "Оптическое покрытие не является покрытием биомассы и не заменяет его."
        ),
    ))

    if units_status != reasons.AVAILABLE or uncertainty_share is None:
        uncertainty_level, basis, applied = UNKNOWN, NO_EVIDENCE, False
    else:
        uncertainty_level = _level_from_fraction(uncertainty_share, low=0.05, high=0.3)
        basis = f"вычет за неопределённость UNC: {uncertainty_share:.6f}"
        applied = True
    risks.append(Risk(
        kind=CALCULATION_UNCERTAINTY,
        level=uncertainty_level,
        basis=basis,
        source="carbon/units.py, правило кейса UNC = min(1, max(0, H/R − 0.10))",
        period=period,
        interpretation=(
            "Неопределённость расчёта уже уменьшила результат по правилу кейса. "
            "Повторный вычет по этому риску был бы двойным счётом."
        ),
        limitations=(
            "Интервал сценарный: вероятностное покрытие не заявляется, поэтому уровень "
            "риска здесь — описание величины вычета, а не вероятность."
        ),
        affects_units=applied,
        already_applied=applied,
    ))

    return RiskReport(risks=tuple(risks))
