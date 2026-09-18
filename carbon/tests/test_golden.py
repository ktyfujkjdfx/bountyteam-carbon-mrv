"""Golden results and end-to-end reproducibility on the five official requests.

The golden file records what the engine answers today, including the passport content
hash. A formula change, a different composition order or a changed passport shape turns
into a visible diff here rather than a silent drift. Regenerate with
`python -m carbon.tests.golden.build_golden` and read the diff before committing it.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from carbon import (
    build_manifest,
    build_passport,
    build_report,
    describe,
    integrity,
    manifest_hash,
    reasons,
    render_html,
    verify,
)
from carbon.parameters import METHOD_VERSION, REPO_ROOT
from carbon.tests.conftest import ALL_REQUESTS, GOLDEN_DIR, build_case

GOLDEN = json.loads((GOLDEN_DIR / "results.json").read_text(encoding="utf-8"))
EXPECTED = {row["request_id"]: row for row in GOLDEN["results"]}

EXACT_FIELDS = (
    "year_start", "year_end", "cells", "units", "status",
    "unavailable_reason", "zero_reason", "input_status",
    "geometry_hash", "passport_content_hash",
)
NUMERIC_FIELDS = (
    "area_ha", "stock_start_tc", "stock_end_tc", "delta_stock_tc", "e_proj_tco2e",
    "e_per_ha_year_tco2e", "sd_tco2e", "lower_tco2e", "upper_tco2e", "e_base_tco2e",
    "baseline_delta_tc_ha", "r_tco2e", "h_tco2e", "ratio", "uncertainty_share",
    "r_adj_tco2e", "buffer_tco2e", "rounding_residual_tco2e",
)


@pytest.fixture(scope="module")
def actual(areas, sample_requests):
    from carbon.tests.golden.build_golden import _row

    return {
        request_id: _row(request_id, areas, sample_requests)
        for request_id in ALL_REQUESTS
    }


def test_the_golden_file_covers_every_official_request():
    assert set(EXPECTED) == set(ALL_REQUESTS)
    assert GOLDEN["method_version"] == METHOD_VERSION


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_golden_values_still_hold(request_id, actual):
    expected, produced = EXPECTED[request_id], actual[request_id]
    for field in EXACT_FIELDS:
        assert produced[field] == expected[field], field
    for field in NUMERIC_FIELDS:
        if expected[field] is None:
            assert produced[field] is None, field
        else:
            assert produced[field] == pytest.approx(expected[field], rel=1e-12), field
    assert produced["note_codes"] == expected["note_codes"]


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_the_content_hash_is_reproducible_within_a_process(request_id, areas, sample_requests):
    hashes = set()
    for _ in range(3):
        _, _, analysis, provenance = build_case(request_id, areas, sample_requests)
        hashes.add(build_passport(analysis, provenance=provenance).content_hash)
    assert hashes == {EXPECTED[request_id]["passport_content_hash"]}


def test_the_content_hash_is_reproducible_in_a_fresh_interpreter():
    """Hash randomisation, import order and dict insertion order must not matter."""
    code = (
        "import json;"
        "from carbon.tests.conftest import build_case, read_csv, load_json;"
        "from carbon.parameters import REPO_ROOT;"
        "from carbon import build_passport;"
        "areas={r['aoi_id']: r for r in read_csv(REPO_ROOT/'data'/'areas.csv')};"
        "sr={f['properties']['request_id']: f for f in "
        "load_json(REPO_ROOT/'data'/'sample_requests.geojson')['features']};"
        "print(json.dumps({rid: build_passport(build_case(rid, areas, sr)[2], "
        "provenance=build_case(rid, areas, sr)[3]).content_hash "
        "for rid in ['RU_TVER_01','RU_MORDOVIA_03','CHECK_TRANSFER_01']}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        env={"PYTHONHASHSEED": "1", "PYTHONUTF8": "1", "PATH": "/usr/bin:/bin"},
    )
    produced = json.loads(completed.stdout)
    for request_id, digest in produced.items():
        assert digest == EXPECTED[request_id]["passport_content_hash"]


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_the_supplied_data_earns_no_units_and_says_why(request_id, actual):
    """Stated plainly in the golden record: valid input, and the case rules give zero."""
    row = actual[request_id]
    assert row["status"] == reasons.AVAILABLE
    assert row["units"] == 0
    assert row["unavailable_reason"] is None
    assert row["zero_reason"] == reasons.NON_POSITIVE_RELATIVE_RESULT
    assert row["r_tco2e"] <= 0.0


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_every_golden_result_is_built_from_verified_official_files(request_id, areas, sample_requests):
    _, inputs, _, provenance = build_case(request_id, areas, sample_requests)
    assert provenance["all_checksums_match"] is True
    recorded = {entry["relative_path"] for entry in provenance["files"]}
    # the two rasters of the period plus the two methodology tables every Q depends on
    assert recorded == set(inputs.source_files) | {
        "methodology/parameters.csv", "methodology/baseline.csv",
    }
    assert len(inputs.source_files) == 2
    assert "CCI_V7" in {source["source_id"] for source in provenance["sources"]}
    for entry in provenance["files"]:
        assert entry["checksum_status"] == "MATCHES_CATALOGUE"
        assert entry["computed_sha256"] == entry["declared_sha256"]


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_the_full_publication_chain_verifies(request_id, areas, sample_requests):
    """Analyse → seal → report → manifest → verify, the way a consumer would."""
    _, _, analysis, provenance = build_case(request_id, areas, sample_requests)
    passport = build_passport(analysis, provenance=provenance)

    report = build_report(
        analysis, passport=passport, manifest_hash=None,
        created_at="2026-09-19T00:00:00Z", run_id="golden",
    )
    report_bytes = json.dumps(report, ensure_ascii=False, allow_nan=False).encode("utf-8")
    page_bytes = render_html(report).encode("utf-8")
    passport_bytes = json.dumps(
        passport.content, ensure_ascii=False, allow_nan=False
    ).encode("utf-8")

    artifacts = {
        "passport.json": passport_bytes,
        "report.json": report_bytes,
        "report.html": page_bytes,
    }
    manifest = build_manifest(
        passport=passport,
        artifacts=[
            describe("passport.json", passport_bytes, media_type="application/json"),
            describe("report.json", report_bytes, media_type="application/json"),
            describe("report.html", page_bytes, media_type="text/html"),
        ],
        created_at="2026-09-19T00:00:00Z",
        run_id="golden",
    )
    outcome = verify(
        manifest=manifest,
        artifacts=artifacts,
        trusted_manifest_hash=manifest_hash(manifest),
        passport_content=passport.content,
    )
    assert outcome.outcome == integrity.VERIFIED_AGAINST_TRUSTED_HASH
    assert manifest["passport_content_hash"] == EXPECTED[request_id]["passport_content_hash"]


def test_the_html_report_opens_without_the_repository(areas, sample_requests, tmp_path):
    """A saved page must render on its own: no relative asset, no missing file."""
    _, _, analysis, provenance = build_case("RU_MORDOVIA_03", areas, sample_requests)
    passport = build_passport(analysis, provenance=provenance)
    report = build_report(
        analysis, passport=passport, manifest_hash="0x0",
        created_at="2026-09-19T00:00:00Z", run_id="offline",
    )
    page = tmp_path / "passport.html"
    page.write_text(render_html(report), encoding="utf-8")
    assert page.stat().st_size > 5000
    assert list(tmp_path.iterdir()) == [page]
    text = page.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    assert str(REPO_ROOT) not in text


def test_the_golden_file_declares_its_provisional_input():
    assert "provisional" in GOLDEN["note"].lower()
    assert all(row["input_status"] == "PROVISIONAL_LOCAL_EXTRACTION" for row in GOLDEN["results"])


def test_the_golden_file_is_the_one_the_builder_writes(areas, sample_requests, tmp_path):
    """The committed file must be exactly what a regeneration produces."""
    from carbon.tests.golden import build_golden

    rebuilt = {
        "note": GOLDEN["note"],
        "method_version": METHOD_VERSION,
        "results": [
            build_golden._row(request_id, areas, sample_requests)
            for request_id in ALL_REQUESTS
        ],
    }
    assert json.dumps(rebuilt, ensure_ascii=False, sort_keys=True) == json.dumps(
        GOLDEN, ensure_ascii=False, sort_keys=True
    )
