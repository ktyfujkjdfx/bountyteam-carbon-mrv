"""Adapter boundary: mock and real web3 adapters expose one interface; identity checks fail closed."""
from __future__ import annotations

import inspect
import json
import socket
import uuid

from backend.app.chain.base import ChainAdapter
from backend.app.chain.mock import MockChainAdapter
from backend.app.chain.web3_adapter import Web3ChainAdapter
from backend.app.contracts import abi_sha256

DUMMY_KEY = "0x" + "11" * 32  # arbitrary non-funded value; real keys only come from the environment


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _manifest(tmp_path, **overrides):
    manifest = {"deployment_id": str(uuid.uuid4()), "chain_id": "31337",
                "contract_address": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
                "deployment_tx_hash": "0x" + "1" * 64, "contract_code_hash": "0x" + "2" * 64,
                "abi_sha256": abi_sha256(),
                "roles": {"owner": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
                          "issuer": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
                          "oracle": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
                          "buyer": "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
                          "recipient": "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"}}
    manifest.update(overrides)
    path = tmp_path / "deployment.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_mock_and_real_adapter_implement_the_same_interface():
    required = {name for name, _ in inspect.getmembers(ChainAdapter, inspect.isfunction) if not name.startswith("_")}
    for adapter in (MockChainAdapter, Web3ChainAdapter):
        missing = {name for name in required if not callable(getattr(adapter, name, None))}
        assert not missing, (adapter.__name__, missing)
        for name in required:
            expected = list(inspect.signature(getattr(ChainAdapter, name)).parameters)
            assert list(inspect.signature(getattr(adapter, name)).parameters)[:len(expected)] == expected


def test_real_adapter_error_selectors_match_blockchain_handoff(tmp_path):
    adapter = Web3ChainAdapter(f"http://127.0.0.1:{_free_port()}", _manifest(tmp_path), {})
    # Selectors published in the Blockchain handoff README (feat/chain-registry).
    assert adapter._errors["0xb5cf512a"] == "BatchNotActive"
    assert adapter._errors["0x82b42900"] == "Unauthorized"
    assert adapter._errors["0x119a7627"] == "UnknownBatch"
    assert adapter._errors["0x53e2a57a"] == "DuplicateIssuance"


def test_real_adapter_identity_fails_closed_when_rpc_down(tmp_path):
    adapter = Web3ChainAdapter(f"http://127.0.0.1:{_free_port()}", _manifest(tmp_path), {}, request_timeout=0.5)
    status = adapter.identity()
    assert not status.ok and status.reason.startswith("CHAIN_UNAVAILABLE") and status.deployment is None


def test_real_adapter_rejects_invalid_or_missing_manifest(tmp_path):
    bad = _manifest(tmp_path, contract_code_hash="0x" + "0" * 64)  # schema forbids zero code hash
    status = Web3ChainAdapter("http://127.0.0.1:1", bad, {}).identity()
    assert not status.ok and status.reason.startswith("DEPLOYMENT_MANIFEST_INVALID")
    missing = Web3ChainAdapter("http://127.0.0.1:1", tmp_path / "absent.json", {}).identity()
    assert not missing.ok and missing.reason.startswith("DEPLOYMENT_MANIFEST_INVALID")


def test_mock_adapter_is_marked_and_not_a_network():
    from backend.app.chain.mock import MOCK_CHAIN_ID
    assert MockChainAdapter.kind == "mock" and Web3ChainAdapter.kind == "web3"
    assert MOCK_CHAIN_ID == "0"  # never impersonates Anvil 31337 or a public chain id


def test_private_keys_are_not_exposed_in_settings_repr():
    from backend.app.config import load_settings
    settings = load_settings({"BACKEND_DEMO_SESSION": "repr-demo-session-000",
                              "BACKEND_PRIVATE_KEY_ORACLE": DUMMY_KEY})
    assert settings.private_keys["oracle"] == DUMMY_KEY
    assert DUMMY_KEY not in repr(settings)
