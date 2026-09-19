"""Common baseline of the case and the baseline result Ebase.

Formulas (Постановка задачи, с. 5):

    g = (c̄_2019 − c̄_2015) / 4
    c_base,y = max(0, c̄_2019 + g × (y − 2019))
    Ebase = −A × (c_base,t1 − c_base,t0) × 44/12

The trajectory itself is given for 2019–2029 in data/methodology/baseline.csv and is
applied as it stands. A sub-polygon uses the per-hectare trajectory of its parent area
and its own requested area; a request crossing several areas sums non-overlapping parts.
The baseline is a condition of the case: it does not establish additionality, and a
declining baseline is easier to beat, which the notes state explicitly.
"""
from __future__ import annotations

import csv
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from . import notes, reasons
from .parameters import REPO_ROOT, CaseParameters, DEFAULT_PARAMETERS, parse_number

BASELINE_CSV = REPO_ROOT / "data" / "methodology" / "baseline.csv"
REFERENCE_YEAR = 2019


@dataclass(frozen=True)
class BaselineRow:
    baseline_id: str
    aoi_id: str
    year_start: int
    year_end: int
    pool: str
    reference_mean_2015_tc_ha: float
    reference_mean_2019_tc_ha: float
    historical_rate_tc_ha_yr: float
    stock_start_tc_ha: float
    stock_end_tc_ha: float
    delta_tc_ha: float
    clipped_at_zero: bool


@dataclass(frozen=True)
class BaselinePart:
    """One non-overlapping part of the request inside a parent area."""

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
    years: tuple[int, int] | None = None
    parts: tuple[BaselinePartResult, ...] = ()
    area_ha: float | None = None
    delta_tc: float | None = None
    delta_tc_ha: float | None = None
    e_base_tco2e: float | None = None
    notes: tuple[notes.Note, ...] = ()


def baseline_stock(
    *, reference_2019_tc_ha: float, rate_tc_ha_yr: float, year: int
) -> float:
    """c_base,y of the case, including the max(0, ...) clamp."""
    return max(0.0, reference_2019_tc_ha + rate_tc_ha_yr * (year - REFERENCE_YEAR))


def load_baseline_table(path: Path = BASELINE_CSV) -> dict[str, tuple[BaselineRow, ...]]:
    rows: dict[str, list[BaselineRow]] = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            row = BaselineRow(
                baseline_id=raw["baseline_id"],
                aoi_id=raw["aoi_id"],
                year_start=int(raw["year_start"]),
                year_end=int(raw["year_end"]),
                pool=raw["pool"],
                reference_mean_2015_tc_ha=parse_number(raw["reference_mean_2015_tc_ha"]),
                reference_mean_2019_tc_ha=parse_number(raw["reference_mean_2019_tc_ha"]),
                historical_rate_tc_ha_yr=parse_number(raw["historical_rate_tc_ha_yr"]),
                stock_start_tc_ha=parse_number(raw["baseline_stock_start_tc_ha"]),
                stock_end_tc_ha=parse_number(raw["baseline_stock_end_tc_ha"]),
                delta_tc_ha=parse_number(raw["baseline_delta_tc_ha"]),
                clipped_at_zero=raw["clipped_at_zero"].strip().lower() == "true",
            )
            rows.setdefault(row.aoi_id, []).append(row)
    return {aoi: tuple(sorted(items, key=lambda r: r.year_start)) for aoi, items in rows.items()}


def _stock_at(rows: tuple[BaselineRow, ...], year: int) -> tuple[float, bool] | None:
    for row in rows:
        if row.year_start == year:
            return max(0.0, row.stock_start_tc_ha), row.clipped_at_zero or row.stock_start_tc_ha < 0.0
        if row.year_end == year:
            return max(0.0, row.stock_end_tc_ha), row.clipped_at_zero or row.stock_end_tc_ha < 0.0
    return None


def compute_baseline(
    parts: Iterable[BaselinePart],
    *,
    year_start: int,
    year_end: int,
    table: dict[str, tuple[BaselineRow, ...]] | None = None,
    parameters: CaseParameters = DEFAULT_PARAMETERS,
) -> BaselineResult:
    """Baseline result Ebase for one or several non-overlapping parts."""
    requested = tuple(parts)
    if not requested:
        return BaselineResult(reasons.UNAVAILABLE, reasons.MISSING_INPUT)
    if year_end <= year_start:
        return BaselineResult(reasons.UNAVAILABLE, reasons.NON_POSITIVE_PERIOD)
    if any(not math.isfinite(part.area_ha) for part in requested):
        return BaselineResult(reasons.UNAVAILABLE, reasons.NON_FINITE_INPUT)
    if any(part.area_ha <= 0.0 for part in requested):
        return BaselineResult(reasons.UNAVAILABLE, reasons.NON_POSITIVE_AREA)

    rows_by_aoi = load_baseline_table() if table is None else table
    results: list[BaselinePartResult] = []
    for part in requested:
        rows = rows_by_aoi.get(part.aoi_id)
        if not rows:
            return BaselineResult(reasons.UNAVAILABLE, reasons.BASELINE_UNKNOWN_AREA)
        start = _stock_at(rows, year_start)
        end = _stock_at(rows, year_end)
        if start is None or end is None:
            return BaselineResult(reasons.UNAVAILABLE, reasons.BASELINE_OUT_OF_COVERAGE)
        delta_tc_ha = end[0] - start[0]
        results.append(
            BaselinePartResult(
                aoi_id=part.aoi_id,
                area_ha=part.area_ha,
                stock_start_tc_ha=start[0],
                stock_end_tc_ha=end[0],
                delta_tc_ha=delta_tc_ha,
                delta_tc=part.area_ha * delta_tc_ha,
                clipped_at_zero=start[1] or end[1],
            )
        )

    area_total = sum(part.area_ha for part in results)
    delta_tc = sum(part.delta_tc for part in results)
    collected = [notes.note(notes.BASELINE_FIXED)]
    collected.extend(
        notes.note(notes.BASELINE_DECLINING, aoi_id=part.aoi_id, decline=-part.delta_tc_ha)
        for part in results
        if part.delta_tc_ha < 0.0
    )
    return BaselineResult(
        status=reasons.AVAILABLE,
        baseline_id=rows_by_aoi[results[0].aoi_id][0].baseline_id,
        years=(year_start, year_end),
        parts=tuple(results),
        area_ha=area_total,
        delta_tc=delta_tc,
        delta_tc_ha=delta_tc / area_total,
        e_base_tco2e=-delta_tc * parameters.co2_per_c,
        notes=tuple(collected),
    )
