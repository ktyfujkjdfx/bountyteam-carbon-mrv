"""Tests for the Carbon Lens raster core.

The strongest tests here are the ones that check our arithmetic against numbers
the organizers published: if the area weighting is right, it reproduces the
official baseline reference means exactly, and if it drifts, those tests fail
before anything downstream can quietly inherit the drift.
"""
import csv
import json
import math

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box, shape

from rs.case2 import biomass, grid, manifest as manifest_module, optical
from rs.case2 import payload as payload_module
from rs.case2.analysis import METHOD_VERSION, analyse
from rs.case2.catalog import CSV_ENCODING, DatasetError, sha256_file
from rs.case2.cli import main
from rs.case2.geometry import GeometryError, geodesic_area_ha, validate
from rs.case2.models import CARBON_FRACTION, CO2_PER_C, CarbonCell
from rs.tests.case2.conftest import SUPPLIED_AOIS

# Arrays built inside a test are logic fixtures, never observations of a plot.
SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"


# --------------------------------------------------------------------------
# Calibration against the published numbers
# --------------------------------------------------------------------------

@pytest.mark.parametrize("aoi_id", SUPPLIED_AOIS)
def test_geodesic_area_matches_the_published_area_for_every_aoi(dataset, aoi_id):
    published = float(dataset.areas[aoi_id]["area_ha"])
    assert geodesic_area_ha(dataset.geometries[aoi_id]) == pytest.approx(
        published, abs=5e-4)


def test_geodesic_area_matches_the_published_area_of_the_sub_plot(sample_request):
    published = float(sample_request["properties"]["area_ha"])
    measured = geodesic_area_ha(shape(sample_request["geometry"]))
    assert measured == pytest.approx(published, abs=5e-4)


@pytest.mark.parametrize("year,column", [
    (2015, "reference_mean_2015_tc_ha"),
    (2019, "reference_mean_2019_tc_ha"),
])
def test_area_weighted_mean_reproduces_the_official_baseline_reference_means(
        dataset, analyses, year, column):
    """The one check that pins our weighting to the organizers' own.

    data/methodology/baseline.csv states its means came from CCI with weights by
    pixel intersection area and CF = 0.47. Recomputing them is therefore a test
    of our area weighting, not of the table.
    """
    with open(dataset.root / "methodology" / "baseline.csv",
              encoding=CSV_ENCODING, newline="") as handle:
        published = {}
        for row in csv.DictReader(handle):
            published.setdefault(row["aoi_id"], row)

    for aoi_id, analysis in analyses.items():
        by_year = {item.year: item for item in analysis.timeline}
        expected = float(published[aoi_id][column])
        assert by_year[year].mean_tc_ha == pytest.approx(expected, abs=5e-9), aoi_id


def test_stock_uses_the_published_carbon_fraction_and_molar_ratio():
    assert CARBON_FRACTION == 0.47
    assert CO2_PER_C == 44 / 12


# --------------------------------------------------------------------------
# Area weighting on a grid measured in degrees
# --------------------------------------------------------------------------

def test_a_cell_of_the_cci_grid_is_not_one_hectare(dataset):
    """Guards the mistake the task description calls out by name."""
    with rasterio.open(dataset.biomass_path("RU_TVER_01", 2019)) as source:
        cell = grid.cell_polygon(source.transform, 0, 0)
    area = geodesic_area_ha(cell)
    assert not math.isclose(area, 1.0, rel_tol=0.05), (
        f"a 0.00088889 degree cell measured {area:.4f} ha; treating a degree step "
        f"as a hectare would be wrong by that factor")
    assert 0.5 < area < 0.7


