"""First integration vertical slice over HTTP + worker.

`test_e2e_contract_fixture_mock_chain` always runs (CONTRACT_FIXTURE, mock ledger).
`test_e2e_local_anvil` runs the SAME flow against a real Anvil deployment of the
Blockchain module and is skipped unless configured:

  BACKEND_E2E_RPC_URL=http://127.0.0.1:8545
  BACKEND_E2E_DEPLOYMENT=blockchain/runtime/deployment.json
  BACKEND_E2E_KEY_ISSUER / _ORACLE / _BUYER / _RECIPIENT = local Anvil dev keys
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.app.chain.base import ContractCall, ContractRevert

from .conftest import AUTH, EXPECTED, PLOT, Harness


def _poll_operation(h: Harness, operation_id: str, ticks: int = 30) -> dict:
    for _ in range(ticks):
        op = h.api.get(f"/operations/{operation_id}", "Operation")
        if op["transaction_state"] in ("CONFIRMED", "FAILED"):
            return op
        h.run(1)
    return h.api.get(f"/operations/{operation_id}", "Operation")


def _negative_flow(h: Harness) -> None:
    """Insufficient data never unlocks issuance, and an older good baseline cannot override it."""
    insufficient = h.verify("insufficient", key="e2e-insufficient")
    assert insufficient["state"] == "SUCCEEDED"
    assert h.api.get(f"/verifications/{insufficient['verification_id']}", "Verification")["decision"] == "REVIEW_REQUIRED"
    baseline = h.verify("baseline", key="e2e-baseline-older")
    # The newer insufficient observation (2024-08-01) stays latest: issuance must be blocked.
    assert h.api.get(f"/verifications/{baseline['verification_id']}", "Verification")["is_latest"] is False
    h.api.post(f"/plots/{PLOT}/issue", {"demo_authorization_id": AUTH}, "issuer", "e2e-issue-blocked", "Error",
               status=409)


def _financial_flow(h: Harness, suffix: str) -> dict:
    """issue -> buy -> transfer -> fire evidence decision -> oracle freeze -> direct transfer revert."""
    baseline = h.verify("baseline", key=f"e2e-baseline-{suffix}")
    assert h.api.get(f"/verifications/{baseline['verification_id']}", "Verification")["decision"] == "NO_RESTRICTION"
    plot = h.api.get(f"/plots/{PLOT}", "Plot", actor="issuer")
    assert plot["can_issue"] is True and plot["action_block_reason"] is None

    issue = h.api.post(f"/plots/{PLOT}/issue", {"demo_authorization_id": AUTH}, "issuer", f"e2e-issue-{suffix}",
                       "OperationAccepted")
    issue_op = _poll_operation(h, issue["operation_id"])
    assert issue_op["transaction_state"] == "CONFIRMED", issue_op
    assert issue_op["receipt"]["status"] == 1 and "Issued" in issue_op["receipt"]["event_names"]
    batch_id = issue_op["batch_id"]

    buy = h.api.post(f"/batches/{batch_id}/buy", {"amount": "10"}, "buyer", f"e2e-buy-{suffix}", "OperationAccepted")
    replay = h.api.post(f"/batches/{batch_id}/buy", {"amount": "10"}, "buyer", f"e2e-buy-{suffix}", "OperationAccepted")
    assert replay == buy  # double click: same operation, no second payment
    assert _poll_operation(h, buy["operation_id"])["transaction_state"] == "CONFIRMED"
    transfer = h.api.post(f"/batches/{batch_id}/transfer", {"to_actor": "recipient", "amount": "3"}, "buyer",
                          f"e2e-transfer-{suffix}", "OperationAccepted")
    assert _poll_operation(h, transfer["operation_id"])["transaction_state"] == "CONFIRMED"
    before = h.api.get(f"/plots/{PLOT}/credits", "Credits", actor="buyer")["items"][0]
    assert (before["credit_status"], before["seller_balance"], before["actor_balance"]) == ("ACTIVE", "90", "7")

    fire = h.verify("post_fire", key=f"e2e-fire-{suffix}")
    fire_view = h.api.get(f"/verifications/{fire['verification_id']}", "Verification")
    assert (fire_view["decision"], fire_view["reason"]) == ("FREEZE_REQUESTED", "FIRE_REVERSAL")
    h.run(2)
    freezes = h.operations("FREEZE")
    assert len(freezes) == 1
    freeze_op = _poll_operation(h, freezes[0]["operation_id"])
    assert freeze_op["transaction_state"] == "CONFIRMED" and "Frozen" in freeze_op["receipt"]["event_names"]
    assert freeze_op["receipt"]["state_readback_ok"] is True

    after = h.api.get(f"/plots/{PLOT}/credits", "Credits", actor="buyer")["items"][0]
    assert after["credit_status"] == "FROZEN" and after["actor_balance"] == "7" and after["frozen_at"]
    assert after["evidence_hash"] == fire_view["evidence_hash"] and after["decision_hash"] == fire_view["decision_hash"]
    with pytest.raises(ContractRevert) as direct:
        h.chain.simulate("buyer", ContractCall("transfer", (int(batch_id), h.chain.signer_address("recipient"), 1)))
    assert direct.value.error_name == "BatchNotActive"

    # Repeat: the same fire request again creates no second freeze.
    h.verify("post_fire", key=f"e2e-fire-repeat-{suffix}")
    h.run(3)
    assert len(h.operations("FREEZE")) == 1

    proof = h.api.get(f"/verifications/{fire['verification_id']}/proof", "Proof")
    assert proof["integrity_ok"] and [a["event_name"] for a in proof["anchors"]] == ["Frozen"]
    baseline_proof = h.api.get(f"/verifications/{baseline['verification_id']}/proof", "Proof")
    assert [a["event_name"] for a in baseline_proof["anchors"]] == ["Issued"]
    events = h.api.get(f"/events?plot_id={PLOT}&limit=100", "Events")["items"]
    kinds = [e["kind"] for e in events]
    assert kinds.count("TX_CONFIRMED") == 4 and "TX_FAILED" not in kinds
    return {"batch_id": batch_id, "issue": issue_op, "freeze": freeze_op, "credits": after, "proof": proof,
            "fire_evidence_hash": fire_view["evidence_hash"]}


def test_e2e_contract_fixture_mock_chain(tmp_path):
    h = Harness(tmp_path)
    result = _financial_flow(h, "mock")
    assert result["fire_evidence_hash"] == EXPECTED["fire"]["evidence_hash"]
    assert h.api.get("/health", "Health")["mode"] == "CONTRACT_FIXTURE"


def test_e2e_negative_branches_do_not_unlock_or_freeze(tmp_path):
    h = Harness(tmp_path)
    _negative_flow(h)
    h.run(3)
    assert h.operations() == []


ANVIL = os.environ.get("BACKEND_E2E_RPC_URL")


@pytest.mark.skipif(not ANVIL, reason="set BACKEND_E2E_RPC_URL, BACKEND_E2E_DEPLOYMENT and BACKEND_E2E_KEY_* "
                                      "to run against a real local Anvil deployment")
def test_e2e_local_anvil(tmp_path):
    keys = {role: os.environ[f"BACKEND_E2E_KEY_{role.upper()}"] for role in ("issuer", "oracle", "buyer", "recipient")}
    h = Harness(tmp_path, mode="LOCAL_DEMO", chain_adapter="web3", rpc_url=ANVIL,
                deployment_path=Path(os.environ["BACKEND_E2E_DEPLOYMENT"]), private_keys=keys)
    identity = h.chain.identity()
    assert identity.ok, identity.reason
    result = _financial_flow(h, "anvil")
    assert h.api.get("/health", "Health") == {"api": "UP", "db": "UP", "worker": "UP", "chain": "UP",
                                              "deployment_id": identity.deployment.deployment_id, "mode": "LOCAL_DEMO"}
    evidence_path = os.environ.get("BACKEND_E2E_EVIDENCE_OUT")
    if evidence_path:
        import json
        Path(evidence_path).write_text(json.dumps({"deployment": identity.deployment.__dict__, **result}, indent=2))
