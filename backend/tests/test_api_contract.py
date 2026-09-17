"""HTTP surface == frozen OpenAPI: routes, headers, auth, errors, idempotency, response models."""
from __future__ import annotations

import sqlite3
import uuid

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.app.config import REPO_ROOT
from backend.app.contracts import openapi_document, sha256_hex
from backend.app.main import create_app

from .conftest import AUTH, EXPECTED, FIXTURES, PLOT, SESSION, Harness, assert_model, make_settings


def test_routes_exactly_match_frozen_openapi(harness):
    from backend.app import main
    served = {(route.path.removeprefix("/api/v1"), method.lower())
              for api_router in (main.public, main.router) for route in api_router.routes
              if isinstance(route, APIRoute) for method in route.methods}
    specified = {(path, method) for path, item in openapi_document()["paths"].items() for method in item}
    assert served == specified
    assert not any("freeze" in path for path, _ in served)
    # Only documentation routes exist outside /api/v1.
    top_level = {route.path for route in harness.app.routes if getattr(route, "path", None)}
    assert top_level == {"/openapi.json", "/docs", "/docs/oauth2-redirect"}


def test_openapi_json_is_the_frozen_contract(harness):
    response = harness.client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json() == openapi_document()


def test_no_public_signing_state_anywhere():
    operation = openapi_document()["components"]["schemas"]["Operation"]
    assert operation["properties"]["transaction_state"]["enum"] == ["QUEUED", "SUBMITTED", "CONFIRMED", "FAILED"]
    for source in (REPO_ROOT / "backend" / "app").rglob("*.py"):
        assert "SIGNING" not in source.read_text(encoding="utf-8"), source


def test_db_rejects_non_contract_transaction_state(harness):
    with pytest.raises(sqlite3.IntegrityError):
        with harness.ctx.db.transaction() as conn:
            conn.execute("INSERT INTO operations (operation_id, kind, transaction_state, plot_id, deployment_id, "
                         "sender_role, sender_address, intent_json, created_at, updated_at) VALUES "
                         "(?, 'FREEZE', 'SIGNING', ?, 'd', 'oracle', '0x0', '{}', 'now', 'now')",
                         (str(uuid.uuid4()), PLOT))


def test_health_is_public_and_matches_model(harness):
    body = harness.client.get("/api/v1/health").json()
    assert_model(body, "Health")
    assert body["mode"] == "CONTRACT_FIXTURE" and body["db"] == "UP" and body["chain"] == "UP"
    harness.worker.tick()
    assert harness.client.get("/api/v1/health").json()["worker"] == "UP"


def test_health_reports_chain_down_honestly(harness):
    harness.chain.set_controls(available=False)
    body = assert_model(harness.client.get("/api/v1/health").json(), "Health")
    assert body["chain"] == "DOWN" and body["deployment_id"] is None


@pytest.mark.parametrize("session", [None, "wrong-session-value-000"])
def test_missing_or_wrong_session_is_401_envelope(harness, session):
    response = harness.client.get("/api/v1/plots", headers=harness.api.headers(session=session))
    assert response.status_code == 401
    body = assert_model(response.json(), "Error")
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert SESSION not in response.text


def test_post_requires_idempotency_key_and_actor(harness):
    url = f"/api/v1/plots/{PLOT}/verify"
    missing_key = harness.client.post(url, json={"scenario_id": "baseline"}, headers=harness.api.headers("issuer"))
    assert missing_key.status_code == 422 and missing_key.json()["error"]["code"] == "VALIDATION_ERROR"
    short_key = harness.client.post(url, json={"scenario_id": "baseline"}, headers=harness.api.headers("issuer", "short"))
    assert short_key.status_code == 422
    no_actor = harness.client.post(url, json={"scenario_id": "baseline"}, headers=harness.api.headers(key="key-000001"))
    assert no_actor.status_code == 422
    bad_actor = harness.client.post(url, json={"scenario_id": "baseline"},
                                    headers={**harness.api.headers(key="key-000001"), "X-Demo-Actor": "oracle"})
    assert bad_actor.status_code == 422


def test_role_enforcement_is_403(harness):
    body = harness.api.post(f"/plots/{PLOT}/verify", {"scenario_id": "baseline"}, "buyer", "verify-by-buyer",
                            "Error", status=403)
    assert body["error"]["code"] == "FORBIDDEN"
    harness.verify("baseline")
    harness.api.post(f"/plots/{PLOT}/issue", {"demo_authorization_id": AUTH}, "recipient", "issue-by-recipient",
                     "Error", status=403)


