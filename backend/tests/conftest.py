from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import REPO_ROOT, Settings
from backend.app.context import create_context
from backend.app.contracts import api_validator, read_json, schema_errors
from backend.app.ingest import register_plot
from backend.app.main import create_app
from backend.app.worker import Worker

SESSION = "test-demo-session-000000"
PLOT = "SYNTHETIC-PLOT-001"
AUTH = "SYNTHETIC-AUTH-001"
FIXTURES = REPO_ROOT / "fixtures"
EXPECTED = read_json(FIXTURES / "expected_results.json")


def fixture_evidence(label: str) -> dict:
    return read_json(FIXTURES / f"verification_{label}.json")


def assert_model(body, model: str):
    errors = schema_errors(api_validator(model), body)
    assert not errors, f"{model} contract violation: {errors}"
    return body


def make_settings(tmp_path: Path, **overrides) -> Settings:
    base = Settings(demo_session=SESSION, db_path=tmp_path / "backend.sqlite", artifact_store=tmp_path / "artifacts",
                    mock_chain_path=tmp_path / "mock-chain.sqlite", rs_work_dir=tmp_path / "rs-runs",
                    worker_poll_seconds=0.05)
    return replace(base, **overrides).validate()


class Api:
    """Thin HTTP helper that validates every JSON response against the frozen API models."""

    def __init__(self, client: TestClient):
        self.client = client

    def headers(self, actor: str | None = None, key: str | None = None, session: str | None = SESSION) -> dict:
        headers = {}
        if session is not None:
            headers["X-Demo-Session"] = session
        if actor:
            headers["X-Demo-Actor"] = actor
        if key:
            headers["Idempotency-Key"] = key
        return headers

    def get(self, path: str, model: str | None, actor: str | None = None, status: int = 200, **kwargs):
        response = self.client.get("/api/v1" + path, headers=self.headers(actor), **kwargs)
        assert response.status_code == status, response.text
        body = response.json()
        assert_model(body, model if status == 200 else "Error")
        return body

    def post(self, path: str, body: dict, actor: str, key: str, model: str, status: int = 202):
        response = self.client.post("/api/v1" + path, json=body, headers=self.headers(actor, key))
        assert response.status_code == status, response.text
        payload = response.json()
        assert_model(payload, model if status == 202 else "Error")
        return payload


class Harness:
    def __init__(self, tmp_path: Path, **overrides):
        self.tmp_path = tmp_path
        self.settings = make_settings(tmp_path, **overrides)
        self.ctx = create_context(self.settings)
        register_plot(self.ctx, read_json(FIXTURES / "plot.json"))
        self.app = create_app(ctx=self.ctx)
        self.client = TestClient(self.app)
        self.api = Api(self.client)
        self.worker = Worker(self.ctx, worker_id="test-worker")

    @property
    def chain(self):
        return self.ctx.chain

    def restart(self) -> "Harness":
        """Simulate a process restart: new context/app/worker over the same DB and mock chain files."""
        fresh = Harness.__new__(Harness)
        fresh.tmp_path = self.tmp_path
        fresh.settings = self.settings
        fresh.ctx = create_context(self.settings)
        fresh.app = create_app(ctx=fresh.ctx)
        fresh.client = TestClient(fresh.app)
        fresh.api = Api(fresh.client)
        fresh.worker = Worker(fresh.ctx, worker_id="test-worker")
        return fresh

    def run(self, ticks: int = 3) -> None:
        for _ in range(ticks):
            assert self.worker.tick()

    def verify(self, scenario: str, key: str | None = None) -> dict:
        accepted = self.api.post(f"/plots/{PLOT}/verify", {"scenario_id": scenario}, "issuer",
                                 key or f"verify-{scenario}-key", "JobAccepted")
        self.run()
        return self.api.get(f"/jobs/{accepted['job_id']}", "Job")

    def issue(self, key: str = "issue-key-0001") -> dict:
        accepted = self.api.post(f"/plots/{PLOT}/issue", {"demo_authorization_id": AUTH}, "issuer", key,
                                 "OperationAccepted")
        self.run()
        return self.api.get(f"/operations/{accepted['operation_id']}", "Operation")

    def operations(self, kind: str | None = None) -> list:
        with self.ctx.db.reader() as conn:
            sql = "SELECT * FROM operations" + (" WHERE kind=?" if kind else "") + " ORDER BY created_at, rowid"
            return conn.execute(sql, (kind,) if kind else ()).fetchall()

    def count(self, table: str, where: str = "1=1", params: tuple = ()) -> int:
        with self.ctx.db.reader() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]


@pytest.fixture
def harness(tmp_path) -> Harness:
    return Harness(tmp_path)


@pytest.fixture
def issued(harness) -> tuple[Harness, str]:
    """Baseline NO_RESTRICTION verification + CONFIRMED issuance; returns (harness, batch_id)."""
    job = harness.verify("baseline")
    assert job["state"] == "SUCCEEDED"
    op = harness.issue()
    assert op["transaction_state"] == "CONFIRMED", op
    return harness, op["batch_id"]


def write_scenarios(tmp_path: Path, **scenario_fixture: str) -> Path:
    """Scenario manifest pointing scenarios at alternative (e.g. tampered) evidence files."""
    config = read_json(REPO_ROOT / "config" / "scenarios.json")
    for scenario, fixture in scenario_fixture.items():
        config["scenarios"][scenario]["fixture"] = fixture
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path
