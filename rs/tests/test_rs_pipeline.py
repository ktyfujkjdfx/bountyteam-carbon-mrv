"""RS-specific tests: harmonization, masks, grid, components, and the full
compute-evidence-and-bundle path on small synthetic local rasters (no network).

Two additional tests validate the actual REAL bundles committed under
rs/data/bundles/{no_change,fire}, produced by `python -m rs.build_bundles`
against real Sentinel-2 L2A scenes over Dadia National Park, Evros, Greece.
"""
import json
import uuid
from pathlib import Path

import numpy as np
import pytest
import rasterio

from rs import components, gridmath, harmonize, masks, pipeline, verify
from rs.contracts import check_schema, digest, read_json, validate_evidence

ROOT = Path(__file__).resolve().parents[2]

AOI_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[26.20, 41.13], [26.2018, 41.13], [26.2018, 41.1315], [26.20, 41.1315], [26.20, 41.13]]],
}
EPSG = gridmath.utm_epsg(26.201, 41.1307)


# --- harmonization: BOA offset must key off baseline, not be unconditional ---

@pytest.mark.parametrize(
    "baseline,expected_offset",
    [("02.14", 0), ("03.01", 0), ("03.99", 0), ("04.00", -1000), ("05.09", -1000)],
)
def test_boa_offset_keyed_by_baseline(baseline, expected_offset):
    scale, offset, origin = harmonize.from_baseline(baseline)
    assert offset == expected_offset
    assert scale == pytest.approx(1 / 10000)
    assert origin == "PRODUCT_METADATA"


def test_provider_harmonized_flag_overrides_baseline():
    # A pre-04.00 baseline would normally get offset=0 anyway, so use a
    # post-04.00 baseline to prove the provider flag suppresses the -1000
    # baseline-only offset instead of stacking with it.
    scale, offset, origin = harmonize.from_provider_metadata("05.09", True)
    assert (scale, offset, origin) == (1 / 10000, 0, "PROVIDER_HARMONIZED")
    scale, offset, origin = harmonize.from_provider_metadata("05.09", None)
    assert (scale, offset, origin) == (1 / 10000, -1000, "PRODUCT_METADATA")


def test_apply_scale_offset_matches_documented_formula():
    dn = np.array([1000, 2000, 11000], dtype="uint16")
    result = harmonize.apply_scale_offset(dn, 1 / 10000, -1000)
    assert np.allclose(result, [0.0, 0.1, 1.0])


# --- SCL mask: frozen exclusion list; dark-area/burn pixels are preserved ---

def test_scl_exclusion_list_is_frozen():
    assert masks.EXCLUDED_SCL_CLASSES == frozenset({0, 1, 2, 3, 6, 7, 8, 9, 10, 11})


def test_scl_mask_preserves_vegetation_and_bare_burnt_classes():
    # 4=vegetation, 5=bare soil/burnt ground: both must remain valid, per
    # RS plan 5.4 ("класс 5 сохраняй: post-fire bare ground может быть сигналом").
    scl = np.array([0, 4, 5, 9])
    assert list(masks.valid_mask(scl)) == [False, True, True, False]


def test_cloud_ratio_counts_only_8_9_10_not_all_excluded():
    scl = np.array([[3, 8], [9, 4]])  # 3 excluded-but-not-"cloud"; 4 valid
    footprint = np.ones_like(scl, dtype=bool)
    assert masks.cloud_ratio(scl, footprint) == pytest.approx(0.5)  # only the two class-8/9 pixels


# --- grid: north-up 20 m UTM, matching the frozen v1 grid contract ---

def test_snapped_grid_is_north_up_20m_utm():
    transform, width, height, _ = gridmath.snapped_grid(AOI_GEOMETRY, EPSG, 20)
    a, b, c, d, e, f = transform
    assert (a, b, d, e) == (20, 0, 0, -20)
    assert width > 0 and height > 0
    assert 32601 <= EPSG <= 32660


def test_pixel_area_is_fixed_at_20m_squared():
    assert components.PIXEL_AREA_HA == pytest.approx(0.04)
    assert components.MIN_COMPONENT_PIXELS == 25  # 1 ha / 0.04 ha


# --- connected components / minimum mapping unit ---

