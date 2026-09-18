"""Provenance of a carbon result: which official files, which versions, which licences.

Everything here comes from the organisers' `data/`: `file_catalog.csv` lists every
supplied raster with its declared SHA-256, and `sources.csv` lists the products with
version, licence, attribution and stated limitations. The passport repeats those records
rather than describing the data in its own words, and `verify_files` recomputes the
digests so a passport cannot claim a file it never read.

A declared checksum that matches proves the file is the supplied one. It does not prove
the measurement is correct, and the passport says so.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .parameters import DEFAULT_PARAMETERS, METHOD_VERSION, REPO_ROOT, CaseParameters

DATA_ROOT = REPO_ROOT / "data"
FILE_CATALOG_CSV = DATA_ROOT / "file_catalog.csv"
SOURCES_CSV = DATA_ROOT / "sources.csv"
AREAS_CSV = DATA_ROOT / "areas.csv"

CHECKSUM_OK = "MATCHES_CATALOGUE"
CHECKSUM_MISMATCH = "DIFFERS_FROM_CATALOGUE"
CHECKSUM_MISSING = "NOT_IN_CATALOGUE"
CHECKSUM_UNREADABLE = "FILE_NOT_FOUND"


@dataclass(frozen=True)
class FileRecord:
    relative_path: str
    aoi_id: str
    source_ids: str
    product_version: str
    period: str
    units: str
    crs: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    product: str
    version: str
    kind: str
    primary_url: str
    doi: str
    license_url: str
    required_attribution: str
    access_date: str
    limitations: str


@dataclass(frozen=True)
class FileCheck:
    relative_path: str
    declared_sha256: str
    computed_sha256: str | None
    status: str

    @property
    def ok(self) -> bool:
        return self.status == CHECKSUM_OK


def _rows(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_file_catalogue(path: Path = FILE_CATALOG_CSV) -> dict[str, FileRecord]:
    return {
        row["relative_path"]: FileRecord(
            relative_path=row["relative_path"],
            aoi_id=row["aoi_id"],
            source_ids=row["source_ids"],
            product_version=row["product_version"],
            period=row["observation_or_scenario_period"],
            units=row["units"],
            crs=row["crs"],
            size_bytes=int(row["size_bytes"]),
            sha256=row["sha256"],
        )
        for row in _rows(path)
    }


def load_sources(path: Path = SOURCES_CSV) -> dict[str, SourceRecord]:
    return {
        row["source_id"]: SourceRecord(
            source_id=row["source_id"],
            product=row["product"],
            version=row["version"],
            kind=row["kind"],
            primary_url=row["primary_url"],
            doi=row["doi"],
            license_url=row["license_url"],
            required_attribution=row["required_attribution"],
            access_date=row["access_date"],
            limitations=row["limitations"],
        )
        for row in _rows(path)
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_files(
    relative_paths: list[str],
    *,
    catalogue: dict[str, FileRecord] | None = None,
    data_root: Path = DATA_ROOT,
) -> tuple[FileCheck, ...]:
    """Recompute the digest of each supplied file and compare it with the catalogue."""
    table = load_file_catalogue() if catalogue is None else catalogue
    checks = []
    for relative in relative_paths:
        record = table.get(relative)
        if record is None:
            checks.append(FileCheck(relative, "", None, CHECKSUM_MISSING))
            continue
        path = Path(data_root) / relative
        if not path.is_file():
            checks.append(FileCheck(relative, record.sha256, None, CHECKSUM_UNREADABLE))
            continue
        computed = file_sha256(path)
        status = CHECKSUM_OK if computed == record.sha256 else CHECKSUM_MISMATCH
        checks.append(FileCheck(relative, record.sha256, computed, status))
    return tuple(checks)


def parameters_snapshot(parameters: CaseParameters = DEFAULT_PARAMETERS) -> dict[str, object]:
    """The exact coefficients a result was produced with, for the passport."""
    return {
        "cf_agb": parameters.cf_agb,
        "co2_per_c": parameters.co2_per_c,
        "co2_per_c_exact": "44/12",
        "unc_allowance": parameters.unc_allowance,
        "unc_stop_ratio": parameters.unc_stop_ratio,
        "buffer_share": parameters.buffer_share,
        "unit_share": 1.0 - parameters.buffer_share,
        "leakage_tco2e": parameters.leakage_tco2e,
        "prices_rub": list(parameters.prices_rub),
        "history_start_year": parameters.history_start_year,
        "history_end_year": parameters.history_end_year,
        "scenario_end_year": parameters.scenario_end_year,
        "source": "data/methodology/parameters.csv",
    }


def build_provenance(
    *,
    relative_paths: list[str],
    parameters: CaseParameters = DEFAULT_PARAMETERS,
    catalogue: dict[str, FileRecord] | None = None,
    sources: dict[str, SourceRecord] | None = None,
    data_root: Path = DATA_ROOT,
    extra_inputs: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Provenance block of the passport: files, their digests, products and licences."""
    table = load_file_catalogue() if catalogue is None else catalogue
    catalogue_sources = load_sources() if sources is None else sources
    checks = verify_files(relative_paths, catalogue=table, data_root=data_root)

    used_source_ids: list[str] = []
    files = []
    for check in checks:
        record = table.get(check.relative_path)
        entry: dict[str, object] = {
            "relative_path": check.relative_path,
            "declared_sha256": check.declared_sha256,
            "computed_sha256": check.computed_sha256,
            "checksum_status": check.status,
        }
        if record is not None:
            entry.update({
                "aoi_id": record.aoi_id,
                "source_ids": record.source_ids,
                "product_version": record.product_version,
                "period": record.period,
                "units": record.units,
                "crs": record.crs,
                "size_bytes": record.size_bytes,
            })
            for source_id in record.source_ids.split(";"):
                cleaned = source_id.strip()
                if cleaned and cleaned not in used_source_ids:
                    used_source_ids.append(cleaned)
        files.append(entry)

    return {
        "official_roots": ["data/", "doc/"],
        "files": files,
        "all_checksums_match": all(check.ok for check in checks),
        "sources": [
            {
                "source_id": record.source_id,
                "product": record.product,
                "version": record.version,
                "kind": record.kind,
                "primary_url": record.primary_url,
                "doi": record.doi,
                "license_url": record.license_url,
                "required_attribution": record.required_attribution,
                "access_date": record.access_date,
                "limitations": record.limitations,
            }
            for source_id in used_source_ids
            if (record := catalogue_sources.get(source_id)) is not None
        ],
        "parameters": parameters_snapshot(parameters),
        "method_version": METHOD_VERSION,
        "extra_inputs": list(extra_inputs or []),
        "note": (
            "Совпадение контрольной суммы подтверждает, что использован именно "
            "предоставленный файл. Оно не подтверждает правильность самой оценки."
        ),
    }
