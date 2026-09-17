"""Orchestrates one request.json + cached local source files into a
VerificationEvidence dict plus the in-memory rasters/vectors bundle.py writes.

Never returns evidence_hash or a token/credit state; those are Backend-owned.
"""
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
from pyproj import Transformer
from rasterio.warp import Resampling, reproject
from shapely.geometry import shape

from rs import (PIPELINE_VERSION, components, firms as firms_mod, forestmask, gridmath, harmonize, indices,
                masks, resample)
from rs.contracts import digest

PARAMETERS = {
    "ndvi_bands": ["B08", "B04"],
    "nbr_bands": ["B8A", "B12"],
    "disturbance_dnbr_min": 0.27,
    "min_component_area_ha": 1,
    "connectivity": 8,
    "excluded_scl_classes": [0, 1, 2, 3, 6, 7, 8, 9, 10, 11],
    "resampling_continuous": "average",
    "resampling_categorical": "nearest",
}
CONFIG_SHA256 = digest(PARAMETERS)

MIN_PAIRED_VALID_FOREST_RATIO = 0.70  # RS's own honesty gate; Backend recomputes independently.


def _scene_source_dir(data_root, plot_id, scene_id):
    return Path(data_root) / plot_id / scene_id


def _round(value, digits=6):
    return None if value is None else round(float(value), digits)


def _load_scene_grids(scene, data_root, plot_id, dst_transform, dst_width, dst_height, dst_epsg):
    """Read cached native files, harmonize to reflectance, reproject to the grid."""
    scene_dir = _scene_source_dir(data_root, plot_id, scene["scene_id"])
    bands = {}
    for asset in scene["assets"]:
        band = asset["band"]
        native_path = scene_dir / f"{band}.tif"
        with rasterio.open(native_path) as src:
            native = src.read(1)
            plan = resample.plan(
                src.transform, src.crs, native.shape,
                dst_transform, dst_width, dst_height, f"EPSG:{dst_epsg}",
            )
            src_transform, src_crs = src.transform, src.crs

        if band == "SCL":
            # Categorical: an exact window slice when the grids coincide, GDAL
            # nearest otherwise (a class must never be averaged).
            sliced = resample.window_slice(native, plan, dst_width, dst_height) if plan else None
            if sliced is not None:
                bands[band] = sliced.astype("int16")
                continue
            dst = np.zeros((dst_height, dst_width), dtype="float64")
            reproject(
                source=native.astype("float64"),
                destination=dst,
                src_transform=src_transform,
                src_crs=src_crs,
                dst_transform=rasterio.Affine(*dst_transform),
                dst_crs=f"EPSG:{dst_epsg}",
                resampling=Resampling.nearest,
            )
            bands[band] = np.round(dst).astype("int16")
        elif plan is not None:
            # Exact path: average the integer DNs, then harmonize. Equivalent
            # to harmonizing first, but the arithmetic is exact, so the result
            # is bit-identical on every platform. See rs/resample.py.
            mean_dn = resample.block_mean(native, plan, dst_width, dst_height)
            bands[band] = harmonize.apply_scale_offset(
                mean_dn, asset["scale_applied"], asset["offset_applied"]
            )
        else:
            reflectance = harmonize.apply_scale_offset(native, asset["scale_applied"], asset["offset_applied"])
            dst = np.full((dst_height, dst_width), np.nan, dtype="float64")
            reproject(
                source=reflectance,
                destination=dst,
                src_transform=src_transform,
                src_crs=src_crs,
                dst_transform=rasterio.Affine(*dst_transform),
                dst_crs=f"EPSG:{dst_epsg}",
                resampling=Resampling.average,
            )
            bands[band] = dst
    return bands


def _temporal_comparability(before_acquired_at, after_acquired_at, cloud_before, cloud_after):
    """DEMO_LOGIC heuristic: same-season proximity + low cloud => YES.

    Not a scientific phenology model; a documented prototype rule (manifest 8).
    """
    before_dt = datetime.strptime(before_acquired_at, "%Y-%m-%dT%H:%M:%SZ")
    after_dt = datetime.strptime(after_acquired_at, "%Y-%m-%dT%H:%M:%SZ")
    day_gap = abs((after_dt.timetuple().tm_yday - before_dt.timetuple().tm_yday))
    day_gap = min(day_gap, 365 - day_gap)
    clouds_ok = all(c is not None and c < 0.3 for c in (cloud_before, cloud_after))
    if day_gap <= 45 and clouds_ok:
        return "YES", f"Acquisitions {day_gap} days apart in season; AOI cloud ratio < 0.3 on both dates."
    if day_gap <= 90:
        return "UNCERTAIN", f"Acquisitions {day_gap} days apart in season or partial cloud cover; phenology not fully controlled."
    return "NO", f"Acquisitions {day_gap} days apart; seasonal window is not comparable."


