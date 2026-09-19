"""The upstream boundary: the real RS shape, the provisional fixture, and honest labels."""
from __future__ import annotations

import pytest

from carbon import RsPayloadError, from_fixture, from_rs_payload
from carbon.rs_adapter import (
    FIXTURE_SCHEMA,
    INPUT_PROVISIONAL,
    INPUT_RS_PAYLOAD,
    RS_ANALYSIS_SCHEMA,
    cells_from_rs_geojson,
)
from carbon.tests.conftest import ALL_REQUESTS, FIXTURE_DIR, load_json


def rs_cell(weight, start_agb, end_agb, start_sd, end_sd, *, years=(2019, 2024)):
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]},
        "properties": {
            "cell_id": "c1",
            "weight_ha": weight,
            "agb_t_ha": {str(years[0]): start_agb, str(years[1]): end_agb},
            "agb_sd_t_ha": {str(years[0]): start_sd, str(years[1]): end_sd},
            "valid": True,
        },
    }


def rs_payload(cells_count=2):
    return {
        "schema": RS_ANALYSIS_SCHEMA,
        "request": {"area_ha": 100.0, "year_start": 2019, "year_end": 2024,
                    "years": [2019, 2024], "parents": ["RU_TVER_01"]},
        "coverage": {
            "requested_ha": 100.0, "calculated_ha": 98.0, "missing_ha": 2.0,
            "complete": False,
            "biomass": {"area_ha": 98.0, "fraction": 0.98},
            "biomass_sd": {"area_ha": 98.0, "fraction": 0.98},
            "optical_paired": {"area_ha": 40.0, "fraction": 0.4},
        },
        "timeline": [
            {"year": 2019, "mean_tc_ha": 80.0, "total_tc": 7840.0,
             "mean_agb_t_ha": 170.2, "cells": cells_count, "covered_ha": 98.0},
        ],
        "optical": {"paired": {"paired_usable_fraction": 0.4}, "scenes": []},
    }


def test_the_real_rs_shape_is_read_into_typed_inputs():
    collection = {"type": "FeatureCollection", "features": [
        rs_cell(50.0, 100.0, 90.0, 10.0, 12.0),
        rs_cell(48.0, 120.0, 118.0, 11.0, 11.0),
    ]}
    inputs = from_rs_payload(rs_payload(), collection)
    assert inputs.input_status == INPUT_RS_PAYLOAD
    assert inputs.cells.count == 2
    assert inputs.coverage.biomass == pytest.approx(0.98)
    assert inputs.area.requested_ha == pytest.approx(100.0)
    assert inputs.area.calculated_ha == pytest.approx(98.0)
    assert inputs.area.missing_ha == pytest.approx(2.0)
    assert inputs.area.complete is False
    assert inputs.parent_aoi_ids == ("RU_TVER_01",)
    assert inputs.optical_quality is not None
    assert len(inputs.timeline) == 1


def test_the_cells_carry_both_dates_and_both_deviations():
    collection = {"type": "FeatureCollection", "features": [rs_cell(50.0, 100.0, 90.0, 10.0, 12.0)]}
    cells = cells_from_rs_geojson(collection, year_start=2019, year_end=2024)
    assert list(cells.area_ha) == [50.0]
    assert list(cells.agb_start) == [100.0]
    assert list(cells.agb_end) == [90.0]
    assert list(cells.sd_start) == [10.0]
    assert list(cells.sd_end) == [12.0]


def test_a_wrong_schema_is_refused_rather_than_guessed():
    with pytest.raises(RsPayloadError, match=RS_ANALYSIS_SCHEMA):
        from_rs_payload({"schema": "something.else/9"}, {"features": []})
    with pytest.raises(RsPayloadError, match=FIXTURE_SCHEMA):
        from_fixture({"schema": "something.else/9"})


def test_a_missing_year_is_an_error_not_a_zero():
    collection = {"type": "FeatureCollection", "features": [
        rs_cell(50.0, 100.0, 90.0, 10.0, 12.0, years=(2019, 2023)),
    ]}
    with pytest.raises(RsPayloadError, match="2024"):
        cells_from_rs_geojson(collection, year_start=2019, year_end=2024)


def test_a_missing_field_is_named():
    collection = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"agb_t_ha": {}, "agb_sd_t_ha": {}}},
    ]}
    with pytest.raises(RsPayloadError, match="weight_ha"):
        cells_from_rs_geojson(collection, year_start=2019, year_end=2024)


def test_an_empty_cell_layer_is_refused():
    with pytest.raises(RsPayloadError, match="no cells"):
        cells_from_rs_geojson({"features": []}, year_start=2019, year_end=2024)


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_every_fixture_loads_and_declares_itself_provisional(request_id):
    inputs = from_fixture(load_json(FIXTURE_DIR / f"cells_{request_id}.json"))
    assert inputs.input_status == INPUT_PROVISIONAL
    assert inputs.cells.count > 0
    assert inputs.coverage.biomass == 1.0
    assert inputs.source_files, "a fixture must name the official files it came from"
    assert all(path.endswith(".tif") for path in inputs.source_files)


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_the_fixture_area_matches_the_official_area_table(request_id, areas, sample_requests):
    """The extraction is defensible only if it reproduces the official area."""
    inputs = from_fixture(load_json(FIXTURE_DIR / f"cells_{request_id}.json"))
    if request_id in sample_requests:
        expected = sample_requests[request_id]["properties"]["area_ha"]
    else:
        expected = float(areas[request_id]["area_ha"])
    assert inputs.area.calculated_ha == pytest.approx(expected, rel=1e-6)
    assert inputs.area.requested_ha == pytest.approx(expected, rel=1e-6)
    assert inputs.area.complete is True


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_the_fixture_timeline_covers_the_supplied_years(request_id):
    inputs = from_fixture(load_json(FIXTURE_DIR / f"cells_{request_id}.json"))
    years = [point.year for point in inputs.timeline]
    assert years == list(range(2015, 2025))
    assert all(point.cells == inputs.cells.count for point in inputs.timeline)


def test_a_fixture_backed_analysis_is_flagged_all_the_way_through(case):
    _, _, analysis, _ = case("RU_TVER_01")
    assert analysis.input_status == INPUT_PROVISIONAL
    assert "PROVISIONAL_INPUT" in {note.code for note in analysis.notes}


def test_an_rs_backed_analysis_carries_no_provisional_flag(case, areas, sample_requests):
    from carbon import AnalysisRequest, BaselinePart, analyse

    collection = {"type": "FeatureCollection", "features": [
        rs_cell(50.0, 100.0, 90.0, 10.0, 12.0),
        rs_cell(48.0, 120.0, 118.0, 11.0, 11.0),
    ]}
    inputs = from_rs_payload(rs_payload(), collection)
    request = AnalysisRequest(
        request_id="RS", geometry={"type": "Point", "coordinates": [0.0, 0.0]},
        year_start=inputs.year_start, year_end=inputs.year_end,
        parts=(BaselinePart(aoi_id="RU_TVER_01", area_ha=inputs.area.calculated_ha),),
    )
    analysis = analyse(
        request, inputs.cells, coverage=inputs.coverage, area=inputs.area,
        input_status=inputs.input_status,
    )
    assert "PROVISIONAL_INPUT" not in {note.code for note in analysis.notes}
    # incomplete mandatory coverage makes Q unavailable, not zero
    assert analysis.units.units is None
    assert analysis.units.unavailable_reason == "INCOMPLETE_COVERAGE"
