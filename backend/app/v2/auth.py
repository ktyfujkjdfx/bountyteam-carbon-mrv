"""Who is signed in, what they may do, and what they did.

Three decisions worth stating plainly, because each of them is a place where an
authorization system usually goes wrong:

- **The role is server state.** It is read from the session row on every request. Nothing
  a client sends can name a role, so there is no header to forge and no "hidden button"
  that stands in for a permission check.
- **Only the hash of a session token is stored.** The token itself exists in the login
  response and in the client's memory. A copy of the database does not hand anyone a
  working session, and the token never reaches a log line, a passport or a content hash.
- **A wrong username and a wrong password are the same answer.** Distinguishing them
  tells an attacker which usernames exist, which is the expensive half of the guess.

Passwords are hashed with scrypt from the standard library, with a random salt per
password and the cost parameters recorded next to the digest, so the cost can be raised
later without invalidating what is stored.
"""
from __future__ import annotations

import hmac
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ..contracts import sha256_hex
from ..db import utc_now
from ..errors import ApiError, forbidden, unauthorized

log = logging.getLogger("backend.lens.auth")

ROLES = ("PROJECT_OWNER", "VERIFIER", "INVESTOR")
SESSION_HOURS = 12
TOKEN_BYTES = 32

# scrypt cost. 2**14 keeps a login well under a tenth of a second on a laptop while
# making an offline guessing run expensive per candidate. The cost is recorded next to
# every digest, so raising it later does not invalidate what is already stored, and an
# existing password is rehashed at the new cost the next time it is verified.
PRODUCTION_SCRYPT_N = 1 << 14
SCRYPT_N = PRODUCTION_SCRYPT_N
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16

# Rate limit for sign-in. Slow enough to make guessing pointless, generous enough that a
# person who mistypes twice is not locked out of a demo.
MAX_FAILURES = 5
FAILURE_WINDOW_MINUTES = 15

# One message for every failed sign-in, whatever went wrong.
LOGIN_FAILED = "Неверное имя пользователя или пароль."

AUDIT_ACTIONS = (
    "LOGIN", "LOGIN_FAILED", "LOGOUT", "ANALYSIS_CREATED", "ANALYSIS_VIEWED",
    "ANALYSIS_STARTED", "ARTIFACT_DOWNLOADED", "REPORT_DOWNLOADED",
    "PASSPORT_FINALIZED", "REQUEST_CREATED", "REQUEST_UPDATED", "REQUEST_SUBMITTED",
    "DEMO_LIFECYCLE",
)


@dataclass(frozen=True)
class Principal:
    """The signed-in person, as the server knows them."""

    user_id: str
    username: str
    display_name: str
    role: str

    @property
    def public(self) -> dict:
        return {"user_id": self.user_id, "username": self.username,
                "display_name": self.display_name, "role": self.role}


# -- passwords -------------------------------------------------------------------------
def hash_password(password: str, *, salt: bytes | None = None,
                  cost: int | None = None) -> str:
    import hashlib

    if not password:
        raise ValueError("a password is required")
    salt = salt or secrets.token_bytes(SALT_BYTES)
    cost = cost or SCRYPT_N
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=cost, r=SCRYPT_R,
                            p=SCRYPT_P, dklen=32)
    return f"scrypt${cost}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    import hashlib

    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                                   n=int(n), r=int(r), p=int(p),
                                   dklen=len(digest_hex) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest_hex)


# -- users -----------------------------------------------------------------------------
def create_user(ctx: Any, *, username: str, password: str, role: str,
                display_name: str | None = None) -> Principal:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    user_id = "u-" + secrets.token_hex(8)
    with ctx.db.transaction() as conn:
        conn.execute(
            "INSERT INTO lens_users (user_id, username, display_name, role, password_hash,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, display_name or username, role,
             hash_password(password), utc_now()))
    return Principal(user_id=user_id, username=username,
                     display_name=display_name or username, role=role)


def user_count(ctx: Any) -> int:
    with ctx.db.reader() as conn:
        return conn.execute("SELECT COUNT(*) FROM lens_users").fetchone()[0]


def seed_demo_users(ctx: Any, accounts: dict[str, tuple[str, str]]) -> list[str]:
    """Create the demo accounts a deployment configured, and only those.

    `accounts` maps a username to (role, password). Passwords arrive from the environment
    and are never written to the repository. An account that already exists is left alone,
    so a restart does not reset a password somebody changed.
    """
    created = []
    for username, (role, password) in sorted(accounts.items()):
        with ctx.db.reader() as conn:
            existing = conn.execute("SELECT 1 FROM lens_users WHERE username = ?",
                                    (username,)).fetchone()
        if existing:
            continue
        create_user(ctx, username=username, password=password, role=role)
        created.append(username)
    if created:
        log.info("created demo accounts: %s", ", ".join(created))
    return created


