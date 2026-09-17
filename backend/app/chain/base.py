"""Chain adapter boundary shared by the real web3 adapter and the CONTRACT_FIXTURE mock ledger.

The application layer (operations/worker) only sees this interface, so switching
mock <-> real chain never changes the REST contract or confirmation rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

CREDIT_STATUS = {0: "ACTIVE", 1: "FROZEN", 2: "REVOKED"}


class ChainUnavailable(RuntimeError):
    """RPC/transport failure: retry later, never treat as failed or confirmed."""


class ContractRevert(RuntimeError):
    def __init__(self, error_name: str):
        super().__init__(error_name)
        self.error_name = error_name


class NonceConsumed(RuntimeError):
    """The stored nonce was used by a different transaction; needs human reconciliation."""


@dataclass(frozen=True)
class Deployment:
    deployment_id: str
    chain_id: str
    contract_address: str
    contract_code_hash: str
    abi_sha256: str
    roles: dict[str, str]


@dataclass(frozen=True)
class IdentityStatus:
    ok: bool
    deployment: Deployment | None
    reason: str | None = None


@dataclass(frozen=True)
class ContractCall:
    function: str
    args: tuple[Any, ...]
    value_wei: int = 0


@dataclass(frozen=True)
class SignedTransaction:
    raw: bytes
    tx_hash: str
    nonce: int
    sender: str


@dataclass(frozen=True)
class DecodedEvent:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ChainReceipt:
    tx_hash: str
    block_number: int
    status: int
    contract_events: list[DecodedEvent] = field(default_factory=list)


@dataclass(frozen=True)
class BatchView:
    plot_id: str
    issuance_key: str
    seller: str
    total_supply: int
    credit_status: str
    unit_price_wei: int
    evidence_hash: str
    decision_hash: str
    issued_at: int
    frozen_at: int
    last_observed_at: int


class ChainAdapter(Protocol):
    kind: str

    def identity(self) -> IdentityStatus: ...

    def signer_address(self, role: str) -> str: ...

    def pending_nonce(self, address: str) -> int: ...

    def mined_nonce(self, address: str) -> int: ...

    def simulate(self, sender_role: str, call: ContractCall) -> None: ...

    def sign(self, sender_role: str, call: ContractCall, nonce: int) -> SignedTransaction: ...

    def broadcast(self, raw: bytes, tx_hash: str) -> None: ...

    def transaction_known(self, tx_hash: str) -> bool: ...

    def receipt(self, tx_hash: str) -> ChainReceipt | None: ...

    def get_batch(self, batch_id: int, block: int | None = None) -> BatchView: ...

    def balance_of(self, batch_id: int, address: str, block: int | None = None) -> int: ...