def test_mmu_drops_small_components_keeps_large_ones():
    transform = (20, 0, 500000, 0, -20, 4600000)
    candidate = np.zeros((10, 10), dtype=bool)
    candidate[0:3, 0:3] = True  # 9 px: below 25 px MMU
    candidate[5:10, 0:5] = True  # 25 px: exactly at MMU
    found = components.affected_components(candidate, rasterio.Affine(*transform))
    kept, dropped = components.apply_minimum_mapping_unit(found)
    assert sorted(count for _, count in kept) == [25]
    assert sorted(count for _, count in dropped) == [9]
    mask = components.rasterize_kept(kept, (10, 10), rasterio.Affine(*transform))
    assert int(mask.sum()) == 25


def test_components_to_geojson_is_valid_wgs84():
    transform = (20, 0, 500000, 0, -20, 4600000)
    candidate = np.zeros((10, 10), dtype=bool)
    candidate[0:5, 0:5] = True
    found = components.affected_components(candidate, rasterio.Affine(*transform))
    kept, _ = components.apply_minimum_mapping_unit(found)
    geojson = components.to_wgs84_geojson(kept, 32635)
    assert geojson["type"] == "FeatureCollection"
    lon, lat = geojson["features"][0]["geometry"]["coordinates"][0][0]
    assert -180 <= lon <= 180 and -90 <= lat <= 90


# --- full compute_evidence + bundle + schema/semantic validation, offline ---

def _write_band(path, array, transform, epsg, dtype="uint16"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", height=array.shape[0], width=array.shape[1], count=1,
        dtype=dtype, crs=f"EPSG:{epsg}", transform=rasterio.Affine(*transform),
    ) as dst:
        dst.write(array.astype(dtype), 1)


def _scene_dict(scene_id, acquired_at, assets):
    return {
        "scene_id": scene_id,
        "acquired_at": acquired_at,
        "provider": "TEST_FIXTURE",
        "collection": "sentinel-2-l2a",
        "processing_baseline": "05.09",
        "mgrs_tile": "35TMF",
        "assets": assets,
    }


def _build_offline_case(tmp_path, *, after_b12_boost, disturbed_slice, forest_everywhere=True, scl_after_cloud=False):
    """Writes native (already-grid-aligned) synthetic bands for one before/after
    pair and returns a fully schema-valid rs-request.json dict.
    """
    from rs import acquire

    transform, width, height, _ = gridmath.snapped_grid(AOI_GEOMETRY, EPSG, 20)
    plot_id = "TESTPLOT-001"
    data_root = tmp_path / "data"

    base_reflectance_dn = {"B04": 1500, "B08": 4000, "B8A": 4200, "B12": 1200}
    scenes = {}
    for side, scene_id, acquired_at in (
        ("before", "TESTSCENE_before", "2023-08-05T09:09:07Z"),
        ("after", "TESTSCENE_after", "2023-08-30T09:09:08Z"),
    ):
        scene_dir = data_root / plot_id / scene_id
        assets = []
        for band, dn_value in base_reflectance_dn.items():
            arr = np.full((height, width), dn_value, dtype="uint16")
            if side == "after" and band == "B12":
                arr = arr.copy()
                arr[disturbed_slice] += after_b12_boost
            if side == "after" and band == "B8A" and after_b12_boost:
                arr = arr.copy()
                arr[disturbed_slice] = arr[disturbed_slice] // 3  # NIR collapse on burn
            path = scene_dir / f"{band}.tif"
            _write_band(path, arr, transform, EPSG)
            assets.append(
                {
                    "band": band,
                    "source_ref": f"test://{scene_id}/{band}",
                    "local_sha256": acquire.sha256_file(path),
                    "scale_applied": 0.0001,
                    "offset_applied": 0,
                    "transform_origin": "PRODUCT_METADATA",
                }
            )
        scl_value = 9 if (side == "after" and scl_after_cloud) else 4
        scl_arr = np.full((height, width), scl_value, dtype="uint8")
        scl_path = scene_dir / "SCL.tif"
        _write_band(scl_path, scl_arr, transform, EPSG, dtype="uint8")
        assets.append(
            {
                "band": "SCL",
                "source_ref": f"test://{scene_id}/SCL",
                "local_sha256": acquire.sha256_file(scl_path),
                "scale_applied": 1,
                "offset_applied": 0,
                "transform_origin": "PRODUCT_METADATA",
            }
        )
        scenes[side] = _scene_dict(scene_id, acquired_at, assets)

    forest_value = 10 if forest_everywhere else 30
    forest_arr = np.full((height, width), forest_value, dtype="uint8")
    forest_path = data_root / plot_id / "forest_mask_source.tif"
    _write_band(forest_path, forest_arr, transform, EPSG, dtype="uint8")

    request_path = tmp_path / "request.json"
    geometry_hash = digest(AOI_GEOMETRY)
    request = {
        "schema_version": "1.0.0",
        "request_id": str(uuid.uuid4()),
        "plot_id": plot_id,
        "geometry": AOI_GEOMETRY,
        "plot_geometry_hash": geometry_hash,
        "before": scenes["before"],
        "after": scenes["after"],
        "parameters": pipeline.PARAMETERS,
        "data_root": str(data_root),
        "dataset_kind": "SYNTHETIC",
    }
    check_schema(request, "rs-request.schema.json")
    request_path.write_text(json.dumps(request), encoding="utf-8")
    return request_path


