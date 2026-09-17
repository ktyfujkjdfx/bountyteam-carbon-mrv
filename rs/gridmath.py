"""Grid construction: one shared north-up 20 m UTM/metric grid per request."""
import math

from pyproj import Transformer


def utm_epsg(lon, lat):
    """WGS84 UTM EPSG code for a longitude/latitude point."""
    zone = int(math.floor((lon + 180) / 6) % 60) + 1
    return (32600 if lat >= 0 else 32700) + zone


def bounds_wgs84(geometry):
    coords = geometry["coordinates"]
    xs, ys = [], []

    def _walk(node):
        if isinstance(node[0], (int, float)):
            xs.append(node[0])
            ys.append(node[1])
        else:
            for child in node:
                _walk(child)

    _walk(coords)
    return min(xs), min(ys), max(xs), max(ys)


def snapped_grid(geometry, epsg, resolution_m=20):
    """Snap the AOI bounds outward to a resolution-aligned grid in `epsg`.

    Returns (transform_tuple, width, height, utm_bounds) with transform in the
    rasterio Affine 6-tuple order (a, b, c, d, e, f), north-up, a=resolution,
    e=-resolution, matching the frozen v1 grid contract.
    """
    west, south, east, north = bounds_wgs84(geometry)
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    xs, ys = transformer.transform([west, east, west, east], [south, south, north, north])
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_x = math.floor(min_x / resolution_m) * resolution_m
    min_y = math.floor(min_y / resolution_m) * resolution_m
    max_x = math.ceil(max_x / resolution_m) * resolution_m
    max_y = math.ceil(max_y / resolution_m) * resolution_m
    width = int(round((max_x - min_x) / resolution_m))
    height = int(round((max_y - min_y) / resolution_m))
    transform = (resolution_m, 0, min_x, 0, -resolution_m, max_y)
    return transform, width, height, (min_x, min_y, max_x, max_y)


def grid_bounds_wgs84(transform, width, height, epsg):
    """[west, south, east, north] of the full grid extent, in EPSG:4326."""
    a, b, c, d, e, f = transform
    min_x, max_y = c, f
    max_x = c + a * width
    min_y = f + e * height
    transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    xs, ys = transformer.transform([min_x, max_x], [min_y, max_y])
    return [min(xs), min(ys), max(xs), max(ys)]
