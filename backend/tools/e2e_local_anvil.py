"""python -m backend.tools.e2e_local_anvil [--blockchain-ref REF] [--port N] [--evidence-out FILE]

Reproducible real-chain E2E for the Backend <-> Blockchain boundary:
  1. take the Blockchain module from the working tree (`--blockchain-ref worktree`) or read-only
     from a git ref (default origin/feat/chain-registry) via `git archive` into a temp dir;
  2. start a throwaway Anvil (chain id 31337) and deploy with blockchain/tools/deploy-local.cjs;
  3. run backend/tests/test_e2e.py::test_e2e_local_anvil against that deployment:
     issue -> buy -> transfer (receipt timeout + backend restart) -> fire decision -> oracle
     freeze -> direct transfer revert, with receipt/event/readback checks.
Anvil's public dev keys are read from Anvil's own startup output at runtime; nothing is written
to the repository. Requires anvil (Foundry), node and npm on PATH. Never touches a shared chain.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from ..app.config import REPO_ROOT

ROLE_INDEX = {"issuer": 1, "oracle": 2, "buyer": 3, "recipient": 4}  # blockchain deploy-local.cjs defaults


def _run(command: list[str], cwd: Path, env: dict | None = None, capture: bool = False) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=capture, check=False)
    if result.returncode != 0:
        detail = (result.stderr or "")[-1500:] if capture else ""
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(command)}\n{detail}")
    return result.stdout if capture else ""


def _wait_rpc(url: str, timeout: float = 20.0) -> None:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}).encode()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(url, body, {"content-type": "application/json"})
            with urllib.request.urlopen(request, timeout=2) as response:
                if json.load(response).get("result") == hex(31337):
                    return
        except OSError:
            pass
        time.sleep(0.25)
    raise SystemExit(f"Anvil did not answer on {url}")


def _anvil_keys(log: Path, timeout: float = 10.0) -> dict[str, str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        if "Private Keys" in text:
            keys = dict(re.findall(r"\((\d+)\)\s+(0x[0-9a-fA-F]{64})", text.split("Private Keys", 1)[1]))
            if all(str(i) in keys for i in ROLE_INDEX.values()):
                return {role: keys[str(i)] for role, i in ROLE_INDEX.items()}
        time.sleep(0.2)
    raise SystemExit("Could not read Anvil dev accounts from its startup output")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--blockchain-ref", default="origin/feat/chain-registry",
                        help="git ref to export, or 'worktree' to use the checked-out blockchain/ directory")
    parser.add_argument("--port", type=int, default=8547, help="throwaway Anvil port (not the shared 8545)")
    parser.add_argument("--evidence-out", help="write receipts/readback/proof evidence JSON here")
    parser.add_argument("--keep", action="store_true", help="keep the temp dir for inspection")
    args = parser.parse_args(argv)
    for tool in ("anvil", "node", "npm", "git"):
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} not found on PATH")

    work = Path(tempfile.mkdtemp(prefix="backend-e2e-anvil-"))
    anvil = None
    try:
        if args.blockchain_ref == "worktree":
            tree = REPO_ROOT
            if not (tree / "blockchain" / "tools" / "deploy-local.cjs").exists():
                raise SystemExit("blockchain/tools/deploy-local.cjs is not in this working tree")
        else:
            tree = work / "tree"
            tree.mkdir()
            archive = subprocess.run(["git", "archive", args.blockchain_ref], cwd=REPO_ROOT, capture_output=True,
                                     check=False)
            if archive.returncode != 0:
                raise SystemExit(f"git archive {args.blockchain_ref} failed: {archive.stderr.decode()[-500:]}")
            subprocess.run(["tar", "-x", "-C", str(tree)], input=archive.stdout, check=True)
            commit = _run(["git", "rev-parse", "--short", args.blockchain_ref], REPO_ROOT, capture=True).strip()
            print(f"blockchain source: {args.blockchain_ref} @ {commit} (read-only export)")
        if not (tree / "node_modules" / "solc").exists():
            _run(["npm", "ci", "--ignore-scripts"], tree)

        rpc = f"http://127.0.0.1:{args.port}"
        log = work / "anvil.log"
        with log.open("w", encoding="utf-8") as handle:
            anvil = subprocess.Popen(["anvil", "--port", str(args.port), "--chain-id", "31337"], stdout=handle,
                                     stderr=subprocess.STDOUT)
        _wait_rpc(rpc)
        keys = _anvil_keys(log)
        deploy_dir = work / "deploy"
        env = {**os.environ, "RPC_URL": rpc, "DEPLOYMENT_DIR": str(deploy_dir), "DEPLOYMENT_BUILD_DIR": str(deploy_dir)}
        _run(["node", "tools/deploy-local.cjs"], tree / "blockchain", env=env, capture=True)
        manifest = deploy_dir / "deployment.json"
        print("deployment:", json.dumps(json.loads(manifest.read_text()), indent=2))

        evidence = Path(args.evidence_out).resolve() if args.evidence_out else work / "anvil-e2e-evidence.json"
        test_env = {**os.environ, "PYTHONUTF8": "1", "BACKEND_E2E_RPC_URL": rpc,
                    "BACKEND_E2E_DEPLOYMENT": str(manifest), "BACKEND_E2E_EVIDENCE_OUT": str(evidence),
                    **{f"BACKEND_E2E_KEY_{role.upper()}": key for role, key in keys.items()}}
        result = subprocess.run([sys.executable, "-m", "pytest", "backend/tests/test_e2e.py", "-q", "-rs",
                                 "-k", "test_e2e_local_anvil"], cwd=REPO_ROOT, env=test_env, check=False)
        if result.returncode == 0 and evidence.exists():
            print("evidence:", evidence)
        return result.returncode
    finally:
        if anvil is not None:
            anvil.terminate()
            anvil.wait(timeout=10)
        if args.keep:
            print("kept:", work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
