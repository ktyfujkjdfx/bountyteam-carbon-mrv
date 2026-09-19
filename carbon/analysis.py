"""One request, one composed result: interval → baseline → units → claim.

This is the single entry point a consumer needs. Backend calls `analyse` once and serves
the fields; the report builder and the passport read the same `Analysis` object and never
recompute a formula. The composition order is fixed here, so the number in the API, the
number in the report and the number under the content hash cannot drift apart.

The function stays pure: it uses the per-cell payload it is given, reads no raster and
computes no area. Coverage, the annual timeline and optical quality are produced by RS and
passed through unchanged, because only RS can measure them.

Optical quality never reduces Q. A cloudy scene weakens the evidence a reader can see; it
does not change the modelled biomass stock. What makes Q unavailable is missing mandatory
numeric input, and that travels through `coverage`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import canonical, notes, reasons
from .baseline import BaselinePart, BaselineResult, compute_baseline
from .claim import AnalysisContext, ClaimInput, ClaimResult, compare_claim
from .interval import INDEPENDENT_CELLS, CellObservations, IntervalResult, compute_interval
from .parameters import DEFAULT_PARAMETERS, METHOD_VERSION, CaseParameters
from .units import Coverage, UnitsResult, compute_units

DEFAULT_POOL = "AGB"
DEFAULT_UNIT = "tCO2e"
# Agreed with RS: completeness is judged in hectares, 1e-4 ha is 1 m².
AREA_TOLERANCE_HA = 1e-4


@dataclass(frozen=True)
class MethodOptions:
    """The signed scenario assumptions of the interval, recorded with every result."""

    temporal_correlation: float = 0.0
    coverage_factor: float = 1.0
    spatial_dependence: str = INDEPENDENT_CELLS


@dataclass(frozen=True)
class TimelinePoint:
    """One year of the annual stock curve, measured upstream and passed through."""

    year: int
    mean_tc_ha: float
    total_tc: float
    mean_agb_t_ha: float
    cells: int
    covered_ha: float


@dataclass(frozen=True)
class AreaCoverage:
    """How much of the requested area the calculation actually covered, in hectares."""

    requested_ha: float
    calculated_ha: float

    @property
    def missing_ha(self) -> float:
        return max(self.requested_ha - self.calculated_ha, 0.0)

    @property
    def complete(self) -> bool:
        return self.missing_ha <= AREA_TOLERANCE_HA


@dataclass(frozen=True)
class AnalysisRequest:
    request_id: str
    geometry: dict
    year_start: int
    year_end: int
    parts: tuple[BaselinePart, ...]
    pool: str = DEFAULT_POOL
    unit: str = DEFAULT_UNIT


@dataclass(frozen=True)
class Analysis:
    request: AnalysisRequest
    geometry_hash: str
    options: MethodOptions
    interval: IntervalResult
    baseline: BaselineResult
    units: UnitsResult
    claim: ClaimResult
    coverage: Coverage
    area: AreaCoverage | None = None
    timeline: tuple[TimelinePoint, ...] = ()
    optical_quality: dict[str, object] | None = None
    input_status: str = "RS_PAYLOAD"
    coverage_raw: dict[str, float] | None = None
    excluded_cells: int = 0
    declared_e_tco2e: float | None = None
    declared_e_agrees: bool | None = None
    method_version: str = METHOD_VERSION
    notes: tuple[notes.Note, ...] = field(default_factory=tuple)

    @property
    def context(self) -> AnalysisContext:
        return AnalysisContext(
            geometry_hash=self.geometry_hash,
            year_start=self.request.year_start,
            year_end=self.request.year_end,
            pool=self.request.pool,
            unit=self.request.unit,
        )


def geometry_hash(geometry: dict) -> str:
    """Content hash of the requested geometry, in the canonical form of the repository."""
    return canonical.content_hash(geometry)


def analyse(
    request: AnalysisRequest,
    cells: CellObservations,
    *,
    claim: ClaimInput | None = None,
    options: MethodOptions = MethodOptions(),
    coverage: Coverage | None = None,
    area: AreaCoverage | None = None,
    timeline: tuple[TimelinePoint, ...] = (),
    optical_quality: dict[str, object] | None = None,
    input_status: str = "RS_PAYLOAD",
    coverage_raw: dict[str, float] | None = None,
    excluded_cells: int = 0,
    declared_e_tco2e: float | None = None,
    parameters: CaseParameters = DEFAULT_PARAMETERS,
    baseline_table: dict | None = None,
) -> Analysis:
    """Compose one full result for one request. Unusable input gives a status, not a raise."""
    interval = compute_interval(
        cells,
        year_start=request.year_start,
        year_end=request.year_end,
        parameters=parameters,
        temporal_correlation=options.temporal_correlation,
        coverage_factor=options.coverage_factor,
        spatial_dependence=options.spatial_dependence,
    )
    baseline = compute_baseline(
        list(request.parts),
        year_start=request.year_start,
        year_end=request.year_end,
        table=baseline_table,
        parameters=parameters,
    )
    effective_coverage = coverage if coverage is not None else Coverage(
        biomass=1.0 if interval.status == reasons.AVAILABLE else 0.0,
        baseline=1.0 if baseline.status == reasons.AVAILABLE else 0.0,
    )
    units = compute_units(
        e_proj_tco2e=interval.e_proj_tco2e,
        e_base_tco2e=baseline.e_base_tco2e,
        lower_tco2e=interval.lower_tco2e,
        upper_tco2e=interval.upper_tco2e,
        area_ha=interval.area_ha,
        year_start=request.year_start,
        year_end=request.year_end,
        coverage=effective_coverage,
        parameters=parameters,
    )
    digest = geometry_hash(request.geometry)
    context = AnalysisContext(
        geometry_hash=digest,
        year_start=request.year_start,
        year_end=request.year_end,
        pool=request.pool,
        unit=request.unit,
    )
    comparison = compare_claim(
        claim, analysis=context, units=units.units, parameters=parameters
    )

    collected = [*interval.notes, *baseline.notes, *units.notes, *comparison.notes]
    if optical_quality is not None:
        collected.append(notes.note(notes.OPTICAL_QUALITY_SEPARATE))
    if area is not None and not area.complete:
        collected.append(notes.note(notes.AREA_NOT_FULLY_COVERED))
    if input_status != "RS_PAYLOAD":
        collected.append(notes.note(notes.PROVISIONAL_INPUT))
    if excluded_cells:
        collected.append(notes.note(notes.CELLS_EXCLUDED, excluded=excluded_cells))

    # RS owns the stock difference. Recomputing it here is a cross-check, not a second
    # opinion: a disagreement is reported, never averaged away.
    agrees: bool | None = None
    if declared_e_tco2e is not None and interval.e_proj_tco2e is not None:
        scale = max(abs(declared_e_tco2e), abs(interval.e_proj_tco2e), 1.0)
        agrees = abs(declared_e_tco2e - interval.e_proj_tco2e) <= 1e-6 * scale
        if not agrees:
            collected.append(notes.note(notes.CANONICAL_E_DISAGREES))
    unique: dict[str, notes.Note] = {}
    for item in collected:
        unique.setdefault(item.code, item)

    return Analysis(
        request=request,
        geometry_hash=digest,
        options=options,
        interval=interval,
        baseline=baseline,
        units=units,
        claim=comparison,
        coverage=effective_coverage,
        area=area,
        timeline=tuple(timeline),
        optical_quality=optical_quality,
        input_status=input_status,
        coverage_raw=coverage_raw,
        excluded_cells=excluded_cells,
        declared_e_tco2e=declared_e_tco2e,
        declared_e_agrees=agrees,
        notes=tuple(unique.values()),
    )
