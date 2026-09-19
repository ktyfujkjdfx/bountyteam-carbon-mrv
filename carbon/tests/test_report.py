"""The report shows the calculated numbers, adds none of its own, and stays inert."""
from __future__ import annotations

import html
import json
import re

import pytest

from carbon import (
    AnalysisRequest,
    BaselinePart,
    ClaimInput,
    analyse,
    build_passport,
    build_report,
    reasons,
    render_html,
)
from carbon.report import REPORT_FORMAT

RUN = {"created_at": "2026-09-19T00:00:00Z", "run_id": "run-1"}


@pytest.fixture(scope="module")
def built(case):
    _, _, analysis, provenance = case("RU_MORDOVIA_03")
    passport = build_passport(analysis, provenance=provenance)
    report = build_report(analysis, passport=passport, manifest_hash="0xabc", **RUN)
    return analysis, passport, report, render_html(report)


def test_report_repeats_the_passport_content_without_recomputing(built):
    analysis, passport, report, _ = built
    assert report["format"] == REPORT_FORMAT
    assert report["passport_content_hash"] == passport.content_hash
    for block in ("interval", "baseline", "units", "claim", "provenance", "timeline"):
        assert report[block] == passport.content[block]
    assert report["units"]["units"] == analysis.units.units


def test_api_report_and_canonical_content_agree_on_every_number(built):
    """The three views a consumer can compare must not disagree."""
    analysis, passport, report, _ = built
    api_view = {
        "units": analysis.units.units,
        "r_tco2e": analysis.units.r_tco2e,
        "h_tco2e": analysis.units.h_tco2e,
        "e_proj_tco2e": analysis.interval.e_proj_tco2e,
        "e_base_tco2e": analysis.baseline.e_base_tco2e,
        "lower_tco2e": analysis.interval.lower_tco2e,
        "upper_tco2e": analysis.interval.upper_tco2e,
    }
    for field, value in api_view.items():
        source = "units" if field in report["units"] else "interval"
        assert report[source][field] == value
        assert passport.content[source][field] == value


def test_html_contains_the_same_numbers_as_the_json(built):
    _, _, report, page = built
    assert report["passport_content_hash"] in page
    assert f"{report['interval']['e_proj_tco2e']:,.3f}".replace(",", " ") in page
    assert f"{report['baseline']['e_base_tco2e']:,.3f}".replace(",", " ") in page


def test_html_is_standalone_and_inert(built):
    _, _, _, page = built
    lowered = page.lower()
    for forbidden in ("<script", "javascript:", "onerror=", "onload=", "<iframe", "<form"):
        assert forbidden not in lowered
    # licence URLs are printed as text, which attribution requires; what must not exist
    # is anything the browser would fetch or execute.
    for attribute in ("href=", "src=", "url(", "@import", "srcset="):
        assert attribute not in lowered
    assert "file://" not in lowered


def test_html_leaks_no_local_path(built):
    _, _, _, page = built
    assert "/Users/" not in page
    assert "C:\\" not in page
    assert ".venv" not in page


def test_user_supplied_strings_are_escaped(case, areas, sample_requests):
    """A crafted request identifier must not become markup in someone else's browser."""
    from carbon.tests.conftest import FIXTURE_DIR, load_json

    from carbon import build_provenance, from_fixture

    inputs = from_fixture(load_json(FIXTURE_DIR / "cells_RU_TVER_01.json"))
    hostile = '"><script>alert(1)</script>'
    request = AnalysisRequest(
        request_id=hostile,
        geometry={"type": "Point", "coordinates": [0.0, 0.0]},
        year_start=inputs.year_start,
        year_end=inputs.year_end,
        parts=(BaselinePart(aoi_id="RU_TVER_01", area_ha=inputs.area.calculated_ha),),
    )
    analysis = analyse(request, inputs.cells, input_status=inputs.input_status)
    passport = build_passport(analysis, provenance=build_provenance(relative_paths=[]))
    page = render_html(build_report(analysis, passport=passport, **RUN))
    assert "<script>alert(1)</script>" not in page
    assert html.escape(hostile, quote=True) in page