def test_interior_cell_weight_is_the_whole_cell_and_varies_only_with_latitude(dataset):
    with rasterio.open(dataset.biomass_path("RU_TVER_01", 2019)) as source:
        transform, width, height = source.transform, source.width, source.height
    geometry = dataset.geometries["RU_TVER_01"]
    weights = {}
    for row, col, weight_ha, cell in grid.weigh(transform, width, height, geometry):
        if geometry.contains(cell):
            weights.setdefault(row, set()).add(round(weight_ha, 12))
    assert weights, "expected interior cells"
    for row, values in weights.items():
        assert len(values) == 1, f"row {row} produced differing full-cell areas"
    assert len(weights) > 1, "expected more than one interior row"


def test_boundary_cell_weight_is_the_geodesic_area_of_the_clipped_piece(dataset):
    """Hand-check one partly covered cell against the geometry itself."""
    with rasterio.open(dataset.biomass_path("RU_TVER_01", 2019)) as source:
        transform, width, height = source.transform, source.width, source.height
    geometry = dataset.geometries["RU_TVER_01"]
    checked = 0
    for row, col, weight_ha, cell in grid.weigh(transform, width, height, geometry):
        if geometry.contains(cell):
            continue
        piece = cell.intersection(geometry)
        assert weight_ha == pytest.approx(geodesic_area_ha(piece), rel=1e-12)
        assert weight_ha < geodesic_area_ha(cell)
        checked += 1
        if checked == 25:
            break
    assert checked == 25, "expected the AOI border to clip at least 25 cells"


def test_cell_weights_sum_to_the_request_area(tver):
    assert tver.cell_weight_sum_ha == pytest.approx(tver.request_area_ha, rel=1e-6)


def test_the_two_area_definitions_are_reported_separately(tver):
    """Geodesic area is not additive over a partition, so both are published."""
    assert tver.request_area_ha != tver.cell_weight_sum_ha
    assert abs(tver.request_area_ha - tver.cell_weight_sum_ha) < 1e-3


# --------------------------------------------------------------------------
# CCI semantics: zero is a value, missing is not zero
# --------------------------------------------------------------------------

def test_zero_agb_is_summed_as_zero_rather_than_dropped():
    cells = [
        CarbonCell("a", "AOI", 0, 0, (0.0, 0.0), (0, 0, 1, 1), 10.0,
                   {2019: 100.0}, {2019: 10.0}, True),
        CarbonCell("b", "AOI", 0, 1, (0.0, 0.0), (0, 0, 1, 1), 10.0,
                   {2019: 0.0}, {2019: 0.0}, True),
    ]
    result = biomass.stock(cells, 2019)
    assert result.cells == 2
    assert result.covered_ha == 20.0
    # Dropping the burned cell would give a mean of 47.0 instead of 23.5.
    assert result.total_tc == pytest.approx(100.0 * 0.47 * 10.0)
    assert result.mean_tc_ha == pytest.approx(23.5)


def test_a_real_aoi_carries_zero_agb_cells_and_still_balances(dataset, analyses):
    analysis = analyses["RU_MORDOVIA_04"]
    zeros = [cell for cell in analysis.cells if cell.valid and cell.agb[2024] == 0.0]
    assert zeros, "RU_MORDOVIA_04 is expected to contain burned, zero-biomass cells"
    end = next(item for item in analysis.timeline if item.year == 2024)
    recomputed = sum(cell.agb[2024] * CARBON_FRACTION * cell.weight_ha
                     for cell in analysis.cells if cell.valid)
    assert end.total_tc == pytest.approx(recomputed, rel=1e-12)
    assert any("zero" in note for note in analysis.limitations)


def test_a_missing_biomass_year_is_an_error_not_a_zero(dataset):
    with pytest.raises(DatasetError):
        biomass.read_year(dataset, "RU_TVER_01", 2014)


