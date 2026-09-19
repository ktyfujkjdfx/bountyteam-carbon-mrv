"""Run the whole Carbon Lens pipeline once, for real, and refuse to pretend otherwise.

This exists because a green suite that only ever ran against replayed vectors tells you
that the plumbing is consistent with itself. It does not tell you that `rs.case2` and
`carbon` still fit the contract, and every integration defect found in this project so
far lived exactly there.

So the script does one thing and does it strictly: it builds the real ports, walks a
request from sign-in to a finalized passport, and checks the things that can only be
checked when both owning packages are present. If either is missing it does not
substitute anything. It says so and exits — with a failure where the pipeline is supposed
to be provable (`LIVE_REQUIRED=1`, which CI sets on `main`), and with a plain statement
elsewhere.

    python backend/tools/live_composition.py
"""
from __future__ import annotations

import os
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

PRECONDITION = 0
FAILURE = 1

AOI = "RU_TVER_01"
YEARS = (2019, 2024)
PASSWORD = "live-composition-password"
ACCOUNTS = {"live-owner": "PROJECT_OWNER", "live-verifier": "VERIFIER",
            "live-investor": "INVESTOR"}


def _say(message: str) -> None:
    print(message, flush=True)


def _check(condition: bool, description: str) -> None:
    if not condition:
        raise AssertionError(description)
    _say(f"  ok   {description}")


def _preconditions() -> list[str]:
    from backend.app.v2.adapters import missing_engines

    return list(missing_engines())


