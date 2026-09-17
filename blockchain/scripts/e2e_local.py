#!/usr/bin/env python3
"""Backend-adapter style integration smoke for CarbonCreditRegistry on local Anvil.

Uses only what Backend receives in the handoff: the frozen ABI (contracts/contract-abi.json)
and the deployment manifest (deployment.json). Flow:

    verify deployment identity -> issue -> buy -> transfer -> freeze
    -> repeat freeze reverts (mined status 0, no logs) -> buy/transfer revert on FROZEN
    -> withdraw proceeds -> Anvil restart is detected as a deployment mismatch

Every successful step is CONFIRMED only by receipt status + expected decoded event + readback.

It always starts its own throwaway Anvil on a free port and deploys with tools/deploy-local.cjs
into a temporary directory. It never connects to the shared deployment in runtime/: Backend is
the only runtime oracle sender, so this smoke must not send `freeze` (or compete for nonces) on
the deployment Backend uses.

Not a pytest module on purpose: the shared `python -m pytest -q` must not require Anvil.
The issuance key/evidence/decision hashes below are synthetic smoke values, not the Backend
canonical JCS/SHA-256 derivations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from web3 import Web3
from web3.exceptions import ContractCustomError

ROOT = Path(__file__).resolve().parents[2]
ABI_PATH = ROOT / "contracts" / "contract-abi.json"
SCHEMA_PATH = ROOT / "contracts" / "deployment.schema.json"
DEPLOY_TOOL = ROOT / "blockchain" / "tools" / "deploy-local.cjs"
FIRE_REVERSAL = 1
STATUS = {0: "ACTIVE", 1: "FROZEN", 2: "REVOKED"}


class SmokeFailure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def sha256_bytes32(label: str) -> bytes:
    return hashlib.sha256(label.encode()).digest()


def hex0x(value) -> str:
    return "0x" + bytes(value).hex()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_anvil(port: int) -> subprocess.Popen:
    anvil = shutil.which("anvil")
    check(anvil is not None, "anvil not found on PATH (install Foundry)")
    proc = subprocess.Popen([anvil, "--port", str(port), "--chain-id", "31337", "--silent"])
    w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{port}"))
    for _ in range(100):
        if w3.is_connected():
            return proc
        time.sleep(0.1)
    proc.kill()
    raise SmokeFailure("anvil did not start")


def deploy(rpc_url: str, out_dir: Path) -> None:
    env = {**os.environ, "RPC_URL": rpc_url, "DEPLOYMENT_DIR": str(out_dir), "DEPLOYMENT_BUILD_DIR": str(out_dir)}
    subprocess.run(["node", str(DEPLOY_TOOL)], check=True, env=env, stdout=subprocess.DEVNULL)


class Adapter:
    """Minimal subset of what the Backend chain adapter must do."""

    def __init__(self, rpc_url: str, deployment: dict):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.deployment = deployment
        self.abi_bytes = ABI_PATH.read_bytes()
        self.abi = json.loads(self.abi_bytes)
        self.contract = self.w3.eth.contract(address=Web3.to_checksum_address(deployment["contract_address"]), abi=self.abi)
        self.roles = {k: Web3.to_checksum_address(v) for k, v in deployment["roles"].items()}
        self.errors = {
            Web3.keccak(text=f"{e['name']}({','.join(i['type'] for i in e['inputs'])})")[:4].hex(): e["name"]
            for e in self.abi
            if e["type"] == "error"
        }

    def verify_identity(self) -> dict:
        chain_id = str(self.w3.eth.chain_id)
        code = self.w3.eth.get_code(self.contract.address)
        code_hash = hex0x(Web3.keccak(code)) if code else None
        abi_sha = "0x" + hashlib.sha256(self.abi_bytes).hexdigest()
        result = {
            "chain_id_matches": chain_id == self.deployment["chain_id"],
            "code_present": bool(code),
            "code_hash_matches": code_hash == self.deployment["contract_code_hash"],
            "abi_sha256_matches": abi_sha == self.deployment["abi_sha256"],
        }
        result["ok"] = all(result.values())
        return result

    def transact(self, fn, sender: str, value: int = 0, event: str | None = None) -> dict:
        tx_hash = fn.transact({"from": sender, "value": value})
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        check(receipt["status"] == 1, f"{fn.fn_name} receipt status {receipt['status']}")
        record = {"tx_hash": hex0x(tx_hash), "block": receipt["blockNumber"], "status": receipt["status"], "gas_used": receipt["gasUsed"]}
        if event:
            decoded = self.contract.events[event]().process_receipt(receipt)
            check(len(decoded) == 1, f"expected exactly one {event} event, got {len(decoded)}")
            record["event"] = {"name": event, "args": {k: self._jsonable(v) for k, v in decoded[0]["args"].items()}}
        return record

    def expect_revert(self, fn, sender: str, error: str, value: int = 0) -> dict:
        """Proves the revert both via eth_call (decoded custom error) and via a mined transaction."""
        try:
            fn.call({"from": sender, "value": value})
        except ContractCustomError as exc:
            data = exc.data if isinstance(exc.data, str) else exc.message
            selector = data[2:10] if data.startswith("0x") else data[:8]
            decoded = self.errors.get(selector)
        else:
            raise SmokeFailure(f"{fn.fn_name} did not revert")
        check(decoded == error, f"{fn.fn_name}: expected {error}, got {decoded}")

        # Explicit gas skips estimation so the failing transaction is really mined.
        tx_hash = fn.transact({"from": sender, "value": value, "gas": 300_000})
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        check(receipt["status"] == 0, f"{fn.fn_name} unexpectedly succeeded on-chain")
        check(len(receipt["logs"]) == 0, f"{fn.fn_name} reverted but emitted logs")
        return {"error": decoded, "mined_tx_hash": hex0x(tx_hash), "status": 0, "logs": 0}

    def batch(self, batch_id: int) -> dict:
        names = [c["name"] for c in next(a for a in self.abi if a.get("name") == "getBatch")["outputs"][0]["components"]]
        view = dict(zip(names, self.contract.functions.getBatch(batch_id).call()))
        view["creditStatus"] = STATUS[view["creditStatus"]]
        return {k: self._jsonable(v) for k, v in view.items()}

    def balances(self, batch_id: int) -> dict:
        return {
            role: self.contract.functions.balanceOf(batch_id, self.roles[role]).call()
            for role in ("issuer", "buyer", "recipient")
        }

    @staticmethod
    def _jsonable(value):
        if isinstance(value, (bytes, bytearray)):
            return hex0x(value)
        if isinstance(value, int) and value > 2**53:
            return str(value)
        return value


def run_flow(adapter: Adapter) -> dict:
    c = adapter.contract.functions
    r = adapter.roles
    evidence: dict = {"deployment": adapter.deployment}

    identity = adapter.verify_identity()
    check(identity["ok"], f"deployment identity mismatch: {identity}")
    evidence["identity"] = identity

    now = adapter.w3.eth.get_block("latest")["timestamp"]
    amount, price = 100, 10**15
    seller = r["issuer"]  # config/demo-authorizations.json: seller_actor = issuer
    issuance_key = sha256_bytes32(f"SMOKE-ISSUANCE:{adapter.deployment['deployment_id']}")
    issue_evidence = sha256_bytes32("SMOKE-ISSUANCE-EVIDENCE")
    issue_observed = now - 86_400

    steps: dict = {}
    steps["issue"] = adapter.transact(
        c.issue(issuance_key, "SYNTHETIC-PLOT-001", seller, amount, price, issue_evidence, issue_observed), r["issuer"], event="Issued"
    )
    batch_id = steps["issue"]["event"]["args"]["batchId"]
    readback = adapter.batch(batch_id)
    check(readback["creditStatus"] == "ACTIVE" and readback["totalSupply"] == amount, f"issue readback {readback}")
    check(readback["issuanceKey"] == hex0x(issuance_key) and readback["seller"] == seller, "issue readback identity")
    steps["issue"]["readback"] = {"batch": readback, "balances": adapter.balances(batch_id)}
    check(steps["issue"]["readback"]["balances"]["issuer"] == amount, "seller balance after issue")

    steps["duplicate_issue"] = adapter.expect_revert(
        c.issue(issuance_key, "SYNTHETIC-PLOT-001", seller, amount, price, issue_evidence, issue_observed), r["issuer"], "DuplicateIssuance"
    )
    steps["unauthorized_freeze"] = adapter.expect_revert(
        c.freeze(batch_id, sha256_bytes32("x"), sha256_bytes32("y"), now, FIRE_REVERSAL), r["issuer"], "Unauthorized"
    )
    steps["wrong_payment"] = adapter.expect_revert(c.buy(batch_id, 10), r["buyer"], "IncorrectPayment", value=10 * price - 1)

    steps["buy"] = adapter.transact(c.buy(batch_id, 10), r["buyer"], value=10 * price, event="Purchased")
    bal = adapter.balances(batch_id)
    check(bal == {"issuer": 90, "buyer": 10, "recipient": 0}, f"balances after buy {bal}")
    steps["buy"]["readback"] = {"balances": bal}

    steps["transfer_active"] = adapter.transact(c.transfer(batch_id, r["recipient"], 3), r["buyer"], event="Transferred")
    bal = adapter.balances(batch_id)
    check(bal == {"issuer": 90, "buyer": 7, "recipient": 3}, f"balances after transfer {bal}")
    steps["transfer_active"]["readback"] = {"balances": bal}

    fire_evidence = sha256_bytes32("SMOKE-FIRE-EVIDENCE")
    decision = sha256_bytes32("SMOKE-FIRE-DECISION")
    fire_observed = now - 3_600
    steps["unknown_batch"] = adapter.expect_revert(c.transfer(batch_id + 1000, r["recipient"], 1), r["buyer"], "UnknownBatch")
    steps["stale_freeze"] = adapter.expect_revert(
        c.freeze(batch_id, fire_evidence, decision, issue_observed - 1, FIRE_REVERSAL), r["oracle"], "StaleObservation"
    )
    check(adapter.batch(batch_id)["creditStatus"] == "ACTIVE", "stale freeze changed status")
    steps["freeze"] = adapter.transact(
        c.freeze(batch_id, fire_evidence, decision, fire_observed, FIRE_REVERSAL), r["oracle"], event="Frozen"
    )
    frozen = adapter.batch(batch_id)
    check(frozen["creditStatus"] == "FROZEN", f"status after freeze {frozen['creditStatus']}")
    check(frozen["evidenceHash"] == hex0x(fire_evidence) and frozen["decisionHash"] == hex0x(decision), "freeze hashes readback")
    check(frozen["lastObservedAt"] == fire_observed and frozen["frozenAt"] > 0, "freeze time readback")
    ev = steps["freeze"]["event"]["args"]
    check(ev["evidenceHash"] == hex0x(fire_evidence) and ev["decisionHash"] == hex0x(decision) and ev["reasonCode"] == 1, "Frozen event args")
    steps["freeze"]["readback"] = {"batch": frozen}

    steps["repeat_freeze"] = adapter.expect_revert(
        c.freeze(batch_id, sha256_bytes32("newer"), sha256_bytes32("newer-decision"), fire_observed + 1, FIRE_REVERSAL), r["oracle"], "BatchNotActive"
    )
    steps["transfer_after_freeze_buyer"] = adapter.expect_revert(c.transfer(batch_id, r["recipient"], 1), r["buyer"], "BatchNotActive")
    steps["transfer_after_freeze_seller"] = adapter.expect_revert(c.transfer(batch_id, r["recipient"], 1), seller, "BatchNotActive")
    steps["buy_after_freeze"] = adapter.expect_revert(c.buy(batch_id, 1), r["recipient"], "BatchNotActive", value=price)
    bal = adapter.balances(batch_id)
    check(bal == {"issuer": 90, "buyer": 7, "recipient": 3}, f"balances changed after freeze {bal}")
    check(adapter.batch(batch_id) == frozen, "batch state changed by rejected calls")
    steps["after_freeze_readback"] = {"balances": bal, "batch_unchanged": True}

    steps["withdraw"] = adapter.transact(c.withdrawProceeds(), seller, event="ProceedsWithdrawn")
    check(int(steps["withdraw"]["event"]["args"]["amountWei"]) == 10 * price, "withdrawn amount")
    steps["withdraw_again"] = adapter.expect_revert(c.withdrawProceeds(), seller, "NoProceeds")

    evidence["batch_id"] = batch_id
    evidence["steps"] = steps
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence-out", type=Path, default=ROOT / "blockchain" / "runtime" / "e2e-evidence.json")
    args = parser.parse_args()

    schema = Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=FormatChecker())
    anvil = None
    tmp = None
    try:
        port = free_port()
        rpc_url = f"http://127.0.0.1:{port}"
        anvil = start_anvil(port)
        tmp = tempfile.TemporaryDirectory()
        deploy(rpc_url, Path(tmp.name))
        manifest = Path(tmp.name) / "deployment.json"

        deployment = json.loads(manifest.read_text())
        schema.validate(deployment)
        evidence = run_flow(Adapter(rpc_url, deployment))
        evidence["deployment_schema_valid"] = True

        anvil.terminate()
        anvil.wait(timeout=10)
        anvil = start_anvil(port)
        restarted = Adapter(rpc_url, deployment).verify_identity()
        check(not restarted["ok"], "restarted Anvil was not detected as a deployment mismatch")
        evidence["restart_detection"] = restarted

        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(json.dumps(evidence, indent=2) + "\n")
        s = evidence["steps"]
        print(json.dumps({
            "ok": True,
            "batch_id": evidence["batch_id"],
            "identity": evidence["identity"]["ok"],
            "issue": s["issue"]["tx_hash"],
            "buy": s["buy"]["tx_hash"],
            "transfer_active": s["transfer_active"]["tx_hash"],
            "freeze": s["freeze"]["tx_hash"],
            "frozen_status": s["freeze"]["readback"]["batch"]["creditStatus"],
            "reverts": {k: v["error"] for k, v in s.items() if isinstance(v, dict) and "error" in v},
            "balances_after_freeze": s["after_freeze_readback"]["balances"],
            "restart_detected": not evidence["restart_detection"]["ok"],
            "evidence": str(args.evidence_out),
        }, indent=2))
        return 0
    except SmokeFailure as exc:
        print(f"E2E FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        if anvil is not None:
            anvil.terminate()
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    sys.exit(main())
