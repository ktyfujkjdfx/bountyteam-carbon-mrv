"""Any admissible contour, not four static pages.

The seven acceptance scenarios of the roadmap, run against the real dataset. No
identifier is special here: a supplied AOI, a sub-plot and a contour drawn by
hand take the same path, and the only thing an `aoi_id` buys a caller is not
having to paste a polygon. What differs between the scenarios is the answer,
and for four of them the answer is a refusal - which has to be as structured as
a result, or a consumer cannot act on it.
"""
import json
from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, box, mapping, shape

from rs.case2 import errors, payload as payload_module
from rs.case2.analysis import analyse
from rs.case2.catalog import DatasetError, InsufficientData
from rs.case2.cli import main
from rs.case2.geometry import GeometryError, geodesic_area_ha
from rs.case2.models import MAX_AREA_HA


def _inside(geometry, shrink=0.25):
    """A smaller box centred on `geometry`, guaranteed to sit inside it."""
    lon_min, lat_min, lon_max, lat_max = geometry.bounds
    dx = (lon_max - lon_min) * shrink
    dy = (lat_max - lat_min) * shrink
    return box(lon_min + dx, lat_min + dy, lon_max - dx, lat_max - dy)


# -- 1. an official area --------------------------------------------------

def test_scenario_1_an_official_area_is_analysed_by_its_polygon(tver):
    payload = payload_module.analysis_payload(tver)
    assert payload["request"]["parents"] == ["RU_TVER_01"]
    assert payload["request"]["area_ha"] == pytest.approx(1750.4731, abs=1e-4)
    assert payload["coverage"]["complete"] is True


# -- 2. the supplied sub-plot ---------------------------------------------

def test_scenario_2_the_sub_plot_is_analysed_without_a_rule_about_its_id(
        dataset, sample_request):
    """CHECK_TRANSFER_01 is a contour, and nothing in the code knows its name."""
    geometry = sample_request["geometry"]
    analysis = analyse(geometry, 2020, 2024, dataset=dataset, include_optical=False)
    assert analysis.request_area_ha == pytest.approx(808.8538, abs=1e-4)
    assert analysis.parents == (sample_request["properties"]["parent_aoi_id"],)
    assert analysis.coverage.complete is True
    # The identifier appears nowhere on the analysis path: the sub-plot is
    # analysed because it is a polygon, not because it is that polygon. The
    # benchmark and research drivers do name it, as a label for a row.
    core = Path(__file__).parents[2] / "case2"
    drivers = {"bench.py", "research.py"}
    for path in core.rglob("*.py"):
        if path.name in drivers:
            continue
        assert "CHECK_TRANSFER" not in path.read_text(encoding="utf-8"), path


# -- 3. a contour drawn by hand -------------------------------------------

def test_scenario_3_a_hand_drawn_contour_runs_without_a_code_change(dataset):
    drawn = _inside(dataset.geometries["RU_TVER_01"])
    analysis = analyse(mapping(drawn), 2019, 2024, dataset=dataset,
                       include_optical=False)
    assert analysis.parents == ("RU_TVER_01",)
    assert analysis.coverage.complete is True
    assert analysis.request_area_ha == pytest.approx(
        geodesic_area_ha(drawn), rel=1e-12)
    assert analysis.cells and analysis.change.e_tco2e == analysis.change.e_tco2e


def test_a_multipolygon_is_accepted_as_one_request(dataset):
    """Two disjoint patches of one area are one request, not two."""
    parent = dataset.geometries["RU_TVER_01"]
    lon_min, lat_min, lon_max, lat_max = parent.bounds
    third = (lon_max - lon_min) / 3
    left = box(lon_min + third * 0.1, lat_min + 0.005,
               lon_min + third * 0.9, lat_max - 0.005)
    right = box(lon_max - third * 0.9, lat_min + 0.005,
                lon_max - third * 0.1, lat_max - 0.005)
    patches = MultiPolygon([left, right])
    analysis = analyse(mapping(patches), 2019, 2024, dataset=dataset,
                       include_optical=False)
    assert analysis.request_area_ha == pytest.approx(
        geodesic_area_ha(patches), rel=1e-12)
    assert analysis.coverage.complete is True
    assert analysis.request_area_ha < geodesic_area_ha(parent)


# -- 4. a contour across two sources --------------------------------------

@pytest.fixture(scope="module")
def across_two_sources(dataset):
    """A strip spanning both Mordovia areas and the uncovered gap between them."""
    third = dataset.geometries["RU_MORDOVIA_03"]
    fourth = dataset.geometries["RU_MORDOVIA_04"]
    strip = box(43.19, fourth.bounds[1] + 0.005, 43.20, third.bounds[3] - 0.005)
    return analyse(mapping(strip), 2019, 2024, dataset=dataset,
                   include_optical=False)


def test_scenario_4_two_source_areas_become_two_disjoint_parts(across_two_sources):
    payload = payload_module.analysis_payload(across_two_sources)
    parts = payload["request"]["parts"]
    assert [part["aoi_id"] for part in parts] == ["RU_MORDOVIA_03", "RU_MORDOVIA_04"]
    assert all(part["area_ha"] > 0 and part["cells"] > 0 for part in parts)


