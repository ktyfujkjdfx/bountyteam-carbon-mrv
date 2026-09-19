"""Signing in, the permission matrix, and the trail of what people did.

Authorization is only real if the server refuses. A hidden button is a styling choice, so
every test here goes through HTTP with a token that belongs to a particular role and
checks what the server does, not what a screen would show.
"""
from __future__ import annotations

import pytest

from backend.app.v2 import auth

from .conftest import ACCOUNTS, PASSWORD, TVER, Harness

BODY = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024}


def _login(harness, username="", password=PASSWORD, **kwargs):
    return harness.client.post("/api/v2/auth/login",
                               json={"username": username, "password": password}, **kwargs)


def _as(harness, role):
    return {"Authorization": "Bearer " + harness.api.tokens[role]}


# -- entering a role without typing its password -----------------------------------------
def test_a_deployment_without_demo_accounts_offers_none(harness):
    """The ordinary answer. One-click entry exists only where somebody enabled it."""
    body = harness.client.get("/api/v2/auth/demo-accounts").json()
    assert body == {"accounts": []}


def test_demo_login_is_404_for_an_existing_user_when_demo_is_off(harness):
    """The refusal describes the demonstration configuration, not the user table.

    `owner` is a real row here and its password is known to the suite; without a declared
    demonstration account the service still refuses, so nobody can walk into a role by
    guessing a username.
    """
    response = harness.client.post("/api/v2/auth/demo-login", json={"username": "owner"})
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_declared_demo_accounts_are_listed_without_their_passwords(tmp_path):
    accounts = (("owner", "PROJECT_OWNER", PASSWORD), ("verifier", "VERIFIER", PASSWORD))
    demo = Harness(tmp_path, lens_demo_accounts=accounts)
    body = demo.client.get("/api/v2/auth/demo-accounts").json()
    assert [item["username"] for item in body["accounts"]] == ["owner", "verifier"]
    assert [item["role"] for item in body["accounts"]] == ["PROJECT_OWNER", "VERIFIER"]
    assert PASSWORD not in demo.client.get("/api/v2/auth/demo-accounts").text
    for item in body["accounts"]:
        assert "password" not in item


def test_entering_a_declared_role_gives_an_ordinary_session(tmp_path):
    """Same token, same /auth/me, same role. A demonstration of the real thing or nothing."""
    accounts = (("verifier", "VERIFIER", PASSWORD),)
    demo = Harness(tmp_path, lens_demo_accounts=accounts)
    session = demo.client.post("/api/v2/auth/demo-login", json={"username": "verifier"})
    assert session.status_code == 200, session.text
    body = session.json()
    assert body["user"]["role"] == "VERIFIER"
    assert len(body["token"]) >= 32
    me = demo.client.get("/api/v2/auth/me",
                         headers={"Authorization": "Bearer " + body["token"]})
    assert me.status_code == 200, me.text
    assert me.json()["role"] == "VERIFIER"


def test_an_undeclared_name_is_refused_even_while_demo_is_on(tmp_path):
    demo = Harness(tmp_path, lens_demo_accounts=(("owner", "PROJECT_OWNER", PASSWORD),))
    response = demo.client.post("/api/v2/auth/demo-login", json={"username": "investor"})
    assert response.status_code == 404, response.text


# -- passwords ---------------------------------------------------------------------------
def test_a_password_is_stored_only_as_a_salted_hash(harness):
    with harness.ctx.db.reader() as conn:
        rows = conn.execute("SELECT username, password_hash FROM lens_users").fetchall()
    assert rows
    for row in rows:
        assert PASSWORD not in row["password_hash"]
        assert row["password_hash"].startswith("scrypt$")
        assert len(row["password_hash"].split("$")) == 6


def test_two_accounts_with_the_same_password_do_not_share_a_hash(harness):
    """A per-password salt, so one cracked hash does not unlock the others."""
    with harness.ctx.db.reader() as conn:
        hashes = [row["password_hash"] for row in
                  conn.execute("SELECT password_hash FROM lens_users").fetchall()]
    assert len(set(hashes)) == len(hashes)


