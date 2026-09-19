"""Zones a map can draw and a reader can open.

A change result is only traceable if the outline on the screen leads back to
the pixels, the products and the arithmetic behind it. These tests check that
chain: the geometry is valid GeoJSON, it lies inside the request, the id that
the map clicks on resolves to one zone and one carbon contribution, a zone that
names an event really overlaps that event, and a zone whose cause was never
established names nothing at all.
"""
import json

import numpy
import pytest
from shapely.geometry import shape

from rs.case2 import artifacts, notices, zones
from rs.case2 import payload as payload_module
from rs.case2.analysis import analyse

FACTS = {zones.FACT_TREE_COVER_LOSS, zones.FACT_SPECTRAL_CHANGE_ONLY,
         zones.FACT_RECOVERY_INDICATION}
CAUSES = {zones.CAUSE_FIRE_SUPPORTED, zones.CAUSE_UNKNOWN,
          zones.CAUSE_NOT_APPLICABLE}
SEVERITIES = {"LOW", "MODERATE", "HIGH", zones.SEVERITY_UNKNOWN,
              zones.SEVERITY_NOT_APPLICABLE}


@pytest.fixture(scope="module")
def zone_layer(mordovia_03):
    return mordovia_03.raw_change["zones_geojson"]


@pytest.fixture(scope="module")
def gap_layer(mordovia_03):
    return mordovia_03.raw_change["gaps_geojson"]


# -- valid GeoJSON, inside the request ------------------------------------

def test_the_zone_layer_is_valid_geojson(zone_layer):
    assert zone_layer["type"] == "FeatureCollection"
    assert zone_layer["features"]
    for feature in zone_layer["features"]:
        assert feature["type"] == "Feature"
        geometry = shape(feature["geometry"])
        assert geometry.geom_type in ("Polygon", "MultiPolygon")
        assert geometry.is_valid and not geometry.is_empty
    json.dumps(zone_layer, allow_nan=False)


def test_every_zone_lies_inside_the_request(zone_layer, dataset):
    """Within a tolerance: the outline is drawn on a projected 20 m grid.

    A pixel on the boundary is a 20 m square that the request cuts through, so
    its corner can fall a few metres outside the polygon. A zone sitting wholly
    outside would be a reprojection error, and that is what this catches.
    """
    request = dataset.geometries["RU_MORDOVIA_03"]
    tolerance_deg = 0.0004  # about 25 m at this latitude, just over one pixel
    padded = request.buffer(tolerance_deg)
    for feature in zone_layer["features"]:
        geometry = shape(feature["geometry"])
        assert geometry.intersects(request), feature["properties"]["zone_id"]
        assert padded.contains(geometry), feature["properties"]["zone_id"]


def test_the_layer_keeps_the_resolution_it_was_detected_at(zone_layer):
    for feature in zone_layer["features"]:
        assert feature["properties"]["detection_resolution_m"] == 20
        assert "about 100 m" in feature["properties"]["attribution_resolution_note"]


# -- a zone is clickable --------------------------------------------------

def test_a_zone_id_is_unique_and_resolves_to_one_zone(zone_layer, mordovia_03):
    ids = [feature["properties"]["zone_id"] for feature in zone_layer["features"]]
    assert len(ids) == len(set(ids))
    rows = {row["zone_id"]: row
            for row in mordovia_03.change_evidence["zones"]}
    assert set(ids) == set(rows)
    for feature in zone_layer["features"]:
        row = rows[feature["properties"]["zone_id"]]
        # The map and the result document are filled from one function, so a
        # zone cannot say one thing on the map and another in the result.
        assert feature["properties"] == row


def test_a_zone_id_is_stable_for_the_same_request(dataset):
    first = analyse(dataset.geometries["RU_MORDOVIA_04"], 2019, 2024,
                    dataset=dataset)
    second = analyse(dataset.geometries["RU_MORDOVIA_04"], 2019, 2024,
                     dataset=dataset)
    assert [zone["zone_id"] for zone in first.change_evidence["zones"]] == \
        [zone["zone_id"] for zone in second.change_evidence["zones"]]
    assert first.raw_change["zones_geojson"] == second.raw_change["zones_geojson"]