def test_a_hectare_is_never_counted_twice_across_parts(across_two_sources):
    """Part areas and part weights add up to the totals, with nothing shared."""
    parts = across_two_sources.parts
    assert sum(part["cell_weight_sum_ha"] for part in parts) == pytest.approx(
        across_two_sources.cell_weight_sum_ha, rel=1e-12)
    assert sum(part["cells"] for part in parts) == len(across_two_sources.cells)
    # The covered pieces are smaller than the request: the gap between the two
    # areas has no biomass map, and that gap is reported, not absorbed.
    covered = sum(part["area_ha"] for part in parts)
    assert covered < across_two_sources.request_area_ha
    assert across_two_sources.coverage.complete is False
    assert across_two_sources.coverage.missing_ha > 0


def test_a_multi_parent_request_states_which_part_the_zones_cover(dataset):
    """The zone rule is published as a rule, not left to be inferred."""
    from rs.case2.analysis import _zone_scope

    scope = _zone_scope(("RU_MORDOVIA_03", "RU_MORDOVIA_04"))
    assert scope["zones_cover"] == ["RU_MORDOVIA_03"]
    assert scope["stock_covers"] == ["RU_MORDOVIA_03", "RU_MORDOVIA_04"]
    assert scope["complete_for_request"] is False
    assert _zone_scope(("RU_TVER_01",))["complete_for_request"] is True


def test_a_multi_parent_request_warns_that_the_zone_map_is_narrower(
        across_two_sources):
    from rs.case2 import notices

    codes = {item["code"] for item
             in payload_module.analysis_payload(across_two_sources)["warnings"]}
    assert notices.ZONES_FIRST_PARENT_ONLY in codes


def test_a_single_parent_request_carries_no_such_warning(tver):
    from rs.case2 import notices

    codes = {item["code"]
             for item in payload_module.analysis_payload(tver)["warnings"]}
    assert notices.ZONES_FIRST_PARENT_ONLY not in codes


# -- 5. too large ---------------------------------------------------------

def test_scenario_5_a_contour_above_the_limit_is_refused_with_its_numbers(dataset):
    parent = dataset.geometries["RU_TVER_01"]
    lon_min, lat_min, lon_max, lat_max = parent.bounds
    oversized = box(lon_min, lat_min, lon_max + 0.05, lat_max + 0.05)
    assert geodesic_area_ha(oversized) > MAX_AREA_HA

    with pytest.raises(GeometryError) as raised:
        analyse(mapping(oversized), 2019, 2024, dataset=dataset)
    error = raised.value
    assert error.code == errors.AREA_LIMIT_EXCEEDED
    assert error.outcome == errors.INVALID_REQUEST
    assert error.details["limit_ha"] == MAX_AREA_HA
    assert error.details["area_ha"] > MAX_AREA_HA
    assert "2000 ha limit" in str(error)


def test_the_limit_is_the_twenty_square_kilometres_the_case_states():
    assert MAX_AREA_HA == 2000.0


# -- 6. self-intersecting -------------------------------------------------

def test_scenario_6_a_self_intersecting_contour_is_refused_not_repaired(dataset):
    bowtie = {"type": "Polygon", "coordinates": [[
        [32.92, 56.60], [32.96, 56.62], [32.92, 56.62], [32.96, 56.60],
        [32.92, 56.60]]]}
    with pytest.raises(GeometryError) as raised:
        analyse(bowtie, 2019, 2024, dataset=dataset)
    error = raised.value
    assert error.code == errors.GEOMETRY_SELF_INTERSECTING
    assert "Self-intersection" in error.details["reason"]
    # Repairing it would silently analyse a different polygon, and hash it as
    # if it were the one that was asked for.
    assert "not repaired automatically" in str(error)


@pytest.mark.parametrize("geometry,code", [
    ({"type": "Polygon", "coordinates": []}, errors.GEOMETRY_EMPTY),
    ({"type": "LineString", "coordinates": [[32.92, 56.60], [32.96, 56.62]]},
     errors.GEOMETRY_TYPE_UNSUPPORTED),
    # A contour left in a projected CRS: metres read as degrees.
    ({"type": "Polygon", "coordinates": [[[431980, 4555740], [432180, 4555740],
                                          [432180, 4555940], [431980, 4555740]]]},
     errors.GEOMETRY_NOT_WGS84),
])
def test_an_unusable_geometry_names_what_is_wrong_with_it(geometry, code, dataset):
    with pytest.raises(GeometryError) as raised:
        analyse(geometry, 2019, 2024, dataset=dataset)
    assert raised.value.code == code


