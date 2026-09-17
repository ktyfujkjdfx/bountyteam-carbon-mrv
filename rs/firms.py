"""NASA FIRMS active-fire hotspots as independent thermal-anomaly support.

FIRMS points are NOT a fire perimeter or ground truth (manifest 10.6 / RS plan
5.6). The public "area" API requires a free self-service MAP_KEY
(https://firms.modaps.eosdis.nasa.gov/api/); without one configured via the
FIRMS_MAP_KEY environment variable this honestly reports NOT_CHECKED rather
than fabricating hotspots, exactly as the schema's `support` enum allows.
"""
import csv
import io
import os
import urllib.request

from pyproj import Transformer
from shapely.geometry import Point

SPATIAL_TOLERANCE_M = 500  # frozen demo tolerance (contracts/*.schema.json)
AREA_API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{product}/{bbox}/{days}/{date}"


def fetch_hotspots(bbox_wgs84, start_date, end_date, product="VIIRS_SNPP_NRT"):
    """Query FIRMS for hotspots in bbox/date window. Returns None if no MAP_KEY."""
    key = os.environ.get("FIRMS_MAP_KEY")
    if not key:
        return None
    days = max(1, (end_date.date() - start_date.date()).days + 1)
    west, south, east, north = bbox_wgs84
    url = AREA_API.format(
        key=key,
        product=product,
        bbox=f"{west},{south},{east},{north}",
        days=days,
        date=start_date.date().isoformat(),
    )
    with urllib.request.urlopen(url, timeout=30) as response:
        text = response.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def match_within_aoi(hotspots, aoi_geometry_wgs84, tolerance_m=SPATIAL_TOLERANCE_M):
    """Filter hotspots within `tolerance_m` of the AOI polygon."""
    from shapely.geometry import shape

    aoi = shape(aoi_geometry_wgs84)
    centroid = aoi.centroid
    to_metric = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    to_wgs = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    aoi_metric_coords = [to_metric.transform(x, y) for x, y in aoi.exterior.coords]
    from shapely.geometry import Polygon

    aoi_metric = Polygon(aoi_metric_coords).buffer(tolerance_m)
    matched = []
    for point in hotspots:
        lon, lat = float(point["longitude"]), float(point["latitude"])
        mx, my = to_metric.transform(lon, lat)
        if aoi_metric.contains(Point(mx, my)):
            matched.append(point)
    return matched