def test_nan_in_the_biomass_map_invalidates_the_cell_instead_of_reading_as_zero(
        tmp_path):
    """SYNTHETIC_TEST_ONLY: a nodata-tagged CCI file, which the supplied set has not."""
    path = tmp_path / "CCI_Biomass_2019.tif"
    agb = numpy.array([[10, 0], [255, 20]], dtype="uint16")
    sd = numpy.array([[1, 0], [255, 2]], dtype="uint16")
    with rasterio.open(path, "w", driver="GTiff", height=2, width=2, count=2,
                       dtype="uint16", crs="EPSG:4326",
                       transform=from_origin(0, 1, 0.5, 0.5), nodata=255) as sink:
        sink.write(agb, 1)
        sink.write(sd, 2)

    class Stub:
        def biomass_path(self, aoi_id, year):
            return path

    values, deviations, _grid = biomass.read_year(Stub(), "SYNTHETIC", 2019)
    assert numpy.isnan(values[1, 0]), f"{SYNTHETIC_TEST_ONLY}: nodata must become NaN"
    assert values[0, 1] == 0.0, "a published zero must survive as zero"
    assert numpy.isnan(deviations[1, 0])


# --------------------------------------------------------------------------
# Every supplied request shape runs through one code path
# --------------------------------------------------------------------------

@pytest.mark.parametrize("aoi_id", SUPPLIED_AOIS)
def test_every_supplied_aoi_runs_end_to_end(analyses, dataset, aoi_id):
    analysis = analyses[aoi_id]
    assert analysis.parents == (aoi_id,)
    assert analysis.coverage.complete
    assert analysis.coverage.biomass_fraction == pytest.approx(1.0, abs=1e-6)
    assert analysis.change.years == 5
    assert len(analysis.timeline) == 10
    assert analysis.cells and all(cell.parent_aoi_id == aoi_id
                                  for cell in analysis.cells)


def test_the_official_sub_plot_uses_its_parent_raster(dataset, sample_request):
    analysis = analyse(sample_request, 2020, 2024, dataset=dataset,
                       include_optical=False)
    assert analysis.parents == ("RU_VOLOGDA_02",)
    assert analysis.request_area_ha == pytest.approx(808.8538, abs=5e-4)
    assert analysis.coverage.complete
    parent_area = float(dataset.areas["RU_VOLOGDA_02"]["area_ha"])
    assert analysis.request_area_ha < parent_area


def test_a_contour_with_no_identifier_runs_without_touching_the_code(dataset):
    """A hand-drawn polygon must take exactly the same path as a supplied AOI."""
    drawn = {
        "type": "Polygon",
        "coordinates": [[[43.18, 54.86], [43.21, 54.86], [43.21, 54.875],
                         [43.18, 54.875], [43.18, 54.86]]],
    }
    analysis = analyse(drawn, 2020, 2022, dataset=dataset, include_optical=False)
    assert analysis.parents == ("RU_MORDOVIA_03",)
    assert 300 < analysis.request_area_ha < 340
    assert analysis.coverage.complete
    assert analysis.change.e_tco2e > 0


def test_a_feature_collection_and_a_bare_geometry_agree(dataset, sample_request):
    collection = {"type": "FeatureCollection", "features": [sample_request]}
    from_collection = analyse(collection, 2020, 2024, dataset=dataset,
                              include_optical=False)
    from_geometry = analyse(sample_request["geometry"], 2020, 2024, dataset=dataset,
                            include_optical=False)
    assert (payload_module.analysis_payload(from_collection)
            == payload_module.analysis_payload(from_geometry))


# --------------------------------------------------------------------------
# Change arithmetic
# --------------------------------------------------------------------------

def test_loss_gives_positive_e_and_gain_gives_negative_e(analyses):
    assert analyses["RU_TVER_01"].change.e_tco2e < 0, "Tver gained biomass"
    for aoi_id in ("RU_VOLOGDA_02", "RU_MORDOVIA_03", "RU_MORDOVIA_04"):
        assert analyses[aoi_id].change.e_tco2e > 0, aoi_id


