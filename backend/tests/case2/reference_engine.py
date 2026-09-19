"""Test double for the `carbon/` package, reachable only from this test directory.

`carbon/` is owned by Trust and is the engine of record. Nothing under `backend/app/`
imports this module or can reach it: the production carbon adapter loads `carbon` and
nothing else, and fails closed when it is absent. This file exists so that the API, the
jobs, the passports and the reports can be exercised before that package is merged, and
it is injected explicitly by `conftest.engine_override`. When `carbon/` lands, the
override stops firing and this file is deleted.

The formulas are the ones written in the statement (`doc/Постановка задачи`, pp. 4-6) and
the coefficients come from `data/methodology/*.csv`, never from a third-party repository:

    c_i,t = b_i,t x CF;  C_t = sum a_i c_i,t;  dC = C_t1 - C_t0;  E = -dC x 44/12
    var(db_i) = s0_i^2 + s1_i^2 - 2 rho s0_i s1_i
    independent cells: sd(E) = sqrt(sum (w_i sd_i)^2);  w_i = a_i x CF x 44/12
    L = E - k sd(E);  U = E + k sd(E);  H = max(E - L, U - E)
    Ebase = -sum_parts(area x baseline_delta_tc_ha) x 44/12
    R = Ebase - E - LK
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.v2 import catalog

METHOD_VERSION = "backend-reference-carbon/0.1.0"

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"

MISSING_INPUT = "MISSING_INPUT"
NON_FINITE_INPUT = "NON_FINITE_INPUT"
NON_POSITIVE_AREA = "NON_POSITIVE_AREA"
NON_POSITIVE_PERIOD = "NON_POSITIVE_PERIOD"
INVALID_UNCERTAINTY_INPUT = "INVALID_UNCERTAINTY_INPUT"
INVALID_INTERVAL = "INVALID_INTERVAL"
INCOMPLETE_COVERAGE = "INCOMPLETE_COVERAGE"
BASELINE_OUT_OF_COVERAGE = "BASELINE_OUT_OF_COVERAGE"
BASELINE_UNKNOWN_AREA = "BASELINE_UNKNOWN_AREA"

NON_POSITIVE_RELATIVE_RESULT = "NON_POSITIVE_RELATIVE_RESULT"
UNCERTAINTY_TOO_HIGH = "UNCERTAINTY_TOO_HIGH"
ROUNDED_TO_ZERO = "ROUNDED_TO_ZERO"

CLAIM_NOT_PROVIDED = "NOT_PROVIDED"
CLAIM_NOT_COMPARABLE = "NOT_COMPARABLE"
CLAIM_UNASSESSABLE = "UNASSESSABLE"
CLAIM_SUPPORTED = "SUPPORTED_BY_CASE"
CLAIM_PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED_BY_CASE"
CLAIM_NOT_SUPPORTED = "NOT_SUPPORTED_BY_CASE"

INVALID_CLAIM_VALUE = "INVALID_CLAIM_VALUE"
GEOMETRY_MISMATCH = "GEOMETRY_MISMATCH"
PERIOD_MISMATCH = "PERIOD_MISMATCH"
POOL_MISMATCH = "POOL_MISMATCH"
UNIT_MISMATCH = "UNIT_MISMATCH"

CLAIM_SOURCE_USER = "USER_INPUT"
CLAIM_SOURCE_DEMO = "DEMO_INPUT"
CLAIM_SOURCES = frozenset({CLAIM_SOURCE_USER, CLAIM_SOURCE_DEMO})

INDEPENDENT_CELLS = "INDEPENDENT_CELLS"
FULLY_DEPENDENT_CELLS = "FULLY_DEPENDENT_CELLS"
SPATIAL_MODES = (INDEPENDENT_CELLS, FULLY_DEPENDENT_CELLS)
SENSITIVITY_TEMPORAL_CORRELATIONS = (0.0, 1.0)
INTERVAL_KIND = "SCENARIO"
UNIT_SHARE = 0.85
COVERAGE_TOLERANCE = 1e-9
REFERENCE_YEAR = 2019


@dataclass(frozen=True)
class CaseParameters:
    cf_agb: float
    co2_per_c: float
    unc_allowance: float
    unc_stop_ratio: float
    buffer_share: float
    leakage_tco2e: float
    prices_rub: tuple[float, ...]


def load_parameters(root: Path = catalog.DATA_ROOT) -> CaseParameters:
    table = catalog.parameters(root)
    number = catalog.parse_number
    return CaseParameters(
        cf_agb=number(table["CF_AGB"]),
        co2_per_c=number(table["CO2_per_C"]),
        unc_allowance=number(table["UNC_allowance"]),
        unc_stop_ratio=number(table["UNC_stop_ratio"]),
        buffer_share=number(table["BUF"]),
        leakage_tco2e=number(table["LK"]),
        prices_rub=tuple(value for _name, value in catalog.prices(root)),
    )


DEFAULT_PARAMETERS = load_parameters()


# -- interval ------------------------------------------------------------------------------
@dataclass(frozen=True)
class CellObservations:
    area_ha: tuple[float, ...]
    agb_start: tuple[float, ...]
    agb_end: tuple[float, ...]
    sd_start: tuple[float, ...]
    sd_end: tuple[float, ...]

    @classmethod
    def from_sequences(cls, *, area_ha: Sequence[float], agb_start: Sequence[float],
                       agb_end: Sequence[float], sd_start: Sequence[float],
                       sd_end: Sequence[float]) -> "CellObservations":
        arrays = tuple(tuple(float(value) for value in values)
                       for values in (area_ha, agb_start, agb_end, sd_start, sd_end))
        if len({len(array) for array in arrays}) != 1:
            raise ValueError("per-cell inputs must have the same length")
        if not arrays[0]:
            raise ValueError("at least one cell is required")
        return cls(*arrays)

    @property
    def count(self) -> int:
        return len(self.area_ha)


@dataclass(frozen=True)
class IntervalVariant:
    label: str
    spatial_dependence: str
    temporal_correlation: float
    sd_tco2e: float
    lower_tco2e: float
    upper_tco2e: float
    half_width_tco2e: float


@dataclass(frozen=True)
class IntervalResult:
    status: str
    unavailable_reason: str | None = None
    area_ha: float | None = None
    cells: int | None = None
    stock_start_tc: float | None = None
    stock_end_tc: float | None = None
    mean_start_tc_ha: float | None = None
    mean_end_tc_ha: float | None = None
    delta_stock_tc: float | None = None
    e_proj_tco2e: float | None = None
    e_per_ha_year_tco2e: float | None = None
    sd_tco2e: float | None = None
    lower_tco2e: float | None = None
    upper_tco2e: float | None = None
    interval_kind: str = INTERVAL_KIND
    method_version: str = METHOD_VERSION
    assumptions: dict = field(default_factory=dict)
    sensitivity: tuple[IntervalVariant, ...] = ()


def _variant(*, spatial_dependence: str, temporal_correlation: float, weights: tuple[float, ...],
             sd_start: tuple[float, ...], sd_end: tuple[float, ...], estimate: float,
             coverage_factor: float) -> IntervalVariant:
    scaled = []
    for weight, s0, s1 in zip(weights, sd_start, sd_end):
        variance = s0 * s0 + s1 * s1 - 2.0 * temporal_correlation * s0 * s1
        scaled.append(weight * math.sqrt(max(variance, 0.0)))
    if spatial_dependence == INDEPENDENT_CELLS:
        total = math.sqrt(sum(value * value for value in scaled))
    else:
        total = sum(scaled)
    half = coverage_factor * total
    return IntervalVariant(
        label=f"{spatial_dependence}_RHO_{temporal_correlation:g}",
        spatial_dependence=spatial_dependence, temporal_correlation=float(temporal_correlation),
        sd_tco2e=total, lower_tco2e=estimate - half, upper_tco2e=estimate + half,
        half_width_tco2e=half)


def compute_interval(cells: CellObservations, *, year_start: int, year_end: int,
                     parameters: CaseParameters = DEFAULT_PARAMETERS,
                     temporal_correlation: float = 0.0, coverage_factor: float = 1.0,
                     spatial_dependence: str = INDEPENDENT_CELLS) -> IntervalResult:
    if year_end <= year_start:
        return IntervalResult(UNAVAILABLE, NON_POSITIVE_PERIOD)
    values = (*cells.area_ha, *cells.agb_start, *cells.agb_end, *cells.sd_start, *cells.sd_end)
    if not all(math.isfinite(value) for value in values):
        return IntervalResult(UNAVAILABLE, NON_FINITE_INPUT)
    if any(value < 0.0 for value in cells.area_ha) or sum(cells.area_ha) <= 0.0:
        return IntervalResult(UNAVAILABLE, NON_POSITIVE_AREA)
    if any(value < 0.0 for value in (*cells.sd_start, *cells.sd_end)):
        return IntervalResult(UNAVAILABLE, INVALID_UNCERTAINTY_INPUT)

    area_total = sum(cells.area_ha)
    span = year_end - year_start
    stock_start = sum(a * b * parameters.cf_agb for a, b in zip(cells.area_ha, cells.agb_start))
    stock_end = sum(a * b * parameters.cf_agb for a, b in zip(cells.area_ha, cells.agb_end))
    delta = stock_end - stock_start
    estimate = -delta * parameters.co2_per_c
    weights = tuple(a * parameters.cf_agb * parameters.co2_per_c for a in cells.area_ha)

    main = _variant(spatial_dependence=spatial_dependence,
                    temporal_correlation=temporal_correlation, weights=weights,
                    sd_start=cells.sd_start, sd_end=cells.sd_end, estimate=estimate,
                    coverage_factor=coverage_factor)
    grid = tuple(_variant(spatial_dependence=mode, temporal_correlation=rho, weights=weights,
                          sd_start=cells.sd_start, sd_end=cells.sd_end, estimate=estimate,
                          coverage_factor=coverage_factor)
                 for mode in SPATIAL_MODES for rho in SENSITIVITY_TEMPORAL_CORRELATIONS)

    return IntervalResult(
        status=AVAILABLE, area_ha=area_total, cells=cells.count, stock_start_tc=stock_start,
        stock_end_tc=stock_end, mean_start_tc_ha=stock_start / area_total,
        mean_end_tc_ha=stock_end / area_total, delta_stock_tc=delta, e_proj_tco2e=estimate,
        e_per_ha_year_tco2e=estimate / (area_total * span), sd_tco2e=main.sd_tco2e,
        lower_tco2e=main.lower_tco2e, upper_tco2e=main.upper_tco2e,
        assumptions={"spatial_dependence": spatial_dependence,
                     "temporal_correlation": float(temporal_correlation),
                     "coverage_factor": float(coverage_factor), "cells": cells.count,
                     "grid": "native CCI cells", "pool": "AGB",
                     "cf_agb": parameters.cf_agb, "co2_per_c": parameters.co2_per_c,
                     "empirically_calibrated": False},
        sensitivity=grid)


# -- baseline ------------------------------------------------------------------------------
@dataclass(frozen=True)
class BaselinePart:
    aoi_id: str
    area_ha: float


@dataclass(frozen=True)
class BaselinePartResult:
    aoi_id: str
    area_ha: float
    stock_start_tc_ha: float
    stock_end_tc_ha: float
    delta_tc_ha: float
    delta_tc: float
    clipped_at_zero: bool


@dataclass(frozen=True)
class BaselineResult:
    status: str
    unavailable_reason: str | None = None
    baseline_id: str | None = None
    parts: tuple[BaselinePartResult, ...] = ()
    area_ha: float | None = None
    delta_tc: float | None = None
    delta_tc_ha: float | None = None
    e_base_tco2e: float | None = None


def load_baseline_table(root: Path = catalog.DATA_ROOT) -> dict[str, tuple[dict, ...]]:
    rows: dict[str, list[dict]] = {}
    for raw in catalog._rows(root / "methodology" / "baseline.csv"):
        rows.setdefault(raw["aoi_id"], []).append(raw)
    return {aoi: tuple(sorted(items, key=lambda row: int(row["year_start"])))
            for aoi, items in rows.items()}


def _stock_at(rows: tuple[dict, ...], year: int) -> tuple[float, bool] | None:
    number = catalog.parse_number
    for row in rows:
        clipped = row["clipped_at_zero"].strip().lower() == "true"
        if int(row["year_start"]) == year:
            value = number(row["baseline_stock_start_tc_ha"])
            return max(0.0, value), clipped or value < 0.0
        if int(row["year_end"]) == year:
            value = number(row["baseline_stock_end_tc_ha"])
            return max(0.0, value), clipped or value < 0.0
    return None


def compute_baseline(parts: Iterable[BaselinePart], *, year_start: int, year_end: int,
                     table: dict | None = None,
                     parameters: CaseParameters = DEFAULT_PARAMETERS) -> BaselineResult:
    requested = tuple(parts)
    if not requested:
        return BaselineResult(UNAVAILABLE, MISSING_INPUT)
    if year_end <= year_start:
        return BaselineResult(UNAVAILABLE, NON_POSITIVE_PERIOD)
    if any(not math.isfinite(part.area_ha) for part in requested):
        return BaselineResult(UNAVAILABLE, NON_FINITE_INPUT)
    if any(part.area_ha <= 0.0 for part in requested):
        return BaselineResult(UNAVAILABLE, NON_POSITIVE_AREA)

    rows_by_aoi = load_baseline_table() if table is None else table
    results: list[BaselinePartResult] = []
    for part in requested:
        rows = rows_by_aoi.get(part.aoi_id)
        if not rows:
            return BaselineResult(UNAVAILABLE, BASELINE_UNKNOWN_AREA)
        start, end = _stock_at(rows, year_start), _stock_at(rows, year_end)
        if start is None or end is None:
            return BaselineResult(UNAVAILABLE, BASELINE_OUT_OF_COVERAGE)
        delta_tc_ha = end[0] - start[0]
        results.append(BaselinePartResult(
            aoi_id=part.aoi_id, area_ha=part.area_ha, stock_start_tc_ha=start[0],
            stock_end_tc_ha=end[0], delta_tc_ha=delta_tc_ha,
            delta_tc=part.area_ha * delta_tc_ha, clipped_at_zero=start[1] or end[1]))

    area_total = sum(part.area_ha for part in results)
    delta_tc = sum(part.delta_tc for part in results)
    return BaselineResult(
        status=AVAILABLE, baseline_id=rows_by_aoi[results[0].aoi_id][0]["baseline_id"],
        parts=tuple(results), area_ha=area_total, delta_tc=delta_tc,
        delta_tc_ha=delta_tc / area_total, e_base_tco2e=-delta_tc * parameters.co2_per_c)


# -- units ---------------------------------------------------------------------------------
@dataclass(frozen=True)
class Coverage:
    biomass: float
    baseline: float


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


def _scenario_values(units: int, parameters: CaseParameters) -> tuple[ScenarioValue, ...]:
    return tuple(ScenarioValue(price_rub=price, value_rub=units * price)
                 for price in parameters.prices_rub)


def compute_units(*, e_proj_tco2e: float | None, e_base_tco2e: float | None,
                  lower_tco2e: float | None, upper_tco2e: float | None, area_ha: float | None,
                  year_start: int | None, year_end: int | None, coverage: Coverage | None = None,
                  parameters: CaseParameters = DEFAULT_PARAMETERS) -> UnitsResult:
    mandatory = (e_proj_tco2e, e_base_tco2e, lower_tco2e, upper_tco2e, area_ha,
                 year_start, year_end)
    if any(value is None for value in mandatory):
        return UnitsResult(UNAVAILABLE, MISSING_INPUT)
    if not all(math.isfinite(float(value)) for value in mandatory):
        return UnitsResult(UNAVAILABLE, NON_FINITE_INPUT)
    if float(area_ha) <= 0.0:
        return UnitsResult(UNAVAILABLE, NON_POSITIVE_AREA)
    if int(year_end) <= int(year_start):
        return UnitsResult(UNAVAILABLE, NON_POSITIVE_PERIOD)
    if coverage is not None:
        shares = (coverage.biomass, coverage.baseline)
        if any(not math.isfinite(share) or not 0.0 <= share <= 1.0 for share in shares):
            raise ValueError("coverage shares must be finite values in [0, 1]")
        if any(share < 1.0 - COVERAGE_TOLERANCE for share in shares):
            return UnitsResult(UNAVAILABLE, INCOMPLETE_COVERAGE)

    estimate, lower, upper = float(e_proj_tco2e), float(lower_tco2e), float(upper_tco2e)
    if not lower <= estimate <= upper:
        return UnitsResult(UNAVAILABLE, INVALID_INTERVAL)

    half = max(estimate - lower, upper - estimate)
    leakage = parameters.leakage_tco2e
    relative = float(e_base_tco2e) - estimate - leakage
    common = dict(e_proj_tco2e=estimate, e_base_tco2e=float(e_base_tco2e), leakage_tco2e=leakage,
                  lower_tco2e=lower, upper_tco2e=upper, h_tco2e=half, r_tco2e=relative)

    if relative <= 0.0:
        return UnitsResult(status=AVAILABLE, zero_reason=NON_POSITIVE_RELATIVE_RESULT, units=0,
                           scenario_values=_scenario_values(0, parameters), **common)
    ratio = half / relative
    if ratio >= parameters.unc_stop_ratio:
        return UnitsResult(status=AVAILABLE, zero_reason=UNCERTAINTY_TOO_HIGH, ratio=ratio,
                           units=0, scenario_values=_scenario_values(0, parameters), **common)

    share = min(1.0, max(0.0, ratio - parameters.unc_allowance))
    adjusted = relative * (1.0 - share)
    units = math.floor(adjusted * UNIT_SHARE)
    buffer = adjusted * parameters.buffer_share
    return UnitsResult(
        status=AVAILABLE, zero_reason=ROUNDED_TO_ZERO if units == 0 else None, ratio=ratio,
        uncertainty_share=share, uncertainty_deduction_tco2e=relative - adjusted,
        r_adj_tco2e=adjusted, buffer_tco2e=buffer, units=units,
        rounding_residual_tco2e=adjusted - buffer - units,
        scenario_values=_scenario_values(units, parameters), **common)


# -- claim ---------------------------------------------------------------------------------
@dataclass(frozen=True)
class AnalysisContext:
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


def compare_claim(claim: ClaimInput | None, *, analysis: AnalysisContext, units: int | None,
                  parameters: CaseParameters = DEFAULT_PARAMETERS) -> ClaimResult:
    if claim is None:
        return ClaimResult(status=CLAIM_NOT_PROVIDED)
    if claim.source not in CLAIM_SOURCES:
        raise ValueError(f"claim source must be one of {sorted(CLAIM_SOURCES)}")

    mismatches: list[str] = []
    value = claim.claimed_units
    if value is None or not math.isfinite(float(value)) or float(value) < 0.0:
        mismatches.append(INVALID_CLAIM_VALUE)
    if claim.geometry_hash != analysis.geometry_hash:
        mismatches.append(GEOMETRY_MISMATCH)
    if (claim.year_start, claim.year_end) != (analysis.year_start, analysis.year_end):
        mismatches.append(PERIOD_MISMATCH)
    if claim.pool != analysis.pool:
        mismatches.append(POOL_MISMATCH)
    if claim.unit != analysis.unit:
        mismatches.append(UNIT_MISMATCH)
    if mismatches:
        return ClaimResult(status=CLAIM_NOT_COMPARABLE, mismatch_reasons=tuple(mismatches),
                           claimed_units=value if value is None or math.isfinite(float(value))
                           else None, source=claim.source, units=units)

    claimed = float(value)
    if units is None:
        return ClaimResult(status=CLAIM_UNASSESSABLE, claimed_units=claimed, source=claim.source)

    gap = max(claimed - units, 0.0)
    if claimed == 0.0:
        share, status = None, CLAIM_SUPPORTED
    else:
        share = min(units / claimed, 1.0)
        if units >= claimed:
            status = CLAIM_SUPPORTED
        elif units > 0:
            status = CLAIM_PARTIALLY_SUPPORTED
        else:
            status = CLAIM_NOT_SUPPORTED
    return ClaimResult(status=status, claimed_units=claimed, source=claim.source, units=units,
                       gap_units=gap, supported_share=share,
                       gap_values=tuple(ClaimGapValue(price_rub=price, value_rub=gap * price)
                                        for price in parameters.prices_rub))


def baseline_stock(*, reference_2019_tc_ha: float, rate_tc_ha_yr: float, year: int) -> float:
    """c_base,y of the case, including the max(0, ...) clamp."""
    return max(0.0, reference_2019_tc_ha + rate_tc_ha_yr * (year - REFERENCE_YEAR))


@dataclass(frozen=True)
class BaselineRow:
    baseline_id: str
    aoi_id: str
    reference_mean_2019_tc_ha: float
    historical_rate_tc_ha_yr: float


def baseline_rows(root: Path = catalog.DATA_ROOT) -> dict[str, BaselineRow]:
    """One trajectory per area, for drawing the baseline beside the observed timeline."""
    rows: dict[str, BaselineRow] = {}
    for raw in catalog._rows(root / "methodology" / "baseline.csv"):
        rows.setdefault(raw["aoi_id"], BaselineRow(
            baseline_id=raw["baseline_id"], aoi_id=raw["aoi_id"],
            reference_mean_2019_tc_ha=catalog.parse_number(raw["reference_mean_2019_tc_ha"]),
            historical_rate_tc_ha_yr=catalog.parse_number(raw["historical_rate_tc_ha_yr"])))
    return rows