@pytest.mark.parametrize("body", [{"scenario_id": "freeze_now"}, {"scenario_id": "baseline", "extra": 1}, {},
                                  {"scenario_id": 7}])
def test_verify_request_schema_error_matches_frozen_invalid_json_example(harness, body):
    error = harness.api.post(f"/plots/{PLOT}/verify", body, "issuer", "bad-body-key", "Error", status=422)
    frozen = _frozen_invalid_json_example()["body"]["error"]
    assert (error["error"]["code"], error["error"]["message"]) == (frozen["code"], frozen["message"])
    assert error["error"]["details"]["category"] == "REQUEST_SCHEMA"
    assert harness.count("verification_jobs") == 0


def _frozen_invalid_json_example() -> dict:
    from backend.app.contracts import read_json
    case = next(c for c in read_json(FIXTURES / "http_examples.json")["cases"] if c["name"] == "invalid_json")
    assert (case["method"], case["path"], case["status"]) == ("POST", "/plots/{plot_id}/verify", 422)
    return case


def test_invalid_json_body_on_verify_matches_frozen_example(harness):
    response = harness.client.post(f"/api/v1/plots/{PLOT}/verify", content=b"{not json",
                                   headers={**harness.api.headers("issuer", "bad-json-key"),
                                            "Content-Type": "application/json"})
    assert response.status_code == 422
    body = assert_model(response.json(), "Error")
    frozen = _frozen_invalid_json_example()["body"]["error"]
    assert (body["error"]["code"], body["error"]["message"]) == (frozen["code"], frozen["message"])
    assert body["error"]["details"]["category"] == "REQUEST_SCHEMA"


def test_non_body_and_other_route_request_errors_stay_validation_error(harness):
    headers = harness.api.headers("issuer", "missing-body-key")
    bad_path = harness.client.post("/api/v1/plots/bad%20id/verify", json={"scenario_id": "baseline"}, headers=headers)
    assert bad_path.status_code == 422 and bad_path.json()["error"]["code"] == "VALIDATION_ERROR"
    harness.verify("baseline")
    issue = harness.api.post(f"/plots/{PLOT}/issue", {"demo_authorization_id": 5}, "issuer", "bad-issue-body", "Error",
                             status=422)
    assert issue["error"]["code"] == "VALIDATION_ERROR" and issue["error"]["details"]["category"] == "REQUEST_SCHEMA"


@pytest.mark.parametrize("path", ["/jobs/not-a-uuid", "/operations/1", "/verifications/x/proof",
                                  "/events?plot_id=../../etc", "/plots/..%2Fsecret"])
def test_invalid_path_and_query_params_are_422_or_404(harness, path):
    response = harness.client.get("/api/v1" + path, headers=harness.api.headers("issuer"))
    assert response.status_code in (404, 422)
    assert_model(response.json(), "Error")


def test_unknown_resources_are_404_envelopes(harness):
    for path in [f"/jobs/{uuid.uuid4()}", f"/verifications/{uuid.uuid4()}", f"/operations/{uuid.uuid4()}",
                 "/plots/UNKNOWN-PLOT", "/artifacts/unknown-artifact", "/plots/UNKNOWN-PLOT/history"]:
        harness.api.get(path, None, actor="issuer", status=404)
    response = harness.client.post("/api/v1/freeze", json={}, headers=harness.api.headers("issuer", "freeze-attempt"))
    assert response.status_code == 404
    assert_model(response.json(), "Error")


def test_verify_idempotency_same_body_same_job_different_body_409(harness):
    first = harness.api.post(f"/plots/{PLOT}/verify", {"scenario_id": "baseline"}, "issuer", "verify-idem-1",
                             "JobAccepted")
    again = harness.api.post(f"/plots/{PLOT}/verify", {"scenario_id": "baseline"}, "issuer", "verify-idem-1",
                             "JobAccepted")
    assert first == again
    assert harness.count("verification_jobs") == 1
    conflict = harness.api.post(f"/plots/{PLOT}/verify", {"scenario_id": "post_fire"}, "issuer", "verify-idem-1",
                                "Error", status=409)
    assert conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert harness.count("verification_jobs") == 1


