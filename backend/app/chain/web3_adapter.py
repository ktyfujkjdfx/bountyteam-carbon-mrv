"""Real chain adapter (local Anvil) over the frozen compiled ABI.

Transactions are signed locally from environment-provided keys so the signed bytes
and tx hash can be persisted BEFORE broadcast. Deployment identity (chain ID,
runtime code hash, ABI hash, role addresses) must match the manifest or every
chain operation is refused.

Calls are synchronous; FastAPI runs sync route handlers in a worker threadpool
and the operation worker runs in its own thread/process, so the asyncio event
loop is never blocked by RPC I/O.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import requests
from eth_account import Account
from web3 import Web3
from web3.exceptions import (ContractCustomError, ContractLogicError, MismatchedABI, ProviderConnectionError,
                             TimeExhausted, TransactionNotFound, Web3RPCError)

from ..contracts import abi, abi_sha256, bytes32_to_hash, deployment_validator, read_json, schema_errors
from .base import (CREDIT_STATUS, BatchView, ChainReceipt, ChainUnavailable, ContractCall, ContractRevert,
                   DecodedEvent, Deployment, IdentityStatus, NonceConsumed, SignedTransaction)

TRANSPORT_ERRORS = (requests.exceptions.RequestException, ProviderConnectionError, TimeExhausted, OSError,
                    TimeoutError)
EVENT_NAMES = ("Issued", "Purchased", "Transferred", "Frozen", "ProceedsWithdrawn",
               "IssuerPermissionChanged", "OraclePermissionChanged")


def _normalize(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return bytes32_to_hash(bytes(value)) if len(value) == 32 else "0x" + bytes(value).hex()
    if isinstance(value, str) and value.startswith("0x") and len(value) == 42:
        return value.lower()
    return value


class Web3ChainAdapter:
    kind = "web3"

    def __init__(self, rpc_url: str, deployment_path: Path, private_keys: dict[str, str],
                 request_timeout: float = 10.0, identity_ttl: float = 3.0):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": request_timeout}))
        self.deployment_path = Path(deployment_path)
        self._accounts = {role: Account.from_key(key) for role, key in private_keys.items()}
        self._identity_ttl = identity_ttl
        self._identity: tuple[float, IdentityStatus] | None = None
        self._lock = threading.Lock()
        self._errors = {}
        for item in abi():
            if item["type"] == "error":
                signature = item["name"] + "(" + ",".join(i["type"] for i in item["inputs"]) + ")"
                self._errors["0x" + Web3.keccak(text=signature)[:4].hex()] = item["name"]

    # -- identity --------------------------------------------------------------------------------
    def _load_deployment(self) -> Deployment:
        manifest = read_json(self.deployment_path)
        errors = schema_errors(deployment_validator(), manifest)
        if errors:
            raise ValueError("deployment manifest does not match deployment.schema.json")
        return Deployment(deployment_id=manifest["deployment_id"], chain_id=manifest["chain_id"],
                          contract_address=manifest["contract_address"],
                          contract_code_hash=manifest["contract_code_hash"],
                          abi_sha256=manifest["abi_sha256"], roles=manifest["roles"])

    def identity(self) -> IdentityStatus:
        with self._lock:
            cached = self._identity
            if cached and time.monotonic() - cached[0] < self._identity_ttl:
                return cached[1]
            status = self._check_identity()
            self._identity = (time.monotonic(), status)
            return status

    def _check_identity(self) -> IdentityStatus:
        try:
            deployment = self._load_deployment()
        except (OSError, ValueError) as exc:
            return IdentityStatus(False, None, "DEPLOYMENT_MANIFEST_INVALID: " + type(exc).__name__)
        try:
            chain_id = str(self.w3.eth.chain_id)
            code = bytes(self.w3.eth.get_code(Web3.to_checksum_address(deployment.contract_address)))
        except TRANSPORT_ERRORS as exc:
            return IdentityStatus(False, None, "CHAIN_UNAVAILABLE: " + type(exc).__name__)
        if chain_id != deployment.chain_id:
            return IdentityStatus(False, None, "CHAIN_ID_MISMATCH")
        if not code or "0x" + Web3.keccak(code).hex() != deployment.contract_code_hash.lower():
            return IdentityStatus(False, None, "CODE_HASH_MISMATCH")
        if abi_sha256() != deployment.abi_sha256:
            return IdentityStatus(False, None, "ABI_HASH_MISMATCH")
        for role, account in self._accounts.items():
            if account.address.lower() != deployment.roles[role].lower():
                return IdentityStatus(False, None, "SIGNER_ROLE_MISMATCH: " + role)
        return IdentityStatus(True, deployment)

    def _deployment(self) -> Deployment:
        status = self.identity()
        if not status.ok or status.deployment is None:
            raise ChainUnavailable(status.reason or "deployment identity not verified")
        return status.deployment

    def _contract(self):
        deployment = self._deployment()
        return self.w3.eth.contract(address=Web3.to_checksum_address(deployment.contract_address), abi=abi())

    # -- accounts --------------------------------------------------------------------------------
    def signer_address(self, role: str) -> str:
        if role in self._accounts:
            return self._accounts[role].address.lower()
        return self._deployment().roles[role].lower()

    def pending_nonce(self, address: str) -> int:
        return self._rpc(lambda: self.w3.eth.get_transaction_count(Web3.to_checksum_address(address), "pending"))

    def mined_nonce(self, address: str) -> int:
        return self._rpc(lambda: self.w3.eth.get_transaction_count(Web3.to_checksum_address(address), "latest"))

    # -- transactions ----------------------------------------------------------------------------
    def _rpc(self, fn):
        try:
            return fn()
        except TRANSPORT_ERRORS as exc:
            raise ChainUnavailable(type(exc).__name__) from None

    def _revert_name(self, exc: Exception) -> str:
        data = getattr(exc, "data", None)
        if isinstance(data, dict):
            data = data.get("data")
        if isinstance(data, str) and len(data) >= 10:
            return self._errors.get(data[:10].lower(), "UnknownContractError")
        return "ContractLogicError"

    def _function(self, call: ContractCall):
        args = [Web3.to_checksum_address(a) if isinstance(a, str) and len(a) == 42 and a.startswith("0x") else a
                for a in call.args]
        return getattr(self._contract().functions, call.function)(*args)

    def simulate(self, sender_role: str, call: ContractCall) -> None:
        sender = Web3.to_checksum_address(self.signer_address(sender_role))
        try:
            self._rpc(lambda: self._function(call).call({"from": sender, "value": call.value_wei}))
        except (ContractCustomError, ContractLogicError) as exc:
            raise ContractRevert(self._revert_name(exc)) from None

    def sign(self, sender_role: str, call: ContractCall, nonce: int) -> SignedTransaction:
        account = self._accounts.get(sender_role)
        if account is None:
            raise ChainUnavailable("SIGNER_NOT_CONFIGURED: " + sender_role)
        deployment = self._deployment()
        function = self._function(call)
        try:
            gas = self._rpc(lambda: function.estimate_gas({"from": account.address, "value": call.value_wei}))
        except (ContractCustomError, ContractLogicError) as exc:
            raise ContractRevert(self._revert_name(exc)) from None
        tx = function.build_transaction({
            "from": account.address, "nonce": nonce, "chainId": int(deployment.chain_id),
            "value": call.value_wei, "gas": int(gas * 1.25) + 10_000,
            "gasPrice": self._rpc(lambda: self.w3.eth.gas_price)})
        signed = account.sign_transaction(tx)
        return SignedTransaction(raw=bytes(signed.raw_transaction), tx_hash="0x" + bytes(signed.hash).hex(),
                                 nonce=nonce, sender=account.address.lower())

    def broadcast(self, raw: bytes, tx_hash: str) -> None:
        try:
            self._rpc(lambda: self.w3.eth.send_raw_transaction(raw))
        except (Web3RPCError, ValueError) as exc:
            message = str(exc).lower()
            if "already known" in message or "already imported" in message:
                return
            if "nonce too low" in message:
                if self.transaction_known(tx_hash):
                    return
                raise NonceConsumed("nonce already used by another transaction") from None
            raise ChainUnavailable("BROADCAST_REJECTED: " + message[:200]) from None

    def transaction_known(self, tx_hash: str) -> bool:
        try:
            self._rpc(lambda: self.w3.eth.get_transaction(tx_hash))
            return True
        except TransactionNotFound:
            return False

    def receipt(self, tx_hash: str) -> ChainReceipt | None:
        try:
            receipt = self._rpc(lambda: self.w3.eth.get_transaction_receipt(tx_hash))
        except TransactionNotFound:
            return None
        contract = self._contract()
        address = contract.address.lower()
        events: list[DecodedEvent] = []
        for log in receipt["logs"]:
            if log["address"].lower() != address:
                continue
            for name in EVENT_NAMES:
                try:
                    decoded = getattr(contract.events, name)().process_log(log)
                except MismatchedABI:
                    continue
                events.append(DecodedEvent(name, {k: _normalize(v) for k, v in decoded["args"].items()}))
                break
        return ChainReceipt(tx_hash="0x" + bytes(receipt["transactionHash"]).hex(),
                            block_number=int(receipt["blockNumber"]), status=int(receipt["status"]),
                            contract_events=events)

    # -- views -----------------------------------------------------------------------------------
    def _view(self, fn, block: int | None):
        try:
            return self._rpc(lambda: fn.call(block_identifier=block if block is not None else "latest"))
        except (ContractCustomError, ContractLogicError) as exc:
            raise ContractRevert(self._revert_name(exc)) from None

    def get_batch(self, batch_id: int, block: int | None = None) -> BatchView:
        values = self._view(self._contract().functions.getBatch(batch_id), block)
        (plot_id, issuance_key, seller, total_supply, credit_status, unit_price_wei, evidence_hash,
         decision_hash, issued_at, frozen_at, last_observed_at) = values
        return BatchView(plot_id=plot_id, issuance_key=bytes32_to_hash(issuance_key), seller=seller.lower(),
                         total_supply=int(total_supply), credit_status=CREDIT_STATUS[int(credit_status)],
                         unit_price_wei=int(unit_price_wei), evidence_hash=bytes32_to_hash(evidence_hash),
                         decision_hash=bytes32_to_hash(decision_hash), issued_at=int(issued_at),
                         frozen_at=int(frozen_at), last_observed_at=int(last_observed_at))

    def balance_of(self, batch_id: int, address: str, block: int | None = None) -> int:
        fn = self._contract().functions.balanceOf(batch_id, Web3.to_checksum_address(address))
        return int(self._view(fn, block))