def test_every_zone_carries_what_a_card_shows(zone_layer):
    for feature in zone_layer["features"]:
        props = feature["properties"]
        assert props["fact"] in FACTS
        assert props["cause"] in CAUSES
        assert props["cause_reason"]
        assert props["severity"]["class"] in SEVERITIES
        assert props["detected_area_ha"] > 0
        assert props["observed_between"]["start"] < props["observed_between"]["end"]
        assert isinstance(props["contribution_tco2e"], float)
        assert isinstance(props["evidence_events"], list)


# -- the contribution the id leads to -------------------------------------

def test_zone_contributions_still_reconcile_with_the_whole_change(mordovia_03):
    reconciliation = mordovia_03.change_evidence["reconciliation"]
    assert reconciliation["balanced"] is True
    assert reconciliation["total_delta_tc"] == pytest.approx(
        mordovia_03.change.delta_tc, rel=1e-12)


def test_the_sum_of_the_layer_matches_the_sum_of_the_result(
        zone_layer, mordovia_03):
    from_layer = sum(feature["properties"]["delta_tc"]
                     for feature in zone_layer["features"])
    assert from_layer == pytest.approx(
        mordovia_03.change_evidence["reconciliation"]["zone_delta_tc"], abs=1e-6)


# -- events are named only where they were established --------------------

def test_a_fire_supported_zone_names_the_event_that_supports_it(zone_layer):
    supported = [feature["properties"] for feature in zone_layer["features"]
                 if feature["properties"]["cause"] == zones.CAUSE_FIRE_SUPPORTED]
    assert supported, "Mordovia 2020-2022 contains the supplied burn"
    for props in supported:
        assert props["evidence_events"], props["zone_id"]
        for event in props["evidence_events"]:
            assert event["product"] == "MODIS MCD64A1"
            assert event["granule"].startswith("MCD64A1.")
            assert event["overlap_pixels"] > 0
            assert event["resolution_m"] == 463
        window = props["event_date_range"]
        assert window["start"] <= window["end"]
        assert "does not delineate" in window["note"]


def test_a_zone_with_no_established_cause_invents_no_event(zone_layer):
    for feature in zone_layer["features"]:
        props = feature["properties"]
        if props["cause"] == zones.CAUSE_FIRE_SUPPORTED:
            continue
        assert props["evidence_events"] == [], props["zone_id"]
        assert props["event_date_range"] is None, props["zone_id"]


def test_the_burn_dates_are_the_ones_the_official_table_records(zone_layer):
    """5 to 22 August 2021, from the supplied MCD64A1 granule."""
    dates = {(event["date_min"], event["date_max"])
             for feature in zone_layer["features"]
             for event in feature["properties"]["evidence_events"]}
    assert dates == {("2021-08-05", "2021-08-22")}


def test_a_recovery_zone_has_no_magnitude_to_report(tver):
    recovery = [zone for zone in tver.change_evidence["zones"]
                if zone["fact"] == zones.FACT_RECOVERY_INDICATION]
    assert recovery, "Tver 2019-2024 carries regrowth zones"
    for zone in recovery:
        assert zone["severity"]["class"] == zones.SEVERITY_NOT_APPLICABLE
        assert zone["severity"]["median_dnbr"] is None
        assert zone["cause"] == zones.CAUSE_NOT_APPLICABLE


def test_severity_says_what_it_measures_and_what_it_does_not(zone_layer):
    graded = [feature["properties"]["severity"]
              for feature in zone_layer["features"]
              if feature["properties"]["severity"]["median_dnbr"] is not None]
    assert graded
    for severity in graded:
        assert "not the carbon lost" in severity["basis"]
        assert -2.0 <= severity["median_dnbr"] <= 2.0


def test_the_severity_classes_follow_the_published_boundaries():
    evidence = {"paired_valid": numpy.ones((2, 2), dtype=bool)}
    zone = {"kind": "loss", "pixel_mask": numpy.ones((2, 2), dtype=bool)}
    for value, expected in ((0.30, "LOW"), (0.50, "MODERATE"), (0.90, "HIGH")):
        evidence["dnbr"] = numpy.full((2, 2), value)
        assert zones.severity(zone, evidence)["class"] == expected
    evidence["dnbr"] = numpy.full((2, 2), numpy.nan)
    assert zones.severity(zone, evidence)["class"] == zones.SEVERITY_UNKNOWN


# -- the observation gaps -------------------------------------------------

