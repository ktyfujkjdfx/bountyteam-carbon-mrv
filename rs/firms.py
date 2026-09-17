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
    """Keep hotspots in the half-open window (start, end] passing the filter.

    The window is the interval *between* the two observations, so the start is
    excluded and the end included. A hotspot detected at exactly T_before was
    already burning when the "before" scene was acquired, so it cannot explain
    a change measured against that scene; one at exactly T_after still can.

    `acq_date`/`acq_time` are UTC in both FIRMS sources; acq_time is HHMM.
    """
    allowed = {c.lower() for c in confidence_filter}
    kept = []
    for point in hotspots:
        stamp = acquired_at(point)
        if stamp is None or not (start < stamp <= end):
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


def match_within_damage_mask(hotspots, damage_geometries, grid_epsg, tolerance_m=SPATIAL_TOLERANCE_M):
    """Hotspots within `tolerance_m` of the detected damage mask.

    Two things matter for this to mean what the contract says:

    * **What is buffered.** The rule is "within 500 m of the damage mask", so
      the buffer is taken around the union of the detected affected-area
      polygons, not around the whole AOI. Buffering the AOI answers a
      different and much weaker question ("was there a fire anywhere near this
      plot"), and over-counts hotspots that are nowhere near what was
      measured.
    * **Where it is buffered.** The buffer is built in the analysis grid's own
      UTM CRS (`method.grid.epsg`). EPSG:3857 is not metric away from the
      equator: its scale factor is 1/cos(latitude), so at Dadia (~41.1 N) a
      "500 m" buffer in Web Mercator units is about 377 m on the ground. UTM
      is metric where the plot is, which is the whole point of computing the
      grid in it.

    `damage_geometries` are shapely polygons already in `grid_epsg`, exactly as
    produced by `rs.components.affected_components`. With no damage there is
    nothing to attribute, and no hotspot can match.
    """
    from shapely.ops import unary_union

    if not damage_geometries:
        return []
    damage = unary_union(list(damage_geometries)).buffer(tolerance_m)
    to_grid = Transformer.from_crs("EPSG:4326", f"EPSG:{grid_epsg}", always_xy=True)
    matched = []
    for point in hotspots:
        x, y = to_grid.transform(float(point["longitude"]), float(point["latitude"]))
        if damage.intersects(Point(x, y)):
            matched.append(point)
    return matched
