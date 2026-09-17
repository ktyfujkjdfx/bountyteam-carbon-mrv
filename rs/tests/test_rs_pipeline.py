"""RS-specific tests: harmonization, masks, grid, indices, components, and the
full compute-evidence-and-bundle path on small synthetic local rasters (no
network required to run this file).

Several tests additionally validate the REAL bundles committed under
rs/bundles/{no_change,fire,evia_reserve_no_change}, produced by
`python -m rs.build_bundles` against real Sentinel-2 L2A scenes over Dadia
National Park, Evros, Greece (primary) and northern Evia (reserve).
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
import rasterio

from rs import components, firms, gridmath, harmonize, indices, masks, pipeline, verify
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


# --- indices: NDVI/NBR/dNBR formulas, matching the frozen band choice ---

def test_ndvi_nbr_dnbr_formulas():
    b04, b08 = np.array([1000.0]), np.array([3000.0])
    assert indices.ndvi(b08, b04) == pytest.approx([(3000 - 1000) / (3000 + 1000)])

    b8a, b12 = np.array([4000.0]), np.array([1000.0])
    nbr_before = indices.nbr(b8a, b12)
    assert nbr_before == pytest.approx([(4000 - 1000) / (4000 + 1000)])

    nbr_after = indices.nbr(np.array([1500.0]), np.array([4000.0]))
    dnbr = indices.dnbr(nbr_before, nbr_after)
    # dNBR = NBR_before - NBR_after; burn signature (NIR down, SWIR up) must
    # yield a large POSITIVE dNBR, matching rs.indices.dnbr_class thresholds.
    assert dnbr[0] > 0.27
    assert indices.dnbr_class(float(dnbr[0])) in ("moderate-high", "high")


def test_dnbr_index_handles_zero_denominator_without_crashing():
    zero = np.array([0.0])
    result = indices.nbr(zero, zero)
    assert np.isnan(result[0])  # explicit NaN, not a ZeroDivisionError/warning crash


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


def test_request_with_reversed_observation_dates_is_rejected(tmp_path):
    request_path = _build_offline_case(tmp_path, after_b12_boost=0, disturbed_slice=np.s_[0:0, 0:0])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["before"], request["after"] = request["after"], request["before"]
    request_path.write_text(json.dumps(request), encoding="utf-8")
    with pytest.raises(ValueError):
        verify.run(request_path, tmp_path / "bundle")


def test_source_index_hashes_match_declared_asset_hashes(tmp_path):
    request_path = _build_offline_case(tmp_path, after_b12_boost=6000, disturbed_slice=np.s_[2:8, 2:7])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    bundle_dir = tmp_path / "bundle"
    verify.run(request_path, bundle_dir)
    source_index = json.loads((bundle_dir / "source-index.json").read_text(encoding="utf-8"))
    declared_hashes = {a["local_sha256"] for scene in (request["before"], request["after"]) for a in scene["assets"]}
    assert declared_hashes <= set(source_index)
    from rs.contracts import sha_bytes

    for hash_value, relative_path in source_index.items():
        assert sha_bytes((bundle_dir / relative_path).read_bytes()) == hash_value


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


# --- byte-level determinism (see rs/determinism.py) ---


def _file_hashes(bundle_dir):
    """SHA-256 of every file in a bundle, keyed by POSIX-style relative path."""
    from rs.contracts import sha_bytes

    return {
        path.relative_to(bundle_dir).as_posix(): sha_bytes(path.read_bytes())
        for path in sorted(bundle_dir.rglob("*"))
        if path.is_file()
    }


def test_rebuilding_a_bundle_twice_gives_byte_identical_files(tmp_path):
    # The whole-bundle version of the reproducibility claim: not just equal
    # JSON values, but the same bytes in every artifact, so the SHA-256 that
    # Backend re-checks on import cannot drift between two runs.
    request_path = _build_offline_case(tmp_path, after_b12_boost=6000, disturbed_slice=np.s_[2:8, 2:7])
    first, second = tmp_path / "run1", tmp_path / "run2"
    fixed_commit = "0" * 40  # pin the one field that is allowed to vary by design
    verify.run(request_path, first, code_commit=fixed_commit)
    verify.run(request_path, second, code_commit=fixed_commit)

    hashes_1, hashes_2 = _file_hashes(first), _file_hashes(second)
    assert set(hashes_1) == set(hashes_2), "the two runs produced different file sets"
    mismatched = [name for name in hashes_1 if hashes_1[name] != hashes_2[name]]
    assert not mismatched, f"non-deterministic artifacts: {mismatched}"
    # and the manifest each bundle declares must agree with the bytes on disk
    for entry in read_json(first / "verification.json")["artifacts"]:
        assert entry["sha256"] == hashes_1[entry["relative_path"]]


def test_bundle_files_are_written_as_bytes_without_platform_newlines(tmp_path):
    # Path.write_text would translate "\n" to "\r\n" on Windows and nowhere
    # else, which silently changes every hash. Canonical JSON has no newline
    # at all, so a CR anywhere in these files means text mode crept back in.
    request_path = _build_offline_case(tmp_path, after_b12_boost=6000, disturbed_slice=np.s_[2:8, 2:7])
    bundle_dir = tmp_path / "bundle"
    verify.run(request_path, bundle_dir, code_commit="0" * 40)
    for name in ("verification.json", "source-index.json", "affected_area.geojson"):
        data = (bundle_dir / name).read_bytes()
        assert b"\r" not in data and b"\n" not in data, f"{name} was written in text mode"


def test_canonical_json_round_trips_through_the_shared_helper(tmp_path):
    # verification.json on disk must BE the canonical bytes Backend hashes, so
    # formatting can never make the file and its evidence_hash disagree.
    from rs.contracts import canonical

    request_path = _build_offline_case(tmp_path, after_b12_boost=0, disturbed_slice=np.s_[0:0, 0:0])
    bundle_dir = tmp_path / "bundle"
    verify.run(request_path, bundle_dir, code_commit="0" * 40)
    raw = (bundle_dir / "verification.json").read_bytes()
    assert raw == canonical(json.loads(raw.decode("utf-8")))


def test_geojson_coordinates_are_rounded_to_a_fixed_precision(tmp_path):
    from rs import determinism

    request_path = _build_offline_case(tmp_path, after_b12_boost=6000, disturbed_slice=np.s_[2:8, 2:7])
    bundle_dir = tmp_path / "bundle"
    verify.run(request_path, bundle_dir, code_commit="0" * 40)
    features = read_json(bundle_dir / "affected_area.geojson")["features"]
    assert features
    for feature in features:
        for ring in feature["geometry"]["coordinates"]:
            for lon, lat in ring:
                assert round(lon, determinism.COORDINATE_DECIMALS) == lon
                assert round(lat, determinism.COORDINATE_DECIMALS) == lat


def test_block_mean_is_exact_integer_arithmetic():
    from rs import resample

    native = np.array([[1, 2, 10, 11],
                       [3, 4, 12, 13],
                       [5, 6, 20, 21],
                       [7, 8, 22, 23]], dtype="uint16")
    got = resample.block_mean(native, (0, 0, 2), 2, 2)
    assert np.array_equal(got, np.array([[2.5, 11.5], [6.5, 21.5]]))
    # exact in binary: /4 is a power of two, so there is no rounding to differ over
    assert all(float(v).is_integer() or float(v * 4).is_integer() for v in got.ravel())


def test_resample_plan_refuses_grids_that_do_not_line_up():
    from rasterio.transform import Affine

    from rs import resample

    dst = (20, 0, 500000, 0, -20, 4000000)
    aligned = Affine(10, 0, 499900, 0, -10, 4000100)
    assert resample.plan(aligned, "EPSG:32635", (400, 400), dst, 10, 10, "EPSG:32635") == (10, 10, 2)
    # different CRS
    assert resample.plan(aligned, "EPSG:32634", (400, 400), dst, 10, 10, "EPSG:32635") is None
    # half-pixel offset
    shifted = Affine(10, 0, 499905, 0, -10, 4000100)
    assert resample.plan(shifted, "EPSG:32635", (400, 400), dst, 10, 10, "EPSG:32635") is None
    # destination runs past the cached window
    assert resample.plan(aligned, "EPSG:32635", (12, 12), dst, 10, 10, "EPSG:32635") is None


def test_preview_stretch_is_immune_to_last_ulp_input_noise():
    # Regression guard for a real cross-platform failure the CI matrix caught:
    # Resampling.average sums in a CPU-dependent order, so reflectance differed
    # in the last ULP on arm64 and previews (but not dnbr.tif) hashed
    # differently on macOS. Perturbing every sample by an ULP must not change a
    # single output byte.
    from rs import preview as preview_mod

    rng = np.random.default_rng(20230821)
    band = np.round(rng.uniform(0.0, 0.6, size=(40, 40)), 4)
    nudged = np.nextafter(band, np.inf)
    nudged[::2] = np.nextafter(band[::2], -np.inf)
    assert not np.array_equal(band, nudged)
    assert np.array_equal(preview_mod._stretch(band), preview_mod._stretch(nudged))


def test_preview_quantisation_is_tie_stable_on_the_dn_lattice():
    # Averaging integer DNs lands on exact .5 constantly, and whether the float
    # is .5 or .5 +/- 1 ULP is exactly what differs between platforms. All
    # three must land on the same lattice point.
    from rs import preview as preview_mod

    half = 2.5 / preview_mod.DN_SCALE
    values = np.array([half, np.nextafter(half, np.inf), np.nextafter(half, -np.inf)])
    quantised = preview_mod._quantize(values)
    assert len(set(quantised.tolist())) == 1
    # NaN must survive quantisation so masked pixels stay "no data"
    assert np.isnan(preview_mod._quantize(np.array([np.nan])))[0]


def test_png_encoding_is_pinned_and_carries_no_timestamp(tmp_path):
    from PIL import Image

    from rs import determinism

    image = Image.fromarray(np.arange(48, dtype="uint8").reshape(4, 4, 3))
    first, second = determinism.png_bytes(image), determinism.png_bytes(image)
    assert first == second
    # tIME is the PNG chunk that would embed "now" into every rebuild.
    assert b"tIME" not in first and b"tEXt" not in first


def test_code_commit_is_null_rather_than_a_commit_that_cannot_reproduce(monkeypatch):
    # Recording HEAD while the pipeline has uncommitted edits would claim a
    # commit whose code does not produce these bytes. Null is the honest answer.
    monkeypatch.setattr(verify, "_git", lambda *args: "a" * 40 if args[0] == "rev-parse" else " M rs/pipeline.py")
    assert verify.resolve_code_commit() is None
    monkeypatch.setattr(verify, "_git", lambda *args: "a" * 40 if args[0] == "rev-parse" else "")
    assert verify.resolve_code_commit() == "a" * 40
    assert verify.resolve_code_commit("b" * 40) == "b" * 40
    with pytest.raises(ValueError):
        verify.resolve_code_commit("not-a-sha")


# --- FIRMS attribution ---


def _hotspot(lon, lat, date, time="1200", confidence="n"):
    return {"longitude": str(lon), "latitude": str(lat), "acq_date": date, "acq_time": time,
            "confidence": confidence}


def test_firms_archive_url_is_keyless_and_per_country_year():
    url = firms.archive_url(2023, "Greece")
    assert url.startswith("https://firms.modaps.eosdis.nasa.gov/data/country/")
    assert url.endswith("viirs-snpp_2023_Greece.csv")
    assert "key" not in url.lower()  # the archive needs no MAP_KEY; the area API does


def test_firms_confidence_labels_cover_archive_and_api_spellings():
    # The yearly archive writes l/n/h, the area API writes low/nominal/high.
    assert [firms.confidence_label(c) for c in ("l", "n", "h")] == ["low", "nominal", "high"]
    assert firms.confidence_label("NOMINAL") == "nominal"
    assert "low" not in firms.DEFAULT_CONFIDENCE_FILTER


def test_firms_window_filter_drops_out_of_window_and_low_confidence():
    start = datetime(2023, 8, 5, 9, 0, tzinfo=timezone.utc)
    end = datetime(2023, 8, 30, 9, 0, tzinfo=timezone.utc)
    rows = [
        _hotspot(26.2, 41.13, "2023-08-22", "1008", "h"),   # kept
        _hotspot(26.2, 41.13, "2023-08-23", "0130", "n"),   # kept
        _hotspot(26.2, 41.13, "2023-08-23", "0130", "l"),   # dropped: low confidence
        _hotspot(26.2, 41.13, "2023-08-04", "1200", "h"),   # dropped: before window
        _hotspot(26.2, 41.13, "2023-09-01", "1200", "h"),   # dropped: after window
    ]
    kept = firms.filter_hotspots(rows, start, end)
    assert [p["acq_date"] for p in kept] == ["2023-08-22", "2023-08-23"]
    assert all(firms.confidence_label(p["confidence"]) != "low" for p in kept)


def test_firms_window_is_half_open_excluding_t_before_including_t_after():
    # (T_before, T_after]: a hotspot burning at the moment the "before" scene
    # was acquired is already part of that scene and cannot explain a change
    # measured against it; one at exactly T_after still can.
    start = datetime(2023, 8, 5, 9, 0, tzinfo=timezone.utc)
    end = datetime(2023, 8, 30, 9, 0, tzinfo=timezone.utc)
    at_start = _hotspot(26.2, 41.13, "2023-08-05", "0900")
    one_minute_after_start = _hotspot(26.2, 41.13, "2023-08-05", "0901")
    at_end = _hotspot(26.2, 41.13, "2023-08-30", "0900")
    one_minute_after_end = _hotspot(26.2, 41.13, "2023-08-30", "0901")
    kept = firms.filter_hotspots([at_start, one_minute_after_start, at_end, one_minute_after_end], start, end)
    assert at_start not in kept
    assert one_minute_after_start in kept
    assert at_end in kept
    assert one_minute_after_end not in kept


def _utm_damage_square(epsg=32635, x=500000.0, y=4550000.0, side=200.0):
    """A square damage component in grid coordinates, as components produce."""
    from shapely.geometry import box

    return [box(x, y, x + side, y + side)]


def _hotspot_at_metres_east(damage, epsg, distance_m, date="2023-08-22"):
    """A hotspot `distance_m` due east of the damage square's eastern edge."""
    from pyproj import Transformer

    minx, miny, maxx, maxy = damage[0].bounds
    to_wgs = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    lon, lat = to_wgs.transform(maxx + distance_m, (miny + maxy) / 2)
    return _hotspot(lon, lat, date)


