"""Mutating API use cases: verification jobs and ISSUE/BUY/TRANSFER intents.

Idempotency binding: (actor, operation, Idempotency-Key) + hash of the normalized
request (path params + body). Same request -> the stored 202 response; different
request with the same key -> 409 IDEMPOTENCY_CONFLICT. The binding row and the
job/operation it points to are committed in one transaction.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Callable

from .chain.base import ChainUnavailable, ContractRevert
from .context import AppContext, audit, utc_to_epoch
from .contracts import digest
from .db import utc_now
from .errors import ApiError, conflict, forbidden, invalid, not_found, unavailable
from .ingest import latest_verification, pending_freeze

UINT256_MAX = 2**256 - 1


def request_hash(operation: str, path: dict, body: dict) -> str:
    return digest({"operation": operation, "path": path, "body": body})


def _replay(conn: sqlite3.Connection, actor: str, operation: str, key: str, req_hash: str) -> dict | None:
    row = conn.execute("SELECT request_hash, response_json FROM idempotency_keys WHERE actor=? AND operation=? "
                       "AND idempotency_key=?", (actor, operation, key)).fetchone()
    if row is None:
        return None
    if row["request_hash"] != req_hash:
        raise conflict("IDEMPOTENCY_CONFLICT", "Idempotency-Key was already used with a different request")
    return json.loads(row["response_json"])


def idempotent(ctx: AppContext, *, actor: str, operation: str, key: str, path: dict, body: dict,
               prepare: Callable[[], Callable[[sqlite3.Connection], dict]]) -> dict:
    """prepare() runs gates (may read chain) and returns a writer executed inside the transaction."""
    req_hash = request_hash(operation, path, body)
    with ctx.db.reader() as conn:
        stored = _replay(conn, actor, operation, key, req_hash)
    if stored is not None:
        return stored
    writer = prepare()
    with ctx.db.transaction() as conn:
        stored = _replay(conn, actor, operation, key, req_hash)
        if stored is not None:
            return stored
        response = writer(conn)
        conn.execute("INSERT INTO idempotency_keys VALUES (?,?,?,?,?,?,?)",
                     (actor, operation, key, req_hash, 202, json.dumps(response), utc_now()))
        audit(conn, "IDEMPOTENT_REQUEST_ACCEPTED", operation, actor=actor, request_hash=req_hash)
    return response


def _plot(ctx: AppContext, plot_id: str) -> sqlite3.Row:
    with ctx.db.reader() as conn:
        row = conn.execute("SELECT * FROM plots WHERE plot_id=?", (plot_id,)).fetchone()
    if row is None:
        raise not_found("Plot")
    return row


def _deployment_id(ctx: AppContext) -> str:
    status = ctx.chain.identity()
    if status.ok and status.deployment is not None:
        return status.deployment.deployment_id
    reason = status.reason or "unknown"
    if reason.startswith("CHAIN_UNAVAILABLE"):
        raise unavailable("CHAIN_UNAVAILABLE", "Chain is unavailable; nothing was queued, retry with the same key")
    raise conflict("DEPLOYMENT_MISMATCH", "Deployment identity check failed; chain operations are stopped",
                   reason=reason.split(":")[0])


def _require_financial_gate(conn: sqlite3.Connection, plot_id: str) -> sqlite3.Row:
    latest = latest_verification(conn, plot_id)
    if latest is None or latest["decision"] != "NO_RESTRICTION":
        raise conflict("ACTION_NOT_ALLOWED", "Latest backend decision does not allow financial actions",
                       latest_decision=None if latest is None else latest["decision"])
    if pending_freeze(conn, plot_id):
        raise conflict("ACTION_NOT_ALLOWED", "A freeze is pending for this plot")
    return latest


def _amount(value: str) -> int:
    amount = int(value)
    if amount > UINT256_MAX:
        raise invalid("VALIDATION_ERROR", "amount exceeds uint256")
    return amount


# -- verification job --------------------------------------------------------------------------------
def start_verification(ctx: AppContext, actor: str, key: str, plot_id: str, body: dict) -> dict:
    def prepare():
        if actor != "issuer":
            raise forbidden("Only demo actor issuer may start verification")
        _plot(ctx, plot_id)
        if body["scenario_id"] not in ctx.scenarios.get("scenarios", {}):
            raise invalid("UNKNOWN_SCENARIO", "Scenario is not configured on this server")

        def write(conn):
            job_id = str(uuid.uuid4())
            conn.execute("INSERT INTO verification_jobs (job_id, plot_id, scenario_id, state, created_at, updated_at) "
                         "VALUES (?,?,?, 'QUEUED', ?,?)", (job_id, plot_id, body["scenario_id"], utc_now(), utc_now()))
            return {"job_id": job_id, "state": "QUEUED", "status_url": "/api/v1/jobs/" + job_id}
        return write
    return idempotent(ctx, actor=actor, operation="startVerification", key=key, path={"plot_id": plot_id},
                      body=body, prepare=prepare)


def _operation_writer(ctx: AppContext, *, kind: str, plot_id: str, deployment_id: str, sender_role: str,
                      intent: dict, batch_id: str | None = None, verification_id: str | None = None,
                      issuance_key: str | None = None):
    def write(conn):
        operation_id = str(uuid.uuid4())
        try:
            conn.execute(
                "INSERT INTO operations (operation_id, kind, transaction_state, plot_id, deployment_id, batch_id, "
                "verification_id, issuance_key, sender_role, sender_address, intent_json, created_at, updated_at) "
                "VALUES (?,?, 'QUEUED', ?,?,?,?,?,?,?,?,?,?)",
                (operation_id, kind, plot_id, deployment_id, batch_id, verification_id, issuance_key, sender_role,
                 ctx.chain.signer_address(sender_role), json.dumps(intent), utc_now(), utc_now()))
        except sqlite3.IntegrityError:
            raise conflict("AUTHORIZATION_ALREADY_USED", "Demo authorization already has an issuance") from None
        audit(conn, "OPERATION_INTENT_QUEUED", operation_id, kind=kind, batch_id=batch_id)
        return {"operation_id": operation_id, "transaction_state": "QUEUED",
                "status_url": "/api/v1/operations/" + operation_id}
    return write


# -- issue ---------------------------------------------------------------------------------------------
def request_issue(ctx: AppContext, actor: str, key: str, plot_id: str, body: dict) -> dict:
    def prepare():
        if actor != "issuer":
            raise forbidden("Only demo actor issuer may issue")
        _plot(ctx, plot_id)
        authorization = ctx.authorizations.get(body["demo_authorization_id"])
        if authorization is None:
            raise not_found("Demo authorization")
        if authorization["plot_id"] != plot_id:
            raise invalid("AUTHORIZATION_PLOT_MISMATCH", "Demo authorization belongs to another plot")
        if authorization["issuer_actor"] != actor:
            raise forbidden("Actor is not the authorized issuer")
        deployment_id = _deployment_id(ctx)
        issuance_key = digest({"plot_id": plot_id, "demo_authorization_id": authorization["demo_authorization_id"],
                               "deployment_id": deployment_id})
        with ctx.db.reader() as conn:
            latest = _require_financial_gate(conn, plot_id)
            if conn.execute("SELECT 1 FROM batches WHERE deployment_id=? AND plot_id=?",
                            (deployment_id, plot_id)).fetchone():
                raise conflict("ACTION_NOT_ALLOWED", "Plot already has an issued batch")
            if conn.execute("SELECT 1 FROM operations WHERE kind='ISSUE' AND issuance_key=? AND "
                            "transaction_state IN ('QUEUED','SUBMITTED','CONFIRMED')", (issuance_key,)).fetchone():
                raise conflict("AUTHORIZATION_ALREADY_USED", "Demo authorization already has an issuance")
        intent = {
            "function": "issue",
            "args": [{"type": "bytes32", "value": issuance_key},
                     {"type": "string", "value": plot_id},
                     {"type": "address", "value": ctx.chain.signer_address(authorization["seller_actor"])},
                     {"type": "uint", "value": str(_amount(authorization["amount"]))},
                     {"type": "uint", "value": str(_amount(authorization["unit_price_wei"]))},
                     {"type": "bytes32", "value": latest["evidence_hash"]},
                     {"type": "uint", "value": str(utc_to_epoch(latest["observed_at"]))}],
            "value_wei": "0",
            "demo_authorization_id": authorization["demo_authorization_id"],
            "seller_actor": authorization["seller_actor"],
        }
        return _operation_writer(ctx, kind="ISSUE", plot_id=plot_id, deployment_id=deployment_id,
                                 sender_role="issuer", intent=intent, verification_id=latest["verification_id"],
                                 issuance_key=issuance_key)
    return idempotent(ctx, actor=actor, operation="issueBatch", key=key, path={"plot_id": plot_id}, body=body,
                      prepare=prepare)


# -- buy / transfer ------------------------------------------------------------------------------------
def _batch_context(ctx: AppContext, batch_id: str) -> tuple[str, sqlite3.Row, object]:
    deployment_id = _deployment_id(ctx)
    with ctx.db.reader() as conn:
        batch = conn.execute("SELECT * FROM batches WHERE deployment_id=? AND batch_id=?",
                             (deployment_id, batch_id)).fetchone()
    if batch is None:
        raise not_found("Batch")
    try:
        view = ctx.chain.get_batch(int(batch_id))
    except ChainUnavailable:
        raise unavailable("CHAIN_UNAVAILABLE", "Chain readback unavailable; nothing was queued") from None
    except ContractRevert:
        raise not_found("Batch")
    if view.credit_status != "ACTIVE":
        raise conflict("BATCH_NOT_ACTIVE", "Batch is not ACTIVE on chain", credit_status=view.credit_status)
    with ctx.db.reader() as conn:
        _require_financial_gate(conn, batch["plot_id"])
    return deployment_id, batch, view


def _balance(ctx: AppContext, batch_id: str, address: str) -> int:
    try:
        return ctx.chain.balance_of(int(batch_id), address)
    except ChainUnavailable:
        raise unavailable("CHAIN_UNAVAILABLE", "Chain readback unavailable; nothing was queued") from None


def request_buy(ctx: AppContext, actor: str, key: str, batch_id: str, body: dict) -> dict:
    def prepare():
        if actor not in ("buyer", "recipient"):
            raise forbidden("Only demo actors buyer or recipient may buy")
        amount = _amount(body["amount"])
        deployment_id, batch, view = _batch_context(ctx, batch_id)
        buyer = ctx.chain.signer_address(actor)
        if buyer.lower() == view.seller.lower():
            raise forbidden("Seller cannot buy its own batch")
        if _balance(ctx, batch_id, view.seller) < amount:
            raise conflict("INSUFFICIENT_BALANCE", "Seller inventory is lower than the requested amount")
        value = amount * view.unit_price_wei
        if value > UINT256_MAX:
            raise invalid("VALIDATION_ERROR", "payment exceeds uint256")
        intent = {"function": "buy",
                  "args": [{"type": "uint", "value": batch_id}, {"type": "uint", "value": str(amount)}],
                  "value_wei": str(value), "seller": view.seller}
        return _operation_writer(ctx, kind="BUY", plot_id=batch["plot_id"], deployment_id=deployment_id,
                                 sender_role=actor, intent=intent, batch_id=batch_id)
    return idempotent(ctx, actor=actor, operation="buyCredits", key=key, path={"batch_id": batch_id}, body=body,
                      prepare=prepare)


def request_transfer(ctx: AppContext, actor: str, key: str, batch_id: str, body: dict) -> dict:
    def prepare():
        if body["to_actor"] == actor:
            raise invalid("INVALID_RECIPIENT", "Transfer to the same demo actor is rejected")
        amount = _amount(body["amount"])
        deployment_id, batch, _view = _batch_context(ctx, batch_id)
        sender = ctx.chain.signer_address(actor)
        if _balance(ctx, batch_id, sender) < amount:
            raise conflict("INSUFFICIENT_BALANCE", "Actor balance is lower than the requested amount")
        intent = {"function": "transfer",
                  "args": [{"type": "uint", "value": batch_id},
                           {"type": "address", "value": ctx.chain.signer_address(body["to_actor"])},
                           {"type": "uint", "value": str(amount)}],
                  "value_wei": "0"}
        return _operation_writer(ctx, kind="TRANSFER", plot_id=batch["plot_id"], deployment_id=deployment_id,
                                 sender_role=actor, intent=intent, batch_id=batch_id)
    return idempotent(ctx, actor=actor, operation="transferCredits", key=key, path={"batch_id": batch_id},
                      body=body, prepare=prepare)


__all__ = ["ApiError", "request_buy", "request_issue", "request_transfer", "start_verification"]
