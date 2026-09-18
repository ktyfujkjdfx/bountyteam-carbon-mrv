"""Comparison of a stated volume with the calculated units.

    gap_units = max(claimed_units − Q, 0)
    supported_share = min(Q / claimed_units, 1)      only for claimed_units > 0
    gap_value_p = gap_units × p

A claim is an input label (USER_INPUT or DEMO_INPUT), never a calculated result, and it
never changes the stock, the interval, the baseline or Q. The arithmetic status sits next
to, and does not replace, the evidence status of the analysis.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import notes, reasons
from .parameters import DEFAULT_PARAMETERS, CaseParameters


@dataclass(frozen=True)
class AnalysisContext:
    """What the calculation actually covered."""

    geometry_hash: str
    year_start: int
    year_end: int
    pool: str
    unit: str


@dataclass(frozen=True)
class ClaimInput:
    claimed_units: float | None
    source: str
    geometry_hash: str
    year_start: int
    year_end: int
    pool: str
    unit: str


@dataclass(frozen=True)
class ClaimGapValue:
    price_rub: float
    value_rub: float


@dataclass(frozen=True)
class ClaimResult:
    status: str
    mismatch_reasons: tuple[str, ...] = ()
    claimed_units: float | None = None
    source: str | None = None
    units: int | None = None
    gap_units: float | None = None
    supported_share: float | None = None
    gap_values: tuple[ClaimGapValue, ...] = ()
    notes: tuple[notes.Note, ...] = ()


def compare_claim(
    claim: ClaimInput | None,
    *,
    analysis: AnalysisContext,
    units: int | None,
    parameters: CaseParameters = DEFAULT_PARAMETERS,
) -> ClaimResult:
    """Compare a stated volume with Q; comparability is checked before Q."""
    if claim is None:
        return ClaimResult(status=reasons.CLAIM_NOT_PROVIDED)
    if claim.source not in reasons.CLAIM_SOURCES:
        raise ValueError(f"claim source must be one of {sorted(reasons.CLAIM_SOURCES)}")

    label = notes.note(notes.CLAIM_INPUT_LABEL)
    mismatches: list[str] = []
    value = claim.claimed_units
    if value is None or not math.isfinite(float(value)) or float(value) < 0.0:
        mismatches.append(reasons.INVALID_CLAIM_VALUE)
    if claim.geometry_hash != analysis.geometry_hash:
        mismatches.append(reasons.GEOMETRY_MISMATCH)
    if (claim.year_start, claim.year_end) != (analysis.year_start, analysis.year_end):
        mismatches.append(reasons.PERIOD_MISMATCH)
    if claim.pool != analysis.pool:
        mismatches.append(reasons.POOL_MISMATCH)
    if claim.unit != analysis.unit:
        mismatches.append(reasons.UNIT_MISMATCH)
    if mismatches:
        return ClaimResult(
            status=reasons.CLAIM_NOT_COMPARABLE,
            mismatch_reasons=tuple(mismatches),
            claimed_units=value if value is None or math.isfinite(float(value)) else None,
            source=claim.source,
            units=units,
            notes=(label,),
        )

    claimed = float(value)
    if units is None:
        return ClaimResult(
            status=reasons.CLAIM_UNASSESSABLE,
            claimed_units=claimed,
            source=claim.source,
            notes=(label,),
        )

    gap = max(claimed - units, 0.0)
    collected = [label, notes.note(notes.CLAIM_GAP_SCENARIO)]
    if claimed == 0.0:
        share = None
        status = reasons.CLAIM_SUPPORTED
        collected.append(notes.note(notes.CLAIM_ZERO))
    else:
        share = min(units / claimed, 1.0)
        if units >= claimed:
            status = reasons.CLAIM_SUPPORTED
        elif units > 0:
            status = reasons.CLAIM_PARTIALLY_SUPPORTED
        else:
            status = reasons.CLAIM_NOT_SUPPORTED

    return ClaimResult(
        status=status,
        claimed_units=claimed,
        source=claim.source,
        units=units,
        gap_units=gap,
        supported_share=share,
        gap_values=tuple(
            ClaimGapValue(price_rub=price, value_rub=gap * price) for price in parameters.prices_rub
        ),
        notes=tuple(collected),
    )
