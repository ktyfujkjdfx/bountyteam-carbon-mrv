"""NASA FIRMS active-fire hotspots as independent thermal-anomaly support.

FIRMS points are NOT a fire perimeter or ground truth (manifest 10.6 / RS plan
5.6); they are an independent thermal signal used only to say whether the
disturbance window contains detected fire activity.

Two sources, in this order:

1. The per-country yearly **archive** CSVs published openly at
   `https://firms.modaps.eosdis.nasa.gov/data/country/...`. These need no key
   and no account, so they are the default: the exact file is cached next to
   the scene rasters and the bundle reproduces offline, like every other input.
2. The near-real-time "area" API, which needs a free self-service MAP_KEY
   (https://firms.modaps.eosdis.nasa.gov/api/) supplied via `FIRMS_MAP_KEY`.

With neither available this reports NOT_CHECKED rather than fabricating
hotspots, exactly as the schema's `support` enum allows.
"""
import csv
import io
import os
import urllib.request
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point

SPATIAL_TOLERANCE_M = 500  # frozen demo tolerance (contracts/*.schema.json)
AREA_API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{product}/{bbox}/{days}/{date}"
ARCHIVE_URL = "https://firms.modaps.eosdis.nasa.gov/data/country/{product}/{year}/{product}_{year}_{country}.csv"
ARCHIVE_PRODUCT = "viirs-snpp"
# FIRMS VIIRS archive encodes confidence as a letter, the area API as a word.
CONFIDENCE_LABELS = {"l": "low", "n": "nominal", "h": "high"}
DEFAULT_CONFIDENCE_FILTER = ("nominal", "high")


def archive_url(year, country, product=ARCHIVE_PRODUCT):
    """Public, keyless per-country yearly archive file for one FIRMS product."""
    return ARCHIVE_URL.format(product=product, year=year, country=country)


def confidence_label(raw):
    """Normalise both archive ('n') and area-API ('nominal') spellings."""
    value = (raw or "").strip().lower()
    return CONFIDENCE_LABELS.get(value, value)


def load_archive(paths):
    """Read cached FIRMS archive CSVs into hotspot dicts (no network)."""
    rows = []
    for path in paths:
        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def filter_hotspots(hotspots, start, end, confidence_filter=DEFAULT_CONFIDENCE_FILTER):
    """Keep hotspots inside [start, end] whose confidence passes the filter.

    `acq_date`/`acq_time` are UTC in both FIRMS sources; acq_time is HHMM.
    """
    allowed = {c.lower() for c in confidence_filter}
    kept = []
    for point in hotspots:
        stamp = acquired_at(point)
        if stamp is None or not (start <= stamp <= end):
            continue
        if confidence_label(point.get("confidence")) not in allowed:
            continue
        kept.append(point)
    return kept


def acquired_at(point):
    """UTC datetime of one hotspot, or None when the row is unparseable."""
    from datetime import datetime, timezone

    date = (point.get("acq_date") or "").strip()
    raw_time = (point.get("acq_time") or "0").strip()
    if not date:
        return None
    try:
        minutes = int(raw_time)
    except ValueError:
        return None
    try:
        return datetime.strptime(date, "%Y-%m-%d").replace(
            hour=minutes // 100, minute=minutes % 100, tzinfo=timezone.utc
        )
    except ValueError:
        return None


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
