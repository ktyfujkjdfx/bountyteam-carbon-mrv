"""The passport: determinism, the two report formats, the proof and honest comparison."""
from __future__ import annotations

import json

import pytest

from .conftest import SESSION, Harness

POSITIVE = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024}
SHORTER = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2022}


def analysed(harness: Harness, body: dict, key: str) -> dict:
    job = harness.analyse(body, key=key)
    assert job["job_state"] == "SUCCEEDED", job
    return job


# -- determinism --------------------------------------------------------------------------
def test_the_same_request_produces_the_same_content_hash(harness):
    first = analysed(harness, POSITIVE, "det-key-00000001")["result"]
    second = analysed(harness, POSITIVE, "det-key-00000002")["result"]
    assert first["passport"]["content_hash"] == second["passport"]["content_hash"]
    assert first["passport"]["report_hash"] == second["passport"]["report_hash"]


def test_the_same_request_on_a_fresh_deployment_hashes_the_same(tmp_path, harness):
    """A different machine, a different database, the same answer."""
    here = analysed(harness, POSITIVE, "cross-key-000001")["result"]
    elsewhere = Harness(tmp_path / "elsewhere")
    there = analysed(elsewhere, POSITIVE, "cross-key-000002")["result"]
    assert here["passport"]["content_hash"] == there["passport"]["content_hash"]


def test_the_run_time_and_the_ids_are_outside_the_content_hash(harness):
    first = analysed(harness, POSITIVE, "outside-key-0001")["result"]
    second = analysed(harness, POSITIVE, "outside-key-0002")["result"]
    assert first["identity"]["analysis_id"] != second["identity"]["analysis_id"]
    assert first["run"]["run_id"] != second["run"]["run_id"]
    assert first["passport"]["content_hash"] == second["passport"]["content_hash"]


def test_a_different_period_is_a_different_passport(harness):
    long_period = analysed(harness, POSITIVE, "period-key-00001")["result"]
    short_period = analysed(harness, SHORTER, "period-key-00002")["result"]
    assert (long_period["passport"]["content_hash"]
            != short_period["passport"]["content_hash"])


def test_the_content_hash_changes_when_a_number_changes(harness):
    from backend.app.v2.assemble import content_view
    from backend.app.v2.contracts import digest

    result = analysed(harness, POSITIVE, "sensitive-key-01")["result"]
    tampered = json.loads(json.dumps(result))
    tampered["units"]["q"] = (tampered["units"]["q"] or 0) + 1
    assert digest(content_view(tampered)) != result["passport"]["content_hash"]


def test_a_tampered_report_no_longer_matches_its_hash(harness):
    """The negative probe: an edited copy of a passport must stop verifying."""
    from backend.app.v2.assemble import content_view
    from backend.app.v2.contracts import digest
    from backend.app.v2.report import REPORT_SCHEMA_VERSION

    job = analysed(harness, POSITIVE, "tamper-key-000001")
    document = harness.api.get(f"/analyses/{job['analysis_id']}/report", "Report")
    recomputed = digest({"report": REPORT_SCHEMA_VERSION,
                         "content": content_view(document["result"])})
    assert recomputed == document["report_hash"]

    edited = json.loads(json.dumps(document))
    edited["result"]["units"]["q"] = 999999
    assert digest({"report": REPORT_SCHEMA_VERSION,
                   "content": content_view(edited["result"])}) != edited["report_hash"]


# -- the report ---------------------------------------------------------------------------
def test_the_json_report_carries_exactly_the_result(harness):
    job = analysed(harness, POSITIVE, "report-key-000001")
    document = harness.api.get(f"/analyses/{job['analysis_id']}/report", "Report")
    assert document["result"] == job["result"]
    assert document["report_hash"] == job["result"]["passport"]["report_hash"]


def test_the_json_report_is_byte_stable_across_downloads(harness):
    job = analysed(harness, POSITIVE, "stable-key-000001")
    path = f"/api/v2/analyses/{job['analysis_id']}/report?format=json"
    first = harness.client.get(path, headers={"X-Demo-Session": SESSION}).content
    second = harness.client.get(path, headers={"X-Demo-Session": SESSION}).content
    assert first == second