def test_the_production_password_cost_is_not_what_the_suite_runs_at():
    """The suite lowers the cost so it can sign in constantly; production must not."""
    assert auth.PRODUCTION_SCRYPT_N >= 1 << 14
    assert auth.SCRYPT_N < auth.PRODUCTION_SCRYPT_N, "conftest should have lowered this"


def test_a_stored_hash_records_its_own_cost_so_it_can_be_raised_later():
    stored = auth.hash_password("whatever", cost=1 << 10)
    assert stored.split("$")[1] == str(1 << 10)
    # Verification reads the cost from the record rather than assuming today's.
    assert auth.verify_password("whatever", stored)


# -- signing in --------------------------------------------------------------------------
def test_a_correct_password_returns_an_opaque_token_and_the_role(harness):
    response = _login(harness, "verifier")
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "VERIFIER"
    assert body["user"]["username"] == "verifier"
    assert len(body["token"]) >= 32
    assert PASSWORD not in body["token"]
    assert "password" not in response.text.lower()


def test_the_token_is_not_stored_in_a_form_that_could_be_replayed(harness):
    token = _login(harness, "owner").json()["token"]
    with harness.ctx.db.reader() as conn:
        rows = [dict(row) for row in
                conn.execute("SELECT * FROM lens_sessions").fetchall()]
    assert rows
    assert all(token not in str(row) for row in rows), "the raw token must not be stored"


def test_a_wrong_password_and_an_unknown_user_are_the_same_answer(harness):
    """Telling them apart tells an attacker which usernames exist."""
    wrong_password = _login(harness, "verifier", "not-the-password")
    unknown_user = _login(harness, "nobody-at-all", "not-the-password")
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["error"] == unknown_user.json()["error"]


def test_repeated_failures_for_one_name_are_rate_limited(harness):
    for _ in range(auth.MAX_FAILURES):
        assert _login(harness, "investor", "wrong").status_code == 401
    limited = _login(harness, "investor", "wrong")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
    # The real password is refused too while the limit holds: this is not a bypass.
    assert _login(harness, "investor", PASSWORD).status_code == 429


def test_a_successful_sign_in_clears_the_failure_count(harness):
    for _ in range(auth.MAX_FAILURES - 1):
        assert _login(harness, "owner", "wrong").status_code == 401
    assert _login(harness, "owner").status_code == 200
    for _ in range(auth.MAX_FAILURES - 1):
        assert _login(harness, "owner", "wrong").status_code == 401
    assert _login(harness, "owner").status_code == 200


def test_who_am_i_answers_from_the_session_not_from_the_request(harness):
    body = harness.api.get("/auth/me", "User", role="INVESTOR")
    assert body["role"] == "INVESTOR"
    # A role announced by the client changes nothing.
    response = harness.client.get("/api/v2/auth/me",
                                  headers={**_as(harness, "INVESTOR"),
                                           "X-Demo-Actor": "VERIFIER",
                                           "X-Role": "VERIFIER"})
    assert response.json()["role"] == "INVESTOR"


def test_logging_out_stops_the_token_working(harness):
    token = _login(harness, "verifier").json()["token"]
    headers = {"Authorization": "Bearer " + token}
    assert harness.client.get("/api/v2/auth/me", headers=headers).status_code == 200
    assert harness.client.post("/api/v2/auth/logout", headers=headers).status_code == 200
    assert harness.client.get("/api/v2/auth/me", headers=headers).status_code == 401
    # Signing out again is 401, because the session it names no longer exists. A client
    # that has already been signed out has nothing left to do.
    assert harness.client.post("/api/v2/auth/logout", headers=headers).status_code == 401


