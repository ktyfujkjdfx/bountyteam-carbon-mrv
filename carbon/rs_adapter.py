"""The boundary between the RS component and the carbon engine.

Everything that knows a field name on the wire lives here; the engine works on
`CellObservations`, `Coverage`, `AreaCoverage` and `TimelinePoint`. When G0 fixes the
shared v2 contract, this file changes and no formula does.

The input of record is the RS payload `rs.case2.raster-analysis/1` together with its
per-cell layer. Four rules make the boundary safe, and each of them exists because the
opposite behaviour would move Q in the flattering direction:

* a cell that RS marked `valid: false` is excluded, and the area it would have carried
  stays missing rather than becoming zero biomass;
* a missing or unusable `agb_sd_t_ha` is an error, never `0.0`. Zero deviation narrows
  the interval and raises Q, so a gap in the deviations must surface as Q = null;
* coverage is reported twice — `raw` exactly as the geodesic arithmetic produced it, and
  the public share clamped to [0, 1]. Geodesic area is not additive over a partition, so
  a raw share slightly above 1 is arithmetic, not a bug, and it is not hidden;
* completeness is decided in hectares against the tolerance RS uses (1e-4 ha), not by
  demanding an exact 1.0 from a float division.

`null`, `NaN` and `Infinity` anywhere in the numbers raise `RsPayloadError` here, at the
edge, instead of travelling into the formulas as a silent nan.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analysis import AreaCoverage, TimelinePoint
from .interval import CellObservations
from .units import Coverage

RS_ANALYSIS_SCHEMA = "rs.case2.raster-analysis/1"
FIXTURE_SCHEMA = "carbon.fixture.cells/1"

INPUT_RS_PAYLOAD = "RS_PAYLOAD"
INPUT_PROVISIONAL = "PROVISIONAL_LOCAL_EXTRACTION"

# Agreed with RS: completeness is judged in hectares, and 1e-4 ha is 1 m².
COVERAGE_TOLERANCE_HA = 1e-4

# RS is the canonical source of the stock difference. The engine recomputes E from the
# cells it was given and compares; the published per-cell values are rounded to nine
# decimals, so a divergence of this relative size is the rounding and nothing else.
CANONICAL_E_TOLERANCE = 1e-6


class RsPayloadError(ValueError):
    """The upstream payload cannot be read into the engine's typed inputs."""


@dataclass(frozen=True)
class CoverageReport:
    """Both readings of one coverage: as measured, and as published."""

    raw: float
    public: float

    @property
    def clamped(self) -> bool:
        return self.raw != self.public


@dataclass(frozen=True)
class RasterInputs:
    """Everything the engine needs from upstream, already typed."""

    cells: CellObservations
    coverage: Coverage
    area: AreaCoverage
    timeline: tuple[TimelinePoint, ...]
    optical_quality: dict[str, Any] | None
    year_start: int
    year_end: int
    parent_aoi_ids: tuple[str, ...]
    input_status: str
    parent_weights_ha: tuple[tuple[str, float], ...] = ()
    coverage_raw: dict[str, CoverageReport] | None = None
    excluded_cells: int = 0
    declared_e_tco2e: float | None = None
    source_files: tuple[str, ...] = ()

    @property
    def is_provisional(self) -> bool:
        return self.input_status != INPUT_RS_PAYLOAD


def _require(payload: Any, key: str) -> Any:
    if not isinstance(payload, dict) or key not in payload:
        raise RsPayloadError(f"missing required field: {key}")
    return payload[key]


