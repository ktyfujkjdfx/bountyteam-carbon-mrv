"""RS evidence acceptance: schema, cross-field semantics, geometry, safe paths and file hashes.

Mirrors the frozen reference validator (tools/contract_helpers.validate_evidence);
backend/tests/test_evidence.py checks both agree. Any failure rejects the import
before policy, decision or chain action.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from .contracts import digest, evidence_validator, loads_json, schema_errors, sha256_hex
from .policy import Policy

REQUIRED_ANALYSABLE_ROLES = {"AFFECTED_AREA", "DNBR_RASTER", "PREVIEW_BEFORE", "PREVIEW_AFTER"}
EXPECTED_MEDIA = {"AFFECTED_AREA": "application/geo+json", "FIRMS_POINTS": "application/geo+json",
                  "DNBR_RASTER": "image/tiff"}


class EvidenceRejected(ValueError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class Limits:
    max_artifact_bytes: int = 64 * 1024 * 1024
    max_bundle_bytes: int = 512 * 1024 * 1024


def _reject(message: str, **details: Any) -> None:
    raise EvidenceRejected(message, details)


def _utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def finite_tree(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        _reject("Non-finite number")
    if isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)


def safe_path(root: Path, relative: str) -> Path:
    base = Path(root).resolve()
    given = Path(relative)
    if given.is_absolute() or ".." in given.parts or "\\" in relative:
        _reject("Unsafe relative path", relative_path=relative)
    path = base / given
    for candidate in [path, *path.parents]:
        if candidate == base:
            break
        if candidate.is_symlink():
            _reject("Symlink in bundle", relative_path=relative)
    if not path.resolve().is_relative_to(base):
        _reject("Path escapes bundle", relative_path=relative)
    if not path.is_file():
        _reject("Missing bundle file", relative_path=relative)
    return path


def _close(actual: Any, expected: float, field: str, tolerance: float = 0.0000011) -> None:
    if actual is None or abs(float(actual) - float(expected)) > tolerance:
        _reject("Inconsistent " + field, field=field)


def validate_geometry(geometry: dict) -> None:
    try:
        geom = shape(geometry)
    except Exception:
        _reject("Invalid GeoJSON geometry")
    if geom.is_empty or not geom.is_valid or geom.geom_type not in ("Polygon", "MultiPolygon"):
        _reject("Invalid polygon")
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for polygon in polygons:
        for ring in polygon:
            if ring[0] != ring[-1]:
                _reject("Unclosed GeoJSON ring")
    west, south, east, north = geom.bounds
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        _reject("Invalid WGS84 coordinates")


def validate_evidence(evidence: Any, policy: Policy, *, bundle_root: Path | None = None,
                      geometry: dict | None = None, limits: Limits = Limits()) -> dict:
    """Return the policy classification of an accepted evidence or raise EvidenceRejected."""
    if not isinstance(evidence, dict):
        _reject("Evidence must be a JSON object")
    finite_tree(evidence)
    errors = schema_errors(evidence_validator(), evidence)
    if errors:
        _reject("Evidence does not match verification.schema.json", schema_errors=errors)

    before = evidence["observation"]["before"]
    after = evidence["observation"]["after"]
    if _utc(before["acquired_at"]) >= _utc(after["acquired_at"]):
        _reject("Invalid observation chronology")
    if geometry is not None:
        validate_geometry(geometry)
        if digest(geometry) != evidence["plot_geometry_hash"]:
            _reject("Wrong plot geometry hash")

    m, q, method = evidence["metrics"], evidence["quality"], evidence["method"]
    if method["config_sha256"] != digest(method["parameters"]):
        _reject("Wrong processing config hash")
    grid = method["grid"]
    if grid:
        a, b, _c, d, f, _g = grid["transform"]
        if b != 0 or d != 0 or a != 20 or f != -20:
            _reject("v1 requires north-up 20 m grid")
        if not (32601 <= grid["epsg"] <= 32660 or 32701 <= grid["epsg"] <= 32760):
            _reject("v1 grid must use WGS84 UTM metres", epsg=grid["epsg"])
        if evidence["outcome"] != "INSUFFICIENT_DATA" and m["baseline_forest_pixel_count"] is None:
            _reject("Missing pixel counts")
        n, v, k = m["baseline_forest_pixel_count"], m["paired_valid_forest_pixel_count"], m["affected_pixel_count"]
        if n is not None:
            if n <= 0 or n > grid["width"] * grid["height"]:
                _reject("Invalid forest count")
            _close(m["baseline_forest_area_ha"], n * 0.04, "forest area")
        if v is not None and n is not None:
            if not 0 <= v <= n:
                _reject("Invalid valid count")
            _close(m["analysed_forest_area_ha"], v * 0.04, "analysed area")
            _close(q["paired_valid_forest_ratio"], v / n, "valid ratio")
        if k is not None and n is not None and v is not None:
            if not 0 <= k <= v:
                _reject("Invalid affected count")
            if 0 < k < 25:
                _reject("Below minimum connected-component area")
            _close(m["affected_area_ha"], k * 0.04, "affected area")
            _close(m["affected_fraction_of_baseline_forest"], k / n, "affected fraction")
    else:
        if q["grid_aligned"]:
            _reject("No grid but grid_aligned=true")
        if evidence["outcome"] != "INSUFFICIENT_DATA":
            _reject("Missing grid")

    artifacts = evidence["artifacts"]
    ids = [x["artifact_id"] for x in artifacts]
    roles = [x["role"] for x in artifacts]
    paths = [x["relative_path"] for x in artifacts]
    if len(set(ids)) != len(ids) or len(set(paths)) != len(paths) or len(set(roles)) != len(roles):
        _reject("Duplicate artifact identity/role/path")
    if evidence["outcome"] != "INSUFFICIENT_DATA":
        if not REQUIRED_ANALYSABLE_ROLES <= set(roles):
            _reject("Missing analysable evidence artifacts")
        for scene in (before, after):
            if sorted(asset["band"] for asset in scene["assets"]) != ["B04", "B08", "B12", "B8A", "SCL"]:
                _reject("Expected exactly five input bands")
    for art in artifacts:
        expected = EXPECTED_MEDIA.get(art["role"])
        if expected and art["media_type"] != expected:
            _reject("Wrong artifact MIME", artifact_id=art["artifact_id"])
        if "bounds_wgs84" in art:
            w, s, e, n_ = art["bounds_wgs84"]
            if not w < e or not s < n_:
                _reject("Invalid preview bounds", artifact_id=art["artifact_id"])
    previews = [a for a in artifacts if a["role"] in ("PREVIEW_BEFORE", "PREVIEW_AFTER")]
    if len(previews) == 2 and any(previews[0][f] != previews[1][f] for f in ("width", "height", "bounds_wgs84")):
        _reject("Unaligned previews")

    firms = evidence["firms"]
    if (firms["window_start"], firms["window_end"]) != (before["acquired_at"], after["acquired_at"]):
        _reject("FIRMS window differs from comparison")
    if firms["support"] == "SUPPORTED" and (firms["matched_points_artifact_id"] not in ids or firms["hotspot_count"] < 1):
        _reject("Missing FIRMS supporting artifact")
    if firms["support"] != "SUPPORTED" and firms["hotspot_count"] != 0:
        _reject("hotspot_count means matched usable detections, not all nearby points")

    if bundle_root is not None:
        _verify_bundle_files(evidence, Path(bundle_root), limits)

    result = policy.evaluate(evidence)
    if result["evidence_quality"] == "INSUFFICIENT" and evidence["outcome"] != "INSUFFICIENT_DATA":
        _reject("Outcome claims analysis despite insufficient data")
    if result["evidence_quality"] != "INSUFFICIENT":
        k = m["affected_pixel_count"]
        if k is None:
            _reject("Analysable report needs affected count")
        if evidence["outcome"] != ("DISTURBANCE_DETECTED" if k > 0 else "NO_CHANGE"):
            _reject("Outcome disagrees with counts/gates")
    return result


def _read_limited(path: Path, limit: int, relative: str) -> bytes:
    size = path.stat().st_size
    if size > limit:
        _reject("Oversized bundle file", relative_path=relative, size_bytes=size)
    return path.read_bytes()


def _verify_bundle_files(evidence: dict, root: Path, limits: Limits) -> None:
    total = 0
    for art in evidence["artifacts"]:
        path = safe_path(root, art["relative_path"])
        data = _read_limited(path, limits.max_artifact_bytes, art["relative_path"])
        total += len(data)
        if len(data) != art["size_bytes"] or sha256_hex(data) != art["sha256"]:
            _reject("Artifact checksum/size mismatch", artifact_id=art["artifact_id"])
    if total > limits.max_bundle_bytes:
        _reject("Oversized bundle outputs")
    index_path = safe_path(root, "source-index.json")
    try:
        index = loads_json(_read_limited(index_path, 1024 * 1024, "source-index.json"))
    except ValueError:
        _reject("Corrupt source-index.json")
    if not isinstance(index, dict):
        _reject("Corrupt source-index.json")
    scenes = (evidence["observation"]["before"], evidence["observation"]["after"])
    hashes = [asset["local_sha256"] for scene in scenes for asset in scene["assets"]]
    if evidence["method"]["forest_mask"]:
        hashes.append(evidence["method"]["forest_mask"]["sha256"])
    for expected in hashes:
        if expected not in index or not isinstance(index[expected], str):
            _reject("Missing source cache entry", sha256=expected)
        source = safe_path(root, index[expected])
        if sha256_hex(_read_limited(source, limits.max_bundle_bytes, index[expected])) != expected:
            _reject("Source checksum mismatch", sha256=expected)
