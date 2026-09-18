"""Retrieving Sentinel-2 from the open catalogue, with a cache and offline replay.

The case requires that data can be obtained from an open source by the
parameters of a request. This module does that against Earth Search, the same
catalogue the supplied crops came from, and it fetches a real windowed read of
a real asset - not just the catalogue JSON, which would prove only that a
search endpoint answers.

Three rules keep it honest:

**It never substitutes for the supplied data.** Every scientific number in this
package comes from `data/`. What the retriever produces is a comparison and a
demonstration, stored apart, and the analysis does not read it.

**A cache miss with the network off is an error.** There is no silent fallback
to a local file dressed up as an online acquisition. Offline replay serves what
was genuinely fetched earlier and says so; anything else stops and reports.

**Nothing temporary is recorded.** Hrefs are stored without their query string,
and a URL carrying signing parameters is refused outright, so no short-lived
token can reach a manifest or a log.

One catalogue behaviour deserves its own note. Earth Search serves two items for
the same acquisition - for 29 July 2021 both `..._0_L2A` at processing baseline
03.01 with offset 0 and `..._1_L2A` at 05.00 with offset -0.1. Both are valid
and they are radiometrically different. Selection is therefore explicit and
recorded; taking the first result would silently produce data that does not
match the reference.
"""
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import rasterio
from rasterio.windows import from_bounds

from rs.case2.catalog import DatasetError
from rs.determinism import write_json

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
USER_AGENT = "carbon-lens-rs/1.0 (+hackathon research client)"
DEFAULT_TIMEOUT_SECONDS = 30
# A window big enough to compare against a supplied crop and small enough that
# nobody mistakes the cache for an archive.
MAX_ASSET_BYTES = 32 * 1024 * 1024
MAX_SEARCH_BYTES = 8 * 1024 * 1024

# STAC asset keys for the bands the supplied product carries.
ASSET_BY_BAND = {
    "B02": "blue", "B03": "green", "B04": "red",
    "B8A": "nir08", "B11": "swir16", "B12": "swir22",
    "SCL": "scl",
}
# Parameters that would mark a temporary signed URL. Their presence is refused
# rather than stripped, so a signing scheme cannot pass unnoticed.
SIGNING_PARAMETERS = ("X-Amz-Signature", "X-Amz-Credential", "sig", "se", "sp",
                      "token", "Signature", "AWSAccessKeyId")


class RetrievalError(RuntimeError):
    """The open source could not be used, and nothing was substituted for it."""


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def strip_query(href):
    """Href without its query string, refusing anything that looks signed."""
    parts = urllib.parse.urlsplit(href)
    if parts.query:
        present = urllib.parse.parse_qs(parts.query)
        signed = [name for name in SIGNING_PARAMETERS if name in present]
        if signed:
            raise RetrievalError(
                f"asset href carries signing parameters {signed}; a temporary "
                f"token must not be recorded, so this source needs a signing "
                f"step that is resolved at read time instead")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


