"""First integration vertical slice over HTTP + worker.

`test_e2e_contract_fixture_mock_chain` always runs (CONTRACT_FIXTURE, mock ledger).
`test_e2e_local_anvil` runs the SAME flow against a real Anvil deployment of the
Blockchain module and is skipped unless configured:

  BACKEND_E2E_RPC_URL=http://127.0.0.1:8545
  BACKEND_E2E_DEPLOYMENT=runtime/deployment.json
  BACKEND_E2E_KEY_ISSUER / _ORACLE / _BUYER / _RECIPIENT = local Anvil dev keys

`python -m backend.tools.e2e_local_anvil` sets all of this up reproducibly.
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


def _signed_rows(h: Harness) -> list[tuple]:
    with h.ctx.db.reader() as conn:
        return [tuple(r) for r in conn.execute("SELECT operation_id, sender_address, nonce, tx_hash, raw_transaction "
                                               "FROM operation_signed_transactions ORDER BY sender_address, nonce")]


class MockMining:
    @staticmethod
    def hold(h: Harness) -> None:
        h.chain.set_controls(hold_mining=True)

    @staticmethod
    def release(h: Harness) -> None:
        h.chain.set_controls(hold_mining=False)
        h.chain.mine()


class AnvilMining:
    @staticmethod
    def hold(h: Harness) -> None:
        h.chain.w3.provider.make_request("evm_setAutomine", [False])

    @staticmethod
    def release(h: Harness) -> None:
        h.chain.w3.provider.make_request("evm_setAutomine", [True])
        h.chain.w3.provider.make_request("evm_mine", [])


def _financial_flow(h: Harness, suffix: str, mining) -> dict:
    """issue -> buy -> transfer (timeout + restart) -> fire decision -> oracle freeze -> direct transfer revert."""
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
    # Receipt timeout + backend restart while the transfer is pending: same signed bytes, no new nonce.
    mining.hold(h)
    transfer = h.api.post(f"/batches/{batch_id}/transfer", {"to_actor": "recipient", "amount": "3"}, "buyer",
                          f"e2e-transfer-{suffix}", "OperationAccepted")
    h.run(3)
    pending = h.api.get(f"/operations/{transfer['operation_id']}", "Operation")
    assert pending["transaction_state"] == "SUBMITTED" and pending["receipt"] is None and pending["tx_hash"]
    signed_before = _signed_rows(h)
    h = h.restart()
    h.run(3)
    assert h.api.get(f"/operations/{transfer['operation_id']}", "Operation")["transaction_state"] == "SUBMITTED"
    assert _signed_rows(h) == signed_before
    mining.release(h)
    confirmed = _poll_operation(h, transfer["operation_id"])
    assert confirmed["transaction_state"] == "CONFIRMED" and confirmed["tx_hash"] == pending["tx_hash"]
    assert _signed_rows(h) == signed_before
    before = h.api.get(f"/plots/{PLOT}/credits", "Credits", actor="buyer")["items"][0]
    assert (before["credit_status"], before["seller_balance"], before["actor_balance"]) == ("ACTIVE", "90", "7")

    fire = h.verify("post_fire", key=f"e2e-fire-{suffix}")
    fire_view = h.api.get(f"/verifications/{fire['verification_id']}", "Verification")
    assert (fire_view["decision"], fire_view["reason"]) == ("FREEZE_REQUESTED", "FIRE_REVERSAL")
    # The freeze demo runs on the synthetic contract fixture and says so everywhere it is exposed.
    assert fire_view["evidence"]["dataset_kind"] == "SYNTHETIC"
    assert fire_view["evidence"]["plot_id"].startswith("SYNTHETIC")
    assert (fire_view["computation_mode"], fire_view["observation_mode"]) == ("CACHED_REPLAY", "HISTORICAL_REPLAY")
    journal = h.api.get(f"/events?plot_id={PLOT}&limit=100", "Events")["items"]
    assert any(e["kind"] == "VERIFICATION" and e["verification_id"] == fire["verification_id"]
               and "SYNTHETIC/CACHED_REPLAY" in e["message"] for e in journal)
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
    return {"harness": h, "batch_id": batch_id, "issue": issue_op, "transfer": confirmed, "freeze": freeze_op,
            "credits": after, "proof": proof, "fire_evidence_hash": fire_view["evidence_hash"],
            "signed_transactions": len(_signed_rows(h))}


def test_e2e_contract_fixture_mock_chain(tmp_path):
    result = _financial_flow(Harness(tmp_path), "mock", MockMining)
    h = result.pop("harness")
    assert result["fire_evidence_hash"] == EXPECTED["fire"]["evidence_hash"]
    assert result["signed_transactions"] == 4  # issue, buy, transfer, freeze: no duplicates after restart
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
    result = _financial_flow(h, "anvil", AnvilMining)
    h = result.pop("harness")
    h.worker.tick()  # heartbeat for /health worker UP
    assert result["signed_transactions"] == 4
    assert h.api.get("/health", "Health") == {"api": "UP", "db": "UP", "worker": "UP", "chain": "UP",
                                              "deployment_id": identity.deployment.deployment_id, "mode": "LOCAL_DEMO"}
    evidence_path = os.environ.get("BACKEND_E2E_EVIDENCE_OUT")
    if evidence_path:
        import json
        Path(evidence_path).write_text(json.dumps({"deployment": identity.deployment.__dict__, **result}, indent=2))


REAL_PLOT = "GR-EVROS-DADIA-001"
RS_ROOT = Path(__file__).resolve().parents[2] / "rs"


def _anvil_harness(tmp_path, **overrides) -> Harness:
    keys = {role: os.environ[f"BACKEND_E2E_KEY_{role.upper()}"] for role in ("issuer", "oracle", "buyer", "recipient")}
    return Harness(tmp_path, mode="LOCAL_DEMO", chain_adapter="web3", rpc_url=ANVIL,
                   deployment_path=Path(os.environ["BACKEND_E2E_DEPLOYMENT"]), private_keys=keys, **overrides)


@pytest.mark.skipif(not ANVIL, reason="set BACKEND_E2E_RPC_URL, BACKEND_E2E_DEPLOYMENT and BACKEND_E2E_KEY_* "
                                      "to run against a real local Anvil deployment")
def test_e2e_real_dadia_anvil(tmp_path):
    """Merged RS real Dadia bundles through Backend policy to a confirmed on-chain freeze.

    config/demo-authorizations.json only authorizes SYNTHETIC-PLOT-001, so this test writes a
    TEST-ONLY authorization for the real plot into tmp_path; it never touches config/.
    """
    import json

    from backend.app.ingest import import_evidence, register_plot
    from backend.tools.seed import plot_from_rs_request

    auth = tmp_path / "e2e-test-only-authorizations.json"
    auth.write_text(json.dumps({"mode": "E2E_TEST_ONLY", "authorizations": [{
        "demo_authorization_id": "E2E-TEST-DADIA-AUTH", "plot_id": REAL_PLOT, "amount": "100",
        "unit_price_wei": "1000000000000000", "issuer_actor": "issuer", "seller_actor": "issuer",
        "single_use": True, "certified_carbon_units": False}]}), encoding="utf-8")
    h = _anvil_harness(tmp_path / "state", authorizations_path=auth)
    assert h.chain.identity().ok, h.chain.identity().reason
    register_plot(h.ctx, plot_from_rs_request(json.loads((RS_ROOT / "configs/request_fire.json").read_text()),
                                              name="Dadia (Evros) wildfire AOI"))

    def load(bundle: str):
        root = RS_ROOT / "bundles" / bundle
        return import_evidence(h.ctx, (root / "verification.json").read_bytes(), root, computation_mode="COMPUTED",
                               expected_plot_id=REAL_PLOT)

    baseline = load("no_change")
    assert (baseline.decision, baseline.reason) == ("NO_RESTRICTION", "NO_SIGNIFICANT_CHANGE")
    issue = h.api.post(f"/plots/{REAL_PLOT}/issue", {"demo_authorization_id": "E2E-TEST-DADIA-AUTH"}, "issuer",
                       "real-dadia-issue", "OperationAccepted")
    issue_op = _poll_operation(h, issue["operation_id"])
    assert issue_op["transaction_state"] == "CONFIRMED", issue_op
    batch_id = issue_op["batch_id"]
    buy = h.api.post(f"/batches/{batch_id}/buy", {"amount": "10"}, "buyer", "real-dadia-buy", "OperationAccepted")
    assert _poll_operation(h, buy["operation_id"])["transaction_state"] == "CONFIRMED"

    fire = load("fire")
    fire_view = h.api.get(f"/verifications/{fire.verification_id}", "Verification")
    assert (fire.decision, fire.reason) == ("FREEZE_REQUESTED", "FIRE_REVERSAL")
    assert fire_view["evidence"]["dataset_kind"] == "REAL" and fire_view["computation_mode"] == "COMPUTED"
    assert (fire_view["evidence"]["firms"]["support"], fire_view["evidence"]["firms"]["hotspot_count"]) == ("SUPPORTED", 37)

    # Freeze submitted but not mined, backend restarted: the same signed freeze must confirm.
    AnvilMining.hold(h)
    h.run(3)
    freezes = h.operations("FREEZE")
    assert len(freezes) == 1 and freezes[0]["transaction_state"] == "SUBMITTED"
    pending_hash, signed_before = freezes[0]["tx_hash"], _signed_rows(h)
    h = h.restart()
    h.run(3)
    assert h.operations("FREEZE")[0]["transaction_state"] == "SUBMITTED" and _signed_rows(h) == signed_before
    AnvilMining.release(h)
    freeze_op = _poll_operation(h, freezes[0]["operation_id"])
    assert freeze_op["transaction_state"] == "CONFIRMED" and freeze_op["tx_hash"] == pending_hash
    receipt = freeze_op["receipt"]
    assert receipt["status"] == 1 and receipt["event_names"] == ["Frozen"] and receipt["state_readback_ok"] is True
    with h.ctx.db.reader() as conn:
        event = json.loads(conn.execute("SELECT decoded_event_json FROM operations WHERE operation_id=?",
                                        (freeze_op["operation_id"],)).fetchone()[0])
    assert event["name"] == "Frozen" and event["args"]["evidenceHash"] == fire.evidence_hash
    assert event["args"]["decisionHash"] == fire.decision_hash and event["args"]["reasonCode"] == 1
    readback = h.chain.get_batch(int(batch_id))
    assert (readback.credit_status, readback.evidence_hash, readback.decision_hash) == (
        "FROZEN", fire.evidence_hash, fire.decision_hash)
    credits = h.api.get(f"/plots/{REAL_PLOT}/credits", "Credits", actor="buyer")["items"][0]
    assert (credits["credit_status"], credits["seller_balance"], credits["actor_balance"]) == ("FROZEN", "90", "10")

    # Idempotency: re-importing the same fire bundle creates nothing and sends no second freeze.
    again = load("fire")
    h.run(3)
    oracle = h.chain.signer_address("oracle")
    assert again.created is False and again.verification_id == fire.verification_id
    assert len(h.operations("FREEZE")) == 1
    assert h.count("operation_signed_transactions", "sender_address=?", (oracle,)) == 1
    with pytest.raises(ContractRevert) as direct:
        h.chain.simulate("buyer", ContractCall("transfer", (int(batch_id), h.chain.signer_address("recipient"), 1)))
    assert direct.value.error_name == "BatchNotActive"
    proof = h.api.get(f"/verifications/{fire.verification_id}/proof", "Proof")
    assert proof["integrity_ok"] and [(a["event_name"], a["evidence_hash"]) for a in proof["anchors"]] == [
        ("Frozen", fire.evidence_hash)]

    evidence_path = os.environ.get("BACKEND_E2E_REAL_EVIDENCE_OUT")
    if evidence_path:
        Path(evidence_path).write_text(json.dumps({
            "deployment": h.chain.identity().deployment.__dict__, "plot_id": REAL_PLOT, "batch_id": batch_id,
            "baseline": baseline.__dict__, "fire": fire.__dict__, "issue": issue_op, "freeze": freeze_op,
            "frozen_event": event, "readback": readback.__dict__, "credits_buyer": credits,
            "repeat_import_created": again.created, "freeze_operations": len(h.operations("FREEZE")),
            "oracle_signed_transactions": 1, "direct_transfer_revert": direct.value.error_name,
            "restart_same_tx_hash": freeze_op["tx_hash"] == pending_hash}, indent=2))
