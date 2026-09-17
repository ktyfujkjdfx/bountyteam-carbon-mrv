from __future__ import annotations

from ..config import Settings
from .base import ChainAdapter


def build_chain_adapter(settings: Settings) -> ChainAdapter:
    if settings.chain_adapter == "mock":
        from .mock import MockChainAdapter
        return MockChainAdapter(settings.mock_chain_path)
    from .web3_adapter import Web3ChainAdapter
    return Web3ChainAdapter(settings.rpc_url, settings.deployment_path, settings.private_keys)
