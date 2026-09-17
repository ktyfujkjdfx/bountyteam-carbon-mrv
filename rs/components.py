"""Connected-component filtering and affected-area polygonization.

Frozen parameters: disturbance_dnbr_min=0.27, min_component_area_ha=1 (=25
twenty-metre pixels), connectivity=8. GDAL's Polygonize (via
rasterio.features.shapes) groups same-valued pixels using the requested
connectivity, so each returned polygon is exactly one connected component.
"""
import numpy as np
import rasterio.features
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform

PIXEL_AREA_HA = 0.04  # 20 m x 20 m
MIN_COMPONENT_PIXELS = 25  # 1 ha / 0.04 ha


def affected_components(candidate_mask, grid_transform, connectivity=8):
    """Group `candidate_mask` True pixels into connected components.

    Returns a list of (polygon_in_grid_crs, pixel_count) for EVERY component
    (including sub-threshold ones), so callers can apply the MMU filter and
    still report what was dropped.
    """
    if not candidate_mask.any():
        return []
    components = []
    for geom, value in rasterio.features.shapes(
        candidate_mask.astype("uint8"),
        mask=candidate_mask,
        transform=grid_transform,
        connectivity=connectivity,
    ):
        if value != 1:
            continue
        poly = shape(geom)
        pixel_count = int(
            rasterio.features.rasterize(
                [(geom, 1)],
                out_shape=candidate_mask.shape,
                transform=grid_transform,
                fill=0,
                dtype="uint8",
            ).sum()
        )
        components.append((poly, pixel_count))
    return components


def apply_minimum_mapping_unit(components, min_pixels=MIN_COMPONENT_PIXELS):
    """Split components into (kept, dropped) by the frozen MMU threshold."""
    kept = [(poly, count) for poly, count in components if count >= min_pixels]
    dropped = [(poly, count) for poly, count in components if count < min_pixels]
    return kept, dropped


def rasterize_kept(kept, out_shape, grid_transform):
    if not kept:
        return np.zeros(out_shape, dtype=bool)
    shapes = [(mapping(poly), 1) for poly, _ in kept]
    return rasterio.features.rasterize(
        shapes, out_shape=out_shape, transform=grid_transform, fill=0, dtype="uint8"
    ).astype(bool)


def to_wgs84_geojson(kept, grid_epsg):
    transformer = Transformer.from_crs(f"EPSG:{grid_epsg}", "EPSG:4326", always_xy=True)
    features = []
    for poly, pixel_count in kept:
        wgs_poly = shapely_transform(lambda x, y: transformer.transform(x, y), poly)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "pixel_count": pixel_count,
                    "area_ha": round(pixel_count * PIXEL_AREA_HA, 6),
                },
                "geometry": mapping(wgs_poly),
            }
        )
    return {"type": "FeatureCollection", "features": features}
