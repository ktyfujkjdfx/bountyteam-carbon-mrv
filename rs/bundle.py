"""Writes a pipeline result to an on-disk bundle: verification.json,
source-index.json, and every artifact referenced by evidence['artifacts'].

Every byte written here is hashed, so every writer goes through
rs/determinism.py rather than text-mode `write_text`/`json.dumps`: the same
inputs must produce the same SHA-256 on Windows, macOS and Linux alike.
"""
import hashlib
import shutil
from pathlib import Path

import numpy as np
import rasterio

from rs import determinism, gridmath, preview


def _sha_and_size(path):
    data = Path(path).read_bytes()
    return "0x" + hashlib.sha256(data).hexdigest(), len(data)


def _write_geotiff(path, array, transform, epsg, dtype, nodata=None):
    """Write a GeoTIFF with the creation options pinned.

    DEFLATE is kept (these rasters compress well) but `zlevel` is stated
    explicitly instead of inherited from the GDAL build's default, and no
    timestamp/software tag is written, so repeated writes of the same array
    produce the same file.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=dtype,
        crs=f"EPSG:{epsg}",
        transform=rasterio.Affine(*transform),
        nodata=nodata,
        compress="deflate",
        zlevel=6,
        predictor=1,
        interleave="band",
        tiled=False,
    ) as dst:
        dst.write(array, 1)


def write_bundle(evidence, artifacts_payload, request, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    source_index = {}

    epsg = artifacts_payload["epsg"]
    transform = artifacts_payload["transform"]
    width, height = artifacts_payload["width"], artifacts_payload["height"]
    bounds_wgs84 = gridmath.grid_bounds_wgs84(transform, width, height, epsg)

    # --- source assets: copy the exact cached bytes RS actually used into the
    # bundle so Backend can verify local_sha256 without touching the network.
    data_root = Path(request["data_root"])
    plot_id = request["plot_id"]
    for side in ("before", "after"):
        scene = request[side]
        for asset in scene["assets"]:
            src = data_root / plot_id / scene["scene_id"] / f"{asset['band']}.tif"
            rel = f"source/{scene['scene_id']}/{asset['band']}.tif"
            dst = output_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            source_index[asset["local_sha256"]] = rel
    forest_mask_src = data_root / plot_id / "forest_mask_source.tif"
    forest_mask_rel = "source/forest_mask_source.tif"
    forest_mask_dst = output_dir / forest_mask_rel
    forest_mask_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(forest_mask_src, forest_mask_dst)
    forest_mask_hash, _ = _sha_and_size(forest_mask_dst)
    source_index[forest_mask_hash] = forest_mask_rel
    evidence["method"]["forest_mask"]["sha256"] = forest_mask_hash

    def add_artifact(artifact_id, role, relative_path, media_type, *, bounds=None, size=None):
        full_path = output_dir / relative_path
        sha, byte_size = _sha_and_size(full_path)
        entry = {
            "artifact_id": artifact_id,
            "role": role,
            "relative_path": relative_path,
            "media_type": media_type,
            "sha256": sha,
            "size_bytes": byte_size,
        }
        if bounds is not None and size is not None:
            entry["bounds_wgs84"] = bounds
            entry["width"], entry["height"] = size
        artifacts.append(entry)

    # Aligned before/after previews are useful even on INSUFFICIENT_DATA (they
    # show why), so they are not gated on a completed classification.
    before_bands, after_bands = artifacts_payload["before_bands"], artifacts_payload["after_bands"]
    before_img = preview.false_color_preview(before_bands["B08"], before_bands["B12"], before_bands["B04"])
    after_img = preview.false_color_preview(after_bands["B08"], after_bands["B12"], after_bands["B04"])
    before_path, after_path = output_dir / "before.png", output_dir / "after.png"
    size = preview.save_png(before_img, before_path)
    preview.save_png(after_img, after_path)
    add_artifact("preview_before", "PREVIEW_BEFORE", "before.png", "image/png", bounds=bounds_wgs84, size=size)
    add_artifact("preview_after", "PREVIEW_AFTER", "after.png", "image/png", bounds=bounds_wgs84, size=size)

    if artifacts_payload.get("dnbr") is not None:
        dnbr_path = output_dir / "dnbr.tif"
        dnbr_arr = np.where(np.isfinite(artifacts_payload["dnbr"]), artifacts_payload["dnbr"], -9999.0).astype("float32")
        _write_geotiff(dnbr_path, dnbr_arr, transform, epsg, "float32", nodata=-9999.0)
        add_artifact("dnbr", "DNBR_RASTER", "dnbr.tif", "image/tiff")

        affected_geojson = _affected_geojson(artifacts_payload)
        determinism.write_json(output_dir / "affected_area.geojson", affected_geojson)
        add_artifact("affected_area", "AFFECTED_AREA", "affected_area.geojson", "application/geo+json")

        # Classify at the float32 precision that dnbr.tif publishes, so the
        # preview cannot disagree with the raster and last-ULP differences
        # between CPU architectures are rounded away before they can flip a
        # class boundary. NaN is preserved (unlike in dnbr_arr, where it became
        # the nodata value), so masked pixels still render as "no data".
        dnbr_at_published_precision = artifacts_payload["dnbr"].astype("float32").astype("float64")
        dnbr_preview_img = preview.dnbr_preview(
            dnbr_at_published_precision, artifacts_payload["footprint"] & artifacts_payload["forest_mask"]
        )
        dnbr_preview_path = output_dir / "dnbr_preview.png"
        dsize = preview.save_png(dnbr_preview_img, dnbr_preview_path)
        add_artifact("dnbr_preview", "DNBR_PREVIEW", "dnbr_preview.png", "image/png", bounds=bounds_wgs84, size=dsize)

    firms_points = artifacts_payload.get("firms_points") or []
    if evidence["firms"]["support"] == "SUPPORTED" and firms_points:
        firms_geojson = determinism.round_geojson(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {k: v for k, v in point.items() if k not in ("longitude", "latitude")},
                        "geometry": {
                            "type": "Point",
                            "coordinates": [float(point["longitude"]), float(point["latitude"])],
                        },
                    }
                    for point in firms_points
                ],
            }
        )
        determinism.write_json(output_dir / "firms.geojson", firms_geojson)
        add_artifact("firms-points", "FIRMS_POINTS", "firms.geojson", "application/geo+json")

    evidence["artifacts"] = artifacts
    determinism.write_json(output_dir / "source-index.json", source_index)
    # Canonical (JCS) bytes: the file on disk is exactly what Backend hashes
    # into evidence_hash, so the two can never drift apart by formatting.
    determinism.write_json(output_dir / "verification.json", evidence)
    return evidence


def _affected_geojson(artifacts_payload):
    from rs.components import to_wgs84_geojson

    return to_wgs84_geojson(artifacts_payload["kept_components"], artifacts_payload["epsg"])