def test_a_collection_of_several_features_is_not_one_request(dataset):
    parent = dataset.geometries["RU_TVER_01"]
    feature = {"type": "Feature", "properties": {},
               "geometry": mapping(_inside(parent))}
    collection = {"type": "FeatureCollection", "features": [feature, feature]}
    with pytest.raises(GeometryError) as raised:
        analyse(collection, 2019, 2024, dataset=dataset)
    assert raised.value.code == errors.REQUEST_NOT_SINGLE_FEATURE
    assert raised.value.details["features"] == 2


# -- 7. no data for the contour -------------------------------------------

def test_scenario_7_a_contour_outside_every_source_is_insufficient_data(dataset):
    """Not an error about the forest: a statement about what the products cover."""
    elsewhere = box(37.60, 55.75, 37.62, 55.77)
    with pytest.raises(InsufficientData) as raised:
        analyse(mapping(elsewhere), 2019, 2024, dataset=dataset)
    error = raised.value
    assert error.code == errors.NO_SOURCE_COVERAGE
    assert error.outcome == errors.INSUFFICIENT_DATA
    assert error.details["available_areas"] == sorted(dataset.geometries)
    assert len(error.details["request_bounds"]) == 4


def test_a_period_the_maps_do_not_reach_is_insufficient_data_too(dataset):
    with pytest.raises(GeometryError) as raised:
        analyse(dataset.geometries["RU_TVER_01"], 2014, 2024, dataset=dataset)
    assert raised.value.code == errors.PERIOD_OUT_OF_RANGE
    assert raised.value.details["supported_min"] == 2019


def test_insufficient_data_is_never_reported_as_an_absence_of_change(dataset):
    elsewhere = box(37.60, 55.75, 37.62, 55.77)
    with pytest.raises(InsufficientData) as raised:
        analyse(mapping(elsewhere), 2019, 2024, dataset=dataset)
    document = raised.value.as_document()
    assert document["outcome"] == errors.INSUFFICIENT_DATA
    assert "never a statement that nothing changed" in document["note"]
    assert "NO_CHANGE" not in json.dumps(document)


# -- the refusal a caller receives ----------------------------------------

def test_every_refusal_is_a_document_with_a_code_and_its_numbers(dataset):
    refusals = []
    for geometry, years in (
            ({"type": "Point", "coordinates": [32.92, 56.60]}, (2019, 2024)),
            (mapping(box(37.60, 55.75, 37.62, 55.77)), (2019, 2024)),
            (dataset.geometries["RU_TVER_01"], (2024, 2019)),
    ):
        with pytest.raises((GeometryError, DatasetError)) as raised:
            analyse(geometry, years[0], years[1], dataset=dataset)
        refusals.append(raised.value.as_document())

    for document in refusals:
        assert document["schema"] == errors.ERROR_SCHEMA
        assert document["outcome"] in (errors.INVALID_REQUEST,
                                       errors.INSUFFICIENT_DATA)
        assert document["code"].startswith("RS_")
        assert document["message"]
        assert isinstance(document["details"], dict)
        json.dumps(document, allow_nan=False)
    assert len({document["code"] for document in refusals}) == 3


def test_the_cli_prints_the_refusal_as_json_beside_the_human_line(
        tmp_path, capsys):
    exit_code = main(["--aoi", "RU_NOWHERE_99", "--start", "2019", "--end", "2024",
                      "--out", str(tmp_path / "out")])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "unknown area" in captured.err
    document = json.loads(captured.out)
    assert document["code"] == errors.UNKNOWN_AREA_ID
    assert document["details"]["aoi_id"] == "RU_NOWHERE_99"
    assert document["details"]["available_areas"]


def test_the_cli_analyses_a_contour_from_a_file(tmp_path, dataset, capsys):
    """The documented `--geometry` path, run end to end on a drawn contour."""
    drawn = _inside(dataset.geometries["RU_MORDOVIA_04"], shrink=0.35)
    path = tmp_path / "plot.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {},
                                "geometry": mapping(drawn)}), encoding="utf-8")
    exit_code = main(["--geometry", str(path), "--start", "2019", "--end", "2024",
                      "--out", str(tmp_path / "out"), "--no-optical"])
    assert exit_code == 0
    printed = capsys.readouterr().out
    assert "RU_MORDOVIA_04" in printed

    payload = json.loads((tmp_path / "out" / "analysis.json").read_text("utf-8"))
    assert payload["request"]["area_ha"] == pytest.approx(
        geodesic_area_ha(drawn), abs=1e-6)
    assert payload["request"]["parts"][0]["aoi_id"] == "RU_MORDOVIA_04"
    assert payload["coverage"]["complete"] is True


def test_a_request_outside_the_products_writes_nothing(tmp_path, capsys):
    out = tmp_path / "out"
    path = tmp_path / "plot.geojson"
    path.write_text(json.dumps(mapping(box(37.60, 55.75, 37.62, 55.77))),
                    encoding="utf-8")
    exit_code = main(["--geometry", str(path), "--start", "2019", "--end", "2024",
                      "--out", str(out)])
    assert exit_code == 2
    assert json.loads(capsys.readouterr().out)["code"] == errors.NO_SOURCE_COVERAGE
    assert not (out / "analysis.json").exists()