class Retriever:
    """Open-catalogue access with an isolated cache and an offline mode."""

    def __init__(self, cache_dir, *, allow_network=True,
                 timeout=DEFAULT_TIMEOUT_SECONDS, max_asset_bytes=MAX_ASSET_BYTES):
        self.cache_dir = Path(cache_dir)
        self.allow_network = allow_network
        self.timeout = timeout
        self.max_asset_bytes = max_asset_bytes
        self.search_dir = self.cache_dir / "search"
        self.asset_dir = self.cache_dir / "assets"

    # -- search ---------------------------------------------------------

    def search(self, bbox, datetime_range, limit=20):
        """STAC search by geometry and date, cached by the exact query."""
        query = {
            "collections": [COLLECTION],
            "bbox": [round(value, 6) for value in bbox],
            "datetime": datetime_range,
            "limit": limit,
        }
        key = _digest(query)
        cached = self.search_dir / f"{key}.json"
        if cached.is_file():
            document = json.loads(cached.read_text(encoding="utf-8"))
            return document["response"], {**document["provenance"],
                                          "from_cache": True}
        if not self.allow_network:
            raise RetrievalError(
                f"no cached search for this query and the network is disabled; "
                f"offline replay can only serve what was fetched before "
                f"(cache: {cached})")

        body = json.dumps(query).encode()
        request = urllib.request.Request(
            EARTH_SEARCH, data=body,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_SEARCH_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RetrievalError(
                f"open catalogue unreachable: {type(exc).__name__}: {exc}") from exc
        if len(raw) > MAX_SEARCH_BYTES:
            raise RetrievalError("search response exceeded the size limit")

        document = json.loads(raw)
        provenance = {
            "endpoint": EARTH_SEARCH,
            "method": "POST",
            "query": query,
            "collection": COLLECTION,
            "response_sha256": hashlib.sha256(raw).hexdigest(),
            "item_count": len(document.get("features", [])),
        }
        write_json(cached, {"provenance": provenance, "response": document})
        return document, {**provenance, "from_cache": False}

    # -- item selection -------------------------------------------------

    @staticmethod
    def describe(item):
        properties = item["properties"]
        return {
            "item_id": item["id"],
            "datetime": properties.get("datetime"),
            "processing_baseline": properties.get("s2:processing_baseline"),
            "cloud_cover": properties.get("eo:cloud_cover"),
        }

    @staticmethod
    def select(items, *, item_id=None, processing_baseline=None):
        """Pick one item explicitly.

        Either name the item, or name the processing baseline and take the most
        recent acquisition on it. Silently taking `items[0]` is what this
        method exists to prevent.
        """
        if item_id is not None:
            for item in items:
                if item["id"] == item_id:
                    return item
            raise RetrievalError(
                f"item {item_id} is not in this result; the catalogue has "
                f"{[entry['id'] for entry in items]}")
        if processing_baseline is not None:
            matching = [item for item in items
                        if item["properties"].get("s2:processing_baseline")
                        == processing_baseline]
            if not matching:
                available = sorted({
                    item["properties"].get("s2:processing_baseline")
                    for item in items})
                raise RetrievalError(
                    f"no item at processing baseline {processing_baseline}; "
                    f"the catalogue offers {available}. The choice matters: "
                    f"from 04.00 the product carries a -0.1 offset")
            return sorted(matching, key=lambda item: item["id"])[0]
        raise RetrievalError(
            "item selection must be explicit: pass item_id or processing_baseline")

    # -- asset window ---------------------------------------------------

    def fetch_window(self, item, band, bounds, *, bounds_crs="EPSG:4326"):
        """Read a window of one asset, cached as a small GeoTIFF.

        `bounds` are in `bounds_crs`; the window is taken in the asset's own
        grid, so nothing is resampled on the way in.
        """
        asset_key = ASSET_BY_BAND.get(band)
        if asset_key is None:
            raise RetrievalError(f"no STAC asset is mapped for band {band}")
        asset = item["assets"].get(asset_key)
        if asset is None:
            raise RetrievalError(
                f"item {item['id']} has no asset {asset_key}; it offers "
                f"{sorted(item['assets'])}")
        href = strip_query(asset["href"])
        key = _digest({"href": href, "bounds": [round(v, 6) for v in bounds],
                       "crs": bounds_crs})
        cached = self.asset_dir / f"{item['id']}__{band}__{key[:16]}.tif"
        sidecar = cached.with_suffix(".provenance.json")

        if cached.is_file() and sidecar.is_file():
            provenance = json.loads(sidecar.read_text(encoding="utf-8"))
            return cached, {**provenance, "from_cache": True}
        if not self.allow_network:
            raise RetrievalError(
                f"no cached window for {item['id']} {band} and the network is "
                f"disabled; this is a cache miss, not a local read standing in "
                f"for an online acquisition")

        cached.parent.mkdir(parents=True, exist_ok=True)
        try:
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                              GDAL_HTTP_TIMEOUT=str(self.timeout),
                              GDAL_HTTP_USERAGENT=USER_AGENT):
                with rasterio.open(f"/vsicurl/{href}") as source:
                    window = from_bounds(
                        *_reproject_bounds(bounds, bounds_crs, source.crs),
                        transform=source.transform).round_lengths().round_offsets()
                    data = source.read(1, window=window)
                    transform = source.window_transform(window)
                    profile = {
                        "driver": "GTiff", "height": data.shape[0],
                        "width": data.shape[1], "count": 1, "dtype": data.dtype,
                        "crs": source.crs, "transform": transform,
                        "compress": "deflate", "zlevel": 6, "predictor": 1,
                        "tiled": False,
                    }
                    raster_band = (asset.get("raster:bands") or [{}])[0]
                    scale = raster_band.get("scale")
                    offset = raster_band.get("offset")
                    nodata = raster_band.get("nodata")
        except (rasterio.errors.RasterioIOError, OSError) as exc:
            raise RetrievalError(
                f"asset window could not be read from the open source: "
                f"{type(exc).__name__}: {exc}") from exc

        with rasterio.open(cached, "w", **profile) as sink:
            sink.write(data, 1)
        size = cached.stat().st_size
        if size > self.max_asset_bytes:
            cached.unlink()
            raise RetrievalError(
                f"retrieved window is {size} bytes, above the {self.max_asset_bytes} "
                f"byte limit; narrow the request rather than caching an archive")

        provenance = {
            "item_id": item["id"],
            "collection": COLLECTION,
            "band": band,
            "asset_key": asset_key,
            "asset_href": href,
            "datetime": item["properties"].get("datetime"),
            "processing_baseline": item["properties"].get("s2:processing_baseline"),
            "source_scale": scale,
            "source_offset": offset,
            "source_nodata": nodata,
            "window_bounds": [round(value, 6) for value in bounds],
            "window_bounds_crs": bounds_crs,
            "raw_sha256": hashlib.sha256(cached.read_bytes()).hexdigest(),
            "size_bytes": size,
            "license": "https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice",
            "required_attribution": "Contains modified Copernicus Sentinel data 2019-2024",
            "note": (
                "retrieved for comparison and demonstration; the supplied "
                "dataset in data/ remains the only source of analysis numbers"),
        }
        write_json(sidecar, provenance)
        return cached, {**provenance, "from_cache": False}