def compute_evidence(request, *, code_commit=None):
    """Returns (evidence_dict, artifacts) where `artifacts` carries the raw
    numpy/shapely payload bundle.py needs to write files and hash them.
    """
    plot_id = request["plot_id"]
    geometry = request["geometry"]
    data_root = request["data_root"]
    before, after = request["before"], request["after"]

    aoi_lonlat = gridmath.bounds_wgs84(geometry)
    centroid_lon = (aoi_lonlat[0] + aoi_lonlat[2]) / 2
    centroid_lat = (aoi_lonlat[1] + aoi_lonlat[3]) / 2
    epsg = gridmath.utm_epsg(centroid_lon, centroid_lat)
    transform, width, height, _ = gridmath.snapped_grid(geometry, epsg, resolution_m=20)

    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    aoi_utm = shape(
        {
            "type": geometry["type"],
            "coordinates": _project_coords(geometry["coordinates"], to_utm),
        }
    )
    footprint = rasterio.features.geometry_mask(
        [aoi_utm], out_shape=(height, width), transform=rasterio.Affine(*transform), invert=True
    )

    before_bands = _load_scene_grids(before, data_root, plot_id, transform, width, height, epsg)
    after_bands = _load_scene_grids(after, data_root, plot_id, transform, width, height, epsg)

    forest_mask_source = Path(data_root) / plot_id / "forest_mask_source.tif"
    forest_mask = forestmask.read_forest_mask(str(forest_mask_source), transform, width, height, epsg)
    forest_mask &= footprint

    scl_before, scl_after = before_bands["SCL"], after_bands["SCL"]
    aoi_cloud_before = masks.cloud_ratio(scl_before, footprint)
    aoi_cloud_after = masks.cloud_ratio(scl_after, footprint)
    paired_valid_footprint = masks.paired_valid(scl_before, scl_after, footprint)
    analysed_mask = paired_valid_footprint & forest_mask

    baseline_forest_pixel_count = int(forest_mask.sum())
    analysed_forest_pixel_count = int(analysed_mask.sum())
    paired_valid_aoi_pixel_count = int((paired_valid_footprint).sum())
    aoi_pixel_count = int(footprint.sum())

    metadata_complete = bool(
        before.get("processing_baseline")
        and after.get("processing_baseline")
        and before.get("mgrs_tile")
        and after.get("mgrs_tile")
        and len(before["assets"]) >= 5
        and len(after["assets"]) >= 5
    )

    temporal_comparability, temporal_note = _temporal_comparability(
        before["acquired_at"], after["acquired_at"], aoi_cloud_before, aoi_cloud_after
    )

    plot_area_ha = round(aoi_utm.area / 10000, 6)
    paired_valid_forest_ratio = (
        None if baseline_forest_pixel_count == 0 else analysed_forest_pixel_count / baseline_forest_pixel_count
    )
    paired_valid_aoi_ratio = None if aoi_pixel_count == 0 else paired_valid_aoi_pixel_count / aoi_pixel_count

    insufficient = (
        baseline_forest_pixel_count == 0
        or analysed_forest_pixel_count == 0
        or not metadata_complete
        or paired_valid_forest_ratio is None
        or paired_valid_forest_ratio < MIN_PAIRED_VALID_FOREST_RATIO
    )

    limitations = []
    artifacts_payload = {
        "epsg": epsg,
        "transform": transform,
        "width": width,
        "height": height,
        "footprint": footprint,
        "forest_mask": forest_mask,
        "before_bands": before_bands,
        "after_bands": after_bands,
    }

    if baseline_forest_pixel_count > 0:
        baseline_forest_area_ha = round(baseline_forest_pixel_count * 0.04, 6)
        analysed_forest_area_ha = round(analysed_forest_pixel_count * 0.04, 6)
    else:
        # contract_helpers treats a non-null pixel count of 0 as invalid (a
        # forest denominator of zero is "no usable baseline", not "measured
        # zero"), so an empty baseline forest mask must serialise as null.
        baseline_forest_area_ha = analysed_forest_area_ha = None
        baseline_forest_pixel_count = analysed_forest_pixel_count = None

    if insufficient:
        outcome = "INSUFFICIENT_DATA"
        ndvi_before_mean = ndvi_after_mean = dnbr_mean = None
        affected_area_ha = affected_fraction = None
        affected_pixel_count = None
        limitations.append(
            "paired_valid_forest_ratio below the 0.70 minimum coverage gate or missing baseline/forest pixels; "
            "outcome reported as INSUFFICIENT_DATA rather than a forced classification."
        )
        artifacts_payload.update(dnbr=None, affected_mask=None, dropped_components=[])
    else:
        ndvi_b = indices.ndvi(before_bands["B08"], before_bands["B04"])
        ndvi_a = indices.ndvi(after_bands["B08"], after_bands["B04"])
        nbr_b = indices.nbr(before_bands["B8A"], before_bands["B12"])
        nbr_a = indices.nbr(after_bands["B8A"], after_bands["B12"])
        dnbr_arr = indices.dnbr(nbr_b, nbr_a)

        ndvi_before_mean = _round(float(np.nanmean(np.where(analysed_mask, ndvi_b, np.nan))))
        ndvi_after_mean = _round(float(np.nanmean(np.where(analysed_mask, ndvi_a, np.nan))))
        dnbr_mean = _round(float(np.nanmean(np.where(analysed_mask, dnbr_arr, np.nan))))

        candidate = analysed_mask & (dnbr_arr >= PARAMETERS["disturbance_dnbr_min"])
        all_components = components.affected_components(candidate, rasterio.Affine(*transform))
        kept, dropped = components.apply_minimum_mapping_unit(all_components)
        affected_mask = components.rasterize_kept(kept, (height, width), rasterio.Affine(*transform))
        affected_pixel_count = int(affected_mask.sum())
        affected_area_ha = round(affected_pixel_count * 0.04, 6)
        affected_fraction = None if baseline_forest_pixel_count == 0 else round(affected_pixel_count / baseline_forest_pixel_count, 6)

        outcome = "DISTURBANCE_DETECTED" if affected_pixel_count > 0 else "NO_CHANGE"
        if dropped:
            limitations.append(
                f"{len(dropped)} candidate disturbance component(s) below the 1 ha / 25-pixel minimum "
                "mapping unit were excluded from affected_area_ha and affected_pixel_count."
            )
        artifacts_payload.update(
            dnbr=dnbr_arr,
            affected_mask=affected_mask,
            kept_components=kept,
            dropped_components=dropped,
            ndvi_before=ndvi_b,
            ndvi_after=ndvi_a,
        )

    if aoi_cloud_before is None or aoi_cloud_after is None:
        limitations.append("AOI cloud ratio could not be computed for one date (empty AOI footprint read).")

    firms_result = _resolve_firms(geometry, before["acquired_at"], after["acquired_at"], data_root, plot_id)
    firms_support = firms_result["support"]
    firms_points = firms_result.pop("points")
    if firms_support == "NOT_CHECKED":
        limitations.append(
            "No FIRMS source available: neither a cached archive under <data_root>/<plot_id>/firms/ nor a "
            "FIRMS_MAP_KEY env var. Fire attribution left as NOT_CHECKED, not fabricated. Backend policy "
            "routes unattributed disturbance to REVIEW_REQUIRED, not automatic freeze."
        )
    elif firms_support == "NOT_FOUND":
        limitations.append(
            "FIRMS checked against the archive for this window and AOI and found no qualifying hotspot; "
            "absence of a thermal anomaly is not proof that no disturbance occurred."
        )
    else:
        limitations.append(
            "FIRMS hotspots are an independent thermal-anomaly signal, not a fire perimeter or ground truth; "
            "they attribute the window, they do not delineate affected_area_ha."
        )

    evidence = {
        "schema_version": "1.0.0",
        "dataset_kind": request["dataset_kind"],
        "plot_id": plot_id,
        "plot_geometry_hash": request["plot_geometry_hash"],
        "observation": {"before": before, "after": after},
        "outcome": outcome,
        "method": {
            "pipeline_version": PIPELINE_VERSION,
            "code_commit": code_commit,
            "config_sha256": CONFIG_SHA256,
            "grid": {
                "epsg": epsg,
                "resolution_m": 20,
                "width": width,
                "height": height,
                "transform": list(transform),
            },
            "forest_mask": {
                "source": "ESA WorldCover 10m v200",
                "version": "v200",
                "reference_year": 2021,
                "sha256": "0x" + "0" * 64,  # filled in by bundle.py once the mask file is written
                "interpretation_note": (
                    "Tree-cover class (10) only; a 10 m global land-cover product resampled to the 20 m "
                    "analysis grid by nearest-neighbour, used identically for both dates in the pair."
                ),
            },
            "parameters": PARAMETERS,
        },
        "quality": {
            "paired_valid_aoi_ratio": _round(paired_valid_aoi_ratio),
            "paired_valid_forest_ratio": _round(paired_valid_forest_ratio),
            "aoi_cloud_ratio_before": _round(aoi_cloud_before),
            "aoi_cloud_ratio_after": _round(aoi_cloud_after),
            "metadata_complete": metadata_complete,
            "grid_aligned": True,
            "temporal_comparability": temporal_comparability,
            "temporal_note": temporal_note,
        },
        "metrics": {
            "plot_area_ha": plot_area_ha,
            "baseline_forest_area_ha": baseline_forest_area_ha,
            "analysed_forest_area_ha": analysed_forest_area_ha,
            "affected_area_ha": affected_area_ha,
            "affected_fraction_of_baseline_forest": affected_fraction,
            "ndvi_before_mean": ndvi_before_mean,
            "ndvi_after_mean": ndvi_after_mean,
            "dnbr_mean": dnbr_mean,
            "dnbr_mean_scope": "PAIRED_VALID_BASELINE_FOREST",
            "baseline_forest_pixel_count": baseline_forest_pixel_count,
            "paired_valid_forest_pixel_count": analysed_forest_pixel_count,
            "affected_pixel_count": affected_pixel_count,
        },
        "firms": {
            "support": firms_support,
            "hotspot_count": firms_result["hotspot_count"],
            "window_start": before["acquired_at"],
            "window_end": after["acquired_at"],
            "spatial_tolerance_m": 500,
            "product": firms_result["product"],
            "confidence_filter": list(firms_mod.DEFAULT_CONFIDENCE_FILTER),
            "source_refs": firms_result["source_refs"],
            "matched_points_artifact_id": firms_result["matched_points_artifact_id"],
        },
        "artifacts": [],  # filled in by bundle.py
        "limitations": limitations,
    }
    artifacts_payload["firms_points"] = firms_points
    return evidence, artifacts_payload


