"""Request geometry: validation, geodesic area and the support it is analysed on.

Area is geodesic on the WGS84 ellipsoid. On the CCI grid a step in degrees is
not a hectare, and at these latitudes a cell is nowhere near 1 ha, so every area
in the analysis comes from here rather than from a pixel count.
"""
from pyproj import Geod
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from rs.case2.models import MAX_AREA_HA

GEOD = Geod(ellps="WGS84")
LON_LIMIT = 180.0
LAT_LIMIT = 90.0


class GeometryError(ValueError):
    """The request geometry cannot be analysed and must not be repaired silently."""


def geodesic_area_ha(geometry):
    """Geodesic area on the WGS84 ellipsoid, in hectares."""
    area, _perimeter = GEOD.geometry_area_perimeter(geometry)
    return abs(area) / 10_000.0


def load_geometry(value):
    """Build a geometry from a GeoJSON mapping, Feature, FeatureCollection or shape."""
    if isinstance(value, BaseGeometry):
        return value
    if not isinstance(value, dict):
        raise GeometryError(f"unsupported geometry input of type {type(value).__name__}")
    kind = value.get("type")
    if kind == "FeatureCollection":
        features = value.get("features") or []
        if len(features) != 1:
            raise GeometryError(
                f"expected exactly one feature in the request, found {len(features)}"
            )
        return load_geometry(features[0])
    if kind == "Feature":
        return load_geometry(value.get("geometry"))
    try:
        return shape(value)
    except Exception as exc:  # noqa: BLE001 - surface the original reason
        raise GeometryError(f"geometry is not readable as GeoJSON: {exc}") from exc


def validate(geometry, *, max_area_ha=MAX_AREA_HA):
    """Return a validated request geometry or explain why it is unusable.

    Nothing is repaired. A self-intersection is a different polygon once fixed,
    so a caller that wants the repaired shape must pass it in explicitly and
    accept the new geometry, and the new hash that comes with it.
    """
    geom = load_geometry(geometry)
    if geom.is_empty:
        raise GeometryError("geometry is empty")
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise GeometryError(
            f"geometry must be a Polygon or MultiPolygon, got {geom.geom_type}"
        )
    if not geom.is_valid:
        from shapely.validation import explain_validity

        raise GeometryError(
            f"geometry is not valid and is not repaired automatically: "
            f"{explain_validity(geom)}"
        )
    lon_min, lat_min, lon_max, lat_max = geom.bounds
    if not (-LON_LIMIT <= lon_min and lon_max <= LON_LIMIT):
        raise GeometryError(
            f"longitude {lon_min}..{lon_max} is outside WGS84; coordinates must be "
            f"lon/lat, not lat/lon or a projected CRS"
        )
    if not (-LAT_LIMIT <= lat_min and lat_max <= LAT_LIMIT):
        raise GeometryError(
            f"latitude {lat_min}..{lat_max} is outside WGS84; coordinates must be "
            f"lon/lat, not lat/lon or a projected CRS"
        )
    area = geodesic_area_ha(geom)
    if area <= 0:
        raise GeometryError("geometry has no area")
    if area > max_area_ha:
        raise GeometryError(
            f"requested area {area:.4f} ha exceeds the {max_area_ha:.0f} ha limit"
        )
    return geom


def validate_years(year_start, year_end, *, minimum, maximum):
    """Check the requested period against the years the case allows."""
    if not isinstance(year_start, int) or not isinstance(year_end, int):
        raise GeometryError("years must be integers")
    if year_start >= year_end:
        raise GeometryError(
            f"year_start {year_start} must be earlier than year_end {year_end}"
        )
    if year_start < minimum or year_end > maximum:
        raise GeometryError(
            f"period {year_start}-{year_end} is outside the supported "
            f"{minimum}-{maximum} range"
        )
    return year_start, year_end
