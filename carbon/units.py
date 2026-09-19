"""Potential units of the case: R, H, UNC, Radj, B, Q and the scenario value.

Formulas (Постановка задачи, с. 6):

    R = Ebase − Eproj − LK;  H = max(Eproj − L, U − Eproj)
    R ≤ 0                    → Q = 0, H/R is not computed
    R > 0 and H/R ≥ 1        → Q = 0 (stop rule)
    otherwise:
        UNC = min(1, max(0, H/R − 0.10));  Radj = R × (1 − UNC)
        Q = floor(Radj × 0.85);  B = Radj × 0.15;  V = Q × p

Q uses the literal factor 0.85 of the statement. In IEEE 754 the factor (1 − 0.15) is
the same double as 0.85, but the subtraction Radj − Radj × 0.15 is not: it lands one unit
higher for about 4.6% of the values next to an integer. Because Q follows the statement
and B keeps its own 0.15 share, the rounding residual Radj − B − Q covers [0, 1] and
reaches exactly 1 on those values.

Missing or unusable mandatory input gives Q = null (status UNAVAILABLE), never zero;
valid input under a rule of the case gives Q = 0 with a zero reason.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import notes, reasons
from .parameters import DEFAULT_PARAMETERS, METHOD_VERSION, CaseParameters

# Literal factor of the statement, kept separate from the 0.15 buffer share on purpose.
UNIT_SHARE = 0.85

# Completeness is decided in hectares upstream, where the geodesic areas live, and the
# share that arrives here is already clamped. Geodesic area is not additive over a
# partition, so a share can miss 1.0 by a few ulp on arithmetic alone; demanding an exact
# 1.0 here would turn seventh-digit rounding into "incomplete coverage".
COVERAGE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Coverage:
    """Shares of the requested area covered by the mandatory numeric inputs.

    `uncertainty` is the share whose AGB_SD is present on both dates. It is tracked apart
    from `biomass` because a source may ship the estimate and its deviation separately,
    and a missing deviation must not silently become zero uncertainty — that would narrow
    the interval and raise Q. `None` means the caller did not report it at all, which is
    itself recorded rather than assumed complete.
    """

    biomass: float
    baseline: float
    uncertainty: float | None = None


@dataclass(frozen=True)
class ScenarioValue:
    price_rub: float
    value_rub: float


@dataclass(frozen=True)
class UnitsResult:
    status: str
    unavailable_reason: str | None = None
    zero_reason: str | None = None
    e_proj_tco2e: float | None = None
    e_base_tco2e: float | None = None
    leakage_tco2e: float | None = None
    lower_tco2e: float | None = None
    upper_tco2e: float | None = None
    h_tco2e: float | None = None
    r_tco2e: float | None = None
    ratio: float | None = None
    uncertainty_share: float | None = None
    uncertainty_deduction_tco2e: float | None = None
    r_adj_tco2e: float | None = None
    buffer_tco2e: float | None = None
    units: int | None = None
    rounding_residual_tco2e: float | None = None
    scenario_values: tuple[ScenarioValue, ...] = ()
    method_version: str = METHOD_VERSION
    notes: tuple[notes.Note, ...] = ()


def _unavailable(reason: str, extra: tuple[notes.Note, ...] = ()) -> UnitsResult:
    return UnitsResult(status=reasons.UNAVAILABLE, unavailable_reason=reason, notes=extra)


def compute_units(
    *,
    e_proj_tco2e: float | None,
    e_base_tco2e: float | None,
    lower_tco2e: float | None,
    upper_tco2e: float | None,
    area_ha: float | None,
    year_start: int | None,
    year_end: int | None,
    coverage: Coverage | None = None,
    parameters: CaseParameters = DEFAULT_PARAMETERS,
) -> UnitsResult:
    """Potential units for one request; returns Q = null or Q = 0 instead of raising."""
    mandatory = (e_proj_tco2e, e_base_tco2e, lower_tco2e, upper_tco2e, area_ha, year_start, year_end)
    if any(value is None for value in mandatory):
        return _unavailable(reasons.MISSING_INPUT)
    if not all(math.isfinite(float(value)) for value in mandatory):
        return _unavailable(reasons.NON_FINITE_INPUT)
    if float(area_ha) <= 0.0:
        return _unavailable(reasons.NON_POSITIVE_AREA)
    if int(year_end) <= int(year_start):
        return _unavailable(reasons.NON_POSITIVE_PERIOD)

    extra_notes: tuple[notes.Note, ...] = ()
    if coverage is not None:
        shares = [coverage.biomass, coverage.baseline]
        if coverage.uncertainty is None:
            # Not reported is not the same as complete, and it is not silently treated as
            # either: the result carries the gap so a reader can see what was not checked.
            extra_notes = (notes.note(notes.UNCERTAINTY_COVERAGE_NOT_REPORTED),)
        else:
            shares.append(coverage.uncertainty)
        if any(not math.isfinite(share) or not 0.0 <= share <= 1.0 for share in shares):
            raise ValueError("coverage shares must be finite values in [0, 1]")
        if any(share < 1.0 - COVERAGE_TOLERANCE for share in shares):
            return _unavailable(
                reasons.INCOMPLETE_COVERAGE,
                (notes.note(notes.COVERAGE_INCOMPLETE), *extra_notes),
            )

    estimate = float(e_proj_tco2e)
    lower = float(lower_tco2e)
    upper = float(upper_tco2e)
    if not lower <= estimate <= upper:
        return _unavailable(reasons.INVALID_INTERVAL)

    half_width = max(estimate - lower, upper - estimate)
    leakage = parameters.leakage_tco2e
    relative = float(e_base_tco2e) - estimate - leakage
    common = dict(
        e_proj_tco2e=estimate,
        e_base_tco2e=float(e_base_tco2e),
        leakage_tco2e=leakage,
        lower_tco2e=lower,
        upper_tco2e=upper,
        h_tco2e=half_width,
        r_tco2e=relative,
    )

    if relative <= 0.0:
        return UnitsResult(
            status=reasons.AVAILABLE,
            zero_reason=reasons.NON_POSITIVE_RELATIVE_RESULT,
            units=0,
            scenario_values=_scenario_values(0, parameters),
            notes=(notes.note(notes.NON_POSITIVE_RESULT), notes.note(notes.CASE_UNITS),
                   *extra_notes),
            **common,
        )

    ratio = half_width / relative
    if ratio >= parameters.unc_stop_ratio:
        return UnitsResult(
            status=reasons.AVAILABLE,
            zero_reason=reasons.UNCERTAINTY_TOO_HIGH,
            ratio=ratio,
            units=0,
            scenario_values=_scenario_values(0, parameters),
            notes=(
                notes.note(notes.STOP_RULE_APPLIED, stop_ratio=parameters.unc_stop_ratio),
                notes.note(notes.CASE_UNITS),
                *extra_notes,
            ),
            **common,
        )

    uncertainty_share = min(1.0, max(0.0, ratio - parameters.unc_allowance))
    adjusted = relative * (1.0 - uncertainty_share)
    units = math.floor(adjusted * UNIT_SHARE)
    buffer = adjusted * parameters.buffer_share
    collected = [notes.note(notes.CASE_UNITS), notes.note(notes.SCENARIO_PRICES), *extra_notes]
    if units == 0:
        collected.insert(0, notes.note(notes.ROUNDED_BELOW_ONE_UNIT))
    if float(e_base_tco2e) > 0.0 and estimate > 0.0:
        collected.insert(0, notes.note(notes.RESULT_FROM_DECLINING_BASELINE))

    return UnitsResult(
        status=reasons.AVAILABLE,
        zero_reason=reasons.ROUNDED_TO_ZERO if units == 0 else None,
        ratio=ratio,
        uncertainty_share=uncertainty_share,
        uncertainty_deduction_tco2e=relative - adjusted,
        r_adj_tco2e=adjusted,
        buffer_tco2e=buffer,
        units=units,
        rounding_residual_tco2e=adjusted - buffer - units,
        scenario_values=_scenario_values(units, parameters),
        notes=tuple(collected),
        **common,
    )


def _scenario_values(units: int, parameters: CaseParameters) -> tuple[ScenarioValue, ...]:
    return tuple(
        ScenarioValue(price_rub=price, value_rub=units * price) for price in parameters.prices_rub
    )