def _number(value: Any, field: str) -> float:
    """A usable number, or an error. `null`, `NaN` and `Infinity` never pass."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _fail(field, value)
    number = float(value)
    if not math.isfinite(number):
        return _fail(field, value)
    return number


def _fail(field: str, value: Any) -> float:
    raise RsPayloadError(f"{field} must be a finite number, got {value!r}")


def _year_value(mapping: Any, year: int, field: str) -> float:
    if not isinstance(mapping, dict):
        raise RsPayloadError(f"{field} must be a year-keyed object")
    key = str(year)
    if key not in mapping:
        raise RsPayloadError(f"{field} has no value for {year}")
    return _number(mapping[key], f"{field}[{year}]")


def _share(covered_ha: float, requested_ha: float) -> CoverageReport:
    raw = covered_ha / requested_ha if requested_ha > 0.0 else 0.0
    return CoverageReport(raw=raw, public=min(1.0, max(0.0, raw)))


def _complete(covered_ha: float, requested_ha: float) -> bool:
    return max(0.0, requested_ha - covered_ha) <= COVERAGE_TOLERANCE_HA


def read_cells(
    collection: dict[str, Any], *, year_start: int, year_end: int
) -> tuple[CellObservations, dict[str, float], int, float]:
    """Read the per-cell layer.

    Returns the observations, the valid weight per parent area, how many cells were
    excluded, and the weight whose deviations are present on both dates.
    """
    features = _require(collection, "features")
    if not features:
        raise RsPayloadError("the per-cell layer contains no cells")

    weights, start, end, sd_start, sd_end = [], [], [], [], []
    per_parent: dict[str, float] = {}
    excluded = 0
    sd_weight = 0.0
    for feature in features:
        properties = _require(feature, "properties")
        if properties.get("valid", True) is not True:
            excluded += 1
            continue
        weight = _number(_require(properties, "weight_ha"), "weight_ha")
        if weight < 0.0:
            raise RsPayloadError(f"weight_ha must not be negative, got {weight!r}")
        agb = _require(properties, "agb_t_ha")
        deviations = _require(properties, "agb_sd_t_ha")
        # A deviation that is absent or unusable is an error here. Defaulting it to zero
        # would narrow the interval and raise Q on the strength of missing data.
        sd_first = _year_value(deviations, year_start, "agb_sd_t_ha")
        sd_last = _year_value(deviations, year_end, "agb_sd_t_ha")
        if sd_first < 0.0 or sd_last < 0.0:
            raise RsPayloadError("agb_sd_t_ha must not be negative")

        weights.append(weight)
        start.append(_year_value(agb, year_start, "agb_t_ha"))
        end.append(_year_value(agb, year_end, "agb_t_ha"))
        sd_start.append(sd_first)
        sd_end.append(sd_last)
        sd_weight += weight
        parent = properties.get("parent_aoi_id")
        if parent:
            per_parent[str(parent)] = per_parent.get(str(parent), 0.0) + weight

    if not weights:
        raise RsPayloadError("every cell of the layer was excluded as invalid")
    observations = CellObservations.from_sequences(
        area_ha=weights, agb_start=start, agb_end=end, sd_start=sd_start, sd_end=sd_end
    )
    return observations, per_parent, excluded, sd_weight


def cells_from_rs_geojson(
    collection: dict[str, Any], *, year_start: int, year_end: int
) -> CellObservations:
    """The per-cell observations alone, for callers that need nothing else."""
    return read_cells(collection, year_start=year_start, year_end=year_end)[0]


def _timeline(rows: Any) -> tuple[TimelinePoint, ...]:
    return tuple(
        TimelinePoint(
            year=int(row["year"]),
            mean_tc_ha=_number(row["mean_tc_ha"], "timeline.mean_tc_ha"),
            total_tc=_number(row["total_tc"], "timeline.total_tc"),
            mean_agb_t_ha=_number(row["mean_agb_t_ha"], "timeline.mean_agb_t_ha"),
            cells=int(row["cells"]),
            covered_ha=_number(row["covered_ha"], "timeline.covered_ha"),
        )
        for row in rows or ()
    )


def _build(
    *,
    request: dict[str, Any],
    coverage_block: dict[str, Any],
    collection: dict[str, Any],
    timeline_rows: Any,
    optical: Any,
    input_status: str,
    declared_e_tco2e: float | None,
    source_files: tuple[str, ...],
    baseline_covered_ha: float | None = None,
) -> RasterInputs:
    year_start = int(_require(request, "year_start"))
    year_end = int(_require(request, "year_end"))
    cells, per_parent, excluded, sd_weight = read_cells(
        collection, year_start=year_start, year_end=year_end
    )

    requested_ha = _number(_require(coverage_block, "requested_ha"), "requested_ha")
    if requested_ha <= 0.0:
        raise RsPayloadError("requested_ha must be positive")
    calculated_ha = _number(_require(coverage_block, "calculated_ha"), "calculated_ha")
    # The declared area and the weight of the cells that survived the `valid` filter can
    # disagree. The calculation ran on the cells, so the smaller of the two is what the
    # result may speak for; the declared value is kept in `area` for the reader.
    valid_weight = float(cells.area_ha.sum())
    effective_ha = min(calculated_ha, valid_weight)

    biomass = _share(effective_ha, requested_ha)
    uncertainty = _share(sd_weight, requested_ha)
    # Baseline coverage is what the baseline table can actually speak for: the weight of
    # the cells whose parent area is named. It is measured, never assumed to be 1.0.
    named_ha = sum(per_parent.values())
    baseline = _share(
        named_ha if baseline_covered_ha is None else baseline_covered_ha, requested_ha
    )

    return RasterInputs(
        cells=cells,
        coverage=Coverage(
            biomass=1.0 if _complete(effective_ha, requested_ha) else biomass.public,
            baseline=1.0 if _complete(
                named_ha if baseline_covered_ha is None else baseline_covered_ha,
                requested_ha,
            ) else baseline.public,
            uncertainty=1.0 if _complete(sd_weight, requested_ha) else uncertainty.public,
        ),
        area=AreaCoverage(requested_ha=requested_ha, calculated_ha=calculated_ha),
        timeline=_timeline(timeline_rows),
        optical_quality=None if optical is None else dict(optical),
        year_start=year_start,
        year_end=year_end,
        parent_aoi_ids=tuple(sorted(per_parent)) or tuple(request.get("parents", ())),
        input_status=input_status,
        parent_weights_ha=tuple(sorted(per_parent.items())),
        coverage_raw={"biomass": biomass, "uncertainty": uncertainty, "baseline": baseline},
        excluded_cells=excluded,
        declared_e_tco2e=declared_e_tco2e,
        source_files=source_files,
    )


def from_rs_payload(
    analysis_payload: dict[str, Any], cells_geojson: dict[str, Any]
) -> RasterInputs:
    """Adapt a real RS result into the engine's typed inputs."""
    schema = analysis_payload.get("schema")
    if schema != RS_ANALYSIS_SCHEMA:
        raise RsPayloadError(f"expected {RS_ANALYSIS_SCHEMA}, got {schema!r}")
    change = analysis_payload.get("stock_change") or {}
    declared = change.get("e_tco2e")
    return _build(
        request=_require(analysis_payload, "request"),
        coverage_block=_require(analysis_payload, "coverage"),
        collection=cells_geojson,
        timeline_rows=analysis_payload.get("timeline"),
        optical=analysis_payload.get("optical"),
        input_status=INPUT_RS_PAYLOAD,
        declared_e_tco2e=None if declared is None else _number(declared, "e_tco2e"),
        source_files=tuple(
            entry.get("relative_path", "")
            for entry in analysis_payload.get("sources", ())
            if entry.get("relative_path")
        ),
    )


