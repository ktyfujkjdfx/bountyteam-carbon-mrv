"""Files a consumer can serve, each with the metadata needed to place it.

Every artifact carries its own checksum, its bounds in both the native grid and
WGS84, its resolution and its unit. Ids are namespaced by request so two
results can sit in one store without colliding, and nothing here emits a path
from the machine that produced it: the browser is meant to receive an API
route, not a filesystem location.

Previews are illustrative. Every number in the analysis comes from the
reflectance and index arrays, never from a stretched preview pixel.
"""
import hashlib

import numpy
import rasterio
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform as shapely_transform

from rs import preview
from rs.determinism import png_bytes, write_json

MEDIA_PNG = "image/png"
MEDIA_GEOJSON = "application/geo+json"
MEDIA_JSON = "application/json"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def wgs84_bounds(transform, width, height, crs):
    """Bounds of a grid in WGS84, for placing an overlay on a map."""
    x0, y0 = transform @ (0, 0)
    x1, y1 = transform @ (width, height)
    native = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    if str(crs).upper() in ("EPSG:4326", "OGC:CRS84"):
        return tuple(native.bounds), tuple(native.bounds)
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    projected = shapely_transform(
        lambda x, y: transformer.transform(x, y), native)
    return tuple(native.bounds), tuple(round(value, 7) for value in projected.bounds)


def record(artifact_id, *, role, media_type, data, relative_path, grid=None,
           unit=None, provenance=None, bounds=None):
    """One artifact entry. `data` is the exact bytes that were written."""
    entry = {
        "id": artifact_id,
        "role": role,
        "media_type": media_type,
        "path": relative_path,
        "api_url": f"artifacts/{artifact_id}",
        "sha256": _sha256(data),
        "size_bytes": len(data),
    }
    if grid is not None:
        native, wgs84 = bounds if bounds else (None, None)
        entry.update({
            "crs": grid.crs,
            "resolution": list(grid.pixel_size),
            "resolution_units": grid.units,
            "bbox_native": list(native) if native else None,
            "bbox_wgs84": list(wgs84) if wgs84 else None,
        })
    if unit:
        entry["unit"] = unit
    if provenance:
        entry["provenance"] = provenance
    return entry


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def mask_png(mask):
    """A boolean mask as a black and white PNG, encoded deterministically."""
    from PIL import Image

    image = Image.fromarray(numpy.asarray(mask).astype("uint8") * 255)
    return png_bytes(image)


def write_change_artifacts(out_dir, prefix, change, grid, root):
    """Write previews, masks and zone geometry; return the artifact records."""
    records = []
    bounds = wgs84_bounds(
        rasterio.Affine.from_gdal(*grid.transform),
        grid.width, grid.height, grid.crs)

    def emit(name, data, role, media_type, unit=None, provenance=None):
        path = out_dir / name
        write_bytes(path, data)
        records.append(record(
            f"{prefix}:{name}", role=role, media_type=media_type, data=data,
            relative_path=name, grid=grid, unit=unit, provenance=provenance,
            bounds=bounds))

    before, after = change["reflectance"]
    emit("before.png",
         png_bytes(preview.false_color_preview(before[3], before[5], before[2])),
         role="optical_preview_before", media_type=MEDIA_PNG,
         provenance=change["pair"]["before_scene_key"])
    emit("after.png",
         png_bytes(preview.false_color_preview(after[3], after[5], after[2])),
         role="optical_preview_after", media_type=MEDIA_PNG,
         provenance=change["pair"]["after_scene_key"])
    emit("dnbr_preview.png",
         png_bytes(preview.dnbr_preview(
             numpy.nan_to_num(change["dnbr"], nan=0.0), change["paired_valid"])),
         role="dnbr_preview", media_type=MEDIA_PNG, unit="dNBR class",
         provenance="Key & Benson severity classes")
    emit("paired_valid_mask.png", mask_png(change["paired_valid"]),
         role="paired_valid_mask", media_type=MEDIA_PNG,
         provenance="scene classification 4 and 5 on both dates")
    emit("zone_mask.png", mask_png(change["zone_mask"]),
         role="zone_mask", media_type=MEDIA_PNG,
         provenance="detected change zones after the minimum mapping unit")

    zones_bytes = write_json(out_dir / "zones.geojson", change["zones_geojson"])
    records.append(record(
        f"{prefix}:zones.geojson", role="change_zones", media_type=MEDIA_GEOJSON,
        data=zones_bytes, relative_path="zones.geojson",
        provenance="WGS84; fact and cause are separate properties"))
    return records


def write_cell_artifacts(out_dir, prefix, cells_geojson, cci_grid):
    data = write_json(out_dir / "cells.geojson", cells_geojson)
    native, wgs84 = (list(cci_grid.pixel_size), None)
    return [record(
        f"{prefix}:cells.geojson", role="cci_cell_layer",
        media_type=MEDIA_GEOJSON, data=data, relative_path="cells.geojson",
        unit="t/ha for AGB and AGB_SD; ha for weight",
        provenance=("native ESA CCI model cells, not a resampled surface; "
                    f"native pixel size {native} degrees"))]
