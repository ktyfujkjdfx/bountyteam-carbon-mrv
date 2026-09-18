"""Integrity: what a manifest proves, and — more importantly — what it does not."""
from __future__ import annotations

import json

import pytest

from carbon import build_manifest, build_passport, describe, integrity, manifest_hash, verify


@pytest.fixture(scope="module")
def sealed(case):
    _, _, analysis, provenance = case("RU_TVER_01")
    passport = build_passport(analysis, provenance=provenance)
    report_bytes = json.dumps({"q": analysis.units.units}, ensure_ascii=False).encode("utf-8")
    page_bytes = b"<!DOCTYPE html><html><body>demo</body></html>"
    artifacts = {"report.json": report_bytes, "report.html": page_bytes}
    manifest = build_manifest(
        passport=passport,
        artifacts=[
            describe("report.json", report_bytes, media_type="application/json"),
            describe("report.html", page_bytes, media_type="text/html"),
        ],
        created_at="2026-09-19T00:00:00Z",
        run_id="run-1",
    )
    return passport, manifest, artifacts


def test_a_clean_download_verifies_against_the_trusted_hash(sealed):
    passport, manifest, artifacts = sealed
    trusted = manifest_hash(manifest)
    report = verify(
        manifest=manifest,
        artifacts=artifacts,
        trusted_manifest_hash=trusted,
        passport_content=passport.content,
    )
    assert report.outcome == integrity.VERIFIED_AGAINST_TRUSTED_HASH
    assert report.ok
    assert all(check.ok for check in report.checks)


def test_the_manifest_never_contains_its_own_hash(sealed):
    _, manifest, _ = sealed
    serialised = json.dumps(manifest, ensure_ascii=False)
    assert manifest_hash(manifest) not in serialised
    assert "manifest_hash" not in manifest


def test_a_tampered_artifact_is_caught(sealed):
    passport, manifest, artifacts = sealed
    forged = dict(artifacts)
    forged["report.json"] = json.dumps({"q": 999}, ensure_ascii=False).encode("utf-8")
    report = verify(
        manifest=manifest, artifacts=forged, trusted_manifest_hash=manifest_hash(manifest)
    )
    assert report.outcome == integrity.FAILED
    assert not report.ok
    broken = {check.name: check.status for check in report.checks}
    assert broken["report.json"] in (
        integrity.ARTIFACT_HASH_MISMATCH, integrity.ARTIFACT_SIZE_MISMATCH
    )
    assert broken["report.html"] == integrity.CHECK_OK


def test_a_forged_copy_with_its_own_valid_manifest_fails_against_the_trusted_hash(sealed):
    """The whole point of the detached hash: a consistent forgery is still a forgery."""
    passport, manifest, artifacts = sealed
    trusted = manifest_hash(manifest)

    forged_bytes = json.dumps({"q": 4242}, ensure_ascii=False).encode("utf-8")
    forged_artifacts = dict(artifacts) | {"report.json": forged_bytes}
    forged_manifest = build_manifest(
        passport=passport,
        artifacts=[
            describe("report.json", forged_bytes, media_type="application/json"),
            describe("report.html", artifacts["report.html"], media_type="text/html"),
        ],
        created_at="2026-09-19T00:00:00Z",
        run_id="run-1",
    )

    # internally consistent, and the utility says exactly that and no more
    self_check = verify(manifest=forged_manifest, artifacts=forged_artifacts)
    assert self_check.outcome == integrity.SELF_CONSISTENT_ONLY
    assert not self_check.ok
    assert "не является подтверждением подлинности" in self_check.explanation

    # against the trusted reference it fails
    against_trusted = verify(
        manifest=forged_manifest,
        artifacts=forged_artifacts,
        trusted_manifest_hash=trusted,
    )
    assert against_trusted.outcome == integrity.FAILED
    assert any(
        check.status == integrity.MANIFEST_HASH_MISMATCH for check in against_trusted.checks
    )


def test_a_missing_file_is_not_silently_skipped(sealed):
    _, manifest, artifacts = sealed
    partial = {"report.html": artifacts["report.html"]}
    report = verify(
        manifest=manifest, artifacts=partial, trusted_manifest_hash=manifest_hash(manifest)
    )
    assert report.outcome == integrity.FAILED
    assert any(check.status == integrity.ARTIFACT_MISSING for check in report.checks)


def test_an_undeclared_extra_file_is_reported(sealed):
    _, manifest, artifacts = sealed
    extra = dict(artifacts) | {"notes.txt": b"hello"}
    report = verify(
        manifest=manifest, artifacts=extra, trusted_manifest_hash=manifest_hash(manifest)
    )
    assert report.outcome == integrity.FAILED
    assert any(check.status == integrity.ARTIFACT_NOT_IN_MANIFEST for check in report.checks)


def test_a_passport_whose_content_does_not_match_its_declared_hash_is_caught(sealed):
    passport, manifest, artifacts = sealed
    edited = json.loads(json.dumps(passport.content))
    edited["units"]["units"] = 10_000
    report = verify(
        manifest=manifest,
        artifacts=artifacts,
        trusted_manifest_hash=manifest_hash(manifest),
        passport_content=edited,
    )
    assert report.outcome == integrity.FAILED
    assert any(check.status == integrity.PASSPORT_HASH_MISMATCH for check in report.checks)


def test_verification_without_a_trusted_reference_refuses_to_claim_authenticity(sealed):
    _, manifest, artifacts = sealed
    report = verify(manifest=manifest, artifacts=artifacts)
    assert report.outcome == integrity.SELF_CONSISTENT_ONLY
    assert not report.ok
    assert report.trusted_manifest_hash is None


def test_the_explanation_does_not_promise_more_than_bytes(sealed):
    passport, manifest, artifacts = sealed
    report = verify(
        manifest=manifest, artifacts=artifacts, trusted_manifest_hash=manifest_hash(manifest)
    )
    assert "неизменность байтов" in report.explanation
    assert "не правильность оценки" in report.explanation
    assert "перепрода" not in report.explanation.lower()


def test_duplicate_artifact_names_are_refused(sealed):
    passport, _, artifacts = sealed
    record = describe("report.html", artifacts["report.html"], media_type="text/html")
    with pytest.raises(ValueError):
        build_manifest(
            passport=passport,
            artifacts=[record, record],
            created_at="2026-09-19T00:00:00Z",
            run_id="run-1",
        )


def test_the_manifest_records_the_version_chain(case):
    _, _, analysis, provenance = case("RU_MORDOVIA_04")
    first = build_passport(analysis, provenance=provenance)
    second = build_passport(
        analysis, provenance=provenance, previous_content_hash=first.content_hash
    )
    first_manifest = build_manifest(
        passport=first, artifacts=[], created_at="2026-09-19T00:00:00Z", run_id="a"
    )
    second_manifest = build_manifest(
        passport=second,
        artifacts=[],
        created_at="2026-09-19T00:01:00Z",
        run_id="b",
        previous_manifest_hash=manifest_hash(first_manifest),
    )
    assert second_manifest["previous_content_hash"] == first.content_hash
    assert second_manifest["previous_manifest_hash"] == manifest_hash(first_manifest)
