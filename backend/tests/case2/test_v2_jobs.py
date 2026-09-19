"""Jobs, idempotency, restart, concurrency and the files an analysis hands out."""
from __future__ import annotations

import sqlite3

import pytest

from .conftest import ACTOR, SESSION, Harness, assert_model

TVER = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024}
MORDOVIA = {"aoi_id": "RU_MORDOVIA_03", "year_start": 2020, "year_end": 2022}


# -- the queue ----------------------------------------------------------------------------
def test_a_new_analysis_starts_queued(harness):
    accepted = harness.api.post("/analyses", TVER, key="queued-key-0001")
    assert accepted["job_state"] == "QUEUED"
    assert accepted["status_url"] == f"/api/v2/analyses/{accepted['analysis_id']}"

    view = harness.api.get(accepted["status_url"].removeprefix("/api/v2"), "Analysis")
    assert view["job_state"] == "QUEUED"
    assert view["result"] is None and view["error"] is None
    assert view["report_url"] is None and view["proof_url"] is None


def test_polling_a_finished_job_carries_the_result_and_the_links(harness):
    job = harness.analyse(TVER, key="finished-key-001")
    assert job["job_state"] == "SUCCEEDED"
    assert job["result"] is not None
    assert job["report_url"] and job["proof_url"]
    assert job["attempts"] == 1


def test_job_state_and_calculation_status_are_separate_axes(harness):
    """A job that finds no data still SUCCEEDS; the missing number is in the result."""
    job = harness.analyse({"aoi_id": "RU_MORDOVIA_04", "year_start": 2019, "year_end": 2024},
                          key="axes-key-00001")
    assert job["job_state"] == "SUCCEEDED"
    assert job["error"] is None
    assert job["result"]["calculation_status"] == "UNAVAILABLE"
    assert job["result"]["units"]["q"] is None


# -- idempotency --------------------------------------------------------------------------
def test_the_same_key_and_body_replays_one_job(harness):
    first = harness.api.post("/analyses", TVER, key="idem-key-000001")
    second = harness.api.post("/analyses", TVER, key="idem-key-000001")
    assert first == second
    assert harness.counted("lens_analyses") == 1


def test_the_same_key_with_a_different_period_is_a_conflict(harness):
    harness.api.post("/analyses", TVER, key="conflict-key-01")
    response = harness.client.post(
        "/api/v2/analyses", json={**TVER, "year_end": 2022},
        headers=harness.api.headers(actor=ACTOR, key="conflict-key-01"))
    assert response.status_code == 409
    assert_model(response.json(), "Error")
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert harness.counted("lens_analyses") == 1


def test_the_same_key_with_a_different_claim_is_a_conflict(harness):
    """A claim is part of what was asked for, even though it changes no measurement."""
    harness.api.post("/analyses", {**TVER, "claimed_units": 100}, key="claim-key-00001")
    response = harness.client.post(
        "/api/v2/analyses", json={**TVER, "claimed_units": 200},
        headers=harness.api.headers(actor=ACTOR, key="claim-key-00001"))
    assert response.status_code == 409


def test_a_role_header_from_the_client_changes_nothing(harness):
    """The caller is derived from the session; a header the client sets is not read.

    If the role header still scoped idempotency, the same key sent twice with two
    different roles would create two analyses. It creates one.
    """
    first = harness.api.post("/analyses", TVER, key="actor-key-000001", actor="issuer")
    second = harness.api.post("/analyses", TVER, key="actor-key-000001", actor="buyer")
    assert first["analysis_id"] == second["analysis_id"]
    assert harness.counted("lens_analyses") == 1


def test_the_same_contour_by_name_and_by_polygon_hashes_the_same(harness):
    from backend.app.v2 import catalog

    by_name = harness.analyse(TVER, key="byname-key-0001")
    by_polygon = harness.analyse(
        {"geometry": catalog.area("RU_TVER_01").geometry, "year_start": 2019, "year_end": 2024},
        key="bypoly-key-0001")
    assert (by_name["result"]["identity"]["geometry_hash"]
            == by_polygon["result"]["identity"]["geometry_hash"])
    assert (by_name["result"]["passport"]["content_hash"]
            == by_polygon["result"]["passport"]["content_hash"])


