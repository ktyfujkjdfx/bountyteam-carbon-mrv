"""The passport: stable content, volatile envelope, honest version linkage."""
from __future__ import annotations

import json

import pytest

from carbon import (
    ClaimInput,
    MethodOptions,
    Passport,
    build_passport,
    canonical,
    link_versions,
    reasons,
    seal,
)
from carbon import passport as passport_module
from carbon.passport import LIMITATIONS


@pytest.fixture(scope="module")
def sealed(case):
    _, _, analysis, provenance = case("RU_MORDOVIA_03")
    return analysis, build_passport(analysis, provenance=provenance)


def test_the_same_analysis_sealed_twice_has_the_same_content_hash(case):
    _, _, analysis, provenance = case("RU_TVER_01")
    first = build_passport(analysis, provenance=provenance)
    second = build_passport(analysis, provenance=provenance)
    assert first.content_hash == second.content_hash
    assert first.canonical_bytes == second.canonical_bytes


def test_recomputing_the_whole_analysis_reproduces_the_hash(case):
    """Determinism has to survive a fresh analysis, not just a second seal of one object."""
    hashes = set()
    for _ in range(2):
        _, _, analysis, provenance = case("CHECK_TRANSFER_01")
        hashes.add(build_passport(analysis, provenance=provenance).content_hash)
    assert len(hashes) == 1


def test_run_metadata_stays_outside_the_content_hash(sealed):
    _, passport = sealed
    first = seal(passport, created_at="2026-01-01T00:00:00Z", run_id="run-1")
    second = seal(passport, created_at="2031-12-31T23:59:59Z", run_id="run-2")
    assert first.passport.content_hash == second.passport.content_hash
    assert first.to_dict()["run"] != second.to_dict()["run"]
    assert "created_at" not in json.dumps(passport.content)
    assert "run_id" not in json.dumps(passport.content)


def test_changing_any_number_changes_the_hash(sealed):
    _, passport = sealed
    tampered = json.loads(json.dumps(passport.content))
    tampered["units"]["units"] = 1
    assert canonical.content_hash(tampered) != passport.content_hash


def test_a_different_method_assumption_gives_a_different_passport(case):
    _, _, default_analysis, provenance = case("RU_VOLOGDA_02")
    _, _, dependent_analysis, _ = case(
        "RU_VOLOGDA_02", options=MethodOptions(spatial_dependence="FULL_SPATIAL_CORRELATION")
    )
    assert (
        build_passport(default_analysis, provenance=provenance).content_hash
        != build_passport(dependent_analysis, provenance=provenance).content_hash
    )


def test_content_carries_the_scientific_record(sealed):
    analysis, passport = sealed
    content = passport.content
    assert content["format"] == canonical.FORMAT
    assert content["request"]["geometry_hash"] == analysis.geometry_hash
    assert content["request"]["year_start"] == analysis.request.year_start
    assert content["request"]["pool"] == "AGB_LIVE_WOODY"
    assert content["provenance"]["parameters"]["co2_per_c_exact"] == "44/12"
    assert content["provenance"]["all_checksums_match"] is True
    assert content["interval"]["kind"] == "SCENARIO"
    assert len(content["interval"]["sensitivity"]) == 4
    assert content["baseline"]["source"] == "data/methodology/baseline.csv"
    assert content["units"]["units"] == analysis.units.units
    assert content["limitations"] == list(LIMITATIONS)
    assert content["input_status"] == "PROVISIONAL_LOCAL_EXTRACTION"


def test_a_provisional_input_is_declared_in_the_passport(sealed):
    _, passport = sealed
    codes = {note["code"] for note in passport.content["notes"]}
    assert "PROVISIONAL_INPUT" in codes


def test_the_passport_is_canonicalisable_and_json_safe(sealed):
    _, passport = sealed
    restored = json.loads(passport.canonical_bytes.decode("utf-8"))
    assert canonical.content_hash(restored) == passport.content_hash


def test_units_for_reader_separates_availability_from_zero(sealed):
    _, passport = sealed
    status, units = passport_module.units_for_reader(passport)
    assert status == reasons.AVAILABLE
    assert units == 0


