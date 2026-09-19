"""Build the provisional per-cell fixtures of the carbon tests from the official data.

PROVISIONAL. The authoritative per-cell payload is produced by the RS component
(`rs.case2.raster-analysis/1`, `cells.geojson`). Until that contract is fixed by G0 and
merged, the carbon tests need real numbers to lock, so this script extracts them from
`data/` directly. It is a test tool, not part of the engine: `carbon/*.py` never reads a
raster, and nothing under `carbon/` imports this module.

What it does, and why each step is defensible:

* cells are the native ESA CCI grid of the supplied GeoTIFF; nothing is resampled;
* band 1 is AGB and band 2 is AGB_SD, in t dry matter/ha, as `data/file_catalog.csv` says;
* a cell weight is the geodesic (WGS84) area of the intersection of the cell with the
  requested rectangle, so a cell on the edge contributes only its overlapping part;
* the sum of the weights therefore reproduces `data/areas.csv`, which is itself the
  geodesic area of the bounding box — the test asserts this agreement;
* every supplied cell carries a value, `nodata` is empty in the catalogue, and the zeros
  are real zero biomass, so no mask is invented here. Masking belongs to RS.

The file is written in the RS shape (`request`, `coverage`, `stock_change`, `timeline`,
`cells` as a GeoJSON FeatureCollection with `valid`, `weight_ha`, `agb_t_ha` and
`agb_sd_t_ha`). Writing it in the real shape means the tests exercise the same adapter
path a real RS payload takes, and swapping in that payload changes no code.

Run from the repository root:

    python -m carbon.tests.fixtures.build_cells
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import rasterio
from pyproj import Geod

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = Path(__file__).resolve().parent
SCHEMA = "carbon.fixture.cells/1"
CO2_PER_C = 44 / 12
GEOD = Geod(ellps="WGS84")
TIMELINE_YEARS = tuple(range(2015, 2025))
WEIGHT_DECIMALS = 9


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _box_area_ha(west: float, south: float, east: float, north: float) -> float:
    """Geodesic area of a lon/lat rectangle, in hectares."""
    area, _ = GEOD.polygon_area_perimeter(
        [west, east, east, west], [south, south, north, north]
    )
    return abs(area) / 1e4


def _cell_weights(dataset, request: tuple[float, float, float, float]) -> dict:
    """Weight every cell by its geodesic overlap with the requested rectangle."""
    west, south, east, north = request
    transform = dataset.transform
    height, width = dataset.shape
    weights: list[float] = []
    index: list[int] = []
    for row in range(height):
        top = transform.f + row * transform.e
        bottom = transform.f + (row + 1) * transform.e
        overlap_south = max(min(bottom, top), south)
        overlap_north = min(max(bottom, top), north)
        if overlap_north <= overlap_south:
            continue
        for col in range(width):
            left = transform.c + col * transform.a
            right = transform.c + (col + 1) * transform.a
            overlap_west = max(left, west)
            overlap_east = min(right, east)
            if overlap_east <= overlap_west:
                continue
            weights.append(
                round(
                    _box_area_ha(overlap_west, overlap_south, overlap_east, overlap_north),
                    WEIGHT_DECIMALS,
                )
            )
            index.append(row * width + col)
    return {"weight_ha": weights, "flat_index": index}


def _bands(aoi_id: str, year: int, flat_index: list[int]) -> tuple[list[int], list[int]]:
    path = REPO_ROOT / "data" / aoi_id / f"CCI_Biomass_{year}.tif"
    with rasterio.open(path) as dataset:
        agb = dataset.read(1).reshape(-1)
        sd = dataset.read(2).reshape(-1)
    return (
        [int(agb[position]) for position in flat_index],
        [int(sd[position]) for position in flat_index],
    )


def _timeline(aoi_id: str, weights: list[float], flat_index: list[int], cf: float) -> list[dict]:
    covered = sum(weights)
    rows = []
    for year in TIMELINE_YEARS:
        agb, _ = _bands(aoi_id, year, flat_index)
        total_tc = sum(weight * value * cf for weight, value in zip(weights, agb))
        rows.append({
            "year": year,
            "total_tc": round(total_tc, 6),
            "mean_tc_ha": round(total_tc / covered, 9),
            "mean_agb_t_ha": round(
                sum(weight * value for weight, value in zip(weights, agb)) / covered, 9
            ),
            "cells": len(weights),
            "covered_ha": round(covered, 6),
        })
    return rows


def build(
    *,
    request_id: str,
    aoi_id: str,
    bbox: tuple[float, float, float, float],
    year_start: int,
    year_end: int,
    cf: float,
    catalogue: dict[str, dict[str, str]],
) -> dict:
    with rasterio.open(REPO_ROOT / "data" / aoi_id / f"CCI_Biomass_{year_start}.tif") as ds:
        geometry = _cell_weights(ds, bbox)
        width = ds.shape[1]
    weights = geometry["weight_ha"]
    flat_index = geometry["flat_index"]

    observations = {}
    sources = []
    for year in (year_start, year_end):
        agb, sd = _bands(aoi_id, year, flat_index)
        observations[str(year)] = {"agb_t_ha": agb, "agb_sd_t_ha": sd}
        relative = f"{aoi_id}/CCI_Biomass_{year}.tif"
        entry = catalogue[relative]
        sources.append({
            "relative_path": relative,
            "source_ids": entry["source_ids"],
            "product_version": entry["product_version"],
            "period": entry["observation_or_scenario_period"],
            "sha256": entry["sha256"],
            "recomputed_sha256": _sha256(REPO_ROOT / "data" / relative),
        })

    covered = sum(weights)
    requested = _box_area_ha(*bbox)
    timeline = _timeline(aoi_id, weights, flat_index, cf)
    by_year = {row["year"]: row for row in timeline}
    delta_tc = by_year[year_end]["total_tc"] - by_year[year_start]["total_tc"]

    features = []
    for position, (row, weight) in enumerate(zip(flat_index, weights)):
        features.append({
            "type": "Feature",
            # The engine reads properties only. Cell outlines are RS's to publish and
            # would multiply this test file by twenty for values nothing here uses.
            "geometry": None,
            "properties": {
                "cell_id": f"{aoi_id}:{row // width:04d}:{row % width:04d}",
                "parent_aoi_id": aoi_id,
                "weight_ha": weight,
                "agb_t_ha": {str(year): observations[str(year)]["agb_t_ha"][position]
                             for year in (year_start, year_end)},
                "agb_sd_t_ha": {str(year): observations[str(year)]["agb_sd_t_ha"][position]
                                for year in (year_start, year_end)},
                "valid": True,
            },
        })

    return {
        "schema": SCHEMA,
        "status": "PROVISIONAL_LOCAL_EXTRACTION",
        "produced_by": "carbon/tests/fixtures/build_cells.py",
        "note": (
            "Not an RS result. Extracted from data/ so the carbon tests can lock real "
            "numbers before the RS per-cell layer is available. Test input only: "
            "carbon.rs_adapter.guard_production_input refuses it for a published result."
        ),
        "request": {
            "request_id": request_id,
            "parent_aoi_id": aoi_id,
            "parents": [aoi_id],
            "bbox_wgs84": [round(value, 9) for value in bbox],
            "year_start": year_start,
            "year_end": year_end,
            "years": [year_start, year_end],
            "area_ha": round(requested, 6),
            "pool": "AGB",
        },
        "grid": {"crs": "EPSG:4326", "cell_size_deg": 0.0008888888888888889,
                 "description": "native ESA CCI cells, not resampled"},
        "stock_change": {
            "stock_start_tc": by_year[year_start]["total_tc"],
            "stock_end_tc": by_year[year_end]["total_tc"],
            "delta_tc": round(delta_tc, 6),
            "e_tco2e": round(-delta_tc * CO2_PER_C, 6),
            "sign_convention": "POSITIVE_E_MEANS_POOL_LOSS",
        },
        "coverage": {
            "requested_ha": round(requested, 6),
            "calculated_ha": round(covered, 6),
            "missing_ha": round(max(0.0, requested - covered), 6),
            "complete": max(0.0, requested - covered) <= 1e-4,
            "biomass": {"area_ha": round(covered, 6), "fraction": covered / requested},
            "biomass_sd": {"area_ha": round(covered, 6), "fraction": covered / requested},
            "optical_paired": {"area_ha": 0.0, "fraction": 0.0},
            "note": (
                "every supplied cell carries a value and the catalogue declares no "
                "nodata, so a zero is zero biomass, not a gap; optical masking is RS work"
            ),
        },
        "cells": {
            "type": "FeatureCollection", "name": "cci_cells",
            "note": "cell outlines are omitted: this is a test input, not a map layer",
            "features": features,
        },
        "timeline": timeline,
        "sources": sources,
    }


def main() -> None:
    areas = {row["aoi_id"]: row for row in _read_csv(REPO_ROOT / "data" / "areas.csv")}
    catalogue = {
        row["relative_path"]: row
        for row in _read_csv(REPO_ROOT / "data" / "file_catalog.csv")
    }
    parameters = {
        row["parameter"]: row["value"]
        for row in _read_csv(REPO_ROOT / "data" / "methodology" / "parameters.csv")
    }
    cf = float(parameters["CF_AGB"])

    requests = [
        {
            "request_id": aoi_id,
            "aoi_id": aoi_id,
            "bbox": (
                float(row["bbox_west"]), float(row["bbox_south"]),
                float(row["bbox_east"]), float(row["bbox_north"]),
            ),
            "year_start": int(row["analysis_start_year"]),
            "year_end": int(row["analysis_end_year"]),
        }
        for aoi_id, row in areas.items()
    ]

    sample = json.loads(
        (REPO_ROOT / "data" / "sample_requests.geojson").read_text(encoding="utf-8")
    )
    for feature in sample["features"]:
        properties = feature["properties"]
        ring = feature["geometry"]["coordinates"][0]
        longitudes = [point[0] for point in ring]
        latitudes = [point[1] for point in ring]
        requests.append({
            "request_id": properties["request_id"],
            "aoi_id": properties["parent_aoi_id"],
            "bbox": (min(longitudes), min(latitudes), max(longitudes), max(latitudes)),
            "year_start": properties["year_start"],
            "year_end": properties["year_end"],
        })

    for request in requests:
        payload = build(cf=cf, catalogue=catalogue, **request)
        path = FIXTURE_DIR / f"cells_{request['request_id']}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        print(
            f"{path.name}: {len(payload['cells']['features'])} cells, "
            f"{payload['coverage']['calculated_ha']} ha"
        )


if __name__ == "__main__":
    main()