def test_no_change_outcome_on_stable_synthetic_pair(tmp_path):
    request_path = _build_offline_case(tmp_path, after_b12_boost=0, disturbed_slice=np.s_[0:0, 0:0])
    evidence = verify.run(request_path, tmp_path / "bundle")
    assert evidence["outcome"] == "NO_CHANGE"
    assert evidence["metrics"]["affected_pixel_count"] == 0


def test_disturbance_detected_with_exact_pixel_count(tmp_path):
    # A 6x5 = 30-pixel block (>= 25 px MMU) gets a strong burn signature.
    request_path = _build_offline_case(tmp_path, after_b12_boost=6000, disturbed_slice=np.s_[2:8, 2:7])
    evidence = verify.run(request_path, tmp_path / "bundle")
    assert evidence["outcome"] == "DISTURBANCE_DETECTED"
    assert evidence["metrics"]["affected_pixel_count"] == 30
    assert evidence["metrics"]["affected_area_ha"] == pytest.approx(30 * 0.04)


def test_sub_mmu_disturbance_is_filtered_to_no_change(tmp_path):
    # A 4x4 = 16-pixel block is below the 25-pixel MMU: must NOT count.
    request_path = _build_offline_case(tmp_path, after_b12_boost=6000, disturbed_slice=np.s_[2:6, 2:6])
    evidence = verify.run(request_path, tmp_path / "bundle")
    assert evidence["outcome"] == "NO_CHANGE"
    assert evidence["metrics"]["affected_pixel_count"] == 0
    assert any("minimum" in note for note in evidence["limitations"])


def test_insufficient_data_when_coverage_below_gate(tmp_path):
    request_path = _build_offline_case(
        tmp_path, after_b12_boost=0, disturbed_slice=np.s_[0:0, 0:0], scl_after_cloud=True
    )
    evidence = verify.run(request_path, tmp_path / "bundle")
    assert evidence["outcome"] == "INSUFFICIENT_DATA"
    assert evidence["metrics"]["affected_pixel_count"] is None
    assert evidence["metrics"]["dnbr_mean"] is None


def test_produced_evidence_has_no_forbidden_fields_or_states(tmp_path):
    request_path = _build_offline_case(tmp_path, after_b12_boost=6000, disturbed_slice=np.s_[2:8, 2:7])
    evidence = verify.run(request_path, tmp_path / "bundle")
    dumped = json.dumps(evidence)
    for forbidden in ('"FROZEN"', '"ACTIVE"', '"REVOKED"', '"FREEZE_REQUESTED"', '"evidence_hash"', '"confidence":', '"confidence_score"'):
        assert forbidden not in dumped


def test_no_nan_or_infinity_and_relative_paths_use_forward_slashes(tmp_path):
    request_path = _build_offline_case(tmp_path, after_b12_boost=6000, disturbed_slice=np.s_[2:8, 2:7])
    bundle_dir = tmp_path / "bundle"
    evidence = verify.run(request_path, bundle_dir)
    raw = (bundle_dir / "verification.json").read_text(encoding="utf-8")
    assert "NaN" not in raw and "Infinity" not in raw
    for artifact in evidence["artifacts"]:
        assert "\\" not in artifact["relative_path"]