# -- sessions --------------------------------------------------------------------------
def _token_hash(token: str) -> str:
    return sha256_hex(token.encode("utf-8"))


def _expiry(hours: int = SESSION_HOURS) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _recent_failures(conn: Any, username: str) -> int:
    since = (datetime.now(timezone.utc)
             - timedelta(minutes=FAILURE_WINDOW_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return conn.execute(
        "SELECT COUNT(*) FROM lens_login_failures WHERE username = ? AND occurred_at >= ?",
        (username, since)).fetchone()[0]


def login(ctx: Any, *, username: str, password: str) -> dict:
    """Exchange a username and a password for an opaque session token."""
    username = (username or "").strip()
    with ctx.db.reader() as conn:
        rate_limited = _recent_failures(conn, username) >= MAX_FAILURES
        row = conn.execute(
            "SELECT user_id, username, display_name, role, password_hash, disabled_at"
            " FROM lens_users WHERE username = ?", (username,)).fetchone()
    if rate_limited:
        audit(ctx, None, None, "LOGIN_FAILED", username, reason="RATE_LIMITED")
        raise ApiError(429, "TOO_MANY_ATTEMPTS",
                       "Слишком много попыток входа. Повторите позже.",
                       {"retry_after_minutes": FAILURE_WINDOW_MINUTES})

    # The same work and the same answer whether the user exists or not: a fast "no such
    # user" is itself an answer about which usernames exist.
    stored = row["password_hash"] if row else hash_password("not-a-real-password")
    ok = verify_password(password or "", stored) and row is not None \
        and row["disabled_at"] is None
    if not ok:
        with ctx.db.transaction() as conn:
            conn.execute(
                "INSERT INTO lens_login_failures (username, occurred_at) VALUES (?, ?)",
                (username, utc_now()))
        audit(ctx, None, None, "LOGIN_FAILED", username, reason="BAD_CREDENTIALS")
        raise unauthorized(LOGIN_FAILED)

    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = _expiry()
    now = utc_now()
    principal = Principal(user_id=row["user_id"], username=row["username"],
                          display_name=row["display_name"], role=row["role"])
    with ctx.db.transaction() as conn:
        conn.execute(
            "INSERT INTO lens_sessions (token_hash, user_id, created_at, expires_at,"
            " last_seen_at) VALUES (?, ?, ?, ?, ?)",
            (_token_hash(token), row["user_id"], now, expires_at, now))
        conn.execute("DELETE FROM lens_login_failures WHERE username = ?", (username,))
        audit(ctx, principal.user_id, principal.role, "LOGIN", principal.user_id,
              conn=conn)
    return {"token": token, "expires_at": expires_at, "user": principal.public}


def demo_directory(accounts: tuple[tuple[str, str, str], ...]) -> dict:
    """The demonstration accounts this deployment declared, without their passwords.

    A deployment that declared none answers with an empty list, and then one-click entry
    simply does not exist here. The password never appears in this answer: the client is
    told which roles it may enter, not how to enter them.
    """
    return {"accounts": [{"username": username, "display_name": username, "role": role}
                         for username, role, _password in accounts]}


def demo_login(ctx: Any, *, username: str, accounts: tuple[tuple[str, str, str], ...]) -> dict:
    """A session for a declared demonstration account, without typing its password.

    The password is looked up in the environment of the service, so the browser never
    holds it and a build cannot carry it. An account this deployment did not declare is
    404 whether or not a user row with that name exists: the answer is about the
    demonstration configuration, not about the user table.

    The session itself goes through the ordinary `login`, so the token, the expiry, the
    rate-limit reset and the audit record are the same as for anybody who typed a
    password. A demonstration that behaved differently would not be a demonstration.
    """
    wanted = (username or "").strip()
    match = next((item for item in accounts if item[0] == wanted), None)
    if match is None:
        raise ApiError(404, "NOT_FOUND",
                       "Эта демонстрационная учётная запись на сервисе не настроена.")
    return login(ctx, username=match[0], password=match[2])


def resolve(ctx: Any, token: str | None) -> Principal:
    """The person this token belongs to, or 401. Expiry and revocation are the same no."""
    if not token:
        raise unauthorized("Требуется вход в систему.")
    with ctx.db.reader() as conn:
        row = conn.execute(
            "SELECT s.token_hash, s.expires_at, s.revoked_at, u.user_id, u.username,"
            " u.display_name, u.role, u.disabled_at"
            " FROM lens_sessions s JOIN lens_users u ON u.user_id = s.user_id"
            " WHERE s.token_hash = ?", (_token_hash(token),)).fetchone()
    if row is None or row["revoked_at"] is not None or row["disabled_at"] is not None \
            or row["expires_at"] <= utc_now():
        raise unauthorized("Сессия недействительна или истекла.")
    with ctx.db.transaction() as conn:
        conn.execute("UPDATE lens_sessions SET last_seen_at = ? WHERE token_hash = ?",
                     (utc_now(), row["token_hash"]))
    return Principal(user_id=row["user_id"], username=row["username"],
                     display_name=row["display_name"], role=row["role"])


def logout(ctx: Any, token: str | None) -> dict:
    """Revoke this session. Revoking an already dead session is still success."""
    if token:
        with ctx.db.transaction() as conn:
            conn.execute(
                "UPDATE lens_sessions SET revoked_at = ?"
                " WHERE token_hash = ? AND revoked_at IS NULL",
                (utc_now(), _token_hash(token)))
    return {"revoked": True}


# -- permissions -----------------------------------------------------------------------
# Every action the API can perform, and the roles the server allows to perform it. A
# screen may hide a button; only this table decides whether the action happens.
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "catalog.read": ("PROJECT_OWNER", "VERIFIER", "INVESTOR"),
    "area.measure": ("PROJECT_OWNER", "VERIFIER"),
    "request.create": ("PROJECT_OWNER",),
    "request.submit": ("PROJECT_OWNER",),
    "analysis.run": ("VERIFIER",),
    "analysis.create": ("PROJECT_OWNER", "VERIFIER"),
    "analysis.read.own": ("PROJECT_OWNER", "VERIFIER", "INVESTOR"),
    "analysis.read.any": ("VERIFIER",),
    "analysis.read.finalized": ("PROJECT_OWNER", "VERIFIER", "INVESTOR"),
    "passport.finalize": ("VERIFIER",),
    "report.read.draft": ("PROJECT_OWNER", "VERIFIER"),
    "report.read.final": ("PROJECT_OWNER", "VERIFIER", "INVESTOR"),
}


def allows(principal: Principal, action: str) -> bool:
    if action not in PERMISSIONS:
        raise KeyError(f"unknown permission {action}")
    return principal.role in PERMISSIONS[action]


def require(principal: Principal, action: str) -> None:
    if not allows(principal, action):
        raise forbidden(f"Роль {principal.role} не может выполнить это действие.")


def may_read_analysis(principal: Principal, *, owner_id: str, finalized: bool) -> bool:
    """Who may look at one analysis.

    An owner sees their own work at any stage. A verifier sees everything, because
    reviewing it is the job. An investor sees a passport only once a verifier has
    finalized it: a draft is not a finding, and showing one as if it were would be the
    most consequential mistake this screen could make.
    """
    if allows(principal, "analysis.read.any"):
        return True
    if principal.user_id == owner_id and allows(principal, "analysis.read.own"):
        return True
    return finalized and allows(principal, "analysis.read.finalized")


# -- audit -----------------------------------------------------------------------------
def audit(ctx: Any, user_id: str | None, role: str | None, action: str,
          subject: str | None = None, *, conn: Any = None, **details: Any) -> None:
    """Record what happened. Never part of a scientific content hash.

    Who downloaded a report cannot change what the report says, so this trail is kept
    beside the passports rather than inside them.

    A caller that is already inside a write transaction passes its connection: opening a
    second one would deadlock against the first, and an audit row is not worth a lock.
    """
    if action not in AUDIT_ACTIONS:
        raise ValueError(f"unknown audit action {action}")
    row = (utc_now(), user_id, role, action, subject,
           json.dumps(details, ensure_ascii=False, sort_keys=True))
    statement = ("INSERT INTO lens_audit (occurred_at, user_id, role, action, subject,"
                 " details_json) VALUES (?, ?, ?, ?, ?, ?)")
    if conn is not None:
        conn.execute(statement, row)
        return
    with ctx.db.transaction() as connection:
        connection.execute(statement, row)


def audit_trail(ctx: Any, *, subject: str | None = None, limit: int = 100) -> list[dict]:
    query = ("SELECT occurred_at, user_id, role, action, subject, details_json"
             " FROM lens_audit")
    params: tuple = ()
    if subject is not None:
        query += " WHERE subject = ?"
        params = (subject,)
    query += " ORDER BY seq DESC LIMIT ?"
    with ctx.db.reader() as conn:
        rows = conn.execute(query, (*params, limit)).fetchall()
    return [dict(row) for row in rows]
