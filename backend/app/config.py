"""Runtime settings. Secrets (demo session token, private keys) come only from environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

MODES = ("CONTRACT_FIXTURE", "LOCAL_DEMO")
LENS_ENGINE_MODES = ("REAL", "FIXTURE")
LENS_ROLES = ("PROJECT_OWNER", "VERIFIER", "INVESTOR")
# The three demo sign-ins, and the environment variable that supplies each password.
# No password has a default: an account exists only if someone chose a password for it.
LENS_DEMO_ACCOUNTS = (
    ("owner", "PROJECT_OWNER", "BACKEND_LENS_DEMO_PASSWORD_OWNER"),
    ("verifier", "VERIFIER", "BACKEND_LENS_DEMO_PASSWORD_VERIFIER"),
    ("investor", "INVESTOR", "BACKEND_LENS_DEMO_PASSWORD_INVESTOR"),
)
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


def _demo_accounts(env: dict[str, str]) -> tuple[tuple[str, str, str], ...]:
    """The demo sign-ins this deployment configured.

    Both the switch and a password are required: a demo account should be something
    somebody turned on deliberately, not something that appears because a variable was
    left at a default. There are no defaults here for exactly that reason.
    """
    if env.get("BACKEND_LENS_DEMO_ACCOUNTS", "0") in ("0", "false", "False", ""):
        return ()
    return tuple((username, role, env[variable])
                 for username, role, variable in LENS_DEMO_ACCOUNTS
                 if env.get(variable))


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
    # Carbon Lens /api/v2. Its files live beside the P0 runtime, never inside it.
    lens_artifact_store: Path = BACKEND_ROOT / "runtime" / "lens-artifacts"
    lens_work_dir: Path = BACKEND_ROOT / "runtime" / "lens-runs"
    lens_enabled: bool = True
    # REAL is the only mode that answers with measurements. FIXTURE replays labelled
    # vectors and must be asked for by name; it is never reached by falling back.
    lens_engine_mode: str = "REAL"
    # Refuse to start at all unless the owning packages are installed, for a deployment
    # that would rather be down than be approximately right.
    lens_require_real: bool = False
    # (username, role, password) for the demo accounts. Passwords come from the
    # environment and are never in the repository, never in a log line and never in a
    # repr of these settings.
    lens_demo_accounts: tuple[tuple[str, str, str], ...] = field(default=(), repr=False)
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
        if self.lens_engine_mode not in LENS_ENGINE_MODES:
            raise ConfigError(f"BACKEND_LENS_ENGINE_MODE must be one of {LENS_ENGINE_MODES}")
        # A deployment that says it demonstrates real data may not serve replayed vectors:
        # the two are indistinguishable once they are on a screen.
        if self.mode == "LOCAL_DEMO" and self.lens_engine_mode == "FIXTURE":
            raise ConfigError(
                "LOCAL_DEMO may not run the Carbon Lens in FIXTURE mode; replayed vectors "
                "are not a demonstration of the supplied data")
        if self.lens_require_real and self.lens_engine_mode == "FIXTURE":
            raise ConfigError(
                "BACKEND_LENS_REQUIRE_REAL=1 contradicts BACKEND_LENS_ENGINE_MODE=FIXTURE")
        for username, role, password in self.lens_demo_accounts:
            if role not in LENS_ROLES:
                raise ConfigError(f"demo account {username}: role must be one of {LENS_ROLES}")
            if len(password) < 12:
                raise ConfigError(
                    f"demo account {username}: password must be at least 12 characters")
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
        lens_artifact_store=_path(env.get("BACKEND_LENS_ARTIFACT_STORE"),
                                  Settings.lens_artifact_store),
        lens_work_dir=_path(env.get("BACKEND_LENS_WORK_DIR"), Settings.lens_work_dir),
        lens_enabled=env.get("BACKEND_LENS_ENABLED", "1") not in ("0", "false", "False"),
        lens_engine_mode=env.get("BACKEND_LENS_ENGINE_MODE", "REAL").upper(),
        lens_require_real=env.get("BACKEND_LENS_REQUIRE_REAL", "0")
        not in ("0", "false", "False", ""),
        lens_demo_accounts=_demo_accounts(env),
        cors_origins=_csv(env.get("BACKEND_CORS_ORIGINS")),
        worker_poll_seconds=float(env.get("BACKEND_WORKER_POLL_SECONDS", "1.0")),
    ).validate()
