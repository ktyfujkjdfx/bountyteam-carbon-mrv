"""Runtime settings. Secrets (demo session token, private keys) come only from environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

MODES = ("CONTRACT_FIXTURE", "LOCAL_DEMO")
CHAIN_ADAPTERS = ("mock", "web3")
ACTORS = ("issuer", "buyer", "recipient")
SIGNER_ROLES = ("issuer", "buyer", "recipient", "oracle")


class ConfigError(RuntimeError):
    pass


def _path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    mode: str = "CONTRACT_FIXTURE"
    demo_session: str = ""
    db_path: Path = BACKEND_ROOT / "runtime" / "backend.sqlite"
    artifact_store: Path = BACKEND_ROOT / "runtime" / "artifacts"
    contracts_dir: Path = REPO_ROOT / "contracts"
    policy_path: Path = REPO_ROOT / "config" / "policy.v1.json"
    scenarios_path: Path = REPO_ROOT / "config" / "scenarios.json"
    authorizations_path: Path = REPO_ROOT / "config" / "demo-authorizations.json"
    chain_adapter: str = "mock"
    mock_chain_path: Path = BACKEND_ROOT / "runtime" / "mock-chain.sqlite"
    rpc_url: str = "http://127.0.0.1:8545"
    deployment_path: Path = REPO_ROOT / "runtime" / "deployment.json"
    private_keys: dict[str, str] = field(default_factory=dict, repr=False)
    rs_mode: str = "cached_bundle"
    rs_command: tuple[str, ...] = ()
    rs_work_dir: Path = BACKEND_ROOT / "runtime" / "rs-runs"
    cors_origins: tuple[str, ...] = ()
    max_artifact_bytes: int = 64 * 1024 * 1024
    max_bundle_bytes: int = 512 * 1024 * 1024
    worker_poll_seconds: float = 1.0
    worker_lease_seconds: float = 15.0

    def validate(self) -> "Settings":
        if self.mode not in MODES:
            raise ConfigError(f"BACKEND_MODE must be one of {MODES}")
        if self.chain_adapter not in CHAIN_ADAPTERS:
            raise ConfigError(f"BACKEND_CHAIN_ADAPTER must be one of {CHAIN_ADAPTERS}")
        # A mock ledger may never be presented as a local demo chain.
        if self.mode == "LOCAL_DEMO" and self.chain_adapter != "web3":
            raise ConfigError("LOCAL_DEMO requires BACKEND_CHAIN_ADAPTER=web3; mock chain is CONTRACT_FIXTURE only")
        if not self.demo_session or len(self.demo_session) < 16:
            raise ConfigError("BACKEND_DEMO_SESSION must be set (>= 16 characters)")
        if self.rs_mode not in ("cached_bundle", "rs_cli"):
            raise ConfigError("BACKEND_RS_MODE must be cached_bundle or rs_cli")
        return self


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ if env is None else env)
    keys = {role: env[f"BACKEND_PRIVATE_KEY_{role.upper()}"]
            for role in SIGNER_ROLES if env.get(f"BACKEND_PRIVATE_KEY_{role.upper()}")}
    return Settings(
        mode=env.get("BACKEND_MODE", "CONTRACT_FIXTURE"),
        demo_session=env.get("BACKEND_DEMO_SESSION", ""),
        db_path=_path(env.get("BACKEND_DB_PATH"), Settings.db_path),
        artifact_store=_path(env.get("BACKEND_ARTIFACT_STORE"), Settings.artifact_store),
        policy_path=_path(env.get("BACKEND_POLICY_PATH"), Settings.policy_path),
        scenarios_path=_path(env.get("BACKEND_SCENARIOS_PATH"), Settings.scenarios_path),
        authorizations_path=_path(env.get("BACKEND_AUTHORIZATIONS_PATH"), Settings.authorizations_path),
        chain_adapter=env.get("BACKEND_CHAIN_ADAPTER", "mock"),
        mock_chain_path=_path(env.get("BACKEND_MOCK_CHAIN_PATH"), Settings.mock_chain_path),
        rpc_url=env.get("BACKEND_RPC_URL", Settings.rpc_url),
        deployment_path=_path(env.get("BACKEND_DEPLOYMENT_PATH"), Settings.deployment_path),
        private_keys=keys,
        rs_mode=env.get("BACKEND_RS_MODE", "cached_bundle"),
        rs_command=tuple(env.get("BACKEND_RS_COMMAND", "").split()),
        rs_work_dir=_path(env.get("BACKEND_RS_WORK_DIR"), Settings.rs_work_dir),
        cors_origins=_csv(env.get("BACKEND_CORS_ORIGINS")),
        worker_poll_seconds=float(env.get("BACKEND_WORKER_POLL_SECONDS", "1.0")),
    ).validate()
