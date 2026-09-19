"""Request geometry: validation, canonical form, geodesic area and the geometry hash.

Area is geodesic on the WGS84 ellipsoid, with the same `pyproj.Geod` call the raster core
uses, so the hectares in a Backend response and the hectares in an RS payload are the same
number rather than two plausible ones.

Nothing is repaired. A self-intersection fixed silently is a different polygon with a
different area and a different hash, and the caller would never learn that the thing they
asked about is not the thing that was measured.
"""
from __future__ import annotations

from typing import Any

from pyproj import Geod
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from ..errors import ApiError, invalid
from .contracts import digest

GEOD = Geod(ellps="WGS84")
YEAR_MIN = 2019
YEAR_MAX = 2024
MAX_AREA_HA = 2000.0
COORDINATE_DECIMALS = 7
MAX_RING_POINTS = 10_000


def geodesic_area_ha(geom: BaseGeometry) -> float:
    area, _perimeter = GEOD.geometry_area_perimeter(geom)
    return abs(area) / 10_000.0


def _fail(code: str, message: str, **details: Any) -> ApiError:
    return invalid(code, message, **details)


def load(value: Any) -> BaseGeometry:
    """Accept a GeoJSON geometry, Feature or single-feature FeatureCollection."""
    if isinstance(value, BaseGeometry):
        return value
    if not isinstance(value, dict):
        raise _fail("INVALID_GEOMETRY", "geometry must be a GeoJSON object")
    kind = value.get("type")
    if kind == "FeatureCollection":
        features = value.get("features") or []
        if len(features) != 1:
            raise _fail("INVALID_GEOMETRY", "the request must carry exactly one feature",
                        features=len(features))
        return load(features[0])
    if kind == "Feature":
        return load(value.get("geometry"))
    try:
        return shape(value)
    except Exception:
        raise _fail("INVALID_GEOMETRY", "geometry is not readable as GeoJSON") from None


def _count_points(geom: BaseGeometry) -> int:
    polygons = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    return sum(len(ring.coords)
               for polygon in polygons
               for ring in (polygon.exterior, *polygon.interiors))


def validate(value: Any, *, max_area_ha: float = MAX_AREA_HA) -> tuple[BaseGeometry, float]:
    """Return the validated geometry and its geodesic area, or raise a typed 422."""
    geom = load(value)
    if geom.is_empty:
        raise _fail("INVALID_GEOMETRY", "geometry is empty")
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise _fail("INVALID_GEOMETRY", "geometry must be a Polygon or a MultiPolygon",
                    geometry_type=geom.geom_type)
    if not geom.is_valid:
        raise _fail("INVALID_GEOMETRY",
                    "geometry is not valid and is never repaired automatically")
    if _count_points(geom) > MAX_RING_POINTS:
        raise _fail("INVALID_GEOMETRY", "geometry has too many coordinates",
                    max_points=MAX_RING_POINTS)
    lon_min, lat_min, lon_max, lat_max = geom.bounds
    if not (-180.0 <= lon_min and lon_max <= 180.0):
        raise _fail("INVALID_GEOMETRY",
                    "longitude is outside WGS84; coordinates must be lon/lat")
    if not (-90.0 <= lat_min and lat_max <= 90.0):
        raise _fail("INVALID_GEOMETRY",
                    "latitude is outside WGS84; coordinates must be lon/lat")
    area = geodesic_area_ha(geom)
    if area <= 0.0:
        raise _fail("INVALID_GEOMETRY", "geometry has no area")
    if area > max_area_ha:
        raise ApiError(422, "AREA_TOO_LARGE",
                       f"Requested area exceeds the limit of {max_area_ha:.0f} ha",
                       {"area_ha": round(area, 4), "max_area_ha": max_area_ha})
    return geom, area


def validate_years(year_start: Any, year_end: Any) -> tuple[int, int]:
    if not isinstance(year_start, int) or not isinstance(year_end, int) \
            or isinstance(year_start, bool) or isinstance(year_end, bool):
        raise _fail("INVALID_PERIOD", "years must be integers")
    if year_start >= year_end:
        raise _fail("INVALID_PERIOD", "year_end must be greater than year_start",
                    year_start=year_start, year_end=year_end)
    if year_start < YEAR_MIN or year_end > YEAR_MAX:
        raise _fail("INVALID_PERIOD",
                    f"period is outside the supported {YEAR_MIN}-{YEAR_MAX} range",
                    year_start=year_start, year_end=year_end)
    return year_start, year_end


def _round(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, COORDINATE_DECIMALS) + 0.0
    if isinstance(value, int):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_round(item) for item in value]
    return value


def canonical_geometry(geom: BaseGeometry) -> dict:
    """GeoJSON at a fixed precision, so the same contour hashes the same on every machine."""
    payload = mapping(geom)
    return {"type": payload["type"], "coordinates": _round(payload["coordinates"])}


def geometry_hash(geom: BaseGeometry) -> str:
    return digest(canonical_geometry(geom))
