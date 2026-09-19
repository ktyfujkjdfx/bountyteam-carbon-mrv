"""Harness for the Carbon Lens API: one composed app, one store, one worker under control.

The worker is driven by hand with `run()` rather than by a background thread, so every test
knows exactly how many passes happened. `restart()` rebuilds the context, the app and the
worker over the same files, which is the only honest way to test that nothing important
lived in a process.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.context import create_context
from backend.app.main import create_app
from backend.app.v2 import auth as auth_module
from backend.app.v2 import catalog
from backend.app.v2.api import compose, create_lens_app
from backend.app.v2.contracts import api_validator, schema_errors
from backend.app.v2.service import create_lens_context
from backend.app.v2.worker import LensWorker

SESSION = "test-demo-session-000000"
# There is no client-supplied role header any more: the role is server state, read from
# the session row. This value is only used to prove that such a header changes nothing.
ACTOR = "issuer"

# The three demo sign-ins the suite creates. Passwords exist only in this file and in the
# database as scrypt hashes; nothing here resembles a deployment secret.
PASSWORD = "test-password-1234"
# The production scrypt cost is deliberately expensive, which makes a suite that signs in
# for every test unbearably slow. The cost is lowered here and nowhere else;
# `test_the_production_password_cost_is_not_what_the_suite_runs_at` pins the real one.
auth_module.SCRYPT_N = 1 << 8
ACCOUNTS = {"owner": "PROJECT_OWNER", "verifier": "VERIFIER", "investor": "INVESTOR"}
DEFAULT_ROLE = "VERIFIER"
TVER = "RU_TVER_01"
MORDOVIA = "RU_MORDOVIA_03"


def assert_model(body, model: str):
    errors = schema_errors(api_validator(model), body)
    assert not errors, f"{model} contract violation: {errors}"
    return body


def _missing_engines() -> tuple:
    from backend.app.v2.adapters import missing_engines

    return missing_engines()


def engine_override() -> dict:
    """How this suite gets an engine before `carbon/` and `rs/case2/` are merged.

    The real packages win whenever they are importable, so once they land the suite
    exercises the production path without a line changing here. Until then the raster
    side replays labelled vectors and the carbon side is handed `reference_engine`, a
    test double that lives in this directory precisely so that nothing under
    `backend/app/` can reach a second implementation of the formulas.
    """
    from backend.app.v2.adapters import FIXTURE, missing_engines

    if not missing_engines():
        return {}
    from . import reference_engine

    return {"engine_mode": FIXTURE, "carbon_module_override": reference_engine}


def make_settings(tmp_path: Path, **overrides) -> Settings:
    base = Settings(demo_session=SESSION, db_path=tmp_path / "backend.sqlite",
                    lens_engine_mode=("FIXTURE" if _missing_engines() else "REAL"),
                    artifact_store=tmp_path / "artifacts",
                    mock_chain_path=tmp_path / "mock-chain.sqlite",
                    rs_work_dir=tmp_path / "rs-runs",
                    lens_artifact_store=tmp_path / "lens-artifacts",
                    lens_work_dir=tmp_path / "lens-runs",
                    worker_poll_seconds=0.05)
    return replace(base, **overrides).validate()


class LensApi:
    """Every JSON response is checked against the published model before a test sees it."""

    def __init__(self, client: TestClient, tokens: dict[str, str] | None = None):
        self.client = client
        self.tokens = tokens or {}

    def headers(self, *, actor: str | None = None, key: str | None = None,
                session: str | None = SESSION, role: str | None = None) -> dict:
        """Authorization from a real sign-in. `session=None` means send none at all."""
        headers = {}
        if session is not None:
            headers["Authorization"] = "Bearer " + self.tokens[role or DEFAULT_ROLE]
        if actor:
            # Deliberately still sent by some tests: an ignored header must stay ignored.
            headers["X-Demo-Actor"] = actor
        if key:
            headers["Idempotency-Key"] = key
        return headers

    def get(self, path: str, model: str | None = None, *, status: int = 200,
            session: str | None = SESSION, role: str | None = None, **kwargs):
        response = self.client.get(
            "/api/v2" + path, headers=self.headers(session=session, role=role), **kwargs)
        assert response.status_code == status, response.text
        if model is None:
            return response
        body = response.json()
        assert_model(body, model if status == 200 else "Error")
        return body

    def post(self, path: str, body: dict, *, actor: str | None = None, key: str,
             status: int = 202, session: str | None = SESSION, role: str | None = None,
             model: str = "AnalysisAccepted"):
        response = self.client.post(
            "/api/v2" + path, json=body,
            headers=self.headers(actor=actor, key=key, session=session, role=role))
        assert response.status_code == status, response.text
        payload = response.json()
        assert_model(payload, model if status == 202 else "Error")
        return payload


class Harness:
    def __init__(self, tmp_path: Path, **overrides):
        self.tmp_path = tmp_path
        self.settings = make_settings(tmp_path, **overrides)
        self._build()

    def _build(self) -> None:
        self.ctx = create_context(self.settings)
        self.lens = create_lens_context(self.ctx, **engine_override())
        self.app = compose(create_app(ctx=self.ctx), create_lens_app(self.lens))
        self.client = TestClient(self.app)
        self.users = self._accounts()
        self.api = LensApi(self.client, self._sign_in())
        self.worker = LensWorker(self.lens, worker_id="test-lens-worker")

    def _accounts(self) -> dict:
        """One account per role, created once and reused across a restart."""
        from backend.app.v2 import auth

        existing = {row["role"]: row for row in auth.audit_trail(self.ctx, limit=0)}
        del existing
        out = {}
        with self.ctx.db.reader() as conn:
            known = {row["role"]: dict(row) for row in conn.execute(
                "SELECT user_id, username, display_name, role FROM lens_users").fetchall()}
        for username, role in ACCOUNTS.items():
            if role in known:
                out[role] = known[role]
                continue
            principal = auth.create_user(self.ctx, username=username, password=PASSWORD,
                                         role=role)
            out[role] = principal.public
        return out

    def _sign_in(self) -> dict[str, str]:
        tokens = {}
        for username, role in ACCOUNTS.items():
            response = self.client.post("/api/v2/auth/login",
                                        json={"username": username, "password": PASSWORD})
            assert response.status_code == 200, response.text
            tokens[role] = response.json()["token"]
        return tokens

    def restart(self) -> "Harness":
        """A process restart over the same database and artifact store."""
        fresh = Harness.__new__(Harness)
        fresh.tmp_path = self.tmp_path
        fresh.settings = self.settings
        fresh._build()
        return fresh

    def run(self, passes: int = 1) -> None:
        for _ in range(passes):
            assert self.worker.tick()

    def submit(self, body: dict, *, key: str, actor: str | None = None,
               role: str | None = None) -> str:
        return self.api.post("/analyses", body, key=key, actor=actor,
                             role=role)["analysis_id"]

    def analyse(self, body: dict, *, key: str, role: str | None = None) -> dict:
        analysis_id = self.submit(body, key=key, role=role)
        self.run()
        return self.api.get(f"/analyses/{analysis_id}", "Analysis", role=role)

    def counted(self, table: str, where: str = "1=1", params: tuple = ()) -> int:
        with self.ctx.db.reader() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]


@pytest.fixture
def harness(tmp_path) -> Harness:
    return Harness(tmp_path)


@pytest.fixture(scope="session")
def replay_entries() -> list[dict]:
    from backend.app.v2.adapters.raster import ReplayRasterAdapter

    entries = ReplayRasterAdapter().entries()
    assert entries, "the replay vectors are missing; the Lens suite cannot run"
    return entries


def entry_for(entries: list[dict], name: str) -> dict:
    return next(item for item in entries if item["name"] == name)


def request_for(entry: dict) -> dict:
    """The API request that reproduces one replay vector."""
    return {"aoi_id": entry["aoi_id"], "year_start": entry["year_start"],
            "year_end": entry["year_end"]}


def geometry_request(entry: dict) -> dict:
    """The same vector addressed by its polygon instead of by an area name."""
    if entry["name"].startswith("check-transfer"):
        sample = next(item for item in catalog.sample_requests()
                      if item["request_id"] == "CHECK_TRANSFER_01")
        geometry = sample["geometry"]
    else:
        geometry = catalog.area(entry["aoi_id"]).geometry
    return {"geometry": geometry, "year_start": entry["year_start"],
            "year_end": entry["year_end"]}