def test_a_claim_does_not_change_the_scientific_input_hash(harness):
    plain = harness.analyse(TVER, key="nohash-key-00001")
    claimed = harness.analyse({**TVER, "claimed_units": 12345}, key="claimhash-key-01")
    assert (plain["result"]["identity"]["input_hash"]
            == claimed["result"]["identity"]["input_hash"])
    assert plain["result"]["units"]["q"] == claimed["result"]["units"]["q"]


# -- durability ---------------------------------------------------------------------------
def test_a_queued_job_survives_a_restart(harness):
    accepted = harness.api.post("/analyses", TVER, key="restart-key-0001")
    fresh = harness.restart()
    fresh.run()
    view = fresh.api.get(f"/analyses/{accepted['analysis_id']}", "Analysis")
    assert view["job_state"] == "SUCCEEDED"


def test_a_job_interrupted_mid_run_is_requeued_not_lost(harness):
    accepted = harness.api.post("/analyses", TVER, key="interrupt-key-01")
    claimed = harness.lens.store.claim(accepted["analysis_id"])
    assert claimed is not None
    assert harness.counted("lens_analyses", "job_state='RUNNING'") == 1

    fresh = harness.restart()
    fresh.run()
    view = fresh.api.get(f"/analyses/{accepted['analysis_id']}", "Analysis")
    assert view["job_state"] == "SUCCEEDED"
    assert view["attempts"] == 2


def test_a_published_result_is_readable_after_a_restart(harness):
    job = harness.analyse(TVER, key="reload-key-00001")
    fresh = harness.restart()
    again = fresh.api.get(f"/analyses/{job['analysis_id']}", "Analysis")
    assert again["result"] == job["result"]
    report = fresh.api.get(f"/analyses/{job['analysis_id']}/report", "Report")
    assert report["report_hash"] == job["result"]["passport"]["report_hash"]


def test_a_published_result_cannot_be_overwritten(harness):
    job = harness.analyse(TVER, key="immutable-key-01")
    with pytest.raises(sqlite3.IntegrityError):
        with harness.ctx.db.transaction() as conn:
            conn.execute("UPDATE lens_analyses SET units_q=1 WHERE analysis_id=?",
                         (job["analysis_id"],))


def test_a_late_worker_does_not_replace_a_published_passport(harness):
    """Two runs of one job: the first publication stands, the second is discarded."""
    from backend.app.v2.service import run_analysis

    accepted = harness.api.post("/analyses", TVER, key="late-key-0000001")
    harness.run()
    published = harness.api.get(f"/analyses/{accepted['analysis_id']}", "Analysis")

    with harness.ctx.db.transaction() as conn:
        conn.execute("UPDATE lens_analyses SET job_state='QUEUED' WHERE analysis_id=? "
                     "AND result_json IS NULL", (accepted["analysis_id"],))
    assert run_analysis(harness.lens, accepted["analysis_id"]) == "SKIPPED"
    again = harness.api.get(f"/analyses/{accepted['analysis_id']}", "Analysis")
    assert again["result"] == published["result"]


def test_a_second_worker_waits_for_the_lease(harness):
    from backend.app.v2.worker import LensWorker

    other = LensWorker(harness.lens, worker_id="second-lens-worker")
    assert harness.worker.tick() is True
    assert other.tick() is False


def test_the_lens_worker_lease_does_not_block_the_p0_worker(harness):
    from backend.app.worker import Worker

    assert harness.worker.tick() is True
    assert Worker(harness.ctx, worker_id="p0-worker").tick() is True


def test_two_requests_for_one_contour_are_two_analyses_with_one_answer(harness):
    first = harness.analyse(TVER, key="concurrent-key-1")
    second = harness.analyse(TVER, key="concurrent-key-2")
    assert first["analysis_id"] != second["analysis_id"]
    assert (first["result"]["passport"]["content_hash"]
            == second["result"]["passport"]["content_hash"])