def _reproject_bounds(bounds, bounds_crs, target_crs):
    if str(bounds_crs).upper() == str(target_crs).upper():
        return bounds
    from pyproj import Transformer

    transformer = Transformer.from_crs(bounds_crs, target_crs, always_xy=True)
    west, south = transformer.transform(bounds[0], bounds[1])
    east, north = transformer.transform(bounds[2], bounds[3])
    return (min(west, east), min(south, north), max(west, east), max(south, north))


def compare_with_supplied(dataset, scene_key, band, retriever, *, window_px=48):
    """Fetch the same scene from the open catalogue and compare it to `data/`.

    This is the version and compatibility check the case asks for: same
    product, same item, same band, our own scaling - do we land on the values
    the organizers distributed? It is a check on our handling, not a
    replacement for their file.
    """
    row = next((entry for entry in dataset.scenes
                if entry["scene_key"] == scene_key), None)
    if row is None:
        raise DatasetError(f"unknown scene {scene_key}")
    with rasterio.open(dataset.path(row["reflectance_path"])) as source:
        descriptions = list(source.descriptions)
        if band not in descriptions:
            raise DatasetError(f"{scene_key} has no band {band}")
        index = descriptions.index(band) + 1
        supplied = source.read(index)
        supplied_transform = source.transform
        supplied_crs = source.crs
    half = window_px // 2
    centre_row, centre_col = supplied.shape[0] // 2, supplied.shape[1] // 2
    row_slice = slice(centre_row - half, centre_row + half)
    col_slice = slice(centre_col - half, centre_col + half)
    west, north = supplied_transform @ (col_slice.start, row_slice.start)
    east, south = supplied_transform @ (col_slice.stop, row_slice.stop)
    bounds = (min(west, east), min(south, north), max(west, east), max(south, north))

    document, search_provenance = retriever.search(
        _to_wgs84_bounds(bounds, supplied_crs),
        _day_range(row["datetime_utc"]))
    item = retriever.select(document["features"], item_id=row["item_id"])
    path, provenance = retriever.fetch_window(
        item, band, bounds, bounds_crs=str(supplied_crs))

    with rasterio.open(path) as source:
        retrieved = source.read(1).astype("float64")
    scale = provenance["source_scale"] or 1.0
    offset = provenance["source_offset"] or 0.0
    converted = retrieved * scale + offset

    reference = supplied[row_slice, col_slice].astype("float64")
    common = min(reference.shape[0], converted.shape[0]), min(
        reference.shape[1], converted.shape[1])
    reference = reference[:common[0], :common[1]]
    converted = converted[:common[0], :common[1]]
    difference = converted - reference
    import numpy

    return {
        "scene_key": scene_key,
        "band": band,
        "item": Retriever.describe(item),
        "supplied_processing_baseline": row["processing_baseline"],
        "compared_pixels": int(reference.size),
        "max_abs_difference": float(numpy.abs(difference).max()),
        "mean_abs_difference": float(numpy.abs(difference).mean()),
        "identical": bool(numpy.allclose(converted, reference, atol=1e-6)),
        "search_provenance": search_provenance,
        "asset_provenance": provenance,
        "cache_path": str(Path(path).name),
        "interpretation": (
            "a difference of zero means our scaling of the open product "
            "reproduces the supplied crop exactly; a systematic offset would "
            "point at a different item or a different processing baseline"),
    }


def _to_wgs84_bounds(bounds, crs):
    return _reproject_bounds(bounds, crs, "EPSG:4326")


def _day_range(datetime_utc):
    day = datetime_utc[:10]
    return f"{day}T00:00:00Z/{day}T23:59:59Z"
