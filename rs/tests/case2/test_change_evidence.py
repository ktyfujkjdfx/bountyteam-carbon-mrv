"""Tests for observation quality, change zones and their attribution.

A zone is a claim about ground, so most of these tests are about keeping claims
apart: fact from cause, detection resolution from carbon resolution, a missing
product from an absent phenomenon, and a stated threshold from a convenient one.
"""
import json

import numpy
import pytest
import rasterio
from shapely.geometry import box, shape

from rs.case2 import change as change_module
from rs.case2 import artifacts, disturbance, indices, quality, scenes, zones
from rs.case2 import payload as payload_module
from rs.case2.analysis import analyse
from rs.case2.cli import main

SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"


# --------------------------------------------------------------------------
# Indices and the denominator policy
# --------------------------------------------------------------------------

def test_ndvi_and_nbr_are_built_from_b8a_because_b08_is_not_supplied(dataset):
    row = dataset.scenes_for("RU_TVER_01")[0]
    with rasterio.open(dataset.path(row["reflectance_path"])) as source:
        assert "B08" not in source.descriptions
        assert source.descriptions == ("B02", "B03", "B04", "B8A", "B11", "B12")
    assert indices.BAND_INDEX["B8A"] == 3


def test_an_index_with_a_vanishing_denominator_is_undefined_not_clamped():
    """SYNTHETIC_TEST_ONLY: constructed reflectances that sum to zero."""
    reflectance = numpy.zeros((6, 1, 3), dtype="float64")
    # B8A and B04 cancel exactly in the first pixel, nearly in the second.
    reflectance[indices.BAND_INDEX["B8A"]] = [[0.05, 0.05, 0.30]]
    reflectance[indices.BAND_INDEX["B04"]] = [[-0.05, -0.049999, 0.10]]
    result = indices.ndvi(reflectance)
    assert numpy.isnan(result[0, 0]), f"{SYNTHETIC_TEST_ONLY}: exact cancellation"
    assert numpy.isnan(result[0, 1]), "below the floor is undefined too"
    assert numpy.isfinite(result[0, 2])
    assert indices.undefined_count(result) == 2


def test_negative_reflectance_still_produces_a_usable_index():
    """The -0.1 offset makes dark pixels negative; the index must survive it."""
    reflectance = numpy.zeros((6, 1, 1), dtype="float64")
    reflectance[indices.BAND_INDEX["B8A"]] = [[0.25]]
    reflectance[indices.BAND_INDEX["B04"]] = [[-0.02]]
    value = indices.ndvi(reflectance)[0, 0]
    assert numpy.isfinite(value)
    assert value > 1.0, "a negative red band legitimately pushes NDVI above one"


def test_difference_is_before_minus_after_so_a_loss_is_positive():
    assert indices.difference(0.6, 0.1) == pytest.approx(0.5)
    assert indices.difference(0.1, 0.6) == pytest.approx(-0.5)


def test_thresholds_are_fixed_constants_not_per_request_choices():
    assert indices.DNBR_DISTURBANCE == 0.27
    assert indices.DNBR_DISTURBANCE in indices.DNBR_SENSITIVITY
    assert indices.DNBR_RECOVERY < 0


# --------------------------------------------------------------------------
# Observation quality
# --------------------------------------------------------------------------

