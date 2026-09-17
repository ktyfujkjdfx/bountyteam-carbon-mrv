"""Download AOI-windowed, native-resolution source bands and build a request.

Only the AOI window is fetched (rasterio windowed reads over HTTPS COGs), never
a full scene. Cached files are the exact bytes later hashed into
`source-index.json`, so acquisition and hashing must operate on the same file.
"""
import hashlib
import json
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

from rs import firms, forestmask, harmonize, stac
from rs.contracts import digest

BANDS = ("B04", "B08", "B8A", "B12", "SCL")


def sha256_file(path):
    return "0x" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fetch_band_window(href, bbox_wgs84, out_path):
    """Read the AOI window of one band at native resolution/CRS and save it."""
    with rasterio.open(href) as src:
        window = from_bounds(*transform_bounds("EPSG:4326", src.crs, *bbox_wgs84), transform=src.transform)
        window = window.round_offsets().round_lengths()
        data = src.read(1, window=window)
        transform = src.window_transform(window)
        profile = src.profile.copy()
        profile.update(
            height=data.shape[0],
            width=data.shape[1],
            transform=transform,
            driver="GTiff",
            compress="deflate",
        )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data, 1)
    return out_path


def fetch_scene_bands(item, bbox_wgs84, data_root, plot_id, scene_id):
    scene_dir = Path(data_root) / plot_id / scene_id
    local_paths = {}
    for band in BANDS:
        href = stac.asset_href(item, band)
        out_path = scene_dir / f"{band}.tif"
        fetch_band_window(href, bbox_wgs84, out_path)
        local_paths[band] = out_path
    return local_paths


def fetch_forest_mask_source(bbox_wgs84, data_root, plot_id):
    lon = (bbox_wgs84[0] + bbox_wgs84[2]) / 2
    lat = (bbox_wgs84[1] + bbox_wgs84[3]) / 2
    url = forestmask.worldcover_url(lon, lat)
    out_path = Path(data_root) / plot_id / "forest_mask_source.tif"
    with rasterio.open(url) as src:
        window = from_bounds(*transform_bounds("EPSG:4326", src.crs, *bbox_wgs84), transform=src.transform)
        window = window.round_offsets().round_lengths()
        data = src.read(1, window=window)
        transform = src.window_transform(window)
        profile = src.profile.copy()
        profile.update(height=data.shape[0], width=data.shape[1], transform=transform, driver="GTiff")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data, 1)
    return out_path


def fetch_firms_archive(data_root, plot_id, years, country, product=firms.ARCHIVE_PRODUCT):
    """Cache the keyless FIRMS per-country yearly archive files for `years`.

    Stored as the untouched upstream bytes so `firms.source_refs` can carry a
    checkable SHA-256, and so `rs.verify` never needs the network.
    """
    out_dir = Path(data_root) / plot_id / "firms"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for year in sorted(set(years)):
        url = firms.archive_url(year, country, product)
        out_path = out_dir / f"{product}_{year}_{country}.csv"
        if not out_path.exists():
            with urllib.request.urlopen(url, timeout=120) as response:
                out_path.write_bytes(response.read())
        paths.append(out_path)
    return paths


def build_scene_descriptor(item, local_paths):
    properties = item["properties"]
    processing_baseline = properties.get("s2:processing_baseline")
    boa_offset_applied = properties.get("earthsearch:boa_offset_applied")
    assets = []
    for band in BANDS:
        if band == "SCL":
            scale_applied, offset_applied, origin = 1, 0, "PRODUCT_METADATA"
        else:
            scale_applied, offset_applied, origin = harmonize.from_provider_metadata(
                processing_baseline, boa_offset_applied
            )
        assets.append(
            {
                "band": band,
                "source_ref": stac.asset_href(item, band),
                "local_sha256": sha256_file(local_paths[band]),
                "scale_applied": scale_applied,
                "offset_applied": offset_applied,
                "transform_origin": origin,
            }
        )
    tile = properties.get("grid:code") or properties.get("s2:mgrs_tile")
    if tile and tile.startswith("MGRS-"):
        tile = tile[len("MGRS-"):]
    return {
        "scene_id": item["id"],
        "acquired_at": properties["datetime"].split(".")[0].rstrip("Z") + "Z",
        "provider": "Element84 Earth Search (AWS Open Data)",
        "collection": item["collection"],
        "processing_baseline": processing_baseline,
        "mgrs_tile": tile,
        "assets": assets,
    }


def write_request(path, *, request_id, plot_id, geometry, plot_geometry_hash, before, after, data_root, dataset_kind="REAL"):
    parameters = {
        "ndvi_bands": ["B08", "B04"],
        "nbr_bands": ["B8A", "B12"],
        "disturbance_dnbr_min": 0.27,
        "min_component_area_ha": 1,
        "connectivity": 8,
        "excluded_scl_classes": [0, 1, 2, 3, 6, 7, 8, 9, 10, 11],
        "resampling_continuous": "average",
        "resampling_categorical": "nearest",
    }
    request = {
        "schema_version": "1.0.0",
        "request_id": request_id,
        "plot_id": plot_id,
        "geometry": geometry,
        "plot_geometry_hash": plot_geometry_hash,
        "before": before,
        "after": after,
        "parameters": parameters,
        "data_root": data_root,
        "dataset_kind": dataset_kind,
    }
    assert digest(geometry) == plot_geometry_hash, "geometry hash mismatch"
    Path(path).write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return request