def _firms_archive_paths(data_root, plot_id):
    archive_dir = Path(data_root) / plot_id / "firms"
    return sorted(archive_dir.glob("*.csv")) if archive_dir.is_dir() else []


def _resolve_firms(geometry, window_start, window_end, data_root, plot_id):
    """Attribute the observation window against FIRMS, offline archive first.

    Returns the schema's `firms` fields plus the matched points bundle.py turns
    into firms.geojson. NOT_CHECKED is reported whenever no source is reachable;
    hotspots are never invented.
    """
    start = datetime.strptime(window_start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    end = datetime.strptime(window_end, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    empty = {
        "support": "NOT_CHECKED",
        "hotspot_count": 0,
        "product": "VIIRS_SNPP_NRT",
        "source_refs": [],
        "matched_points_artifact_id": None,
        "points": [],
    }

    archive_paths = _firms_archive_paths(data_root, plot_id)
    if archive_paths:
        hotspots = firms_mod.load_archive(archive_paths)
        product = "VIIRS_SNPP_ARCHIVE_C2"
        source_refs = [
            f"NASA FIRMS archive {path.name} sha256={_sha256_file(path)}" for path in archive_paths
        ]
    else:
        bbox = gridmath.bounds_wgs84(geometry)
        hotspots = firms_mod.fetch_hotspots(bbox, start, end)
        if hotspots is None:
            return empty
        product = "VIIRS_SNPP_NRT"
        source_refs = ["NASA FIRMS VIIRS_SNPP_NRT area API"]

    in_window = firms_mod.filter_hotspots(hotspots, start, end)
    matched = firms_mod.match_within_aoi(in_window, geometry)
    return {
        "support": "SUPPORTED" if matched else "NOT_FOUND",
        "hotspot_count": len(matched),
        "product": product,
        "source_refs": source_refs,
        "matched_points_artifact_id": "firms-points" if matched else None,
        "points": matched,
    }


def _sha256_file(path):
    digest_obj = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest_obj.update(chunk)
    return digest_obj.hexdigest()


def _project_coords(coords, transformer):
    if isinstance(coords[0], (int, float)):
        x, y = transformer.transform(coords[0], coords[1])
        return [x, y]
    return [_project_coords(c, transformer) for c in coords]