def test_quality_counts_every_class_on_one_stated_denominator():
    """SYNTHETIC_TEST_ONLY: one pixel of every published SCL code."""
    scl = numpy.array([[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], dtype="uint8")
    footprint = numpy.ones((1, 12), dtype=bool)
    counts = quality.category_counts(scl, footprint)
    assert counts["total_in_request"] == 12
    assert counts["unaccounted"] == 0
    assert counts["cloud"] == 3, "codes 8, 9 and 10 are all cloud"
    assert counts["snow_and_ice"] == 1
    assert counts["nodata"] == 1 and counts["defective"] == 1
    assert quality.fractions(counts)["vegetation"] == pytest.approx(1 / 12)


def test_the_footprint_is_the_denominator_not_the_whole_crop():
    scl = numpy.full((1, 10), 4, dtype="uint8")
    footprint = numpy.zeros((1, 10), dtype=bool)
    footprint[0, :4] = True
    counts = quality.category_counts(scl, footprint)
    assert counts["total_in_request"] == 4
    assert counts["vegetation"] == 4


def test_paired_valid_is_the_intersection_of_two_dates():
    before = numpy.array([[True, True, False, False]])
    after = numpy.array([[True, False, True, False]])
    footprint = numpy.ones((1, 4), dtype=bool)
    assert quality.paired_valid(before, after, footprint).tolist() == [
        [True, False, False, False]]


def test_real_quality_counts_reach_the_result(mordovia_03):
    evidence = mordovia_03.change_evidence
    assert evidence["available"]
    counts = evidence["observation_quality"]
    assert counts["denominator_pixels"] > 0
    assert "Sentinel-2 pixels whose centre" in counts["denominator_rule"]
    assert counts["before"]["vegetation"] > 0
    assert counts["paired_valid_fraction"] > 0.5


# --------------------------------------------------------------------------
# Scene selection
# --------------------------------------------------------------------------

def test_the_cloudy_september_scene_is_rejected_for_being_unobservable(dataset):
    analysis = analyse(dataset.geometries["RU_MORDOVIA_03"], 2021, 2022,
                       dataset=dataset)
    report = analysis.change_evidence["scene_selection"]
    rejected = {item["scene_key"]: item["reason"] for item in report["rejected"]}
    cloudy = [key for key in rejected if "20210912" in key]
    assert cloudy, "expected the September 2021 scene among the candidates"
    assert "below the" in rejected[cloudy[0]]
    assert "20210912" not in report.get("outcome", "")
    assert analysis.change_evidence["pair"]["before_scene_key"] not in cloudy


def test_the_pair_with_the_smallest_seasonal_gap_wins(mordovia_03):
    report = mordovia_03.change_evidence["scene_selection"]
    assert report["outcome"] == "pair selected"
    assert report["seasonal_gap_days"] <= scenes.SEASONAL_GAP_WARN_DAYS
    assert "day-of-year difference" in report["rule"]


def test_a_large_seasonal_gap_is_reported_rather_than_hidden():
    """SYNTHETIC_TEST_ONLY: two stub scenes 100 days apart in the season."""
    class Stub:
        def __init__(self, key, year, stamp, fraction=1.0):
            self.scene_key, self.year = key, year
            self.datetime_utc, self.usable_fraction = stamp, fraction
            self.pixels_in_request = 100

    before = Stub("A", 2019, "2019-05-01T00:00:00Z")
    after = Stub("B", 2024, "2024-08-09T00:00:00Z")
    picked_before, picked_after, report = scenes.select(
        [before, after], 2019, 2024, lambda a, b: 10)
    assert picked_before is before and picked_after is after
    # Day 121 of 2019 against day 222 of 2024; 2024 is a leap year, which is
    # why the gap is 101 and not the 100 a calendar subtraction suggests.
    assert report["seasonal_gap_days"] == 101
    assert report["seasonal_gap_days"] > scenes.SEASONAL_GAP_WARN_DAYS
    assert "phenology" in report["seasonal_warning"]


def test_no_usable_pair_is_stated_as_such():
    class Stub:
        scene_key, year = "A", 2019
        datetime_utc = "2019-07-01T00:00:00Z"
        usable_fraction, pixels_in_request = 0.01, 100

    before, after, report = scenes.select([Stub()], 2019, 2024, lambda a, b: 0)
    assert before is None and after is None
    assert "no usable pair" in report["outcome"]
    assert report["rejected"][0]["reason"].startswith("only 1.0%")


# --------------------------------------------------------------------------
# Loss year and fire evidence
# --------------------------------------------------------------------------

def test_loss_year_codes_match_the_interval_named_in_the_data_description():
    assert disturbance.loss_year_codes(2019, 2024) == (20, 21, 22, 23, 24)
    assert disturbance.loss_year_codes(2020, 2022) == (21, 22)


def test_loss_year_zero_means_not_recorded_not_missing_data(dataset):
    with rasterio.open(dataset.path("RU_TVER_01/GFC_2025_v1_13.tif")) as source:
        lossyear = source.read(disturbance.GFC_LOSSYEAR_BAND)
        datamask = source.read(disturbance.GFC_DATAMASK_BAND)
    assert (datamask == disturbance.GFC_LAND).all(), "this crop is all land"
    assert (lossyear == 0).any(), "most pixels carry no recorded loss"
    assert not numpy.isin(lossyear, disturbance.loss_year_codes(2019, 2024)).any(), (
        "RU_TVER_01 is the control plot and records no loss in 2020-2024")


def test_missing_modis_is_reported_as_an_absent_product(dataset):
    result = disturbance.fire_on_grid(
        dataset, "RU_TVER_01", rasterio.Affine.identity(), 2, 2, "EPSG:4326",
        2019, 2024)
    assert result["available"] is False
    assert "absence of the product" in result["reason"]
    assert "not evidence that nothing burned" in result["reason"]
    assert not result["burned"].any()


def test_modis_burn_dates_match_the_official_event_table(dataset, mordovia_03):
    fire = mordovia_03.change_evidence["fire"]
    assert fire["available"]
    detection = fire["detections"][0]
    assert detection["date_min"] == "2021-08-05"
    assert detection["date_max"] == "2021-08-22"
    assert detection["date_uncertainty_days_min"] == 1
    assert detection["date_uncertainty_days_max"] == 7
    assert "463 m" in fire["resolution_note"]


def test_the_qa_bit_rule_is_applied_and_stated(dataset, mordovia_03):
    assert "QA bits 0 (land) and 1 (enough data)" in (
        mordovia_03.change_evidence["fire"]["qa_rule"])


@pytest.mark.synthetic_test_only
def test_a_burn_date_without_the_quality_bits_is_not_trusted(tmp_path):
    """SYNTHETIC_TEST_ONLY: a constructed granule with QA bits cleared."""
    transform = rasterio.transform.from_origin(0, 1, 0.5, 0.5)
    directory = tmp_path / "SYNTHETIC_AOI" / "MODIS"
    directory.mkdir(parents=True)
    stem = "MCD64A1.A2021213.h20v03.061.0000000000000"
    values = {"Burn_Date": numpy.array([[220, 220]], dtype="int16"),
              "QA": numpy.array([[3, 0]], dtype="uint8"),
              "Burn_Date_Uncertainty": numpy.array([[2, 2]], dtype="uint8")}
    for suffix, array in values.items():
        with rasterio.open(directory / f"{stem}_{suffix}.tif", "w", driver="GTiff",
                           height=1, width=2, count=1, dtype=array.dtype,
                           crs="EPSG:4326", transform=transform) as sink:
            sink.write(array, 1)

    class Stub:
        root = tmp_path

        def path(self, relative):
            return tmp_path / relative

    result = disturbance.fire_on_grid(
        Stub(), "SYNTHETIC_AOI", transform, 2, 1, "EPSG:4326", 2020, 2022)
    assert result["available"] is True
    assert result["burned"].tolist() == [[True, False]], (
        f"{SYNTHETIC_TEST_ONLY}: only the pixel with QA bits 0 and 1 set counts")
    assert result["detections"][0]["pixels_on_target_grid"] == 1


# --------------------------------------------------------------------------
# Zones: components, facts, causes
# --------------------------------------------------------------------------

def test_connected_components_use_eight_connectivity():
    mask = numpy.array([[True, False], [False, True]])
    labels, counts = zones.label_components(mask, connectivity=8)
    assert len(counts) == 1, "diagonal neighbours belong to one component"
    labels, counts = zones.label_components(mask, connectivity=4)
    assert len(counts) == 2


def test_patches_below_the_minimum_mapping_unit_are_dropped_and_counted():
    mask = numpy.zeros((20, 20), dtype=bool)
    mask[0:6, 0:6] = True      # 36 pixels, kept
    mask[15, 15] = True        # 1 pixel, dropped
    evidence = {"loss_candidate": mask,
                "recovery_candidate": numpy.zeros_like(mask)}
    detected = zones.detect(evidence, rasterio.Affine.scale(20, -20))
    assert len(detected["zones"]) == 1
    assert detected["zones"][0]["pixel_count"] == 36
    assert detected["dropped_below_mmu"] == 1
    assert detected["dropped_below_mmu_ha"] == pytest.approx(zones.PIXEL_AREA_HA)


def test_loss_and_recovery_zones_cannot_overlap():
    both = numpy.zeros((10, 10), dtype=bool)
    both[0:6, 0:6] = True
    evidence = {"loss_candidate": both, "recovery_candidate": both}
    detected = zones.detect(evidence, rasterio.Affine.scale(20, -20))
    assert len(detected["zones"]) == 1, "a pixel cannot both lose and regain signal"
    assert detected["zones"][0]["kind"] == "loss"


def test_fact_and_cause_are_separate_claims():
    pixels = numpy.zeros((4, 4), dtype=bool)
    pixels[0:2, 0:2] = True
    zone = {"kind": "loss", "pixel_mask": pixels, "pixel_count": 4}
    evidence = {"gfc_loss": pixels.copy(), "spectral_change": pixels.copy(),
                "paired_valid": pixels.copy()}
    fire = {"available": True, "burned": numpy.zeros((4, 4), dtype=bool)}
    result = zones.classify(zone, evidence, fire)
    assert result["fact"] == zones.FACT_TREE_COVER_LOSS, "cover loss is established"
    assert result["cause"] == zones.CAUSE_UNKNOWN, "nothing establishes why"


def test_an_absent_burn_product_gives_unknown_with_the_product_reason():
    pixels = numpy.ones((2, 2), dtype=bool)
    zone = {"kind": "loss", "pixel_mask": pixels, "pixel_count": 4}
    evidence = {"gfc_loss": pixels, "spectral_change": pixels,
                "paired_valid": pixels}
    fire = {"available": False, "reason": "MODIS was not supplied for X",
            "burned": numpy.zeros((2, 2), dtype=bool)}
    result = zones.classify(zone, evidence, fire)
    assert result["cause"] == zones.CAUSE_UNKNOWN
    assert result["cause_reason"] == "MODIS was not supplied for X"


def test_a_recovery_zone_has_no_cause_to_establish():
    pixels = numpy.ones((2, 2), dtype=bool)
    zone = {"kind": "recovery", "pixel_mask": pixels, "pixel_count": 4}
    evidence = {"gfc_loss": numpy.zeros((2, 2), dtype=bool),
                "spectral_change": pixels, "paired_valid": pixels}
    fire = {"available": True, "burned": pixels}
    result = zones.classify(zone, evidence, fire)
    assert result["fact"] == zones.FACT_RECOVERY_INDICATION
    assert result["cause"] == zones.CAUSE_NOT_APPLICABLE
    assert "not evidence of recovered carbon" in result["cause_reason"]


# --------------------------------------------------------------------------
# Attribution and reconciliation
# --------------------------------------------------------------------------

def test_zone_contributions_and_the_remainder_add_back_to_the_whole(mordovia_03):
    reconciliation = mordovia_03.change_evidence["reconciliation"]
    assert reconciliation["balanced"], reconciliation
    assert reconciliation["accounted_delta_tc"] == pytest.approx(
        reconciliation["total_delta_tc"], abs=reconciliation["tolerance_tc"])
    assert reconciliation["total_delta_tc"] == pytest.approx(
        mordovia_03.change.delta_tc, rel=1e-12)


def test_the_reconciliation_refuses_a_double_counted_zone():
    contribution = {"per_zone_delta_tc": {"Z1": -100.0, "Z2": -100.0},
                    "remainder_delta_tc": -50.0}
    assert not zones.reconcile(contribution, -150.0)["balanced"]
    assert zones.reconcile(contribution, -250.0)["balanced"]


def test_stock_difference_is_never_added_to_a_separate_fire_emission(mordovia_03):
    note = mordovia_03.change_evidence["reconciliation"]["note"]
    assert "count the same loss twice" in note


def test_the_intra_cell_assumption_travels_with_the_result(mordovia_03):
    note = mordovia_03.change_evidence["method_note"]
    assert "20 m" in note and "evenly within the cell" in note
    assert note in mordovia_03.limitations


def test_the_fire_zone_carries_most_of_the_loss(mordovia_03):
    """The August 2021 fire should dominate the 2020-2022 stock change."""
    zone_rows = mordovia_03.change_evidence["zones"]
    fire_zones = [zone for zone in zone_rows if zone["cause"] == "FIRE_SUPPORTED"]
    assert fire_zones, "expected fire-supported zones on RU_MORDOVIA_03"
    largest = max(fire_zones, key=lambda zone: zone["detected_area_ha"])
    assert largest["contribution_tco2e"] > 0, "a burn is a loss, so positive"
    assert largest["contribution_tco2e"] < mordovia_03.change.e_tco2e, (
        "one zone cannot carry more than the whole change")
    assert largest["evidence"]["fire_fraction"] > 0.5


# --------------------------------------------------------------------------
# Honest warnings
# --------------------------------------------------------------------------

def test_a_change_covering_the_whole_plot_is_flagged_as_suspect(dataset):
    """The control plot flags a near-total 'recovery' as an observation artefact."""
    analysis = analyse(dataset.geometries["RU_TVER_01"], 2019, 2024, dataset=dataset)
    selection = analysis.change_evidence["scene_selection"]
    assert "extent_warning" in selection
    assert any("more often a difference between the two observations" in note
               for note in analysis.limitations)


def test_a_pair_from_two_processing_baselines_is_flagged(dataset):
    analysis = analyse(dataset.geometries["RU_TVER_01"], 2019, 2024, dataset=dataset)
    note = analysis.change_evidence["scene_selection"]["radiometric_note"]
    assert note["before_baseline"] != note["after_baseline"]
    assert note["before_offset"] != note["after_offset"]
    assert "processor difference" in note["warning"]


def test_a_plot_with_losses_and_no_cause_keeps_them_unknown(dataset):
    """Acceptance scenario S3: cover loss is real, the cause is not established."""
    analysis = analyse(dataset.geometries["RU_VOLOGDA_02"], 2019, 2024,
                       dataset=dataset)
    evidence = analysis.change_evidence
    assert not evidence["fire"]["available"]
    losses = [zone for zone in evidence["zones"]
              if zone["fact"] == zones.FACT_TREE_COVER_LOSS]
    assert losses, "RU_VOLOGDA_02 records cover loss in this interval"
    assert all(zone["cause"] == zones.CAUSE_UNKNOWN for zone in losses)


def test_sensitivity_shows_what_other_choices_would_have_given(mordovia_03):
    rows = mordovia_03.change_evidence["sensitivity"]
    assert rows, "expected a sensitivity table"
    published = [row for row in rows if row["is_published_choice"]]
    assert len(published) == 1
    assert published[0]["mask"] == "strict"
    assert published[0]["dnbr_threshold"] == indices.DNBR_DISTURBANCE
    strict = {row["dnbr_threshold"]: row for row in rows if row["mask"] == "strict"}
    assert strict[0.10]["zone_area_ha"] >= strict[0.44]["zone_area_ha"], (
        "a lower threshold cannot select less area")
    extended = [row for row in rows if row["mask"] == "extended"]
    assert all(row["usable_pixels"] >= published[0]["usable_pixels"]
               for row in extended), "admitting classes 2 and 7 cannot shrink the mask"


# --------------------------------------------------------------------------
# Artifacts
# --------------------------------------------------------------------------

def test_artifacts_carry_checksums_bounds_and_no_local_paths(tmp_path):
    out = tmp_path / "run"
    assert main(["--aoi", "RU_MORDOVIA_03", "--start", "2020", "--end", "2022",
                 "--out", str(out), "--quiet"]) == 0
    payload = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    records = payload["artifacts"]
    assert records
    roles = {record["role"] for record in records}
    assert {"optical_preview_before", "optical_preview_after", "dnbr_preview",
            "paired_valid_mask", "zone_mask", "change_zones",
            "cci_cell_layer"} <= roles
    for record in records:
        assert len(record["sha256"]) == 64
        assert record["api_url"].startswith("artifacts/")
        assert ":" in record["id"], "ids are namespaced by request"
        assert not record["path"].startswith(("/", "C:", "\\"))
        written = out / record["path"]
        assert written.is_file()
        import hashlib
        assert hashlib.sha256(written.read_bytes()).hexdigest() == record["sha256"]


def test_raster_artifacts_declare_their_grid_and_both_bounding_boxes(tmp_path):
    out = tmp_path / "run"
    main(["--aoi", "RU_MORDOVIA_03", "--start", "2020", "--end", "2022",
          "--out", str(out), "--quiet"])
    payload = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    preview = next(record for record in payload["artifacts"]
                   if record["role"] == "dnbr_preview")
    assert preview["crs"].startswith("EPSG:326")
    assert preview["resolution"] == [20.0, 20.0]
    assert preview["resolution_units"] == "metre"
    assert len(preview["bbox_native"]) == 4
    west, south, east, north = preview["bbox_wgs84"]
    assert 40 < west < 45 and 54 < south < 56


def test_the_cell_layer_says_it_is_native_and_not_resampled(tmp_path):
    out = tmp_path / "run"
    main(["--aoi", "RU_TVER_01", "--start", "2019", "--end", "2024",
          "--out", str(out), "--no-optical", "--quiet"])
    payload = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    cells = next(record for record in payload["artifacts"]
                 if record["role"] == "cci_cell_layer")
    assert "not a resampled surface" in cells["provenance"]


def test_zone_geometry_is_wgs84_and_non_overlapping(tmp_path):
    out = tmp_path / "run"
    main(["--aoi", "RU_MORDOVIA_03", "--start", "2020", "--end", "2022",
          "--out", str(out), "--quiet"])
    collection = json.loads((out / "zones.geojson").read_text(encoding="utf-8"))
    polygons = [shape(feature["geometry"]) for feature in collection["features"]]
    assert polygons
    for polygon in polygons:
        west, south, east, north = polygon.bounds
        assert 40 < west < 45 and 54 < south < 56, "zones are reported in WGS84"
    # Coordinates are rounded to 1 cm so the same zones hash identically on
    # every platform. Two zones that share a pixel edge can therefore overlap
    # by a sliver a few centimetres wide. Anything larger would be a real
    # double count: one 20 m pixel is 400 m2, about 3e-8 square degrees here.
    sliver_limit_deg2 = 1e-9
    for left in range(len(polygons)):
        for right in range(left + 1, len(polygons)):
            overlap = polygons[left].intersection(polygons[right])
            assert overlap.area < sliver_limit_deg2, (
                f"zones {left} and {right} overlap by {overlap.area:.2e} deg2, "
                f"far more than coordinate rounding can explain")
    properties = collection["features"][0]["properties"]
    assert {"fact", "cause", "cause_reason", "contribution_tco2e"} <= set(properties)


def test_zone_pixel_masks_are_strictly_disjoint(mordovia_03):
    """The real non-overlap guarantee, before any coordinate rounding."""
    raw = mordovia_03.raw_change
    assert raw is not None and raw["zones"]
    total = numpy.zeros_like(raw["zones"][0]["pixel_mask"], dtype="int32")
    for zone in raw["zones"]:
        total += zone["pixel_mask"].astype("int32")
    assert total.max() <= 1, "a pixel belongs to at most one zone"


def test_change_artifacts_are_absent_rather_than_empty_without_optics(tmp_path):
    out = tmp_path / "run"
    main(["--aoi", "RU_TVER_01", "--start", "2019", "--end", "2024",
          "--out", str(out), "--no-optical", "--quiet"])
    payload = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    assert payload["change_evidence"] is None
    assert not (out / "zones.geojson").exists()
    assert any("switched off" in note for note in payload["limitations"])


def test_rebuilding_a_change_result_reproduces_every_artifact_hash(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    for out in (first, second):
        main(["--aoi", "RU_MORDOVIA_04", "--start", "2019", "--end", "2024",
              "--out", str(out), "--quiet"])
    left = json.loads((first / "analysis.json").read_text(encoding="utf-8"))
    right = json.loads((second / "analysis.json").read_text(encoding="utf-8"))
    assert ([record["sha256"] for record in left["artifacts"]]
            == [record["sha256"] for record in right["artifacts"]])
    assert (first / "analysis.json").read_bytes() == (second / "analysis.json").read_bytes()