def test_an_expired_session_is_refused_like_a_revoked_one(harness):
    token = _login(harness, "owner").json()["token"]
    with harness.ctx.db.transaction() as conn:
        conn.execute("UPDATE lens_sessions SET expires_at = ?", ("2020-01-01T00:00:00Z",))
    response = harness.client.get("/api/v2/auth/me",
                                  headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401


def test_a_session_survives_a_restart(harness):
    """Sessions live in the database, not in a process.

    A worker restart or a second process must not sign everybody out; that is the
    difference between a session store and an in-memory dictionary.
    """
    token = _login(harness, "verifier").json()["token"]
    fresh = harness.restart()
    response = fresh.client.get("/api/v2/auth/me",
                                headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200 and response.json()["role"] == "VERIFIER"


@pytest.mark.parametrize("header", ["", "Bearer", "Bearer ", "Basic abc", "token abc"])
def test_a_malformed_authorization_header_is_401_not_a_crash(harness, header):
    response = harness.client.get("/api/v2/catalog", headers={"Authorization": header})
    assert response.status_code == 401


# -- the permission matrix ----------------------------------------------------------------
@pytest.mark.parametrize("role,expected", [("PROJECT_OWNER", 202), ("VERIFIER", 202),
                                           ("INVESTOR", 403)])
def test_only_the_working_roles_may_queue_an_analysis(harness, role, expected):
    response = harness.client.post(
        "/api/v2/analyses", json=BODY,
        headers={**_as(harness, role), "Idempotency-Key": f"role-key-{role[:8]}"})
    assert response.status_code == expected


@pytest.mark.parametrize("role,expected", [("PROJECT_OWNER", 200), ("VERIFIER", 200),
                                           ("INVESTOR", 403)])
def test_only_the_working_roles_may_measure_a_contour(harness, role, expected):
    response = harness.client.post(
        "/api/v2/areas/measure",
        json={"geometry": {"type": "Polygon", "coordinates": [[
            [35.0, 57.0], [35.01, 57.0], [35.01, 57.01], [35.0, 57.01], [35.0, 57.0]]]}},
        headers=_as(harness, role))
    assert response.status_code == expected


@pytest.mark.parametrize("role", ["PROJECT_OWNER", "VERIFIER", "INVESTOR"])
def test_every_role_may_read_the_catalog(harness, role):
    assert harness.client.get("/api/v2/catalog",
                              headers=_as(harness, role)).status_code == 200


def test_an_owner_sees_their_own_draft_and_a_verifier_sees_it_too(harness):
    job = harness.analyse(BODY, key="own-key-00000001", role="PROJECT_OWNER")
    analysis_id = job["analysis_id"]
    for role in ("PROJECT_OWNER", "VERIFIER"):
        response = harness.client.get(f"/api/v2/analyses/{analysis_id}",
                                      headers=_as(harness, role))
        assert response.status_code == 200, role


def test_an_investor_cannot_see_a_draft_passport(harness):
    """A draft is not a finding, and showing one as if it were is the worst mistake here."""
    job = harness.analyse(BODY, key="draftonly-key-001", role="PROJECT_OWNER")
    analysis_id = job["analysis_id"]
    response = harness.client.get(f"/api/v2/analyses/{analysis_id}",
                                  headers=_as(harness, "INVESTOR"))
    # 404 rather than 403: probing identifiers must not reveal which ones exist.
    assert response.status_code == 404
    assert harness.client.get(f"/api/v2/analyses/{analysis_id}/report",
                              headers=_as(harness, "INVESTOR")).status_code == 404
    assert harness.client.get(f"/api/v2/analyses/{analysis_id}/proof",
                              headers=_as(harness, "INVESTOR")).status_code == 404


def test_an_artifact_follows_the_same_rule_as_the_analysis(harness):
    job = harness.analyse(BODY, key="artrole-key-00001", role="PROJECT_OWNER")
    artifact = job["result"]["artifacts"][0]
    assert harness.client.get(artifact["url"],
                              headers=_as(harness, "VERIFIER")).status_code == 200
    assert harness.client.get(artifact["url"],
                              headers=_as(harness, "INVESTOR")).status_code == 404


def test_the_permission_table_covers_every_role_and_nothing_else():
    for action, roles in auth.PERMISSIONS.items():
        assert roles, f"{action} is allowed to nobody"
        assert set(roles) <= set(auth.ROLES), action
    assert set(ACCOUNTS.values()) == set(auth.ROLES)


def test_an_unknown_permission_is_a_programming_error_not_an_allow():
    principal = auth.Principal("u-1", "someone", "Someone", "VERIFIER")
    with pytest.raises(KeyError):
        auth.allows(principal, "analysis.invent")


# -- the audit trail ----------------------------------------------------------------------
def test_the_trail_records_who_did_what(harness):
    job = harness.analyse(BODY, key="audit-key-0000001", role="PROJECT_OWNER")
    harness.client.get(f"/api/v2/analyses/{job['analysis_id']}/report",
                       headers=_as(harness, "VERIFIER"))

    actions = [row["action"] for row in auth.audit_trail(harness.ctx, limit=100)]
    assert "LOGIN" in actions
    assert "ANALYSIS_CREATED" in actions
    assert "REPORT_DOWNLOADED" in actions

    created = [row for row in auth.audit_trail(harness.ctx, subject=job["analysis_id"])
               if row["action"] == "ANALYSIS_CREATED"]
    assert created and created[0]["role"] == "PROJECT_OWNER"
    assert created[0]["user_id"] == harness.users["PROJECT_OWNER"]["user_id"]


def test_a_failed_sign_in_is_recorded_without_the_password(harness):
    _login(harness, "verifier", "a-very-secret-guess")
    rows = auth.audit_trail(harness.ctx, limit=20)
    failures = [row for row in rows if row["action"] == "LOGIN_FAILED"]
    assert failures
    assert all("a-very-secret-guess" not in str(row) for row in rows)


def test_the_trail_is_not_part_of_the_scientific_content(harness):
    """Who read a report cannot change what the report says."""
    job = harness.analyse(BODY, key="audithash-key-001", role="PROJECT_OWNER")
    before = job["result"]["passport"]["content_hash"]
    for _ in range(3):
        harness.client.get(f"/api/v2/analyses/{job['analysis_id']}/report",
                           headers=_as(harness, "VERIFIER"))
    again = harness.api.get(f"/analyses/{job['analysis_id']}", "Analysis", role="VERIFIER")
    assert again["result"]["passport"]["content_hash"] == before


def test_no_token_reaches_the_audit_trail_or_a_passport(harness):
    token = harness.api.tokens["VERIFIER"]
    job = harness.analyse(BODY, key="notoken-key-00001", role="VERIFIER")
    assert token not in str(auth.audit_trail(harness.ctx, limit=100))
    assert token not in str(job["result"])
    html = harness.client.get(f"/api/v2/analyses/{job['analysis_id']}/report?format=html",
                              headers=_as(harness, "VERIFIER")).text
    assert token not in html and "Authorization" not in html


# -- demo accounts ------------------------------------------------------------------------
def test_demo_accounts_exist_only_when_a_deployment_configured_them():
    from backend.app.config import Settings

    assert Settings(demo_session="x" * 16).lens_demo_accounts == ()


def test_a_demo_password_must_be_chosen_and_long_enough():
    from backend.app.config import ConfigError, Settings

    with pytest.raises(ConfigError):
        Settings(demo_session="x" * 16,
                 lens_demo_accounts=(("owner", "PROJECT_OWNER", "short"),)).validate()
    Settings(demo_session="x" * 16,
             lens_demo_accounts=(("owner", "PROJECT_OWNER", "long-enough-1"),)).validate()


def test_a_demo_password_never_appears_in_a_repr_of_the_settings():
    from backend.app.config import Settings

    settings = Settings(demo_session="x" * 16,
                        lens_demo_accounts=(("owner", "PROJECT_OWNER", "hunter2hunter2"),))
    assert "hunter2hunter2" not in repr(settings)


def test_seeding_does_not_reset_a_password_somebody_changed(harness):
    created = auth.seed_demo_users(harness.ctx, {"owner": ("PROJECT_OWNER", "another-one")})
    assert created == []
    assert _login(harness, "owner").status_code == 200


def test_the_suite_signs_in_through_the_same_route_a_client_uses(harness):
    assert set(harness.api.tokens) == set(auth.ROLES)
    assert _login(harness, "owner").status_code == 200
    assert TVER == "RU_TVER_01"