def test_e_is_the_stock_difference_carried_through_the_molar_ratio(tver):
    change = tver.change
    assert change.delta_tc == pytest.approx(
        change.stock_end_tc - change.stock_start_tc, rel=1e-12)
    assert change.e_tco2e == pytest.approx(-change.delta_tc * 44 / 12, rel=1e-12)
    assert change.e_per_ha_per_year == pytest.approx(
        change.e_tco2e / (change.normalisation_area_ha * change.years), rel=1e-12)


def test_2019_to_2024_is_five_annual_transitions(tver):
    assert tver.change.year_start == 2019
    assert tver.change.year_end == 2024
    assert tver.change.years == 5


def test_both_dates_are_measured_on_the_same_ground(analyses):
    """Including ground that lost its cover: the cell set never changes by year."""
    analysis = analyses["RU_MORDOVIA_03"]
    start = next(item for item in analysis.timeline if item.year == 2019)
    end = next(item for item in analysis.timeline if item.year == 2024)
    assert start.cells == end.cells
    assert start.covered_ha == pytest.approx(end.covered_ha, rel=1e-15)
    assert end.mean_tc_ha < start.mean_tc_ha


def test_the_timeline_is_comparable_year_to_year(tver):
    covered = {round(item.covered_ha, 9) for item in tver.timeline}
    assert len(covered) == 1, "a timeline on shifting support cannot be compared"


# --------------------------------------------------------------------------
# Coverage: three questions, three answers
# --------------------------------------------------------------------------

def test_partial_coverage_reports_the_gap_and_does_not_extrapolate(dataset):
    """Half of this box lies west of RU_TVER_01, where no baseline applies."""
    half_outside = {
        "type": "Polygon",
        "coordinates": [[[32.88, 56.60], [32.94, 56.60], [32.94, 56.62],
                         [32.88, 56.62], [32.88, 56.60]]],
    }
    analysis = analyse(half_outside, 2019, 2024, dataset=dataset,
                       include_optical=False)
    coverage = analysis.coverage
    assert not coverage.complete
    assert coverage.calculated_ha < coverage.requested_ha
    assert coverage.missing_ha == pytest.approx(
        coverage.requested_ha - coverage.calculated_ha, abs=1e-6)
    assert coverage.biomass_fraction == pytest.approx(0.5, abs=0.01)
    assert any("partial coverage" in note for note in analysis.limitations)
    assert any("not computed for a partial request" in note
               for note in analysis.limitations)


def test_a_contour_outside_every_supplied_area_is_refused(dataset):
    far_away = {
        "type": "Polygon",
        "coordinates": [[[10.0, 50.0], [10.01, 50.0], [10.01, 50.01],
                         [10.0, 50.01], [10.0, 50.0]]],
    }
    with pytest.raises(DatasetError, match="does not intersect"):
        analyse(far_away, 2019, 2024, dataset=dataset, include_optical=False)


def test_the_three_coverages_are_independent(tver):
    coverage = tver.coverage
    assert coverage.biomass_fraction == pytest.approx(1.0, abs=1e-6)
    assert coverage.biomass_sd_fraction == pytest.approx(1.0, abs=1e-6)
    assert 0.0 <= coverage.optical_paired_fraction <= 1.0
    payload = payload_module.analysis_payload(tver)
    assert set(payload["coverage"]) >= {"biomass", "biomass_sd", "optical_paired"}


def test_cloud_lowers_optical_coverage_without_touching_biomass_coverage(
        mordovia_cloudy):
    """The September 2021 scene is heavily clouded over both Mordovia plots.

    It is the case the task description singles out: bad optics must not be
    allowed to look like missing biomass data.
    """
    cloudy = [scene for scene in mordovia_cloudy.scenes
              if "20210912" in scene.scene_key]
    assert cloudy, "expected the cloudy September 2021 scene in the 2021-2022 window"
    assert cloudy[0].usable_fraction < 0.2
    assert mordovia_cloudy.coverage.biomass_fraction == pytest.approx(1.0, abs=1e-6)
    assert mordovia_cloudy.coverage.complete
    assert (mordovia_cloudy.paired_optical.paired_usable_fraction
            > cloudy[0].usable_fraction), (
        "a better summer scene exists in the same year and must be preferred")