def test_the_html_report_is_self_contained(harness):
    job = analysed(harness, POSITIVE, "html-key-00000001")
    response = harness.client.get(
        f"/api/v2/analyses/{job['analysis_id']}/report?format=html",
        headers={"X-Demo-Session": SESSION})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "<script" not in html.lower()
    assert "<link" not in html.lower()
    assert "http://" not in html and "https://" not in html
    assert "X-Demo-Session" not in html and SESSION not in html


def test_the_html_report_shows_the_numbers_and_the_hash(harness):
    job = analysed(harness, POSITIVE, "htmlnum-key-00001")
    html = harness.client.get(
        f"/api/v2/analyses/{job['analysis_id']}/report?format=html",
        headers={"X-Demo-Session": SESSION}).text
    result = job["result"]
    assert str(result["units"]["q"]) in html
    assert result["passport"]["content_hash"] in html
    assert result["identity"]["method_version"] in html
    assert "надземная" in html


def test_the_html_report_states_the_fixture_label(harness):
    job = analysed(harness, POSITIVE, "htmlfix-key-00001")
    html = harness.client.get(
        f"/api/v2/analyses/{job['analysis_id']}/report?format=html",
        headers={"X-Demo-Session": SESSION}).text
    assert job["result"]["fixture"]["label"] in html
    assert "UNIT_TEST_VECTOR" in html


def test_an_absent_number_is_explained_rather_than_shown_as_zero(harness):
    job = analysed(harness, {"aoi_id": "RU_MORDOVIA_04", "year_start": 2019, "year_end": 2024},
                   "htmlnull-key-0001")
    html = harness.client.get(
        f"/api/v2/analyses/{job['analysis_id']}/report?format=html",
        headers={"X-Demo-Session": SESSION}).text
    assert "не рассчитаны" in html
    assert "Сценарная стоимость не рассчитывается" in html


def test_a_report_for_an_unknown_analysis_is_404(harness):
    harness.api.get("/analyses/00000000-0000-4000-8000-0000000000bb/report", "Error", status=404)


def test_an_unknown_report_format_is_refused(harness):
    job = analysed(harness, POSITIVE, "format-key-000001")
    response = harness.client.get(
        f"/api/v2/analyses/{job['analysis_id']}/report?format=pdf",
        headers={"X-Demo-Session": SESSION})
    assert response.status_code == 422


def test_a_stored_passport_is_immutable(harness):
    import sqlite3

    job = analysed(harness, POSITIVE, "immutable-key-001")
    with pytest.raises(sqlite3.IntegrityError):
        with harness.ctx.db.transaction() as conn:
            conn.execute("UPDATE lens_reports SET report_hash='0x00' WHERE analysis_id=?",
                         (job["analysis_id"],))


# -- the proof ----------------------------------------------------------------------------
def test_the_proof_links_the_hashes_and_the_versions(harness):
    job = analysed(harness, POSITIVE, "proof-key-0000001")
    proof = harness.api.get(f"/analyses/{job['analysis_id']}/proof", "Proof")
    assert proof["identity"] == job["result"]["identity"]
    assert proof["passport"] == job["result"]["passport"]
    assert proof["report_urls"]["html"].endswith("format=html")
    assert proof["artifacts"] == job["result"]["artifacts"]


def test_the_anchor_is_honest_about_not_being_requested(harness):
    job = analysed(harness, POSITIVE, "anchor-key-000001")
    anchor = harness.api.get(f"/analyses/{job['analysis_id']}/proof", "Proof")["anchor"]
    assert anchor["status"] == "NOT_REQUESTED"
    assert anchor["tx_hash"] is None and anchor["deployment_id"] is None
    assert "не предотвращает двойную продажу" in anchor["note"]
    assert "не удостоверяет истинность" in anchor["note"]


def test_the_proof_names_the_dataset_and_the_parameters(harness):
    from backend.app.v2 import catalog

    job = analysed(harness, POSITIVE, "dataset-key-00001")
    identity = harness.api.get(f"/analyses/{job['analysis_id']}/proof", "Proof")["identity"]
    assert identity["dataset_hash"] == catalog.dataset_hash()
    assert identity["parameters_hash"] == catalog.parameters_hash()
    assert identity["dataset_version"] == catalog.DATASET_VERSION
    assert identity["source_manifest_hash"].startswith("0x")


