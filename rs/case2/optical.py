"""Sentinel-2 usability inside the request.

RS-1 answers one optical question: how much of the request is observable on a
given date, and on a pair of dates at once. Which pair a change analysis should
use is a seasonal-comparability decision that belongs to RS-2.

Two rules are deliberate here. Scene classification 4 and 5 are the usable
classes; 2 and 7 are excluded from the main mask and may only come back in a
signed sensitivity variant. And negative reflectance is never clamped: from
processing baseline 04.00 the product carries a -0.1 radiometric offset, which
the supplied rasters already apply, so dark targets are legitimately below zero
and clamping them would bias every index computed later.
"""
import numpy
import rasterio
from pyproj import Transformer
from shapely.ops import transform as shapely_transform

from rs.case2.grid import grid_spec, pixel_centres_inside
from rs.case2.models import PairedOptical, SceneQuality

USABLE_SCL_CLASSES = frozenset({4, 5})
EXCLUDED_SCL_CLASSES = frozenset({0, 1, 2, 3, 6, 7, 8, 9, 10, 11})
SENSITIVITY_ONLY_SCL_CLASSES = frozenset({2, 7})
PAIRED_SELECTION_RULE = (
    "provisional: the pair of scenes with the largest paired-valid area inside "
    "the request; seasonal comparability is decided in RS-2"
)


def usable_mask(scl, reflectance):
    """Pixels usable for an index: an accepted SCL class and finite reflectance.

    Value magnitude plays no part. A legitimately negative reflectance is usable
    data; a NaN is not.
    """
    accepted = numpy.isin(scl, sorted(USABLE_SCL_CLASSES))
    finite = numpy.isfinite(reflectance).all(axis=0)
    return accepted & finite


def to_scene_crs(geometry, crs):
    """Project a WGS84 request into the scene's own UTM zone."""
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    return shapely_transform(
        lambda x, y: transformer.transform(x, y), geometry)


def read_scene(dataset, row):
    """Reflectance stack, SCL and grid of one scene, exactly as published."""
    with rasterio.open(dataset.path(row["reflectance_path"])) as source:
        reflectance = source.read().astype("float32")
        grid = grid_spec(source, units="metre")
        bands = tuple(source.descriptions)
    with rasterio.open(dataset.path(row["scl_path"])) as source:
        scl = source.read(1)
    return reflectance, scl, grid, bands


def scene_quality(dataset, row, geometry):
    """How much of the request this one scene can actually see."""
    reflectance, scl, grid, _bands = read_scene(dataset, row)
    transform = rasterio.Affine.from_gdal(*grid.transform)
    footprint = pixel_centres_inside(
        transform, grid.width, grid.height, to_scene_crs(geometry, grid.crs))
    inside = int(footprint.sum())
    usable = usable_mask(scl, reflectance) & footprint
    classes = {}
    for code in sorted(USABLE_SCL_CLASSES | EXCLUDED_SCL_CLASSES):
        count = int(((scl == code) & footprint).sum())
        if count:
            classes[code] = count
    finite = numpy.isfinite(reflectance)
    return SceneQuality(
        scene_key=row["scene_key"],
        item_id=row["item_id"],
        aoi_id=row["aoi_id"],
        datetime_utc=row["datetime_utc"],
        year=int(row["year"]),
        processing_baseline=row["processing_baseline"],
        reflectance_offset_applied=dataset.reflectance_offset(row["scene_key"]),
        pixels_in_request=inside,
        usable_pixels=int(usable.sum()),
        usable_fraction=(float(usable.sum()) / inside) if inside else 0.0,
        scl_class_pixels=classes,
        negative_reflectance_pixels=int((reflectance[:, footprint] < 0).sum()),
        non_finite_pixels=int((~finite[:, footprint]).sum()),
    ), usable, grid


def best_pair(scene_masks, year_start, year_end, pixels_in_request):
    """Pick the scene pair seeing the most of the request on both dates.

    `scene_masks` maps a scene key to `(year, usable_mask)`. Both scenes must
    share a grid, which they do within one AOI; a cross-AOI pair is not formed.
    """
    before = [(key, mask) for key, (year, mask) in scene_masks.items()
              if year == year_start]
    after = [(key, mask) for key, (year, mask) in scene_masks.items()
             if year == year_end]
    if not before or not after:
        return None
    best = None
    for before_key, before_mask in sorted(before):
        for after_key, after_mask in sorted(after):
            if before_mask.shape != after_mask.shape:
                continue
            paired = int((before_mask & after_mask).sum())
            candidate = (paired, before_key, after_key)
            if best is None or candidate > best:
                best = candidate
    if best is None:
        return None
    paired, before_key, after_key = best
    return PairedOptical(
        before_scene_key=before_key,
        after_scene_key=after_key,
        paired_usable_pixels=paired,
        pixels_in_request=pixels_in_request,
        paired_usable_fraction=(
            float(paired) / pixels_in_request if pixels_in_request else 0.0),
        selection_rule=PAIRED_SELECTION_RULE,
    )
