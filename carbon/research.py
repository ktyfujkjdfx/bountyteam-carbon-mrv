"""Research table: how the answer moves when the assumptions move.

The point of this module is to make the influence of each choice visible instead of
arguing about it. One request is recomputed across a grid of assumptions — spatial
dependence of the cell errors, temporal correlation of the two dates, the coverage factor
— and, separately, across two baselines:

* `OFFICIAL_CASE_BASELINE` — `data/methodology/baseline.csv`, the only baseline that
  produces a reported Q;
* `RESEARCH_FLAT_BASELINE` — the same official 2019 reference mean held constant, so the
  without-project scenario neither grows nor declines. It exists to show how much of the
  result is the baseline trajectory rather than the observed change.

The research baseline is a research variant and nothing else. It never enters a passport,
never replaces the reported Q, and every row it produces is labelled. The grid is chosen
before the numbers are looked at, and rows are reported whatever they show, including the
rows where the assumptions decide the answer.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import reasons
from .analysis import AnalysisRequest, MethodOptions
from .baseline import compute_baseline
from .interval import (
    FULLY_DEPENDENT_CELLS,
    INDEPENDENT_CELLS,
    CellObservations,
    compute_interval,
)
from .parameters import DEFAULT_PARAMETERS, CaseParameters
from .units import Coverage, compute_units

BASELINE_OFFICIAL = "OFFICIAL_CASE_BASELINE"
BASELINE_FLAT_RESEARCH = "RESEARCH_FLAT_BASELINE"
BASELINE_VARIANTS = (BASELINE_OFFICIAL, BASELINE_FLAT_RESEARCH)

DEFAULT_ASSUMPTIONS = (
    MethodOptions(temporal_correlation=0.0, spatial_dependence=INDEPENDENT_CELLS),
    MethodOptions(temporal_correlation=1.0, spatial_dependence=INDEPENDENT_CELLS),
    MethodOptions(temporal_correlation=0.0, spatial_dependence=FULLY_DEPENDENT_CELLS),
    MethodOptions(temporal_correlation=1.0, spatial_dependence=FULLY_DEPENDENT_CELLS),
)


@dataclass(frozen=True)
class ResearchRow:
    request_id: str
    aoi_ids: tuple[str, ...]
    year_start: int
    year_end: int
    baseline_variant: str
    spatial_dependence: str
    temporal_correlation: float
    coverage_factor: float
    e_proj_tco2e: float | None
    sd_tco2e: float | None
    lower_tco2e: float | None
    upper_tco2e: float | None
    e_base_tco2e: float | None
    r_tco2e: float | None
    h_tco2e: float | None
    ratio: float | None
    uncertainty_share: float | None
    r_adj_tco2e: float | None
    units: int | None
    status: str
    unavailable_reason: str | None
    zero_reason: str | None
    value_base_price_rub: float | None

    @property
    def is_research_only(self) -> bool:
        return self.baseline_variant != BASELINE_OFFICIAL


def _flat_baseline_tco2e() -> float:
    """A baseline that holds the 2019 reference mean constant emits and removes nothing."""
    return 0.0


def research_rows(
    request: AnalysisRequest,
    cells: CellObservations,
    *,
    assumptions: tuple[MethodOptions, ...] = DEFAULT_ASSUMPTIONS,
    baseline_variants: tuple[str, ...] = BASELINE_VARIANTS,
    parameters: CaseParameters = DEFAULT_PARAMETERS,
    baseline_table: dict | None = None,
) -> tuple[ResearchRow, ...]:
    """Recompute one request across the assumption grid and both baselines."""
    official = compute_baseline(
        list(request.parts),
        year_start=request.year_start,
        year_end=request.year_end,
        table=baseline_table,
        parameters=parameters,
    )
    rows: list[ResearchRow] = []
    for variant in baseline_variants:
        if variant == BASELINE_OFFICIAL:
            e_base = official.e_base_tco2e
        elif variant == BASELINE_FLAT_RESEARCH:
            e_base = _flat_baseline_tco2e() if official.status == reasons.AVAILABLE else None
        else:
            raise ValueError(f"unknown baseline variant: {variant!r}")

        for option in assumptions:
            interval = compute_interval(
                cells,
                year_start=request.year_start,
                year_end=request.year_end,
                parameters=parameters,
                temporal_correlation=option.temporal_correlation,
                coverage_factor=option.coverage_factor,
                spatial_dependence=option.spatial_dependence,
            )
            units = compute_units(
                e_proj_tco2e=interval.e_proj_tco2e,
                e_base_tco2e=e_base,
                lower_tco2e=interval.lower_tco2e,
                upper_tco2e=interval.upper_tco2e,
                area_ha=interval.area_ha,
                year_start=request.year_start,
                year_end=request.year_end,
                coverage=Coverage(biomass=1.0, baseline=1.0),
                parameters=parameters,
            )
            base_price = parameters.prices_rub[1] if len(parameters.prices_rub) > 1 else None
            rows.append(ResearchRow(
                request_id=request.request_id,
                aoi_ids=tuple(part.aoi_id for part in request.parts),
                year_start=request.year_start,
                year_end=request.year_end,
                baseline_variant=variant,
                spatial_dependence=option.spatial_dependence,
                temporal_correlation=option.temporal_correlation,
                coverage_factor=option.coverage_factor,
                e_proj_tco2e=interval.e_proj_tco2e,
                sd_tco2e=interval.sd_tco2e,
                lower_tco2e=interval.lower_tco2e,
                upper_tco2e=interval.upper_tco2e,
                e_base_tco2e=e_base,
                r_tco2e=units.r_tco2e,
                h_tco2e=units.h_tco2e,
                ratio=units.ratio,
                uncertainty_share=units.uncertainty_share,
                r_adj_tco2e=units.r_adj_tco2e,
                units=units.units,
                status=units.status,
                unavailable_reason=units.unavailable_reason,
                zero_reason=units.zero_reason,
                value_base_price_rub=(
                    None if units.units is None or base_price is None
                    else units.units * base_price
                ),
            ))
    return tuple(rows)


def research_table(
    cases: list[tuple[AnalysisRequest, CellObservations]],
    *,
    assumptions: tuple[MethodOptions, ...] = DEFAULT_ASSUMPTIONS,
    baseline_variants: tuple[str, ...] = BASELINE_VARIANTS,
    parameters: CaseParameters = DEFAULT_PARAMETERS,
    baseline_table: dict | None = None,
) -> tuple[ResearchRow, ...]:
    """The same grid over several requests, so a control area sits next to a disturbed one."""
    rows: list[ResearchRow] = []
    for request, cells in cases:
        rows.extend(research_rows(
            request,
            cells,
            assumptions=assumptions,
            baseline_variants=baseline_variants,
            parameters=parameters,
            baseline_table=baseline_table,
        ))
    return tuple(rows)


def decided_by_assumptions(rows: tuple[ResearchRow, ...]) -> tuple[str, ...]:
    """Requests whose answer changes across the grid, under the official baseline only.

    A request listed here is one where the reported Q depends on a signed assumption
    rather than on the data alone. That is a limitation to state, not a knob to turn.
    """
    official = [row for row in rows if row.baseline_variant == BASELINE_OFFICIAL]
    decided: list[str] = []
    for request_id in dict.fromkeys(row.request_id for row in official):
        answers = {
            row.units for row in official if row.request_id == request_id
        }
        if len(answers) > 1:
            decided.append(request_id)
    return tuple(decided)