def test_supplied_areas_do_not_overlap_so_parts_cannot_be_double_counted(dataset):
    names = sorted(dataset.geometries)
    for left in range(len(names)):
        for right in range(left + 1, len(names)):
            a, b = dataset.geometries[names[left]], dataset.geometries[names[right]]
            assert a.intersection(b).area == 0.0


def test_overlapping_sources_are_refused_rather_than_summed(dataset, monkeypatch):
    """SYNTHETIC_TEST_ONLY: the supplied areas are disjoint; this forces an overlap."""
    overlapping = dict(dataset.geometries)
    overlapping["SYNTHETIC_OVERLAP"] = box(32.90, 56.58, 32.98, 56.64)
    monkeypatch.setattr(type(dataset), "geometries",
                        property(lambda self: overlapping))
    with pytest.raises(DatasetError, match="overlap"):
        dataset.parents_for(box(32.92, 56.60, 32.93, 56.61))


# --------------------------------------------------------------------------
# Request validation: explain, never repair
# --------------------------------------------------------------------------

def test_a_self_intersecting_polygon_is_rejected_and_not_repaired():
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    with pytest.raises(GeometryError, match="not repaired automatically"):
        validate(bowtie)


def test_an_area_above_the_limit_is_rejected():
    too_big = box(32.0, 56.0, 33.0, 56.5)
    with pytest.raises(GeometryError, match="exceeds"):
        validate(too_big)


def test_a_line_is_not_an_area():
    with pytest.raises(GeometryError, match="Polygon"):
        validate({"type": "LineString", "coordinates": [[0, 0], [1, 1]]})


@pytest.mark.parametrize("start,end,message", [
    (2020, 2020, "earlier than"),
    (2024, 2019, "earlier than"),
    (2018, 2024, "outside the supported"),
    (2019, 2025, "outside the supported"),
])
def test_impossible_periods_are_rejected(dataset, start, end, message):
    with pytest.raises(GeometryError, match=message):
        analyse(dataset.geometries["RU_TVER_01"], start, end, dataset=dataset,
                include_optical=False)


def test_coordinates_outside_wgs84_are_rejected_with_the_likely_cause():
    with pytest.raises(GeometryError, match="lon/lat"):
        validate({"type": "Feature", "properties": {},
                  "geometry": {"type": "Polygon",
                               "coordinates": [[[181.0, 10.0], [182.0, 10.0],
                                                [182.0, 11.0], [181.0, 11.0],
                                                [181.0, 10.0]]]}})


def test_a_latitude_longitude_swap_that_stays_in_range_fails_at_the_data(dataset):
    """Bounds cannot catch every swap, so the next check has to.

    RU_TVER_01 written lat-first is a valid WGS84 polygon - it just sits in
    Iraq. The request is refused because no supplied area covers it, which is
    the honest reason, rather than being analysed against the wrong raster.
    """
    swapped = {"type": "Polygon",
               "coordinates": [[[56.6, 32.9], [56.6, 32.95], [56.63, 32.95],
                                [56.63, 32.9], [56.6, 32.9]]]}
    validate(swapped)
    with pytest.raises(DatasetError, match="does not intersect"):
        analyse(swapped, 2019, 2024, dataset=dataset, include_optical=False)


# --------------------------------------------------------------------------
# Optical: the offset stays, the classes are explicit
# --------------------------------------------------------------------------