def test_firms_point_499m_from_damage_mask_is_included():
    damage = _utm_damage_square()
    point = _hotspot_at_metres_east(damage, 32635, 499)
    assert firms.match_within_damage_mask([point], damage, 32635) == [point]


def test_firms_point_501m_from_damage_mask_is_excluded():
    damage = _utm_damage_square()
    point = _hotspot_at_metres_east(damage, 32635, 501)
    assert firms.match_within_damage_mask([point], damage, 32635) == []
    assert firms.SPATIAL_TOLERANCE_M == 500


def test_firms_buffer_is_metric_in_the_grid_crs_not_web_mercator():
    # EPSG:3857 units are not metres away from the equator: at ~41 N a "500 m"
    # Web Mercator buffer is only ~377 m on the ground, so a genuine 450 m
    # hotspot would be wrongly dropped. The grid CRS is metric where the plot is.
    from pyproj import Transformer
    from shapely.geometry import Point
    from shapely.ops import transform as shapely_transform, unary_union

    damage = _utm_damage_square()
    point = _hotspot_at_metres_east(damage, 32635, 450)
    assert firms.match_within_damage_mask([point], damage, 32635) == [point]

    to_3857 = Transformer.from_crs("EPSG:32635", "EPSG:3857", always_xy=True)
    mercator_damage = shapely_transform(lambda x, y: to_3857.transform(x, y), unary_union(damage))
    mercator_point = Point(*to_3857.transform(
        *Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True).transform(
            float(point["longitude"]), float(point["latitude"]))))
    assert not mercator_damage.buffer(500).intersects(mercator_point), (
        "if this ever passes, Web Mercator became metric and the CRS choice stopped mattering")