def test_an_unavailable_passport_reports_null_units_not_zero(case):
    _, inputs, _, provenance = case("RU_TVER_01")
    from carbon import AnalysisRequest, BaselinePart, analyse

    request = AnalysisRequest(
        request_id="EMPTY_BASELINE",
        geometry={"type": "Point", "coordinates": [0.0, 0.0]},
        year_start=2019,
        year_end=2024,
        parts=(BaselinePart(aoi_id="RU_UNKNOWN_99", area_ha=100.0),),
    )
    analysis = analyse(request, inputs.cells)
    passport = build_passport(analysis, provenance=provenance)
    status, units = passport_module.units_for_reader(passport)
    assert status == reasons.UNAVAILABLE
    assert units is None
    assert passport.content["units"]["units"] is None


# --- version linkage -------------------------------------------------------------


def test_the_first_passport_is_initial(sealed):
    _, passport = sealed
    link = link_versions(None, passport)
    assert link.status == passport_module.VERSION_INITIAL
    assert link.previous_content_hash is None


def test_a_rerun_of_the_same_scope_is_a_revision(case):
    _, _, analysis, provenance = case("RU_TVER_01")
    first = build_passport(analysis, provenance=provenance)
    second = build_passport(
        analysis, provenance=provenance, previous_content_hash=first.content_hash
    )
    link = link_versions(first, second)
    assert link.status == passport_module.VERSION_REVISION
    assert link.changed == ()
    assert second.content["previous_content_hash"] == first.content_hash


def test_a_different_period_is_a_new_observation_and_writes_nothing_off(case):
    """Re-observing the same place over a new period does not replace the earlier answer."""
    _, _, analysis, provenance = case("RU_VOLOGDA_02")
    first = build_passport(analysis, provenance=provenance)
    later = json.loads(json.dumps(first.content))
    later["request"]["year_start"] = 2021
    later["previous_content_hash"] = first.content_hash
    second = Passport(content=later, content_hash=canonical.content_hash(later))

    link = link_versions(first, second)
    assert link.status == passport_module.VERSION_NEW_OBSERVATION
    assert link.changed == ("year_start",)
    assert {note.code for note in link.notes} == {"PASSPORT_NEW_OBSERVATION"}
    # the earlier passport keeps its own hash and its own Q
    assert first.content_hash != second.content_hash
    assert first.content["units"]["units"] == analysis.units.units


def test_a_different_geometry_is_not_comparable(case):
    _, _, tver, provenance = case("RU_TVER_01")
    _, _, vologda, _ = case("RU_VOLOGDA_02")
    first = build_passport(tver, provenance=provenance)
    second = build_passport(vologda, provenance=provenance)
    link = link_versions(first, second)
    assert link.status == passport_module.VERSION_NOT_COMPARABLE
    assert "geometry_hash" in link.changed


def test_a_claim_is_recorded_as_an_input_label_and_does_not_move_q(case):
    _, _, plain, provenance = case("RU_MORDOVIA_04")
    claimed = ClaimInput(
        claimed_units=1000.0,
        source=reasons.CLAIM_SOURCE_DEMO,
        geometry_hash=plain.geometry_hash,
        year_start=plain.request.year_start,
        year_end=plain.request.year_end,
        pool=plain.request.pool,
        unit=plain.request.unit,
    )
    _, _, with_claim, _ = case("RU_MORDOVIA_04", claim=claimed)
    assert with_claim.units.units == plain.units.units
    assert with_claim.interval.e_proj_tco2e == plain.interval.e_proj_tco2e
    assert with_claim.baseline.e_base_tco2e == plain.baseline.e_base_tco2e
    content = build_passport(with_claim, provenance=provenance).content
    assert content["claim"]["source"] == reasons.CLAIM_SOURCE_DEMO
    assert content["claim"]["claimed_units"] == 1000.0


# -- the four hashes --------------------------------------------------------------------


