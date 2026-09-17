"""Baseline (pre-event) forest mask from ESA WorldCover 10 m v200 (2021).

One source mask is used for both dates in a pair, per manifest 10.4/5.4: the
mask must not be recomputed per-date from a post-event product.
"""
import math

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

WORLDCOVER_TREE_COVER_CLASS = 10
WORLDCOVER_BASE_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)


def worldcover_tile_id(lon, lat):
    """3x3 degree WorldCover tile name covering (lon, lat)."""
    tile_lat = int(math.floor(lat / 3) * 3)
    tile_lon = int(math.floor(lon / 3) * 3)
    lat_prefix = "N" if tile_lat >= 0 else "S"
    lon_prefix = "E" if tile_lon >= 0 else "W"
    return f"{lat_prefix}{abs(tile_lat):02d}{lon_prefix}{abs(tile_lon):03d}"


def worldcover_url(lon, lat):
    return WORLDCOVER_BASE_URL.format(tile=worldcover_tile_id(lon, lat))


def read_forest_mask(url, dst_transform, dst_width, dst_height, dst_crs):
    """Reproject WorldCover tree-cover class onto the shared 20 m grid.

    Categorical source: nearest-neighbour resampling, per the frozen
    resampling_categorical parameter.
    """
    with rasterio.open(url) as src:
        source = src.read(1)
        classified = (source == WORLDCOVER_TREE_COVER_CLASS).astype("uint8")
        dst = np.zeros((dst_height, dst_width), dtype="uint8")
        reproject(
            source=classified,
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=rasterio.Affine(*dst_transform),
            dst_crs=f"EPSG:{dst_crs}",
            resampling=Resampling.nearest,
        )
    return dst.astype(bool)
