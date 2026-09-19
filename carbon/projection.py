"""The official baseline extended to 2029, kept strictly apart from what was observed.

Two series live here and they are never joined into one line. The observed series ends at
the last year the data actually covers. The projected series continues the official
baseline trajectory of `data/methodology/baseline.csv` to the scenario horizon, and every
point of it is marked `SCENARIO_PROJECTION` so a chart can draw it dashed and a reader can
see where measurement stops and assumption begins.

What the projection is: the case's own without-project trajectory, evaluated at later
years with the same formula and the same clamp,
`c_base,y = max(0, c̄_2019 + g × (y − 2019))`.

What it is not: a forecast of the biomass that will be there, a market forecast, or a
model of anything. No trend is fitted, no external model is consulted, and nothing learned
from the observed series feeds back into it.

A projected value can never reach Q. Q belongs to the requested period and is computed
from the two dates of that period; `project_baseline` returns a separate result that no
unit calculation reads, and a test holds that line.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import notes, reasons
from .baseline import REFERENCE_YEAR, BaselinePart, baseline_stock, load_baseline_table
from .parameters import DEFAULT_PARAMETERS, METHOD_VERSION, CaseParameters

OBSERVED = "OBSERVED"
SCENARIO_PROJECTION = "SCENARIO_PROJECTION"

FORMULA = "c_base,y = max(0, c̄_2019 + g × (y − 2019)); g = (c̄_2019 − c̄_2015) / 4"
SOURCE = "data/methodology/baseline.csv"
STOCK_UNIT = "t C"
STOCK_UNIT_PER_HA = "t C/ha"


@dataclass(frozen=True)
class ProjectionPoint:
    year: int
    kind: str
    baseline_tc_ha: float
    baseline_tc: float
    observed_tc: float | None = None
    observed_tc_ha: float | None = None
    clipped_at_zero: bool = False

    @property
    def is_projected(self) -> bool:
        return self.kind == SCENARIO_PROJECTION


@dataclass(frozen=True)
class ProjectionResult:
    status: str
    unavailable_reason: str | None = None
    area_ha: float | None = None
    last_observed_year: int | None = None
    horizon_year: int | None = None
    points: tuple[ProjectionPoint, ...] = ()
    stock_unit: str = STOCK_UNIT
    stock_unit_per_ha: str = STOCK_UNIT_PER_HA
    source: str = SOURCE
    formula: str = FORMULA
    method_version: str = METHOD_VERSION
    notes: tuple[notes.Note, ...] = ()

    @property
    def observed(self) -> tuple[ProjectionPoint, ...]:
        return tuple(point for point in self.points if not point.is_projected)

    @property
    def projected(self) -> tuple[ProjectionPoint, ...]:
        return tuple(point for point in self.points if point.is_projected)


def _trajectory(table: dict, aoi_id: str) -> tuple[float, float] | None:
    """The official reference mean and rate of one area, read from the supplied table."""
    rows = table.get(aoi_id)
    if not rows:
        return None
    first = rows[0]
    return first.reference_mean_2019_tc_ha, first.historical_rate_tc_ha_yr


def project_baseline(
    parts: list[BaselinePart],
    *,
    observed: dict[int, float] | None = None,
    horizon_year: int | None = None,
    table: dict | None = None,
    parameters: CaseParameters = DEFAULT_PARAMETERS,
) -> ProjectionResult:
    """The official baseline evaluated year by year to the scenario horizon.

    `observed` maps a year to the measured stock in t C, so the two series can be charted
    on one axis without being merged. Years beyond the last observed one carry no observed
    value at all — `None`, never a projected number standing in for a measurement.
    """
    if not parts:
        return ProjectionResult(reasons.UNAVAILABLE, reasons.MISSING_INPUT)
    rows = load_baseline_table() if table is None else table
    horizon = parameters.scenario_end_year if horizon_year is None else int(horizon_year)

    trajectories: list[tuple[float, float, float]] = []
    for part in parts:
        if part.area_ha <= 0.0:
            return ProjectionResult(reasons.UNAVAILABLE, reasons.NON_POSITIVE_AREA)
        trajectory = _trajectory(rows, part.aoi_id)
        if trajectory is None:
            return ProjectionResult(reasons.UNAVAILABLE, reasons.BASELINE_UNKNOWN_AREA)
        trajectories.append((part.area_ha, *trajectory))

    area_total = sum(area for area, _, _ in trajectories)
    measured = dict(observed or {})
    last_observed = max(measured) if measured else None
    if horizon < REFERENCE_YEAR:
        return ProjectionResult(reasons.UNAVAILABLE, reasons.BASELINE_OUT_OF_COVERAGE)

    first_year = min([REFERENCE_YEAR, *measured]) if measured else REFERENCE_YEAR
    points: list[ProjectionPoint] = []
    for year in range(first_year, horizon + 1):
        stock_tc = 0.0
        clipped = False
        for area, reference, rate in trajectories:
            per_ha = baseline_stock(
                reference_2019_tc_ha=reference, rate_tc_ha_yr=rate, year=year
            )
            if reference + rate * (year - REFERENCE_YEAR) < 0.0:
                clipped = True
            stock_tc += per_ha * area
        observed_tc = measured.get(year)
        points.append(ProjectionPoint(
            year=year,
            # The mark is the whole point: a year we measured is not a year we assumed.
            kind=OBSERVED if last_observed is not None and year <= last_observed else
            SCENARIO_PROJECTION,
            baseline_tc_ha=stock_tc / area_total,
            baseline_tc=stock_tc,
            observed_tc=observed_tc,
            observed_tc_ha=None if observed_tc is None else observed_tc / area_total,
            clipped_at_zero=clipped,
        ))

    attached = [notes.note(notes.BASELINE_PROJECTION), notes.note(notes.BASELINE_FIXED)]
    if any(point.clipped_at_zero for point in points):
        attached.append(notes.note(notes.PROJECTION_CLIPPED))
    return ProjectionResult(
        status=reasons.AVAILABLE,
        area_ha=area_total,
        last_observed_year=last_observed,
        horizon_year=horizon,
        points=tuple(points),
        notes=tuple(attached),
    )
