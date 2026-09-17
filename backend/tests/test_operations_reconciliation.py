"""Chain operations: gates, idempotency, nonce/restart reconciliation, confirmation rules, repeated freeze."""
from __future__ import annotations

import json
import uuid

import pytest

from backend.app.chain.base import ContractCall, ContractRevert
from backend.app.contracts import hash_to_bytes32
from backend.app.worker import Worker

from .conftest import AUTH, EXPECTED, FIXTURES, PLOT, Harness, fixture_evidence

ISSUE_BODY = {"demo_authorization_id": AUTH}


def _signed(h: Harness):
    with h.ctx.db.reader() as conn:
        return conn.execute("SELECT operation_id, nonce, tx_hash, raw_transaction FROM operation_signed_transactions "
                            "ORDER BY nonce").fetchall()


def _buy(h: Harness, batch_id: str, amount: str = "10", key: str = "buy-key-00001", actor: str = "buyer"):
    return h.api.post(f"/batches/{batch_id}/buy", {"amount": amount}, actor, key, "OperationAccepted")


def _op(h: Harness, operation_id: str) -> dict:
    return h.api.get(f"/operations/{operation_id}", "Operation")


# -- request idempotency and gates --------------------------------------------------------------------------
def test_issue_replay_returns_same_operation_and_conflict_on_other_body(harness):
    harness.verify("baseline")
    first = harness.api.post(f"/plots/{PLOT}/issue", ISSUE_BODY, "issuer", "issue-idem-key", "OperationAccepted")
    replay = harness.api.post(f"/plots/{PLOT}/issue", ISSUE_BODY, "issuer", "issue-idem-key", "OperationAccepted")
    assert first == replay and len(harness.operations("ISSUE")) == 1
    other = harness.api.post(f"/plots/{PLOT}/issue", {"demo_authorization_id": "SYNTHETIC-AUTH-999"}, "issuer",
                             "issue-idem-key", "Error", status=409)
    assert other["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    harness.run()
    # Replay after confirmation still returns the original accepted operation, never a second issuance.
    assert harness.api.post(f"/plots/{PLOT}/issue", ISSUE_BODY, "issuer", "issue-idem-key",
                            "OperationAccepted") == first
    assert len(harness.operations("ISSUE")) == 1 and len(_signed(harness)) == 1


def test_single_use_authorization_rejects_second_issue_key(issued):
    h, _ = issued
    error = h.api.post(f"/plots/{PLOT}/issue", ISSUE_BODY, "issuer", "issue-second-key", "Error", status=409)
    assert error["error"]["code"] in ("ACTION_NOT_ALLOWED", "AUTHORIZATION_ALREADY_USED")
    assert len(h.operations("ISSUE")) == 1


def test_issue_parameters_come_from_authorization_and_hashes(issued):
    h, batch_id = issued
    view = h.chain.get_batch(int(batch_id))
    assert view.total_supply == 100 and view.unit_price_wei == 10**15
    assert view.evidence_hash == EXPECTED["no_change"]["evidence_hash"]
    from backend.app.contracts import digest
    deployment_id = h.chain.identity().deployment.deployment_id
    assert view.issuance_key == digest({"plot_id": PLOT, "demo_authorization_id": AUTH, "deployment_id": deployment_id})


def test_buy_transfer_gates(issued):
    h, batch_id = issued
    assert h.api.post(f"/batches/{batch_id}/buy", {"amount": "10"}, "issuer", "seller-buys-own", "Error",
                      status=403)["error"]["code"] == "FORBIDDEN"
    assert h.api.post(f"/batches/{batch_id}/buy", {"amount": "101"}, "buyer", "too-many-units", "Error",
                      status=409)["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert h.api.post("/batches/999/buy", {"amount": "1"}, "buyer", "unknown-batch", "Error", status=404)
    assert h.api.post(f"/batches/{batch_id}/buy", {"amount": "0"}, "buyer", "zero-amount", "Error", status=422)
    assert h.api.post(f"/batches/{batch_id}/transfer", {"to_actor": "buyer", "amount": "1"}, "buyer",
                      "self-transfer", "Error", status=422)["error"]["code"] == "INVALID_RECIPIENT"
    assert h.api.post(f"/batches/{batch_id}/transfer", {"to_actor": "recipient", "amount": "1"}, "buyer",
                      "no-balance-yet", "Error", status=409)["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert h.count("operations") == 1  # only the issuance


def test_buy_and_transfer_confirm_with_real_balance_deltas(issued):
    h, batch_id = issued
    buy = _buy(h, batch_id)
    h.run()
    op = _op(h, buy["operation_id"])
    assert op["transaction_state"] == "CONFIRMED" and op["receipt"]["event_names"] == ["Purchased"]
    transfer = h.api.post(f"/batches/{batch_id}/transfer", {"to_actor": "recipient", "amount": "3"}, "buyer",
                          "transfer-key-01", "OperationAccepted")
    h.run()
    assert _op(h, transfer["operation_id"])["transaction_state"] == "CONFIRMED"
    credits = {actor: h.api.get(f"/plots/{PLOT}/credits", "Credits", actor=actor)["items"][0]
               for actor in ("issuer", "buyer", "recipient")}
    assert credits["buyer"]["seller_balance"] == "90"
    assert (credits["buyer"]["actor_balance"], credits["recipient"]["actor_balance"]) == ("7", "3")
    assert credits["buyer"]["can_buy"] and not credits["issuer"]["can_buy"]


# -- timeout, restart and nonce safety -------------------------------------------------------------------------
def test_receipt_timeout_stays_submitted_and_restart_reuses_same_transaction(issued, tmp_path):
    h, batch_id = issued
    h.chain.set_controls(hold_mining=True)
    buy = _buy(h, batch_id)
    h.run(5)
    op = _op(h, buy["operation_id"])
    assert op["transaction_state"] == "SUBMITTED" and op["receipt"] is None
    assert op["error"]["code"] == "RECEIPT_PENDING"
    signed_before = _signed(h)
    restarted = h.restart()  # backend crash + restart while pending
    restarted.run(5)
    assert _op(restarted, buy["operation_id"])["transaction_state"] == "SUBMITTED"
    assert _signed(restarted) == signed_before  # no re-sign, no new nonce, same bytes
    restarted.chain.set_controls(hold_mining=False)
    restarted.chain.mine()
    restarted.run(1)
    confirmed = _op(restarted, buy["operation_id"])
    assert confirmed["transaction_state"] == "CONFIRMED" and confirmed["tx_hash"] == signed_before[-1]["tx_hash"]
    assert len(_signed(restarted)) == 2 and restarted.count("events", "kind='TX_CONFIRMED'") == 2


def test_crash_after_signing_before_broadcast_rebroadcasts_same_bytes(issued):
    h, batch_id = issued
    h.chain.set_controls(drop_broadcasts=1)  # broadcast attempt fails after bytes were persisted
    buy = _buy(h, batch_id)
    h.run(1)
    op = _op(h, buy["operation_id"])
    assert op["transaction_state"] == "QUEUED" and op["tx_hash"] is not None
    assert op["error"]["code"] == "CHAIN_UNAVAILABLE"
    signed = _signed(h)
    restarted = h.restart()
    restarted.run(1)
    assert _op(restarted, buy["operation_id"])["transaction_state"] == "CONFIRMED"
    assert _signed(restarted) == signed
    assert restarted.count("events", "kind='TX_SUBMITTED' AND operation_id=?", (buy["operation_id"],)) == 1


def test_chain_unavailable_keeps_intent_queued_then_recovers(issued):
    h, batch_id = issued
    buy = _buy(h, batch_id)
    h.chain.set_controls(available=False)
    h.run(3)
    op = _op(h, buy["operation_id"])
    assert op["transaction_state"] == "QUEUED" and op["error"]["code"] == "CHAIN_UNAVAILABLE"
    assert len(_signed(h)) == 1  # nothing signed while chain is down
    assert h.api.get(f"/plots/{PLOT}/credits", None, actor="buyer", status=503)["error"]["code"] == "CHAIN_UNAVAILABLE"
    h.chain.set_controls(available=True)
    h.run(1)
    assert _op(h, buy["operation_id"])["transaction_state"] == "CONFIRMED"


def test_nonces_are_serialized_per_sender(issued):
    h, batch_id = issued
    h.chain.set_controls(hold_mining=True)
    first = _buy(h, batch_id, amount="1", key="buy-nonce-0001")
    second = _buy(h, batch_id, amount="2", key="buy-nonce-0002")
    h.run(2)
    buyer = h.chain.signer_address("buyer")
    with h.ctx.db.reader() as conn:
        nonces = [r[0] for r in conn.execute("SELECT nonce FROM operation_signed_transactions WHERE sender_address=? "
                                             "ORDER BY nonce", (buyer,))]
    assert nonces == [0, 1]
    h.chain.set_controls(hold_mining=False)
    h.chain.mine()
    h.run(1)
    assert {_op(h, o["operation_id"])["transaction_state"] for o in (first, second)} == {"CONFIRMED"}


def test_only_one_worker_holds_the_signer_lease(issued):
    h, _ = issued
    other = Worker(h.ctx, worker_id="second-worker")
    assert h.worker.tick() is True
    assert other.tick() is False


# -- confirmation rules ----------------------------------------------------------------------------------------
def test_reverted_receipt_marks_failed(issued):
    h, batch_id = issued
    h.chain.set_controls(hold_mining=True)
    a = _buy(h, batch_id, amount="60", key="buy-revert-001")
    b = _buy(h, batch_id, amount="60", key="buy-revert-002")  # both pass gates; together exceed inventory
    h.run(2)
    h.chain.set_controls(hold_mining=False)
    h.chain.mine()
    h.run(1)
    states = {_op(h, o["operation_id"])["transaction_state"] for o in (a, b)}
    assert states == {"CONFIRMED", "FAILED"}
    failed = next(_op(h, o["operation_id"]) for o in (a, b) if _op(h, o["operation_id"])["transaction_state"] == "FAILED")
    assert failed["error"]["code"] == "TX_REVERTED" and failed["receipt"] is None and failed["tx_hash"]
    assert h.count("events", "kind='TX_FAILED'") == 1


def test_receipt_without_expected_event_is_never_confirmed(issued):
    h, batch_id = issued
    h.chain.set_controls(omit_events=1)
    buy = _buy(h, batch_id)
    h.run(3)
    op = _op(h, buy["operation_id"])
    assert op["transaction_state"] == "SUBMITTED" and op["receipt"] is None
    assert op["error"]["code"] == "EXPECTED_EVENT_MISSING"
    assert h.count("events", "kind='TX_CONFIRMED' AND operation_id=?", (buy["operation_id"],)) == 0


def test_readback_mismatch_is_never_confirmed(harness):
    harness.verify("baseline")
    harness.chain.set_controls(corrupt_readback=True)
    accepted = harness.api.post(f"/plots/{PLOT}/issue", ISSUE_BODY, "issuer", "issue-readback", "OperationAccepted")
    harness.run(3)
    op = _op(harness, accepted["operation_id"])
    assert op["transaction_state"] == "SUBMITTED" and op["error"]["code"] == "READBACK_MISMATCH"
    assert harness.count("batches") == 0
    harness.chain.set_controls(corrupt_readback=False)
    harness.run(1)
    assert _op(harness, accepted["operation_id"])["transaction_state"] == "CONFIRMED"


def test_preflight_revert_fails_without_sending(issued):
    h, batch_id = issued
    buy = _buy(h, batch_id, amount="5", key="buy-preflight-1")
    # The stored intent would revert on chain (wrong payment): the worker must fail it before signing.
    with h.ctx.db.transaction() as conn:
        conn.execute("UPDATE operations SET intent_json=? WHERE operation_id=?",
                     (json.dumps({"function": "buy", "args": [{"type": "uint", "value": batch_id},
                                                              {"type": "uint", "value": "5"}],
                                  "value_wei": "1", "seller": h.chain.signer_address("issuer")}),
                      buy["operation_id"]))
    h.run(1)
    op = _op(h, buy["operation_id"])
    assert op["transaction_state"] == "FAILED" and op["error"]["details"]["contract_error"] == "IncorrectPayment"
    assert op["tx_hash"] is None and len(_signed(h)) == 1


def test_deployment_change_stops_operations_and_never_rebroadcasts(issued, tmp_path):
    h, batch_id = issued
    buy = _buy(h, batch_id, key="buy-before-redeploy")
    # A new local deployment appears (new ledger == Anvil restart + redeploy with a new deployment_id).
    from backend.app.chain.mock import MockChainAdapter
    h.ctx.chain = MockChainAdapter(tmp_path / "redeployed-chain.sqlite")
    h.run(1)
    op = _op(h, buy["operation_id"])
    assert op["transaction_state"] == "FAILED" and op["error"]["code"] == "DEPLOYMENT_MISMATCH"
    assert op["tx_hash"] is None
    assert h.api.get(f"/plots/{PLOT}/credits", "Credits", actor="buyer") == {"items": []}  # old batches not reused


# -- freeze: oracle-only, once per batch, FROZEN -> FROZEN sends nothing -------------------------------------------
def _second_fire_evidence(tmp_path):
    evidence = fixture_evidence("fire")
    evidence["limitations"] = evidence["limitations"] + ["Re-run of the same synthetic scene with another note"]
    path = tmp_path / "second_fire.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return evidence


def test_fire_decision_freezes_once_and_direct_transfer_reverts(issued, tmp_path):
    h, batch_id = issued
    _buy(h, batch_id)
    h.run()
    fire = h.verify("post_fire")
    freezes = h.operations("FREEZE")
    assert len(freezes) == 1 and freezes[0]["transaction_state"] == "CONFIRMED"
    assert freezes[0]["verification_id"] == fire["verification_id"] and freezes[0]["sender_role"] == "oracle"
    credit = h.api.get(f"/plots/{PLOT}/credits", "Credits", actor="buyer")["items"][0]
    assert credit["credit_status"] == "FROZEN" and credit["actor_balance"] == "10"
    assert credit["decision_hash"] == EXPECTED["fire"]["decision_hash"]
    assert not credit["can_buy"] and not credit["can_transfer_backend"]
    # Direct contract calls bypassing the backend revert at contract level.
    buyer_to = h.chain.signer_address("recipient")
    with pytest.raises(ContractRevert) as transfer_revert:
        h.chain.simulate("buyer", ContractCall("transfer", (int(batch_id), buyer_to, 1)))
    assert transfer_revert.value.error_name == "BatchNotActive"
    with pytest.raises(ContractRevert) as refreeze:
        h.chain.simulate("oracle", ContractCall("freeze", (int(batch_id), hash_to_bytes32("0x" + "ab" * 32),
                                                           hash_to_bytes32("0x" + "cd" * 32), 1722488400, 1)))
    assert refreeze.value.error_name == "BatchNotActive"
    # Backend API also refuses.
    assert h.api.post(f"/batches/{batch_id}/transfer", {"to_actor": "recipient", "amount": "1"}, "buyer",
                      "transfer-frozen", "Error", status=409)["error"]["code"] == "BATCH_NOT_ACTIVE"
    proof = h.api.get(f"/verifications/{fire['verification_id']}/proof", "Proof")
    assert [a["event_name"] for a in proof["anchors"]] == ["Frozen"]


def test_repeated_fire_evidence_and_requests_send_no_second_freeze(issued, tmp_path):
    h, batch_id = issued
    first = h.verify("post_fire", key="verify-fire-first")
    h.verify("post_fire", key="verify-fire-again")  # duplicate request/evidence
    frozen_events_before = h.count("events", "kind='TX_CONFIRMED'")
    new_evidence = _second_fire_evidence(tmp_path)
    from backend.app.ingest import import_evidence
    result = import_evidence(h.ctx, new_evidence, FIXTURES, computation_mode="CACHED_REPLAY")
    assert result.created and result.decision == "FREEZE_REQUESTED" and result.evidence_hash != EXPECTED["fire"]["evidence_hash"]
    h.run(5)
    assert len(h.operations("FREEZE")) == 1  # FROZEN -> FROZEN: no second freeze transaction
    assert h.count("events", "kind='TX_CONFIRMED'") == frozen_events_before
    assert h.count("operation_signed_transactions", "sender_address=?", (h.chain.signer_address("oracle"),)) == 1
    # The new evidence is stored separately and is NOT given the old on-chain anchor.
    new_proof = h.api.get(f"/verifications/{result.verification_id}/proof", "Proof")
    assert new_proof["anchors"] == [] and new_proof["integrity_ok"]
    old_proof = h.api.get(f"/verifications/{first['verification_id']}/proof", "Proof")
    assert old_proof["anchors"][0]["evidence_hash"] == EXPECTED["fire"]["evidence_hash"]


def test_chain_already_frozen_with_lagging_db_sends_no_freeze(issued):
    h, batch_id = issued
    # The batch is FROZEN on chain, but SQLite has no freeze operation (e.g. restored older DB backup).
    oracle = h.chain.signer_address("oracle")
    call = ContractCall("freeze", (int(batch_id), hash_to_bytes32(EXPECTED["fire"]["evidence_hash"]),
                                   hash_to_bytes32(EXPECTED["fire"]["decision_hash"]), 1722488400, 1))
    tx = h.chain.sign("oracle", call, h.chain.pending_nonce(oracle))
    h.chain.broadcast(tx.raw, tx.tx_hash)
    assert h.chain.get_batch(int(batch_id)).credit_status == "FROZEN"
    h.verify("post_fire")
    h.run(3)
    assert h.operations("FREEZE") == []
    assert h.count("audit_log", "category='FREEZE_NOT_SENT_BATCH_NOT_ACTIVE'") >= 1


def test_pending_freeze_blocks_actions_and_is_not_frozen(issued):
    h, batch_id = issued
    h.chain.set_controls(hold_mining=True)
    h.verify("post_fire")
    freeze = h.operations("FREEZE")[0]
    assert freeze["transaction_state"] == "SUBMITTED"
    plot = h.api.get(f"/plots/{PLOT}", "Plot", actor="buyer")
    assert not (plot["can_buy"] or plot["can_transfer_backend"]) and "Freeze requested" in plot["action_block_reason"]
    assert h.api.get(f"/plots/{PLOT}/credits", "Credits", actor="buyer")["items"][0]["credit_status"] == "ACTIVE"
    h.run(3)
    assert len(h.operations("FREEZE")) == 1  # pending freeze is reconciled, not duplicated
    h.chain.set_controls(hold_mining=False)
    h.chain.mine()
    h.run(1)
    assert h.operations("FREEZE")[0]["transaction_state"] == "CONFIRMED"


def test_unsent_buy_is_not_signed_after_fire_decision(issued):
    h, batch_id = issued
    buy = _buy(h, batch_id, key="buy-before-fire")  # accepted while NO_RESTRICTION, not yet processed
    accepted = h.api.post(f"/plots/{PLOT}/verify", {"scenario_id": "post_fire"}, "issuer", "fire-after-buy",
                          "JobAccepted")
    h.worker.process_jobs()  # fire decision lands before the worker reaches the queued buy
    h.run(3)
    op = _op(h, buy["operation_id"])
    assert op["transaction_state"] == "FAILED" and op["error"]["code"] == "ACTION_NO_LONGER_ALLOWED"
    assert op["tx_hash"] is None
    assert h.api.get(f"/jobs/{accepted['job_id']}", "Job")["state"] == "SUCCEEDED"
    assert h.operations("FREEZE")[0]["transaction_state"] == "CONFIRMED"
    assert h.api.get(f"/plots/{PLOT}/credits", "Credits", actor="buyer")["items"][0]["actor_balance"] == "0"


def test_negative_branches_never_freeze(issued):
    h, _ = issued
    h.verify("insufficient")
    h.run(3)
    assert h.operations("FREEZE") == []
    unattributed = fixture_evidence("fire")
    unattributed["firms"].update(support="NOT_FOUND", hotspot_count=0, matched_points_artifact_id=None)
    from backend.app.ingest import import_evidence
    result = import_evidence(h.ctx, unattributed, FIXTURES, computation_mode="CACHED_REPLAY")
    assert result.reason == "DISTURBANCE_UNATTRIBUTED"
    h.run(3)
    assert h.operations("FREEZE") == []


def test_superseded_older_fire_evidence_sends_no_freeze(issued):
    h, _ = issued
    older = fixture_evidence("fire")
    # Valid FREEZE_REQUESTED evidence observed BEFORE the accepted baseline (2024-07-10).
    for scene, date in (("before", "2023-06-01T05:00:00Z"), ("after", "2023-07-01T05:00:00Z")):
        older["observation"][scene]["acquired_at"] = date
    older["firms"].update(window_start="2023-06-01T05:00:00Z", window_end="2023-07-01T05:00:00Z")
    from backend.app.ingest import import_evidence, plan_freeze_intents
    result = import_evidence(h.ctx, older, FIXTURES, computation_mode="CACHED_REPLAY")
    assert result.decision == "FREEZE_REQUESTED"
    assert plan_freeze_intents(h.ctx, PLOT) == []
    h.run(3)
    assert h.operations("FREEZE") == []
    assert h.api.get(f"/verifications/{result.verification_id}", "Verification")["is_latest"] is False


def test_freeze_requires_existing_batch(harness):
    harness.verify("post_fire")
    harness.run(3)
    assert harness.operations("FREEZE") == []
