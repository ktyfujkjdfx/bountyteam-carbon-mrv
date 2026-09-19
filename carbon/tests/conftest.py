"""Shared helpers: build a full analysis for one official request from the fixtures.

The per-cell numbers come from `carbon/tests/fixtures/`, a provisional local extraction
from `data/` that stands in for the RS payload until G0 fixes the contract. Everything
else — geometry, period, baseline area — comes from `data/areas.csv` and
`data/sample_requests.geojson`, so the tests are anchored to the official request
definitions rather than to numbers invented here.
"""
from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from carbon import (
    AnalysisRequest,
    BaselinePart,
    MethodOptions,
    analyse,
    build_provenance,
    from_fixture,
    from_rs_payload,
)
from carbon.parameters import REPO_ROOT

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

OFFICIAL_AOIS = ("RU_TVER_01", "RU_VOLOGDA_02", "RU_MORDOVIA_03", "RU_MORDOVIA_04")
SAMPLE_REQUEST = "CHECK_TRANSFER_01"
ALL_REQUESTS = (*OFFICIAL_AOIS, SAMPLE_REQUEST)
_REAL_INPUT_CACHE: dict[str, tuple] = {}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def bbox_polygon(west: float, south: float, east: float, north: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [west, south], [east, south], [east, north], [west, north], [west, south],
        ]],
    }


@pytest.fixture(scope="session")
def areas() -> dict[str, dict[str, str]]:
    return {row["aoi_id"]: row for row in read_csv(REPO_ROOT / "data" / "areas.csv")}


@pytest.fixture(scope="session")
def sample_requests() -> dict[str, dict]:
    collection = load_json(REPO_ROOT / "data" / "sample_requests.geojson")
    return {
        feature["properties"]["request_id"]: feature for feature in collection["features"]
    }


def request_geometry(request_id: str, areas: dict, sample_requests: dict) -> dict:
    if request_id in sample_requests:
        return sample_requests[request_id]["geometry"]
    row = areas[request_id]
    return bbox_polygon(
        float(row["bbox_west"]), float(row["bbox_south"]),
        float(row["bbox_east"]), float(row["bbox_north"]),
    )


def parent_aoi(request_id: str, sample_requests: dict) -> str:
    if request_id in sample_requests:
        return sample_requests[request_id]["properties"]["parent_aoi_id"]
    return request_id


def build_case(
    request_id: str,
    areas: dict,
    sample_requests: dict,
    *,
    claim=None,
    options: MethodOptions = MethodOptions(),
):
    """One official request as (AnalysisRequest, RasterInputs, Analysis, provenance)."""
    inputs = from_fixture(load_json(FIXTURE_DIR / f"cells_{request_id}.json"))
    aoi_id = parent_aoi(request_id, sample_requests)
    assert aoi_id in dict(inputs.parent_weights_ha) or not inputs.parent_weights_ha
    request = AnalysisRequest(
        request_id=request_id,
        geometry=request_geometry(request_id, areas, sample_requests),
        year_start=inputs.year_start,
        year_end=inputs.year_end,
        parts=(BaselinePart(aoi_id=aoi_id, area_ha=inputs.area.calculated_ha),),
    )
    analysis = analyse(
        request,
        inputs.cells,
        claim=claim,
        options=options,
        coverage=inputs.coverage,
        area=inputs.area,
        timeline=inputs.timeline,
        input_status=inputs.input_status,
        coverage_raw={name: report.raw for name, report in (inputs.coverage_raw or {}).items()},
        excluded_cells=inputs.excluded_cells,
        declared_e_tco2e=inputs.declared_e_tco2e,
    )
    provenance = build_provenance(relative_paths=list(inputs.source_files))
    return request, inputs, analysis, provenance


def build_real_case(
    request_id: str,
    areas: dict,
    sample_requests: dict,
    *,
    claim=None,
    options: MethodOptions = MethodOptions(),
):
    """Run the official contour through RS and feed its reviewed payload to Carbon."""
    from rs.case2 import analysis as rs_analysis
    from rs.case2 import payload as rs_payload
    from rs.case2.catalog import Dataset

    cached = _REAL_INPUT_CACHE.get(request_id)
    if cached is None:
        geometry = request_geometry(request_id, areas, sample_requests)
        if request_id in sample_requests:
            props = sample_requests[request_id]["properties"]
            year_start, year_end = int(props["year_start"]), int(props["year_end"])
        else:
            year_start, year_end = 2019, 2024
        raster = rs_analysis.analyse(
            geometry, year_start, year_end, dataset=Dataset(), include_optical=True
        )
        wire = rs_payload.analysis_payload(raster)
        cells = rs_payload.cells_payload(raster)
        inputs = replace(
            from_rs_payload(wire, cells),
            source_files=tuple(
                source.relative_path.removeprefix("data/").replace("\\", "/")
                for source in raster.sources
            ),
        )
        provenance = build_provenance(relative_paths=list(inputs.source_files))
        _REAL_INPUT_CACHE[request_id] = (geometry, inputs, provenance)
    else:
        geometry, inputs, provenance = cached
    request = AnalysisRequest(
        request_id=request_id,
        geometry=geometry,
        year_start=inputs.year_start,
        year_end=inputs.year_end,
        parts=tuple(
            BaselinePart(aoi_id=aoi_id, area_ha=area_ha)
            for aoi_id, area_ha in inputs.parent_weights_ha
        ),
    )
    analysis = analyse(
        request,
        inputs.cells,
        claim=claim,
        options=options,
        coverage=inputs.coverage,
        area=inputs.area,
        timeline=inputs.timeline,
        optical_quality=inputs.optical_quality,
        input_status=inputs.input_status,
        coverage_raw={name: report.raw for name, report in (inputs.coverage_raw or {}).items()},
        excluded_cells=inputs.excluded_cells,
        declared_e_tco2e=inputs.declared_e_tco2e,
    )
    return request, inputs, analysis, provenance


@pytest.fixture(scope="session")
def case(areas, sample_requests):
    def factory(request_id: str, **kwargs):
        return build_case(request_id, areas, sample_requests, **kwargs)

    return factory
