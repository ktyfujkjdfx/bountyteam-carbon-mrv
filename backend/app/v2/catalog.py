"""The supplied dataset as the API sees it.

Everything here is read from `data/`: the area register, the polygons, the sample
sub-request, the source register and the case parameters. Nothing is hard-coded, because
a coefficient typed into Python is a coefficient nobody can audit against the CSV it was
supposed to come from.

The official CSVs are UTF-8 with a byte order mark and are read as `utf-8-sig`. Reading
them as plain UTF-8 turns the first column name into `﻿aoi_id`, and every lookup
against it then silently misses.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT
from ..contracts import read_json, sha256_hex
from .contracts import digest

DATA_ROOT = REPO_ROOT / "data"
DATASET_VERSION = "sr-data-case2/2026-09-16"
BIOMASS_YEAR = re.compile(r"^CCI_Biomass_(\d{4})\.tif$")
PRICE_KEYS = (("low", "price_low"), ("base", "price_base"), ("high", "price_high"))


def _rows(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class Area:
    aoi_id: str
    name: str
    region: str
    area_ha: float
    analysis_start_year: int
    analysis_end_year: int
    selection_role: str
    project_status: str
    baseline_id: str
    bbox: tuple[float, float, float, float]
    geometry: dict
    available_years: tuple[int, ...]


@lru_cache(maxsize=None)
def _geometries(root: Path) -> dict[str, dict]:
    collection = read_json(root / "areas.geojson")
    return {feature["properties"]["aoi_id"]: feature["geometry"]
            for feature in collection["features"]}


@lru_cache(maxsize=None)
def _available_years(root: Path, aoi_id: str) -> tuple[int, ...]:
    directory = root / aoi_id
    if not directory.is_dir():
        return ()
    years = {int(match.group(1))
             for entry in directory.iterdir()
             if (match := BIOMASS_YEAR.match(entry.name))}
    return tuple(sorted(years))


@lru_cache(maxsize=None)
def areas(root: Path = DATA_ROOT) -> tuple[Area, ...]:
    geometries = _geometries(root)
    collected = []
    for row in _rows(root / "areas.csv"):
        aoi_id = row["aoi_id"]
        collected.append(Area(
            aoi_id=aoi_id,
            name=row["name"],
            region=row["region"],
            area_ha=float(row["area_ha"]),
            analysis_start_year=int(row["analysis_start_year"]),
            analysis_end_year=int(row["analysis_end_year"]),
            selection_role=row["selection_role"],
            project_status=row["project_status"],
            baseline_id=row["baseline_id"],
            bbox=(float(row["bbox_west"]), float(row["bbox_south"]),
                  float(row["bbox_east"]), float(row["bbox_north"])),
            geometry=geometries[aoi_id],
            available_years=_available_years(root, aoi_id),
        ))
    return tuple(collected)


def area(aoi_id: str, root: Path = DATA_ROOT) -> Area | None:
    return next((item for item in areas(root) if item.aoi_id == aoi_id), None)


@lru_cache(maxsize=None)
def sample_requests(root: Path = DATA_ROOT) -> tuple[dict, ...]:
    collection = read_json(root / "sample_requests.geojson")
    return tuple({**feature["properties"], "geometry": feature["geometry"]}
                 for feature in collection["features"])


@lru_cache(maxsize=None)
def sources(root: Path = DATA_ROOT) -> tuple[dict, ...]:
    return tuple({
        "source_id": row["source_id"],
        "product": row["product"],
        "version": row["version"],
        "license_url": row["license_url"],
        "attribution": row["required_attribution"],
        "access_date": row["access_date"],
        "role": row["kind"],
    } for row in _rows(root / "sources.csv"))


def sources_by_id(root: Path = DATA_ROOT) -> dict[str, dict]:
    return {item["source_id"]: item for item in sources(root)}


@lru_cache(maxsize=None)
def events(root: Path = DATA_ROOT) -> tuple[dict, ...]:
    return tuple(_rows(root / "events.csv"))


@lru_cache(maxsize=None)
def parameters(root: Path = DATA_ROOT) -> dict[str, str]:
    return {row["parameter"]: row["value"] for row in _rows(root / "methodology" / "parameters.csv")}


def parse_number(value: str) -> float:
    """The official CO2_per_C is written as the ratio 44/12, not as a decimal."""
    text = value.strip().replace(",", ".")
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        return float(numerator) / float(denominator)
    return float(text)


def prices(root: Path = DATA_ROOT) -> tuple[tuple[str, float], ...]:
    table = parameters(root)
    return tuple((name, parse_number(table[key])) for name, key in PRICE_KEYS)


@lru_cache(maxsize=None)
def dataset_hash(root: Path = DATA_ROOT) -> str:
    """Hash of the supplied file register, which already carries every file's own sha256."""
    return sha256_hex((root / "file_catalog.csv").read_bytes())


@lru_cache(maxsize=None)
def parameters_hash(root: Path = DATA_ROOT) -> str:
    return sha256_hex((root / "methodology" / "parameters.csv").read_bytes())


def baseline_hash(root: Path = DATA_ROOT) -> str:
    return sha256_hex((root / "methodology" / "baseline.csv").read_bytes())


def source_manifest_hash(entries: list[dict]) -> str:
    """Hash over what a particular run actually read, not over the whole dataset."""
    return digest(sorted(entries, key=lambda item: item.get("path", "")))


def document(*, raster_adapter: str, carbon_adapter: str, schema_version: str,
             method_version: str, root: Path = DATA_ROOT) -> dict[str, Any]:
    from .geometry import MAX_AREA_HA, YEAR_MAX, YEAR_MIN

    return {
        "schema_version": schema_version,
        "method_version": method_version,
        "dataset_version": DATASET_VERSION,
        "dataset_hash": dataset_hash(root),
        "year_min": YEAR_MIN,
        "year_max": YEAR_MAX,
        "max_area_ha": MAX_AREA_HA,
        "raster_adapter": raster_adapter,
        "carbon_adapter": carbon_adapter,
        "areas": [{
            "aoi_id": item.aoi_id, "name": item.name, "region": item.region,
            "area_ha": item.area_ha, "analysis_start_year": item.analysis_start_year,
            "analysis_end_year": item.analysis_end_year, "selection_role": item.selection_role,
            "project_status": item.project_status, "baseline_id": item.baseline_id,
            "bbox": list(item.bbox), "geometry": item.geometry,
            "available_years": list(item.available_years),
        } for item in areas(root)],
        "sample_requests": [{
            "request_id": item["request_id"], "parent_aoi_id": item["parent_aoi_id"],
            "year_start": int(item["year_start"]), "year_end": int(item["year_end"]),
            "area_ha": float(item["area_ha"]), "purpose": item["purpose"],
            "baseline_rule": item["baseline_rule"], "geometry": item["geometry"],
        } for item in sample_requests(root)],
        "prices": [{"id": name, "rub_per_unit": value} for name, value in prices(root)],
        "sources": list(sources(root)),
    }