def test_read_models_after_three_scenarios(harness):
    jobs = {s: harness.verify(s) for s in ("baseline", "post_fire", "insufficient")}
    assert all(job["state"] == "SUCCEEDED" and job["error"] is None for job in jobs.values())
    expected_label = {"baseline": "no_change", "post_fire": "fire", "insufficient": "insufficient"}
    for scenario, job in jobs.items():
        label = expected_label[scenario]
        body = harness.api.get(f"/verifications/{job['verification_id']}", "Verification")
        assert body["evidence_hash"] == EXPECTED[label]["evidence_hash"]
        assert body["decision_hash"] == EXPECTED[label]["decision_hash"]
        assert body["decision_record"] == EXPECTED[label]["decision_record"]
        assert (body["observation_mode"], body["computation_mode"]) == ("HISTORICAL_REPLAY", "CACHED_REPLAY")
        assert body["evidence"]["dataset_kind"] == "SYNTHETIC"
        proof = harness.api.get(f"/verifications/{job['verification_id']}/proof", "Proof")
        assert proof["integrity_ok"] and proof["recomputed_hash"] == proof["evidence_hash"]
        assert proof["anchors"] == []  # nothing issued/frozen yet: no fabricated anchor
        canonical = harness.client.get(proof["canonical_url"], headers=harness.api.headers())
        assert canonical.status_code == 200 and canonical.headers["content-type"].startswith("application/json")
        assert canonical.content == (FIXTURES / f"verification_{label}.canonical.json").read_bytes()
        assert sha256_hex(canonical.content) == body["evidence_hash"]
        assert_model(canonical.json(), "VerificationEvidence")
        for link in body["artifacts"]:
            served = harness.client.get(link["url"], headers=harness.api.headers())
            assert served.status_code == 200
            assert served.headers["content-type"].startswith(link["media_type"])
            assert sha256_hex(served.content) == link["sha256"]
    history = harness.api.get(f"/plots/{PLOT}/history", "History")
    assert [item["observed_at"] for item in history["items"]] == sorted(i["observed_at"] for i in history["items"])
    assert sum(item["is_latest"] for item in history["items"]) == 1
    plots = harness.api.get("/plots", "Plots")
    assert plots["items"][0]["plot_id"] == PLOT
    plot = harness.api.get(f"/plots/{PLOT}", "Plot", actor="issuer")
    assert plot["geometry_hash"] == "0xec548e113e459a13ce79a1eb08bdf02291148a14676e745be47f2c7696fb1bb9"
    # Latest evidence (insufficient, observed 2024-08-01 after post_fire) blocks all financial actions.
    assert plot["latest_decision"] == "REVIEW_REQUIRED"
    assert plot["can_issue"] is False and plot["action_block_reason"]
    assert harness.api.get(f"/plots/{PLOT}/credits", "Credits", actor="buyer") == {"items": []}
    events = harness.api.get(f"/events?plot_id={PLOT}&limit=2", "Events")
    assert len(events["items"]) == 2 and events["next_cursor"]
    rest = harness.api.get(f"/events?plot_id={PLOT}&limit=100&cursor={events['next_cursor']}", "Events")
    assert len(rest["items"]) == 4 and rest["next_cursor"] is None
    assert {e["kind"] for e in events["items"] + rest["items"]} == {"VERIFICATION", "DECISION"}


def test_cors_is_closed_by_default_and_explicit_when_configured(tmp_path):
    closed = Harness(tmp_path / "closed")
    response = closed.client.options("/api/v1/plots", headers={"Origin": "http://evil.example",
                                                               "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in response.headers
    opened = Harness(tmp_path / "open", cors_origins=("http://127.0.0.1:5173",))
    allowed = opened.client.options("/api/v1/plots", headers={"Origin": "http://127.0.0.1:5173",
                                                              "Access-Control-Request-Method": "GET"})
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    denied = opened.client.get("/api/v1/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in denied.headers


def test_security_headers_present(harness):
    response = harness.client.get("/api/v1/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"


def test_unexpected_errors_do_not_leak_details(tmp_path, monkeypatch):
    harness = Harness(tmp_path)
    from backend.app import views

    def boom(ctx):
        raise RuntimeError("secret-internal-detail /Users/private/path")
    monkeypatch.setattr(views, "plots", boom)
    client = TestClient(create_app(ctx=harness.ctx), raise_server_exceptions=False)
    response = client.get("/api/v1/plots", headers=harness.api.headers())
    assert response.status_code == 503
    assert_model(response.json(), "Error")
    assert "secret-internal-detail" not in response.text and "Traceback" not in response.text


def test_settings_refuse_missing_session_and_mock_in_local_demo(tmp_path):
    from backend.app.config import ConfigError
    with pytest.raises(ConfigError):
        make_settings(tmp_path, demo_session="")
    with pytest.raises(ConfigError):
        make_settings(tmp_path, mode="LOCAL_DEMO", chain_adapter="mock")