def from_fixture(payload: dict[str, Any]) -> RasterInputs:
    """Adapt the provisional local extraction, which is published in the RS shape.

    The fixture is a test input only. Its status travels into the passport and the report,
    and `guard_production_input` refuses to let it reach a published result.
    """
    schema = payload.get("schema")
    if schema not in (FIXTURE_SCHEMA, RS_ANALYSIS_SCHEMA):
        raise RsPayloadError(f"expected {FIXTURE_SCHEMA}, got {schema!r}")
    change = payload.get("stock_change") or {}
    declared = change.get("e_tco2e")
    return _build(
        request=_require(payload, "request"),
        coverage_block=_require(payload, "coverage"),
        collection=_require(payload, "cells"),
        timeline_rows=payload.get("timeline"),
        optical=payload.get("optical"),
        input_status=INPUT_PROVISIONAL,
        declared_e_tco2e=None if declared is None else _number(declared, "e_tco2e"),
        source_files=tuple(
            entry.get("relative_path", "")
            for entry in payload.get("sources", ())
            if entry.get("relative_path")
        ),
    )


def agrees_with_declared_e(inputs: RasterInputs, computed_e_tco2e: float | None) -> bool | None:
    """Does the engine's E match the canonical E that RS published?

    RS owns the stock difference. The engine recomputes it from the per-cell layer purely
    as a check; a disagreement beyond the rounding of the published values means the two
    sides are not looking at the same data and must be reconciled, not averaged.
    """
    if inputs.declared_e_tco2e is None or computed_e_tco2e is None:
        return None
    declared = inputs.declared_e_tco2e
    scale = max(abs(declared), abs(computed_e_tco2e), 1.0)
    return abs(declared - computed_e_tco2e) <= CANONICAL_E_TOLERANCE * scale


def guard_production_input(inputs: RasterInputs) -> None:
    """Refuse to build a published result from a provisional input."""
    if inputs.is_provisional:
        raise RsPayloadError(
            "a provisional local extraction is a test input; a published or demonstrated "
            "result must come from the RS payload"
        )


def load_fixture(path: Path) -> dict[str, Any]:
    """Read a payload file with an explicit encoding, so Windows behaves like Linux."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