def test_an_adapter_failure_fails_the_job_without_leaking_internals(harness, monkeypatch):
    def explode(request):
        raise RuntimeError("secret detail /Users/somebody/key.pem")

    monkeypatch.setattr(harness.lens.ports.raster, "analyse", explode, raising=False)
    job = harness.analyse(TVER, key="failure-key-00001")
    assert job["job_state"] == "FAILED"
    assert job["result"] is None
    assert job["error"]["code"] == "ANALYSIS_ERROR"
    assert "secret detail" not in str(job["error"])
    assert "/Users/" not in str(job["error"])


# -- artifacts ----------------------------------------------------------------------------
def test_an_analysis_serves_only_its_own_manifest_files(harness):
    job = harness.analyse(TVER, key="artifact-key-0001")
    artifacts = job["result"]["artifacts"]
    assert artifacts, "the analysis published no artifact to check"
    artifact = artifacts[0]
    assert artifact["url"] == (f"/api/v2/analyses/{job['analysis_id']}"
                               f"/artifacts/{artifact['artifact_id']}")
    response = harness.client.get(artifact["url"], headers={"X-Demo-Session": SESSION})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(artifact["media_type"])
    assert len(response.content) == artifact["size_bytes"]


def test_an_artifact_of_another_analysis_is_not_reachable(harness):
    first = harness.analyse(TVER, key="cross-key-000001")
    second = harness.analyse(MORDOVIA, key="cross-key-000002")
    stolen = first["result"]["artifacts"][0]["artifact_id"]
    harness.api.get(f"/analyses/{second['analysis_id']}/artifacts/{stolen}", "Error", status=404)


def test_an_unknown_artifact_is_404(harness):
    job = harness.analyse(TVER, key="unknown-art-key1")
    harness.api.get(f"/analyses/{job['analysis_id']}/artifacts/not-a-file", "Error", status=404)


def test_a_path_traversal_artifact_id_never_reaches_the_filesystem(harness):
    job = harness.analyse(TVER, key="traversal-key-01")
    for candidate in ("..%2f..%2fetc%2fpasswd", "....//etc/passwd"):
        response = harness.client.get(
            f"/api/v2/analyses/{job['analysis_id']}/artifacts/{candidate}",
            headers={"X-Demo-Session": SESSION})
        assert response.status_code in (404, 422), candidate
        assert b"root:" not in response.content


def test_a_tampered_artifact_is_refused_rather_than_served(harness):
    job = harness.analyse(TVER, key="tamper-key-00001")
    artifact = job["result"]["artifacts"][0]
    rows = harness.lens.store.artifact_rows(job["analysis_id"])
    path = harness.lens.store.artifact_root / rows[0]["storage_name"]
    path.write_bytes(path.read_bytes() + b"tampered")

    response = harness.client.get(artifact["url"], headers={"X-Demo-Session": SESSION})
    assert response.status_code == 503
    assert_model(response.json(), "Error")
    assert response.json()["error"]["code"] == "ARTIFACT_INTEGRITY_FAILED"


def test_a_missing_artifact_file_is_503_not_a_silent_empty_body(harness):
    job = harness.analyse(TVER, key="missing-key-00001")
    artifact = job["result"]["artifacts"][0]
    rows = harness.lens.store.artifact_rows(job["analysis_id"])
    (harness.lens.store.artifact_root / rows[0]["storage_name"]).unlink()

    response = harness.client.get(artifact["url"], headers={"X-Demo-Session": SESSION})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ARTIFACT_UNAVAILABLE"


def test_artifacts_publish_api_urls_and_never_filesystem_paths(harness):
    job = harness.analyse(TVER, key="nopath-key-00001")
    for artifact in job["result"]["artifacts"]:
        assert artifact["url"].startswith("/api/v2/analyses/")
        assert "/Users/" not in artifact["url"] and "\\" not in artifact["url"]
        assert artifact["sha256"].startswith("0x")


def test_the_lens_store_is_separate_from_the_p0_artifact_store(harness):
    harness.analyse(TVER, key="separate-key-0001")
    assert harness.counted("lens_artifacts") >= 1
    assert harness.counted("artifacts") == 0