def test_a_stop_rule_result_does_not_get_a_normal_waterfall():
    from carbon.units import Coverage, compute_units

    stopped = compute_units(
        e_proj_tco2e=0.0, e_base_tco2e=1000.0, lower_tco2e=-1000.0, upper_tco2e=1000.0,
        area_ha=100.0, year_start=2019, year_end=2024, coverage=Coverage(1.0, 1.0),
    )
    assert stopped.units == 0 and stopped.r_adj_tco2e is None
    page = render_html({
        "format": REPORT_FORMAT, "passport_content_hash": "0x0", "manifest_hash": None,
        "hashes": {"scientific_passport_content_hash": "0x0",
                   "source_manifest_hash": "0x0", "integrity_manifest_hash": None},
        "method_version": "test", "run": RUN,
        "request": {"request_id": "S", "geometry_hash": "0x0", "year_start": 2019,
                    "year_end": 2024, "pool": "AGB", "unit": "tCO2e", "baseline_parts": []},
        "input_status": "RS_PAYLOAD", "area": None,
        "coverage": {"biomass": 1.0, "baseline": 1.0}, "optical_quality": None,
        "timeline": [],
        "interval": {"sensitivity": [], "stock_start_tc": 0.0, "stock_end_tc": 0.0,
                     "delta_stock_tc": 0.0, "e_proj_tco2e": 0.0,
                     "e_per_ha_year_tco2e": 0.0, "sd_tco2e": 0.0,
                     "lower_tco2e": -1000.0, "upper_tco2e": 1000.0},
        "baseline": {"source": "data/methodology/baseline.csv", "delta_tc_ha": 0.0,
                     "e_base_tco2e": 1000.0},
        "units": {
            "status": stopped.status, "unavailable_reason": None,
            "zero_reason": stopped.zero_reason, "leakage_tco2e": stopped.leakage_tco2e,
            "r_tco2e": stopped.r_tco2e, "h_tco2e": stopped.h_tco2e,
            "ratio": stopped.ratio, "uncertainty_share": None,
            "uncertainty_deduction_tco2e": None, "r_adj_tco2e": None,
            "buffer_tco2e": None, "units": 0, "rounding_residual_tco2e": None,
            "scenario_values": [],
        },
        "claim": {"status": reasons.CLAIM_NOT_PROVIDED, "source": None,
                  "claimed_units": None, "units": None, "unsupported_gap": None,
                  "supported_share": None},
        "method_options": {"spatial_dependence": "INDEPENDENT_NATIVE_CELLS",
                           "temporal_correlation": 0.0, "coverage_factor": 1.0},
        "provenance": {"sources": [], "files": []},
        "notes": [], "limitations": [],
    })
    assert "UNCERTAINTY_TOO_HIGH" in page
    assert "не строится" in page


def test_an_unavailable_result_is_not_shown_as_zero(case):
    from carbon import build_provenance

    request = AnalysisRequest(
        request_id="NO_BASELINE",
        geometry={"type": "Point", "coordinates": [0.0, 0.0]},
        year_start=2019, year_end=2024,
        parts=(BaselinePart(aoi_id="RU_UNKNOWN_99", area_ha=10.0),),
    )
    _, inputs, _, _ = case("RU_TVER_01")
    analysis = analyse(request, inputs.cells)
    passport = build_passport(analysis, provenance=build_provenance(relative_paths=[]))
    page = render_html(build_report(analysis, passport=passport, **RUN))
    assert "Это не ноль единиц" in page
    assert analysis.units.units is None


def test_optical_quality_is_shown_separately_from_the_units(case):
    from carbon import build_provenance
    from carbon.tests.conftest import FIXTURE_DIR, load_json

    from carbon import from_fixture

    inputs = from_fixture(load_json(FIXTURE_DIR / "cells_RU_VOLOGDA_02.json"))
    request = AnalysisRequest(
        request_id="OPTICAL", geometry={"type": "Point", "coordinates": [0.0, 0.0]},
        year_start=inputs.year_start, year_end=inputs.year_end,
        parts=(BaselinePart(aoi_id="RU_VOLOGDA_02", area_ha=inputs.area.calculated_ha),),
    )
    cloudy = analyse(
        request, inputs.cells, optical_quality={"paired_usable_fraction": 0.11},
        input_status=inputs.input_status,
    )
    clear = analyse(request, inputs.cells, input_status=inputs.input_status)
    assert cloudy.units.units == clear.units.units
    assert "OPTICAL_QUALITY_SEPARATE" in {note.code for note in cloudy.notes}
    passport = build_passport(cloudy, provenance=build_provenance(relative_paths=[]))
    page = render_html(build_report(cloudy, passport=passport, **RUN))
    assert "не влияет на число единиц" in page