def run() -> int:
    missing = _preconditions()
    if missing:
        required = os.environ.get("LIVE_REQUIRED", "0") not in ("0", "false", "")
        message = ("the real engines are not importable on this ref: "
                   + ", ".join(missing))
        if required:
            _say(f"FAIL  {message}")
            _say("      This job proves the pipeline runs for real. It is not allowed to "
                 "fall back to fixtures, so there is nothing for it to do.")
            return FAILURE
        _say(f"NOT RUN  {message}")
        _say("         Nothing was substituted. Merge the owning packages and this job "
             "becomes meaningful without a line changing here.")
        return PRECONDITION

    from fastapi.testclient import TestClient

    from backend.app.config import Settings
    from backend.app.context import create_context
    from backend.app.main import create_app
    from backend.app.v2 import auth
    from backend.app.v2.api import compose, create_lens_app
    from backend.app.v2.service import create_lens_context

    work = Path(tempfile.mkdtemp(prefix="lens-live-"))
    settings = Settings(
        demo_session="live-composition-session",
        db_path=work / "backend.sqlite", artifact_store=work / "artifacts",
        mock_chain_path=work / "chain.sqlite", rs_work_dir=work / "rs",
        lens_artifact_store=work / "lens-artifacts", lens_work_dir=work / "lens-runs",
        lens_engine_mode="REAL", lens_require_real=True).validate()

    ctx = create_context(settings)
    for username, role in ACCOUNTS.items():
        auth.create_user(ctx, username=username, password=PASSWORD, role=role)

    lens = create_lens_context(ctx)
    _say(f"adapters: {lens.ports.raster.name} | {lens.ports.carbon.name}")
    _check(lens.ports.raster.name.startswith("rs.case2"),
           "the raster port is the real raster core")
    _check("carbon/" in lens.ports.carbon.name,
           "the carbon port is the real carbon engine")

    client = TestClient(compose(create_app(ctx=ctx), create_lens_app(lens)))
    tokens = {}
    for username, role in ACCOUNTS.items():
        response = client.post("/api/v2/auth/login",
                               json={"username": username, "password": PASSWORD})
        _check(response.status_code == 200, f"{username} can sign in")
        tokens[role] = response.json()["token"]

    def headers(role: str, **extra) -> dict:
        return {"Authorization": "Bearer " + tokens[role], **extra}

    _say("\nengine mode as the catalog reports it")
    catalog = client.get("/api/v2/catalog", headers=headers("VERIFIER")).json()
    _check(catalog["engine_mode"] == "REAL", "the catalog says REAL, not FIXTURE")

    _say("\nowner submits a request")
    created = client.post("/api/v2/requests",
                          json={"aoi_id": AOI, "year_start": YEARS[0],
                                "year_end": YEARS[1], "claimed_units": 500},
                          headers=headers("PROJECT_OWNER"))
    _check(created.status_code == 201, "the request is created as a draft")
    request_id = created.json()["request_id"]
    _check(client.post(f"/api/v2/requests/{request_id}/submit",
                       headers=headers("PROJECT_OWNER")).status_code == 200,
           "the owner submits it")

    _say("\nverifier runs the calculation over the supplied rasters")
    started = client.post(f"/api/v2/requests/{request_id}/analysis",
                          headers=headers("VERIFIER",
                                          **{"Idempotency-Key": "live-key-00000001"}))
    _check(started.status_code == 202, "the analysis is queued")

    from backend.app.v2.worker import LensWorker

    worker = LensWorker(lens, worker_id="live-composition")
    _check(worker.tick(), "the worker picked the job up")

    analysis_url = client.get(f"/api/v2/requests/{request_id}",
                              headers=headers("VERIFIER")).json()["analysis_url"]
    job = client.get(analysis_url, headers=headers("VERIFIER")).json()
    _check(job["job_state"] == "SUCCEEDED", f"the job succeeded ({job['job_state']})")

    result = job["result"]
    units = result["units"]
    _say(f"\n  q = {units['q']}  zero_reason={units['zero_reason']} "
         f"unavailable_reason={units['unavailable_reason']}")
    _say(f"  origin = {result['run']['dataset_origin']}  zones = {len(result['zones'])}  "
         f"artifacts = {len(result['artifacts'])}")

    _check(result["run"]["dataset_origin"] == "COMPUTED_FROM_SUPPLIED_DATA",
           "the numbers were computed from the supplied data")
    _check(result["fixture"] is None, "no fixture label, because nothing was replayed")
    encoded = json.dumps(result, ensure_ascii=False)
    _check("STUB_FIXTURE" not in encoded and "PROVISIONAL_INPUT" not in encoded,
           "the production response contains no fixture or provisional marker")
    _check(units["q"] != 395,
           "the real result was not replaced by the DOC_EXAMPLE value")
    _check(units["status"] in ("AVAILABLE", "UNAVAILABLE"),
           "the calculation reports a status either way")
    # q is deliberately not asserted to be positive. Every supplied plot comes out at
    # zero, and a job that demanded otherwise would be demanding a different answer.

    _say("\nsources and artifacts")
    source_ids = {item["source_id"] for item in result["sources"]}
    _check("CCI_V7" in source_ids,
           "the biomass product is credited, as its licence requires")
    blocking = [item for item in result["evidence"]["warnings"]
                if item["severity"] == "BLOCKING"]
    _check(not [item for item in blocking
                if item["code"] == "SOURCE_ATTRIBUTION_INCOMPLETE"],
           "every product used is credited")
    _check(not [item for item in blocking if item["code"] == "EPROJ_DISAGREEMENT"],
           "the raster core and the carbon engine agree on Eproj")

    for artifact in result["artifacts"]:
        served = client.get(artifact["url"], headers=headers("VERIFIER"))
        _check(served.status_code == 200,
               f"artifact {artifact['role']} is served ({served.status_code})")
    if result["zones"]:
        _check(all(zone["artifact_ref"] for zone in result["zones"]),
               "every published zone points at the file holding its geometry")

    _say("\nthe passport is reproducible")
    repeat = client.post("/api/v2/analyses",
                         json={"aoi_id": AOI, "year_start": YEARS[0],
                               "year_end": YEARS[1], "claimed_units": 500},
                         headers=headers("VERIFIER",
                                         **{"Idempotency-Key": "live-key-00000002"}))
    _check(repeat.status_code == 202, "a second analysis of the same contour is accepted")
    worker.tick()
    second = client.get(f"/api/v2/analyses/{repeat.json()['analysis_id']}",
                        headers=headers("VERIFIER")).json()["result"]
    _check(second["passport"]["content_hash"] == result["passport"]["content_hash"],
           "the same request on the same data produces the same content hash")
    _check(second["passport"]["comparison_result"] == "REVISION_OF_SAME_SCOPE",
           "the repeat is recorded as a revision of the same scope")

    _say("\nverifier finalizes; the numbers do not move")
    finalized = client.post(f"/api/v2/requests/{request_id}/finalize",
                            headers=headers("VERIFIER"))
    _check(finalized.status_code == 200, "the verifier finalizes the passport")
    after = client.get(analysis_url, headers=headers("VERIFIER")).json()["result"]
    _check(after["units"] == result["units"], "finalizing changed no number")
    _check(after["passport"]["status"] == "FINALIZED", "the passport status moved")
    _check(after["passport"]["content_hash"] == result["passport"]["content_hash"],
           "and the content hash did not")

    _say("\nroles are enforced by the server")
    _check(client.post("/api/v2/requests",
                       json={"aoi_id": AOI, "year_start": YEARS[0],
                             "year_end": YEARS[1]},
                       headers=headers("INVESTOR")).status_code == 403,
           "an investor cannot open a request")
    _check(client.post(f"/api/v2/requests/{request_id}/finalize",
                       headers=headers("PROJECT_OWNER")).status_code in (403, 409),
           "an owner cannot finalize their own verification")
    _check(client.get(analysis_url, headers=headers("INVESTOR")).status_code == 200,
           "an investor can read it once it is finalized")

    _say("\nthe report is complete and self-contained")
    html = client.get(f"{analysis_url}/report?format=html",
                      headers=headers("VERIFIER")).text
    _check("<script" not in html.lower() and "http://" not in html,
           "the report loads nothing from a network")
    _check(result["passport"]["content_hash"] in html, "the report carries its own hash")
    _check(tokens["VERIFIER"] not in html, "the report carries no session token")

    _say("\nthe demonstration lifecycle refuses a zero result")
    issued = client.post(f"/api/v2/requests/{request_id}/demo/issue",
                         headers=headers("PROJECT_OWNER"))
    if units["q"]:
        _check(issued.status_code == 201, "a positive q may be demonstrated")
    else:
        _check(issued.status_code == 409
               and issued.json()["error"]["code"] == "NO_POSITIVE_UNITS",
               "a zero result cannot be issued, which is the normal case here")

    _say("\nLIVE COMPOSITION OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except AssertionError as failure:
        _say(f"FAIL  {failure}")
        raise SystemExit(FAILURE) from None