def test_a_proof_for_an_unfinished_analysis_is_404(harness):
    accepted = harness.api.post("/analyses", POSITIVE, key="unfinished-key-1")
    harness.api.get(f"/analyses/{accepted['analysis_id']}/proof", "Error", status=404)


# -- comparison ---------------------------------------------------------------------------
def test_the_first_analysis_of_a_scope_has_no_predecessor(harness):
    result = analysed(harness, POSITIVE, "first-key-0000001")["result"]
    assert result["passport"]["previous_hash"] is None
    assert result["passport"]["comparison_result"] == "INITIAL"
    assert result["passport"]["comparison_direction"] == "NOT_COMPARED"


def test_a_fresh_passport_is_a_draft_and_carries_no_anchor_status(harness):
    """Two axes, two fields: a document state is not a record on a chain."""
    job = analysed(harness, POSITIVE, "draft-key-00000001")
    passport = job["result"]["passport"]
    assert passport["status"] == "DRAFT" and passport["finalized_at"] is None
    assert "anchor" not in passport and "anchor_status" not in passport
    proof = harness.api.get(f"/analyses/{job['analysis_id']}/proof", "Proof")
    assert proof["anchor"]["status"] == "NOT_REQUESTED"
    assert proof["passport"]["status"] == "DRAFT"


def test_an_identical_repeat_is_unchanged_not_a_downgrade(harness):
    analysed(harness, POSITIVE, "repeat-key-000001")
    again = analysed(harness, POSITIVE, "repeat-key-000002")["result"]
    assert again["passport"]["previous_hash"] is not None
    assert again["passport"]["comparison_result"] == "REVISION_OF_SAME_SCOPE"
    assert again["passport"]["comparison_direction"] == "UNCHANGED"


def test_a_different_period_is_not_compared_at_all(harness):
    analysed(harness, POSITIVE, "nocmp-key-0000001")
    other = analysed(harness, SHORTER, "nocmp-key-0000002")["result"]
    assert other["passport"]["previous_hash"] is None
    assert other["passport"]["comparison_result"] == "INITIAL"


def test_the_comparison_scope_is_stated_on_every_passport(harness):
    result = analysed(harness, POSITIVE, "scope-key-0000001")["result"]
    assert result["passport"]["comparison_scope"] == (
        "geometry_hash+year_start+year_end+pool+method_version")


def test_a_downgrade_says_it_is_not_an_annulment(harness):
    from backend.app.v2.assemble import compare

    previous = {"content_hash": "0x" + "a" * 64, "q": 500}
    result, direction, previous_hash, note = compare(previous, "0x" + "b" * 64, {"q": 100})
    assert result == "REVISION_OF_SAME_SCOPE" and direction == "DECREASED"
    assert previous_hash == previous["content_hash"]
    assert "не аннулирование" in note


def test_an_absent_number_is_a_new_observation_not_a_downgrade(harness):
    from backend.app.v2.assemble import compare

    result, direction, _hash, note = compare({"content_hash": "0x" + "a" * 64, "q": 500},
                                             "0x" + "b" * 64, {"q": None})
    assert result == "NEW_OBSERVATION" and direction == "NOT_COMPARED"
    assert "не проводится" in note


def test_a_superseded_passport_is_recorded_in_the_journal(harness):
    analysed(harness, POSITIVE, "journal-key-00001")
    second = analysed(harness, POSITIVE, "journal-key-00002")
    kinds = [event["kind"] for event in harness.lens.store.events(second["analysis_id"])]
    assert "ANALYSIS_COMPLETED" in kinds
    assert "PASSPORT_SUPERSEDED" in kinds


def test_reading_an_old_analysis_does_not_change_it(harness):
    first = analysed(harness, POSITIVE, "readonly-key-0001")
    before = harness.api.get(f"/analyses/{first['analysis_id']}", "Analysis")
    analysed(harness, POSITIVE, "readonly-key-0002")
    after = harness.api.get(f"/analyses/{first['analysis_id']}", "Analysis")
    assert after["result"] == before["result"]
    assert after["job_state"] == "SUCCEEDED"