def test_the_page_states_that_its_timestamp_is_outside_the_hash(built):
    _, _, _, page = built
    assert "не входит в content_hash" in page


def test_the_page_opens_offline_without_any_external_resource(built):
    _, _, _, page = built
    for tag in re.findall(r"<(?:link|img|script|source)\b[^>]*>", page, flags=re.I):
        pytest.fail(f"the page references an external resource: {tag}")


def test_a_claim_is_labelled_as_input_in_the_report(case):
    _, _, base, provenance = case("RU_MORDOVIA_04")
    claim = ClaimInput(
        claimed_units=500.0, source=reasons.CLAIM_SOURCE_USER,
        geometry_hash=base.geometry_hash, year_start=base.request.year_start,
        year_end=base.request.year_end, pool=base.request.pool, unit=base.request.unit,
    )
    _, _, analysis, _ = case("RU_MORDOVIA_04", claim=claim)
    passport = build_passport(analysis, provenance=provenance)
    report = build_report(analysis, passport=passport, **RUN)
    page = render_html(report)
    assert report["claim"]["status"] == reasons.CLAIM_NOT_SUPPORTED
    assert "USER_INPUT" in page
    assert "не влияет" in page


def test_report_json_is_serialisable_and_finite(built):
    _, _, report, _ = built
    text = json.dumps(report, ensure_ascii=False, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text


def test_the_page_embeds_its_chart_and_outline_as_inline_svg(built):
    """The roadmap asks for an embedded chart; it must not come from a library or a CDN."""
    _, _, report, page = built
    assert page.count('class="chart"') == 1
    assert page.count('class="map"') == 1
    assert page.count("<polyline") == 1
    assert page.count("<circle") == len(report["timeline"])
    assert "<svg" in page and "</svg>" in page


def test_the_chart_is_drawn_from_the_printed_timeline(built):
    """A picture that disagrees with the table would be worse than no picture."""
    from carbon.report import _timeline_chart

    chart = _timeline_chart(report_timeline := built[2]["timeline"])
    for point in report_timeline:
        assert f"{point['year']}: {point['mean_tc_ha']:.3f}" in chart


def test_a_flat_series_does_not_divide_by_zero():
    from carbon.report import _timeline_chart

    flat = [
        {"year": year, "mean_tc_ha": 42.0, "total_tc": 1.0,
         "mean_agb_t_ha": 1.0, "cells": 1, "covered_ha": 1.0}
        for year in (2019, 2020, 2021)
    ]
    chart = _timeline_chart(flat)
    assert "<polyline" in chart
    assert "nan" not in chart.lower() and "inf" not in chart.lower()


def test_a_short_series_says_so_instead_of_drawing_nonsense():
    from carbon.report import _timeline_chart

    assert "<svg" not in _timeline_chart([])
    assert "слишком короткий" in _timeline_chart([])


def test_an_unusable_geometry_draws_nothing_rather_than_guessing():
    from carbon.report import _geometry_outline

    assert _geometry_outline(None) == ""
    assert _geometry_outline({"type": "Point", "coordinates": [0.0, 0.0]}) == ""
    assert _geometry_outline({"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]}) == ""


def test_the_outline_cannot_carry_markup_from_a_crafted_geometry():
    """Coordinates go through float(), so a string cannot reach the page as markup."""
    from carbon.report import _geometry_outline

    with pytest.raises((ValueError, TypeError)):
        _geometry_outline({
            "type": "Polygon",
            "coordinates": [[['"><script>', 0], [1, 1], [1, 0], ['"><script>', 0]]],
        })


def test_the_passport_carries_the_geometry_next_to_its_hash(built):
    """A hash nobody can recompute proves nothing, so the geometry travels with it."""
    _, passport, report, _ = built
    from carbon import canonical

    geometry = report["request"]["geometry"]
    assert canonical.content_hash(geometry) == report["request"]["geometry_hash"]
    assert passport.content["request"]["geometry"] == geometry
