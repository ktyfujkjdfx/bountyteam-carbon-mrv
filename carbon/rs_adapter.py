"""The boundary between the RS component and the carbon engine.

G0 has not fixed the shared v2 contract yet, so this module is the internal typed
interface in its place: everything that knows a field name on the wire lives here, and
the engine works on `CellObservations`, `Coverage`, `AreaCoverage` and `TimelinePoint`.
When G0 fixes the contract, this file changes and no formula does.

Two input shapes are read, and a result always says which one it came from:

* `rs.case2.raster-analysis/1` — the real RS payload (`analysis.json` plus
  `cells.geojson`), the shape published in the RS branch;
* `carbon.fixture.cells/1` — the provisional extraction under `carbon/tests/fixtures/`,
  built from the official rasters so the tests can lock real numbers before RS is merged.

A fixture-backed result is marked `PROVISIONAL_LOCAL_EXTRACTION` and carries the
`PROVISIONAL_INPUT` note all the way into the passport. It is never presented as an RS
result, and every number derived from it must be recomputed once RS is available.
"""
from __future__ import annotations

import json
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


class RsPayloadError(ValueError):
    """The upstream payload cannot be read into the engine's typed inputs."""


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
    source_files: tuple[str, ...] = ()


def _require(payload: Any, key: str) -> Any:
    if not isinstance(payload, dict) or key not in payload:
        raise RsPayloadError(f"missing required field: {key}")
    return payload[key]


def _year_value(mapping: Any, year: int, field: str) -> float:
    if not isinstance(mapping, dict):
        raise RsPayloadError(f"{field} must be a year-keyed object")
    key = str(year)
    if key not in mapping:
        raise RsPayloadError(f"{field} has no value for {year}")
    return float(mapping[key])


def cells_from_rs_geojson(
    collection: dict[str, Any], *, year_start: int, year_end: int
) -> CellObservations:
    """Read the RS per-cell layer. The cells themselves carry the spatial detail."""
    features = _require(collection, "features")
    if not features:
        raise RsPayloadError("the per-cell layer contains no cells")
    weights, start, end, sd_start, sd_end = [], [], [], [], []
    for feature in features:
        properties = _require(feature, "properties")
        weights.append(float(_require(properties, "weight_ha")))
        agb = _require(properties, "agb_t_ha")
        sd = _require(properties, "agb_sd_t_ha")
        start.append(_year_value(agb, year_start, "agb_t_ha"))
        end.append(_year_value(agb, year_end, "agb_t_ha"))
        sd_start.append(_year_value(sd, year_start, "agb_sd_t_ha"))
        sd_end.append(_year_value(sd, year_end, "agb_sd_t_ha"))
    return CellObservations.from_sequences(
        area_ha=weights, agb_start=start, agb_end=end, sd_start=sd_start, sd_end=sd_end
    )


def _timeline(rows: Any) -> tuple[TimelinePoint, ...]:
    return tuple(
        TimelinePoint(
            year=int(row["year"]),
            mean_tc_ha=float(row["mean_tc_ha"]),
            total_tc=float(row["total_tc"]),
            mean_agb_t_ha=float(row["mean_agb_t_ha"]),
            cells=int(row["cells"]),
            covered_ha=float(row["covered_ha"]),
        )
        for row in rows or ()
    )


def from_rs_payload(
    analysis_payload: dict[str, Any], cells_geojson: dict[str, Any]
) -> RasterInputs:
    """Adapt a real RS result into the engine's typed inputs."""
    schema = analysis_payload.get("schema")
    if schema != RS_ANALYSIS_SCHEMA:
        raise RsPayloadError(f"expected {RS_ANALYSIS_SCHEMA}, got {schema!r}")
    request = _require(analysis_payload, "request")
    coverage_block = _require(analysis_payload, "coverage")
    year_start = int(_require(request, "year_start"))
    year_end = int(_require(request, "year_end"))

    optical = analysis_payload.get("optical")
    return RasterInputs(
        cells=cells_from_rs_geojson(
            cells_geojson, year_start=year_start, year_end=year_end
        ),
        coverage=Coverage(
            biomass=float(coverage_block["biomass"]["fraction"]),
            baseline=1.0,
        ),
        area=AreaCoverage(
            requested_ha=float(coverage_block["requested_ha"]),
            calculated_ha=float(coverage_block["calculated_ha"]),
        ),
        timeline=_timeline(analysis_payload.get("timeline")),
        optical_quality=None if optical is None else dict(optical),
        year_start=year_start,
        year_end=year_end,
        parent_aoi_ids=tuple(request.get("parents", ())),
        input_status=INPUT_RS_PAYLOAD,
    )


def from_fixture(payload: dict[str, Any]) -> RasterInputs:
    """Adapt the provisional local extraction. Marked provisional all the way through."""
    schema = payload.get("schema")
    if schema != FIXTURE_SCHEMA:
        raise RsPayloadError(f"expected {FIXTURE_SCHEMA}, got {schema!r}")
    request = _require(payload, "request")
    block = _require(payload, "cells")
    observations = _require(block, "observations")
    year_start = int(request["year_start"])
    year_end = int(request["year_end"])

    def band(year: int, name: str) -> list[float]:
        key = str(year)
        if key not in observations:
            raise RsPayloadError(f"the fixture has no observations for {year}")
        return [float(value) for value in observations[key][name]]

    weights = [float(value) for value in block["weight_ha"]]
    calculated = float(block["weight_sum_ha"])
    return RasterInputs(
        cells=CellObservations.from_sequences(
            area_ha=weights,
            agb_start=band(year_start, "agb_t_ha"),
            agb_end=band(year_end, "agb_t_ha"),
            sd_start=band(year_start, "agb_sd_t_ha"),
            sd_end=band(year_end, "agb_sd_t_ha"),
        ),
        coverage=Coverage(
            biomass=float(payload["coverage"]["biomass"]),
            baseline=1.0,
        ),
        area=AreaCoverage(
            requested_ha=float(request["requested_area_ha"]),
            calculated_ha=calculated,
        ),
        timeline=_timeline(payload.get("timeline")),
        optical_quality=None,
        year_start=year_start,
        year_end=year_end,
        parent_aoi_ids=(request["parent_aoi_id"],),
        input_status=INPUT_PROVISIONAL,
        source_files=tuple(entry["relative_path"] for entry in payload.get("sources", ())),
    )


def load_fixture(path: Path) -> dict[str, Any]:
    """Read a fixture file with an explicit encoding, so Windows behaves like Linux."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