def test_firms_matches_the_damage_mask_not_the_whole_aoi():
    # Buffering the AOI answers a weaker question ("was there a fire anywhere
    # near this plot") and over-counts hotspots far from what was measured.
    damage = _utm_damage_square()
    near_damage = _hotspot_at_metres_east(damage, 32635, 100)
    elsewhere_in_aoi = _hotspot_at_metres_east(damage, 32635, 3000)
    matched = firms.match_within_damage_mask([near_damage, elsewhere_in_aoi], damage, 32635)
    assert matched == [near_damage]


def test_firms_finds_nothing_when_there_is_no_damage_to_attribute():
    point = _hotspot(26.2, 41.13, "2023-08-22")
    assert firms.match_within_damage_mask([point], [], 32635) == []


def test_firms_is_not_checked_without_an_archive_or_map_key(tmp_path, monkeypatch):
    # No cached archive directory and no MAP_KEY must yield NOT_CHECKED with an
    # explicit limitation - never an invented hotspot count.
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    request_path = _build_offline_case(tmp_path, after_b12_boost=0, disturbed_slice=np.s_[0:0, 0:0])
    evidence = verify.run(request_path, tmp_path / "bundle")
    assert evidence["firms"] == {
        "support": "NOT_CHECKED", "hotspot_count": 0,
        "window_start": evidence["observation"]["before"]["acquired_at"],
        "window_end": evidence["observation"]["after"]["acquired_at"],
        "spatial_tolerance_m": 500, "product": "VIIRS_SNPP_NRT",
        "confidence_filter": ["nominal", "high"], "source_refs": [],
        "matched_points_artifact_id": None,
    }
    assert any("NOT_CHECKED" in line for line in evidence["limitations"])


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
def test_real_scenes_use_the_exact_resampling_path(bundle_name, request_name, _outcome, _tile):
    # Guard against silently falling back to GDAL's warper, which was measured
    # to differ between platforms and is what broke preview hashes on macOS.
    from rs import resample

    request_path = ROOT / "rs" / "configs" / request_name
    if not request_path.exists():
        pytest.skip(f"request not present: {request_path}")
    request = read_json(request_path)
    bounds = gridmath.bounds_wgs84(request["geometry"])
    epsg = gridmath.utm_epsg((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
    transform, width, height, _ = gridmath.snapped_grid(request["geometry"], epsg, 20)
    for side in ("before", "after"):
        for asset in request[side]["assets"]:
            path = (ROOT / request["data_root"] / request["plot_id"]
                    / request[side]["scene_id"] / f"{asset['band']}.tif")
            if not path.exists():
                pytest.skip(f"cached source not present: {path}")
            with rasterio.open(path) as src:
                plan = resample.plan(src.transform, src.crs, (src.height, src.width),
                                     transform, width, height, f"EPSG:{epsg}")
            assert plan is not None, f"{asset['band']} would fall back to GDAL warping"
            assert resample.describe(plan) in ("EXACT_SLICE", "EXACT_BLOCK_MEAN_2X")


# Exact counts, not just "> 0": matching against the whole AOI instead of the
# damage mask, or an inclusive window start, both silently inflate this.
REAL_BUNDLE_FIRMS = [("no_change", "NOT_FOUND", 0), ("fire", "SUPPORTED", 37),
                     ("evia_reserve_no_change", "NOT_FOUND", 0)]


@pytest.mark.parametrize("bundle_name,expected_support,expected_count", REAL_BUNDLE_FIRMS)
def test_real_bundle_firms_hotspot_count_is_exact(bundle_name, expected_support, expected_count):
    bundle_dir = ROOT / "rs" / "bundles" / bundle_name
    evidence_path = bundle_dir / "verification.json"
    if not evidence_path.exists():
        pytest.skip(f"real bundle not present: {evidence_path}")
    block = read_json(evidence_path)["firms"]
    assert (block["support"], block["hotspot_count"]) == (expected_support, expected_count)


@pytest.mark.parametrize("bundle_name,expected_support,_count", REAL_BUNDLE_FIRMS)
def test_real_bundle_firms_matched_points_obey_the_stated_rule(bundle_name, expected_support, _count):
    # Re-derive the rule from the committed artifacts: every point in
    # firms.geojson must sit in (T_before, T_after] and within 500 m of the
    # committed affected_area polygons, measured in method.grid.epsg.
    bundle_dir = ROOT / "rs" / "bundles" / bundle_name
    evidence_path = bundle_dir / "verification.json"
    if not evidence_path.exists():
        pytest.skip(f"real bundle not present: {evidence_path}")
    evidence = read_json(evidence_path)
    if evidence["firms"]["support"] != "SUPPORTED":
        return
    from pyproj import Transformer
    from shapely.geometry import Point, shape
    from shapely.ops import transform as shapely_transform, unary_union

    epsg = evidence["method"]["grid"]["epsg"]
    to_grid = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    damage_wgs84 = unary_union([shape(f["geometry"])
                                for f in read_json(bundle_dir / "affected_area.geojson")["features"]])
    damage = shapely_transform(lambda x, y: to_grid.transform(x, y), damage_wgs84)
    start = datetime.strptime(evidence["firms"]["window_start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    end = datetime.strptime(evidence["firms"]["window_end"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    for feature in read_json(bundle_dir / "firms.geojson")["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        distance = damage.distance(Point(*to_grid.transform(lon, lat)))
        assert distance <= evidence["firms"]["spatial_tolerance_m"], f"{distance:.1f} m from the damage mask"
        stamp = firms.acquired_at(feature["properties"])
        assert start < stamp <= end


@pytest.mark.parametrize("bundle_name,expected_support,_count", REAL_BUNDLE_FIRMS)
def test_real_bundle_firms_support_matches_the_committed_points(bundle_name, expected_support, _count):
    # The keyless FIRMS archive is checked for every real bundle, so support is
    # never NOT_CHECKED here; SUPPORTED must be backed by a real points artifact
    # and NOT_FOUND must carry no count and no artifact.
    bundle_dir = ROOT / "rs" / "bundles" / bundle_name
    evidence_path = bundle_dir / "verification.json"
    if not evidence_path.exists():
        pytest.skip(f"real bundle not present: {evidence_path}")
    block = read_json(evidence_path)["firms"]
    assert block["support"] == expected_support
    assert block["product"] == "VIIRS_SNPP_ARCHIVE_C2"
    assert block["source_refs"] and all("sha256=" in ref for ref in block["source_refs"])
    if expected_support == "NOT_FOUND":
        assert block["hotspot_count"] == 0 and block["matched_points_artifact_id"] is None
        assert not (bundle_dir / "firms.geojson").exists()
        return
    assert block["matched_points_artifact_id"] == "firms-points"
    features = read_json(bundle_dir / "firms.geojson")["features"]
    assert len(features) == block["hotspot_count"] > 0
    start = datetime.strptime(block["window_start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    end = datetime.strptime(block["window_end"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    for feature in features:
        stamp = firms.acquired_at(feature["properties"])
        assert start <= stamp <= end
        assert firms.confidence_label(feature["properties"]["confidence"]) in block["confidence_filter"]


def test_fire_bundle_satisfies_every_frozen_freeze_precondition():
    # RS does not decide a freeze, but the fire bundle must carry everything
    # policy v1 requires for Backend to be able to: area, forest fraction and
    # independent FIRMS support. RS still emits no decision or credit state.
    bundle_dir = ROOT / "rs" / "bundles" / "fire"
    evidence_path = bundle_dir / "verification.json"
    if not evidence_path.exists():
        pytest.skip(f"real bundle not present: {evidence_path}")
    evidence = read_json(evidence_path)
    policy = read_json(ROOT / "config" / "policy.v1.json")
    metrics = evidence["metrics"]
    assert metrics["affected_area_ha"] >= policy["freeze_min_area_ha"]
    assert metrics["affected_fraction_of_baseline_forest"] >= policy["freeze_min_forest_fraction"]
    assert policy["require_firms_support"] and evidence["firms"]["support"] == "SUPPORTED"
    assert "decision" not in evidence and "credit_status" not in evidence


@pytest.mark.parametrize("bundle_name,request_name,_outcome,_tile", REAL_BUNDLES)
def test_real_bundle_rebuilds_byte_identically_on_this_platform(tmp_path, bundle_name, request_name, _outcome, _tile):
    # The cross-platform half of the determinism claim. The committed bundles
    # were generated on one OS; this rebuilds them from the committed sources
    # on whatever OS is running and requires every byte to match. In CI that
    # is Windows, macOS and Linux (see .github/workflows/cross-platform-readiness.yml).
    bundle_dir = ROOT / "rs" / "bundles" / bundle_name
    if not (bundle_dir / "verification.json").exists():
        pytest.skip(f"real bundle not present: {bundle_dir}")
    committed = read_json(bundle_dir / "verification.json")
    rebuilt_dir = tmp_path / bundle_name
    verify.run(ROOT / "rs" / "configs" / request_name, rebuilt_dir,
               code_commit=committed["method"]["code_commit"])

    committed_hashes, rebuilt_hashes = _file_hashes(bundle_dir), _file_hashes(rebuilt_dir)
    assert set(committed_hashes) == set(rebuilt_hashes)
    mismatched = [name for name in committed_hashes if committed_hashes[name] != rebuilt_hashes[name]]
    if mismatched:
        # Name what actually drifted. A preview-only difference and a drift in
        # the measured science are very different bugs, and the file list alone
        # cannot tell them apart (verification.json embeds artifact hashes), so
        # also report how far apart the raster bytes are: a handful of pixels
        # off by one grey level is a quantisation boundary, a broad difference
        # is a different computation.
        rebuilt = read_json(rebuilt_dir / "verification.json")
        fields = sorted(k for k in set(committed) | set(rebuilt) if committed.get(k) != rebuilt.get(k))
        detail = []
        for name in mismatched:
            if not name.endswith(".png"):
                continue
            from PIL import Image

            a = np.asarray(Image.open(bundle_dir / name)).astype("int32")
            b = np.asarray(Image.open(rebuilt_dir / name)).astype("int32")
            if a.shape != b.shape:
                detail.append(f"{name}: shape {a.shape} vs {b.shape}")
                continue
            diff = np.abs(a - b)
            detail.append(f"{name}: {int((diff > 0).sum())}/{diff.size} samples differ, max={int(diff.max())}")
        pytest.fail(f"{bundle_name} is not byte-reproducible here: files={mismatched} "
                    f"verification.json fields={fields} | {' ; '.join(detail)}")


@pytest.mark.parametrize("bundle_name,request_name,_outcome,_tile", REAL_BUNDLES)
def test_real_bundle_code_commit_is_a_commit_that_contains_the_pipeline(bundle_name, request_name, _outcome, _tile):
    # method.code_commit is a reproducibility claim, so it must name a real
    # commit whose tree actually holds the pipeline that produced the bundle -
    # never a placeholder or a pre-RS commit.
    import subprocess

    bundle_dir = ROOT / "rs" / "bundles" / bundle_name
    if not (bundle_dir / "verification.json").exists():
        pytest.skip(f"real bundle not present: {bundle_dir}")
    commit = read_json(bundle_dir / "verification.json")["method"]["code_commit"]
    assert commit and len(commit) == 40
    listing = subprocess.run(["git", "ls-tree", "-r", "--name-only", commit, "rs/"],
                             capture_output=True, text=True, cwd=ROOT)
    if listing.returncode != 0:
        pytest.skip("not a git checkout with that commit available")
    files = set(listing.stdout.split())
    for required in ("rs/pipeline.py", "rs/bundle.py", "rs/verify.py", "rs/determinism.py",
                     f"rs/configs/{request_name}"):
        assert required in files, f"{commit} does not contain {required}"


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
