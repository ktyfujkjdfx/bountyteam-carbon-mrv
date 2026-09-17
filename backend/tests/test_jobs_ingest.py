"""Durable verification jobs, one import pipeline for fixtures/bundles, deduplication and restart safety."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

from backend.app.config import REPO_ROOT
from backend.app.contracts import read_json
from backend.app.evidence import EvidenceRejected
from backend.app.ingest import import_evidence

from .conftest import AUTH, EXPECTED, FIXTURES, PLOT, Harness, fixture_evidence, write_scenarios


def _tampered_bundle(tmp_path, mutate_file=None, mutate_evidence=None):
    bundle = tmp_path / "bundle"
    shutil.copytree(FIXTURES, bundle)
    evidence = fixture_evidence("fire")
    if mutate_file:
        with (bundle / mutate_file).open("ab") as handle:
            handle.write(b"TAMPER")
    if mutate_evidence:
        mutate_evidence(evidence)
    path = bundle / "verification_fire.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return path


def test_verify_returns_202_queued_and_worker_completes(harness):
    accepted = harness.api.post(f"/plots/{PLOT}/verify", {"scenario_id": "post_fire"}, "issuer", "verify-202-key",
                                "JobAccepted")
    queued = harness.api.get(f"/jobs/{accepted['job_id']}", "Job")
    assert queued == {"job_id": accepted["job_id"], "state": "QUEUED", "verification_id": None, "error": None}
    harness.run(1)
    done = harness.api.get(f"/jobs/{accepted['job_id']}", "Job")
    assert done["state"] == "SUCCEEDED"
    verification = harness.api.get(f"/verifications/{done['verification_id']}", "Verification")
    assert (verification["decision"], verification["reason"]) == ("FREEZE_REQUESTED", "FIRE_REVERSAL")


def test_job_survives_restart_before_worker_runs(tmp_path):
    first = Harness(tmp_path)
    accepted = first.api.post(f"/plots/{PLOT}/verify", {"scenario_id": "baseline"}, "issuer", "verify-restart",
                              "JobAccepted")
    restarted = first.restart()
    restarted.run(1)
    assert restarted.api.get(f"/jobs/{accepted['job_id']}", "Job")["state"] == "SUCCEEDED"


def test_running_job_interrupted_by_crash_is_requeued(tmp_path):
    first = Harness(tmp_path)
    accepted = first.api.post(f"/plots/{PLOT}/verify", {"scenario_id": "baseline"}, "issuer", "verify-crash",
                              "JobAccepted")
    with first.ctx.db.transaction() as conn:  # crash while RUNNING
        conn.execute("UPDATE verification_jobs SET state='RUNNING' WHERE job_id=?", (accepted["job_id"],))
    restarted = first.restart()
    restarted.run(1)
    job = restarted.api.get(f"/jobs/{accepted['job_id']}", "Job")
    assert job["state"] == "SUCCEEDED" and restarted.count("verifications") == 1


def test_duplicate_evidence_creates_no_new_decision_or_events(harness):
    first = harness.verify("post_fire", key="verify-dup-1")
    second = harness.verify("post_fire", key="verify-dup-2")
    assert first["verification_id"] == second["verification_id"]
    assert harness.count("verifications") == 1
    assert harness.count("events", "kind='DECISION'") == 1
    assert harness.count("audit_log", "category='EVIDENCE_DUPLICATE'") == 1
    again = import_evidence(harness.ctx, fixture_evidence("fire"), FIXTURES, computation_mode="CACHED_REPLAY")
    assert (again.created, again.verification_id) == (False, first["verification_id"])


def test_import_bundle_cli_accepts_and_rejects(tmp_path):
    harness = Harness(tmp_path)
    env = {"BACKEND_DEMO_SESSION": "cli-demo-session-000000", "BACKEND_DB_PATH": str(harness.settings.db_path),
           "BACKEND_ARTIFACT_STORE": str(harness.settings.artifact_store),
           "BACKEND_MOCK_CHAIN_PATH": str(harness.settings.mock_chain_path), "PYTHONUTF8": "1"}
    command = [sys.executable, "-m", "backend.tools.import_bundle", "--bundle", str(FIXTURES),
               "--evidence", str(FIXTURES / "verification_no_change.json")]
    accepted = subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert accepted.returncode == 0, accepted.stderr
    record = json.loads(accepted.stdout)
    assert record["accepted"] and record["evidence_hash"] == EXPECTED["no_change"]["evidence_hash"]
    assert record["decision_hash"] == EXPECTED["no_change"]["decision_hash"]
    tampered = _tampered_bundle(tmp_path, mutate_file="assets/verification_fire/dnbr.tif")
    rejected = subprocess.run(command[:4] + [str(tampered.parent), "--evidence", str(tampered)], cwd=REPO_ROOT, env=env,
                              capture_output=True, text=True, timeout=120)
    assert rejected.returncode == 2
    assert json.loads(rejected.stderr)["error"]["code"] == "INVALID_EVIDENCE"


def test_corrupt_json_is_rejected_before_decision(harness):
    for payload in (b"{not-json", b'{"plot_id": "SYNTHETIC-PLOT-001", "x": NaN}', b"\xff\xfe"):
        try:
            import_evidence(harness.ctx, payload, FIXTURES, computation_mode="CACHED_REPLAY")
        except EvidenceRejected:
            pass
        else:
            raise AssertionError("corrupt JSON accepted")
    assert harness.count("verifications") == 0 and harness.count("events") == 0


def _job_fails(tmp_path, *, mutate_file=None, mutate_evidence=None, expected_message=None):
    evidence_path = _tampered_bundle(tmp_path, mutate_file, mutate_evidence)
    harness = Harness(tmp_path / "state", scenarios_path=write_scenarios(tmp_path, post_fire=str(evidence_path)))
    job = harness.verify("post_fire")
    assert job["state"] == "FAILED" and job["verification_id"] is None
    assert job["error"]["code"] == "INVALID_EVIDENCE"
    if expected_message:
        assert expected_message in job["error"]["message"]
    assert harness.count("verifications") == 0 and harness.count("operations") == 0
    assert harness.count("events", "kind='DECISION'") == 0
    return job


def test_tampered_raster_job_fails_without_decision(tmp_path):
    _job_fails(tmp_path, mutate_file="assets/verification_fire/dnbr.tif", expected_message="checksum")


def test_tampered_geojson_job_fails(tmp_path):
    _job_fails(tmp_path, mutate_file="assets/verification_fire/affected_area.geojson", expected_message="checksum")


def test_tampered_source_file_job_fails(tmp_path):
    _job_fails(tmp_path, mutate_file="assets/verification_fire/after_SCL.tif", expected_message="Source checksum")


def test_rs_sent_frozen_status_job_fails(tmp_path):
    _job_fails(tmp_path, mutate_evidence=lambda e: e.__setitem__("credit_status", "FROZEN"))


def test_mismatched_date_and_units_job_fails(tmp_path):
    _job_fails(tmp_path / "a", mutate_evidence=lambda e: e["observation"]["after"].__setitem__("acquired_at",
                                                                                               "2023-01-01T00:00:00Z"))
    _job_fails(tmp_path / "b", mutate_evidence=lambda e: e["metrics"].__setitem__("affected_area_ha", 1600))


def test_wrong_plot_geometry_job_fails(tmp_path):
    _job_fails(tmp_path, mutate_evidence=lambda e: e.__setitem__("plot_geometry_hash", "0x" + "3" * 64),
               expected_message="geometry")


def test_older_evidence_imported_later_never_becomes_latest(harness):
    fire = harness.verify("post_fire")
    baseline = harness.verify("baseline")  # observed 2024-07-10, earlier than post_fire 2024-08-01
    assert harness.api.get(f"/verifications/{fire['verification_id']}", "Verification")["is_latest"] is True
    assert harness.api.get(f"/verifications/{baseline['verification_id']}", "Verification")["is_latest"] is False
    plot = harness.api.get(f"/plots/{PLOT}", "Plot", actor="issuer")
    assert plot["latest_decision"] == "FREEZE_REQUESTED" and plot["can_issue"] is False
    blocked = harness.api.post(f"/plots/{PLOT}/issue", {"demo_authorization_id": AUTH}, "issuer", "issue-old-good",
                               "Error", status=409)
    assert blocked["error"]["code"] == "ACTION_NOT_ALLOWED"


def test_insufficient_quality_blocks_issue(harness):
    harness.verify("insufficient")
    error = harness.api.post(f"/plots/{PLOT}/issue", {"demo_authorization_id": AUTH}, "issuer", "issue-insufficient",
                             "Error", status=409)
    assert error["error"]["code"] == "ACTION_NOT_ALLOWED"
    assert harness.count("operations") == 0


def test_unregistered_plot_and_plot_mismatch_rejected(harness):
    evidence = fixture_evidence("fire")
    try:
        import_evidence(harness.ctx, evidence, FIXTURES, computation_mode="CACHED_REPLAY", expected_plot_id="OTHER-PLOT")
    except EvidenceRejected as exc:
        assert "does not match" in exc.message
    else:
        raise AssertionError("plot mismatch accepted")


def test_rs_cli_mode_marks_computed_and_uses_same_pipeline(tmp_path):
    fake_rs = tmp_path / "fake_rs.py"
    fake_rs.write_text(
        "import argparse, json, shutil, pathlib\n"
        "p = argparse.ArgumentParser(); p.add_argument('--request'); p.add_argument('--output'); a = p.parse_args()\n"
        f"src = pathlib.Path({str(FIXTURES)!r})\n"
        "out = pathlib.Path(a.output); shutil.copytree(src / 'assets', out / 'assets')\n"
        "shutil.copy(src / 'source-index.json', out / 'source-index.json')\n"
        "shutil.copy(src / 'verification_no_change.json', out / 'verification.json')\n", encoding="utf-8")
    harness = Harness(tmp_path / "state", rs_mode="rs_cli", rs_command=(sys.executable, str(fake_rs)))
    job = harness.verify("baseline")
    assert job["state"] == "SUCCEEDED", job
    verification = harness.api.get(f"/verifications/{job['verification_id']}", "Verification")
    assert verification["computation_mode"] == "COMPUTED"
    assert verification["evidence_hash"] == EXPECTED["no_change"]["evidence_hash"]


def test_rs_cli_failure_is_reported_not_hidden(tmp_path):
    failing = tmp_path / "fail_rs.py"
    failing.write_text("import sys; sys.stderr.write('cloud mask missing'); sys.exit(4)\n", encoding="utf-8")
    harness = Harness(tmp_path / "state", rs_mode="rs_cli", rs_command=(sys.executable, str(failing)))
    job = harness.verify("baseline")
    assert job["state"] == "FAILED" and job["error"]["details"]["exit_code"] == 4


def test_artifact_store_integrity_checked_on_serve(harness):
    job = harness.verify("baseline")
    link = harness.api.get(f"/verifications/{job['verification_id']}", "Verification")["artifacts"][0]
    with harness.ctx.db.reader() as conn:
        name = conn.execute("SELECT storage_name FROM artifacts WHERE artifact_id=?",
                            (link["artifact_id"],)).fetchone()[0]
    (harness.settings.artifact_store / name).write_bytes(b"corrupted on disk")
    response = harness.client.get(link["url"], headers=harness.api.headers())
    assert response.status_code == 503 and response.json()["error"]["code"] == "ARTIFACT_INTEGRITY_FAILED"


def test_plot_registration_refuses_geometry_change(harness):
    plot = read_json(FIXTURES / "plot.json")
    plot["geometry"]["coordinates"][0][1][0] += 0.001
    try:
        from backend.app.contracts import digest
        plot["geometry_hash"] = digest(plot["geometry"])
        from backend.app.ingest import register_plot
        register_plot(harness.ctx, plot)
    except EvidenceRejected as exc:
        assert "different geometry" in exc.message
    else:
        raise AssertionError("geometry version silently replaced")