def test_usable_mask_accepts_only_scl_4_and_5():
    scl = numpy.array([[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], dtype="uint8")
    reflectance = numpy.zeros((6, 1, 12), dtype="float32")
    mask = optical.usable_mask(scl, reflectance)
    assert mask.tolist() == [[False] * 4 + [True, True] + [False] * 6], (
        f"{SYNTHETIC_TEST_ONLY}: every SCL code exercised on a constructed array")


@pytest.mark.synthetic_test_only
@pytest.mark.parametrize("scl_code,meaning", [
    (0, "no data"),
    (1, "saturated or defective"),
    (11, "snow and ice"),
])
def test_synthetic_scl_classes_absent_from_the_supplied_crops_are_excluded(
        scl_code, meaning):
    """SYNTHETIC_TEST_ONLY.

    Codes 0, 1 and 11 do not occur in any supplied scene, so their exclusion
    cannot be shown on real data. These arrays are constructed to exercise the
    rule and are not an observation of no-data, defective pixels or snow on any
    of the four plots.
    """
    scl = numpy.full((1, 4), scl_code, dtype="uint8")
    scl[0, 0] = 4  # one usable pixel, so a false pass cannot come from an empty mask
    reflectance = numpy.zeros((6, 1, 4), dtype="float32")
    mask = optical.usable_mask(scl, reflectance)
    assert mask[0, 0], f"{SYNTHETIC_TEST_ONLY}: class 4 must stay usable"
    assert not mask[0, 1:].any(), (
        f"{SYNTHETIC_TEST_ONLY}: class {scl_code} ({meaning}) must be excluded")


@pytest.mark.synthetic_test_only
def test_the_supplied_scenes_really_do_lack_classes_0_1_and_11(dataset):
    """Proves the synthetic tests above are necessary rather than redundant."""
    seen = set()
    for row in dataset.scenes:
        with rasterio.open(dataset.path(row["scl_path"])) as source:
            seen.update(numpy.unique(source.read(1)).tolist())
    assert seen, "expected to read scene classification"
    assert not ({0, 1, 11} & seen), (
        "classes 0, 1 and 11 have appeared in the data; the synthetic vectors "
        "should be replaced by a real observation")


def test_negative_reflectance_is_preserved_and_stays_usable():
    """From baseline 04.00 the product carries a -0.1 offset; dark ground is negative."""
    scl = numpy.full((1, 2), 4, dtype="uint8")
    reflectance = numpy.full((6, 1, 2), -0.05, dtype="float32")
    assert optical.usable_mask(scl, reflectance).all(), (
        f"{SYNTHETIC_TEST_ONLY}: clamping negatives would discard valid dark pixels")


def test_real_scenes_carry_negative_reflectance_that_is_not_clipped(dataset, tver):
    with_offset = [scene for scene in tver.scenes
                   if scene.reflectance_offset_applied != 0.0]
    assert with_offset, "expected at least one baseline 04.00+ scene in this window"
    assert any(scene.negative_reflectance_pixels > 0 for scene in with_offset)
    for scene in with_offset:
        assert scene.reflectance_offset_applied == pytest.approx(-0.1)


def test_non_finite_reflectance_is_unusable_even_in_an_accepted_class():
    scl = numpy.full((1, 2), 4, dtype="uint8")
    reflectance = numpy.zeros((6, 1, 2), dtype="float32")
    reflectance[3, 0, 1] = numpy.nan
    mask = optical.usable_mask(scl, reflectance)
    assert mask.tolist() == [[True, False]]


def test_scene_classes_2_and_7_are_named_as_sensitivity_only():
    assert optical.SENSITIVITY_ONLY_SCL_CLASSES == {2, 7}
    assert optical.SENSITIVITY_ONLY_SCL_CLASSES <= optical.EXCLUDED_SCL_CLASSES


def test_the_paired_rule_states_that_scene_selection_is_not_settled(tver):
    assert tver.paired_optical is not None
    assert "RS-2" in tver.paired_optical.selection_rule


# --------------------------------------------------------------------------
# Three grids, none assumed
# --------------------------------------------------------------------------

def test_sources_arrive_on_different_grids_and_each_is_recorded(dataset, tver):
    cci = tver.grids["cci_biomass:RU_TVER_01"]
    assert cci.crs == "EPSG:4326"
    assert cci.units == "degree"
    assert cci.pixel_size[0] == pytest.approx(0.0008888888888888889)

    with rasterio.open(dataset.path(dataset.scenes_for("RU_TVER_01")[0]["reflectance_path"])) as source:
        assert str(source.crs) == "EPSG:32636"
        assert source.res == (20.0, 20.0)

    with rasterio.open(dataset.path("RU_TVER_01/GFC_2025_v1_13.tif")) as source:
        assert str(source.crs) == "EPSG:4326"
        assert source.res[0] == pytest.approx(0.00025)

    with rasterio.open(dataset.path(
            "RU_MORDOVIA_03/MODIS/"
            "MCD64A1.A2021213.h20v03.061.2021309115600_Burn_Date.tif")) as source:
        assert "Sinusoidal" in source.crs.to_wkt()
        assert source.res[0] == pytest.approx(463.3127165279167)


def test_each_aoi_keeps_its_own_utm_zone(dataset):
    zones = {}
    for aoi_id in SUPPLIED_AOIS:
        row = dataset.scenes_for(aoi_id)[0]
        with rasterio.open(dataset.path(row["reflectance_path"])) as source:
            zones[aoi_id] = str(source.crs)
    assert zones["RU_TVER_01"] == "EPSG:32636"
    assert zones["RU_VOLOGDA_02"] == "EPSG:32637"
    assert zones["RU_MORDOVIA_03"] == zones["RU_MORDOVIA_04"] == "EPSG:32638"


# --------------------------------------------------------------------------
# Per-cell layer, manifest and replay
# --------------------------------------------------------------------------

def test_the_cell_layer_carries_both_dates_weights_and_validity(tver):
    cells = payload_module.cells_payload(tver)
    assert cells["type"] == "FeatureCollection"
    assert len(cells["features"]) == len(tver.cells)
    properties = cells["features"][0]["properties"]
    assert {"cell_id", "parent_aoi_id", "weight_ha", "agb_t_ha", "agb_sd_t_ha",
            "valid", "centroid"} <= set(properties)
    assert {"2019", "2024"} <= set(properties["agb_t_ha"])
    assert {"2019", "2024"} <= set(properties["agb_sd_t_ha"])
    assert sum(feature["properties"]["weight_ha"]
               for feature in cells["features"]) == pytest.approx(
        tver.cell_weight_sum_ha, rel=1e-6)


def test_cell_ids_are_unique_and_name_their_parent(tver):
    ids = [cell.cell_id for cell in tver.cells]
    assert len(set(ids)) == len(ids)
    assert all(cell_id.startswith("RU_TVER_01:") for cell_id in ids)


def test_the_manifest_checksums_every_file_that_was_read(dataset, tver):
    payload = payload_module.analysis_payload(tver)
    manifest = manifest_module.build(tver, payload)
    assert manifest["method_version"] == METHOD_VERSION
    listed = {entry["path"]: entry for entry in manifest["dataset"]["files"]}
    assert listed, "expected recorded sources"
    for path, entry in listed.items():
        assert path.startswith("data/"), "paths must be relative to the repository"
        real = dataset.root.parent / path
        assert entry["sha256"] == sha256_file(real)
        assert entry["size_bytes"] == real.stat().st_size
    assert any("CCI_Biomass_2019" in path for path in listed)
    assert any("CCI_Biomass_2024" in path for path in listed)


def test_recorded_checksums_match_the_official_catalogue(dataset, tver):
    payload = payload_module.analysis_payload(tver)
    manifest = manifest_module.build(tver, payload)
    for entry in manifest["dataset"]["files"]:
        relative = entry["path"].removeprefix("data/")
        catalogued = dataset.catalog.get(relative)
        if catalogued:
            assert entry["sha256"] == catalogued["sha256"], relative


def test_the_content_hash_excludes_the_run_time(tver):
    payload = payload_module.analysis_payload(tver)
    early = manifest_module.build(tver, payload, generated_at="2026-01-01T00:00:00Z")
    late = manifest_module.build(tver, payload, generated_at="2026-09-19T12:00:00Z")
    assert early["content_sha256"] == late["content_sha256"]
    assert early["generated_at"] != late["generated_at"]


def test_replaying_a_request_reproduces_identical_bytes(dataset, tmp_path):
    from rs.determinism import canonical_bytes

    first = analyse(dataset.geometries["RU_MORDOVIA_04"], 2019, 2024,
                    dataset=dataset, include_optical=False)
    second = analyse(dataset.geometries["RU_MORDOVIA_04"], 2019, 2024,
                     dataset=dataset, include_optical=False)
    first_payload = payload_module.analysis_payload(first)
    second_payload = payload_module.analysis_payload(second)
    assert canonical_bytes(first_payload) == canonical_bytes(second_payload)
    assert (canonical_bytes(payload_module.cells_payload(first))
            == canonical_bytes(payload_module.cells_payload(second)))
    assert (manifest_module.build(first, first_payload)["content_sha256"]
            == manifest_module.build(second, second_payload)["content_sha256"])


def test_results_cannot_be_written_into_the_supplied_dataset(dataset, tmp_path):
    assert not manifest_module.outputs_are_safe(dataset.root, dataset.root)
    assert not manifest_module.outputs_are_safe(
        dataset.root / "RU_TVER_01", dataset.root)
    assert manifest_module.outputs_are_safe(tmp_path, dataset.root)


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_cli_writes_the_three_artifacts_and_reports_the_hash(tmp_path, capsys):
    exit_code = main(["--aoi", "RU_TVER_01", "--start", "2019", "--end", "2024",
                      "--out", str(tmp_path / "run"), "--no-optical"])
    assert exit_code == 0
    written = tmp_path / "run"
    for name in ("analysis.json", "cells.geojson", "manifest.json"):
        assert (written / name).is_file()
    printed = capsys.readouterr().out
    assert "content sha256 : 0x" in printed

    payload = json.loads((written / "analysis.json").read_text(encoding="utf-8"))
    manifest = json.loads((written / "manifest.json").read_text(encoding="utf-8"))
    assert payload["request"]["parents"] == ["RU_TVER_01"]
    assert manifest["content_sha256"].startswith("0x")


def test_cli_refuses_to_write_inside_the_dataset(dataset, capsys):
    exit_code = main(["--aoi", "RU_TVER_01", "--start", "2019", "--end", "2024",
                      "--out", str(dataset.root / "RU_TVER_01")])
    assert exit_code == 2
    assert "refusing to write" in capsys.readouterr().err


def test_cli_explains_an_unusable_request_instead_of_failing_obscurely(
        tmp_path, capsys):
    exit_code = main(["--aoi", "RU_TVER_01", "--start", "2024", "--end", "2019",
                      "--out", str(tmp_path / "run")])
    assert exit_code == 2
    assert "earlier than" in capsys.readouterr().err


def test_cli_rejects_an_unknown_area(tmp_path, capsys):
    exit_code = main(["--aoi", "RU_NOWHERE_99", "--start", "2019", "--end", "2024",
                      "--out", str(tmp_path / "run")])
    assert exit_code == 2
    assert "unknown area" in capsys.readouterr().err


# --------------------------------------------------------------------------
# What this stage deliberately does not produce
# --------------------------------------------------------------------------

def test_the_raster_core_states_no_baseline_uncertainty_or_units(tver):
    payload = payload_module.analysis_payload(tver)
    text = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in ("potential_units", "baseline_stock", "\"q\":", "radj",
                      "uncertainty_interval", "investable"):
        assert forbidden not in text, (
            f"{forbidden} belongs to another owner and must not appear in a "
            f"raster result")