def test_the_gap_layer_is_valid_geojson_and_says_what_it_is_not(gap_layer):
    assert gap_layer["type"] == "FeatureCollection"
    assert "not areas where nothing happened" in gap_layer["note"]
    for feature in gap_layer["features"]:
        geometry = shape(feature["geometry"])
        assert geometry.is_valid and not geometry.is_empty
        assert feature["properties"]["reason"]
        assert feature["properties"]["area_ha"] > 0
    json.dumps(gap_layer, allow_nan=False)


def test_a_gap_id_is_unique(gap_layer):
    ids = [feature["properties"]["gap_id"] for feature in gap_layer["features"]]
    assert len(ids) == len(set(ids))


def test_the_gap_summary_adds_up_to_the_unpaired_part(mordovia_03):
    gaps = mordovia_03.change_evidence["observation_gaps"]
    quality = mordovia_03.change_evidence["observation_quality"]
    assert gaps["gap_pixels"] == (quality["denominator_pixels"]
                                  - quality["paired_valid_pixels"])
    assert sum(block["pixels"] for block in gaps["by_reason"].values()) == \
        gaps["gap_pixels"]
    assert gaps["gap_fraction"] == pytest.approx(
        1.0 - quality["paired_valid_fraction"], abs=1e-9)


def test_every_gap_reason_is_a_class_the_product_publishes(mordovia_03):
    known = {name for name, _codes in zones.GAP_REASONS}
    known.add("UNDEFINED_REFLECTANCE")
    assert set(mordovia_03.change_evidence["observation_gaps"]["by_reason"]) <= known


def test_the_gaps_raise_their_own_warning(mordovia_03):
    codes = {item["code"]
             for item in payload_module.analysis_payload(mordovia_03)["warnings"]}
    assert notices.OBSERVATION_GAP_ZONES in codes


def test_a_fully_paired_request_produces_no_gap_zones():
    """The empty case is a valid result, not a missing one."""
    full = numpy.ones((4, 4), dtype=bool)
    scl = numpy.full((4, 4), 4)
    gaps = zones.observation_gaps(scl, scl, full, full, None)
    assert gaps["zones"] == []
    assert gaps["gap_pixels"] == 0
    assert gaps["gap_fraction"] == 0.0
    assert zones.gaps_to_geojson(gaps, "EPSG:4326")["features"] == []
    assert zones.gaps_payload(gaps)["zone_count"] == 0


def test_an_empty_zone_set_is_a_valid_result():
    empty = {"per_zone_delta_tc": {}, "per_zone_overlap_ha": {}}
    layer = zones.to_geojson([], [], empty, "EPSG:4326")
    assert layer["features"] == []
    assert layer["type"] == "FeatureCollection"
    json.dumps(layer, allow_nan=False)


# -- the artifacts a consumer serves --------------------------------------

def test_both_vector_layers_carry_their_grid_metadata(tmp_path, mordovia_03):
    records = artifacts.write_change_artifacts(
        tmp_path, "test", mordovia_03.raw_change,
        mordovia_03.raw_change["grid"], tmp_path)
    vectors = {item["role"]: item for item in records
               if item["media_type"] == artifacts.MEDIA_GEOJSON}
    assert set(vectors) == {"change_zones", "observation_gap_zones"}
    for item in vectors.values():
        assert item["crs"].startswith("EPSG:")
        assert item["resolution"] == [20, 20]
        assert item["resolution_units"]
        assert len(item["bbox_native"]) == 4
        assert len(item["bbox_wgs84"]) == 4
        assert item["unit"] and item["provenance"]
        assert len(item["sha256"]) == 64
        assert item["size_bytes"] > 0


def test_the_cell_layer_carries_its_own_grid_not_the_maps(tmp_path, mordovia_03):
    """The cells are on the CCI grid in degrees, not on the 20 m Sentinel grid."""
    cci = mordovia_03.grids["cci_biomass:RU_MORDOVIA_03"]
    record = artifacts.write_cell_artifacts(
        tmp_path, "test", payload_module.cells_payload(mordovia_03), cci)[0]
    assert record["crs"] == cci.crs
    assert record["resolution"] == list(cci.pixel_size)
    assert record["resolution_units"] == "degree"
    assert max(abs(value) for value in record["resolution"]) < 1
    assert len(record["bbox_wgs84"]) == 4