def test_reproducible_rerun_produces_identical_canonical_bytes(tmp_path):
    from rs.contracts import canonical

    request_path = _build_offline_case(tmp_path, after_b12_boost=6000, disturbed_slice=np.s_[2:8, 2:7])
    evidence_1 = verify.run(request_path, tmp_path / "bundle1")
    evidence_2 = verify.run(request_path, tmp_path / "bundle2")
    # method.code_commit may legitimately differ across environments (absent
    # vs. present git checkout); everything scientifically relevant must match.
    for key in ("outcome", "quality", "metrics", "firms", "limitations"):
        assert evidence_1[key] == evidence_2[key]
    assert canonical({k: v for k, v in evidence_1.items() if k != "artifacts"}) == canonical(
        {k: v for k, v in evidence_2.items() if k != "artifacts"}
    )


# --- the real bundles committed under rs/bundles/ ---

REAL_BUNDLES = [
    ("no_change", "request_no_change.json", "NO_CHANGE", "35TMF"),
    ("fire", "request_fire.json", "DISTURBANCE_DETECTED", "35TMF"),
    ("evia_reserve_no_change", "request_evia_reserve_no_change.json", "DISTURBANCE_DETECTED", "34SFJ"),
]


@pytest.mark.parametrize("bundle_name,request_name,expected_outcome,expected_tile", REAL_BUNDLES)
def test_real_bundle_is_schema_and_semantically_valid(bundle_name, request_name, expected_outcome, expected_tile):
    bundle_dir = ROOT / "rs" / "bundles" / bundle_name
    evidence_path = bundle_dir / "verification.json"
    if not evidence_path.exists():
        pytest.skip(f"real bundle not present: {evidence_path}")
    evidence = read_json(evidence_path)
    assert evidence["dataset_kind"] == "REAL"
    assert evidence["outcome"] == expected_outcome
    request = read_json(ROOT / "rs" / "configs" / request_name)
    result = validate_evidence(evidence, bundle_dir, request["geometry"])
    assert result["evidence_quality"] in ("SUFFICIENT", "REVIEW_REQUIRED", "INSUFFICIENT")
    for scene in (evidence["observation"]["before"], evidence["observation"]["after"]):
        assert not scene["scene_id"].startswith("SYNTHETIC")
        assert scene["provider"] and scene["mgrs_tile"] == expected_tile


def test_real_bundle_below_policy_area_threshold_is_not_over_claimed():
    # The Evia reserve pair legitimately finds a small (1.68 ha) real
    # disturbance well under the 5 ha backend policy freeze threshold: RS must
    # report it as DISTURBANCE_DETECTED (honest), not suppress it as
    # NO_CHANGE, and must not itself decide REVIEW_REQUIRED/FREEZE_REQUESTED.
    bundle_dir = ROOT / "rs" / "bundles" / "evia_reserve_no_change"
    evidence_path = bundle_dir / "verification.json"
    if not evidence_path.exists():
        pytest.skip(f"real bundle not present: {evidence_path}")
    evidence = read_json(evidence_path)
    assert evidence["outcome"] == "DISTURBANCE_DETECTED"
    assert evidence["metrics"]["affected_area_ha"] < 5
    assert "decision" not in evidence and "credit_status" not in evidence
    policy = read_json(ROOT / "config" / "policy.v1.json")
    result = validate_evidence(evidence)
    assert evidence["metrics"]["affected_area_ha"] < policy["freeze_min_area_ha"]
    assert result["decision"] == "REVIEW_REQUIRED"  # Backend's own recomputation, read-only here


@pytest.mark.parametrize("bundle_name,request_name,_outcome,_tile", REAL_BUNDLES)
def test_real_bundle_rejects_tampered_artifact(tmp_path, bundle_name, request_name, _outcome, _tile):
    # Equivalent of Backend's import-time integrity check on one of OUR real
    # bundles: flipping a byte in a committed artifact must fail validation.
    bundle_dir = ROOT / "rs" / "bundles" / bundle_name
    if not (bundle_dir / "verification.json").exists():
        pytest.skip(f"real bundle not present: {bundle_dir}")
    import shutil

    copy_dir = tmp_path / "bundle"
    shutil.copytree(bundle_dir, copy_dir)
    evidence = read_json(copy_dir / "verification.json")
    request = read_json(ROOT / "rs" / "configs" / request_name)
    tampered_artifact = next(a for a in evidence["artifacts"] if a["media_type"] in ("image/png", "image/tiff"))
    with (copy_dir / tampered_artifact["relative_path"]).open("ab") as handle:
        handle.write(b"TAMPERED")
    with pytest.raises(ValueError):
        validate_evidence(evidence, copy_dir, request["geometry"])