def test_the_four_hashes_are_named_apart(sealed):
    """Four hashes answer four questions; nobody should have to guess which is which."""
    from carbon import build_manifest, build_report, describe, manifest_hash
    from carbon import passport as module

    analysis, passport = sealed
    assert set(passport.hashes()) == {
        module.SCIENTIFIC_CONTENT_HASH, module.SOURCE_MANIFEST_HASH,
    }
    assert passport.hashes()[module.SCIENTIFIC_CONTENT_HASH] == passport.content_hash
    assert passport.source_manifest_hash.startswith("0x")
    assert passport.source_manifest_hash != passport.content_hash

    page = b"<!DOCTYPE html><html><body>x</body></html>"
    manifest = build_manifest(
        passport=passport,
        artifacts=[describe("report.html", page, media_type="text/html")],
        created_at="2026-09-19T00:00:00Z", run_id="hashes",
    )
    assert manifest[module.SCIENTIFIC_CONTENT_HASH] == passport.content_hash
    assert manifest[module.SOURCE_MANIFEST_HASH] == passport.source_manifest_hash
    assert manifest["artifacts"][0][module.REPORT_FILE_HASH].startswith("0x")
    # the manifest hash itself lives outside the manifest
    assert manifest_hash(manifest) not in json.dumps(manifest, ensure_ascii=False)

    report = build_report(
        analysis, passport=passport, manifest_hash=manifest_hash(manifest),
        created_at="2026-09-19T00:00:00Z", run_id="hashes",
    )
    assert report["hashes"]["scientific_passport_content_hash"] == passport.content_hash
    assert report["hashes"]["source_manifest_hash"] == passport.source_manifest_hash


def test_the_source_manifest_hash_covers_the_inputs_only(case):
    """Changing an input must move it; changing a method assumption must not."""
    _, _, analysis, provenance = case("RU_VOLOGDA_02")
    first = build_passport(analysis, provenance=provenance)
    _, _, other_options, _ = case(
        "RU_VOLOGDA_02", options=MethodOptions(spatial_dependence="FULL_SPATIAL_CORRELATION")
    )
    second = build_passport(other_options, provenance=provenance)
    assert first.content_hash != second.content_hash
    assert first.source_manifest_hash == second.source_manifest_hash

    edited = json.loads(json.dumps(provenance))
    edited["files"][0]["declared_sha256"] = "0xdeadbeef"
    third = build_passport(analysis, provenance=edited)
    assert third.source_manifest_hash != first.source_manifest_hash


def test_the_passport_records_everything_a_reader_must_check(sealed):
    _, passport = sealed
    content = passport.content
    request = content["request"]
    assert {"request_id", "geometry", "geometry_hash", "year_start", "year_end",
            "pool", "unit", "baseline_parts"} <= set(request)
    assert content["area"]["requested_ha"] > 0
    assert set(content["coverage"]) >= {"biomass", "uncertainty", "baseline", "raw"}
    assert content["timeline"], "the annual series is part of the record"
    interval = content["interval"]
    assert interval["lower_tco2e"] <= interval["e_proj_tco2e"] <= interval["upper_tco2e"]
    units = content["units"]
    assert {"h_tco2e", "r_tco2e", "ratio", "uncertainty_share", "r_adj_tco2e",
            "buffer_tco2e", "units", "rounding_residual_tco2e"} <= set(units)
    assert content["baseline"]["e_base_tco2e"] is not None
    assert content["cross_check"]["agrees"] is True
    assert content["limitations"]
    assert content["method_version"]
    assert content["provenance"]["source_manifest_hash"]


def test_a_self_consistent_check_is_not_offered_as_an_independent_one(sealed):
    from carbon import integrity, verify

    _, passport = sealed
    page = b"<html></html>"
    from carbon import build_manifest, describe

    manifest = build_manifest(
        passport=passport, artifacts=[describe("r.html", page, media_type="text/html")],
        created_at="2026-09-19T00:00:00Z", run_id="x",
    )
    report = verify(manifest=manifest, artifacts={"r.html": page})
    assert report.outcome == integrity.SELF_CONSISTENT_ONLY
    assert report.ok is False
    assert "не независимая проверка" in report.explanation
