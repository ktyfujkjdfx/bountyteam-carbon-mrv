# BountyTeam Carbon MRV

Hackathon monorepo for satellite verification of forest carbon-credit projects
and programmable temporary restrictions after a confirmed fire reversal.

## Source of truth

- Product rules: `docs/common/00_BOUNTYTEAM_MANIFEST.md`
- Architecture: `docs/common/01_ARCHITECTURE_AND_FLOW.md`
- Human-readable contracts: `docs/common/02_JSON_API_ABI_CONTRACTS.md`
- Evidence schema: `contracts/verification.schema.json`
- HTTP API: `contracts/openapi.yaml`
- Chain interface: `contracts/contract-interface.sol`
- Policy: `config/policy.v1.json`
- State semantics: `docs/common/status-machine.md`
- Pull Request workflow: `docs/common/07_PR_WORKFLOW.md`

Current contract baseline: `contracts-v1.0.0`.

## Modules

| Directory | Owner |
|---|---|
| `rs/` | Remote Sensing developer |
| `backend/` | Backend developer and Integration Owner |
| `blockchain/` | Blockchain developer |
| `frontend/` | Frontend developer and Demo Operator |
| `docs/` | Team Lead; shared contract changes require affected owners |

## Validate the shared package

Use Python **3.12** (reference version) or **3.13**, and Node.js **24.19.0**
from `.nvmrc` with its bundled npm. Use `npm ci --ignore-scripts` and the committed
`package-lock.json`; do not regenerate the lockfile or run `npm audit fix`.
See [the readiness audit](docs/common/08_READINESS_AUDIT.md) for verified platforms
and remaining blockers. The cross-platform CI matrix must pass before claiming
support on every platform.

After cloning, start with a clean working tree and synchronize the baseline:

```text
git fetch origin --tags
git switch main
git pull --ff-only origin main
```

On **Windows PowerShell**, verify that `python --version` reports 3.12 or 3.13:

```powershell
python -m venv .venv
$env:PYTHONUTF8='1'
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-contracts.txt
npm.cmd ci --ignore-scripts
python -m pytest -q
npm.cmd run check:abi
```

If execution policy blocks activation, skip activation and replace `python` in
the install/test commands with `.\.venv\Scripts\python.exe`; keep
`$env:PYTHONUTF8='1'` in that terminal. `npm.cmd` avoids the `npm.ps1` restriction.
No system execution-policy change or global Python dependency installation is needed.

On **macOS/Linux**, verify that `python3 --version` reports 3.12 or 3.13:

```bash
python3 -m venv .venv
source .venv/bin/activate
export PYTHONUTF8=1
python -m pip install -r requirements-contracts.txt
npm ci --ignore-scripts
python -m pytest -q
npm run check:abi
```

If the default interpreter differs, use an installed `python3.12`/`python3.13`
on macOS/Linux or `py -3.12`/`py -3.13` on Windows to create `.venv`.
Do not reuse a virtual environment copied from another OS.

Expected: **68 passed**; ABI `ok: true`, **9 functions**, **7 events**,
`specification_only: true`. These checks also validate schemas/OpenAPI, reproduce
canonical fixture bytes/hashes, and read the binary fixtures. They do not run
fixture generators or implement the application. Keep local private keys only
in environment variables (an untracked `.env` may supply them); never place
them in committed config or deployment manifests.

Build output stays untracked; package `frontend/dist` into the approved demo
release bundle when implemented, as required by the release plan.

## Branches

- `feat/rs-pipeline`
- `feat/backend-api`
- `feat/chain-registry`
- `feat/frontend-dashboard`
- `docs/teamlead`

No direct pushes to `main`. Team Lead or Integration Owner merges a reviewed PR
after required checks. Chat messages do not modify contracts.

## Important boundary

This baseline contains specifications and synthetic contract fixtures. It is not
the implemented application: runtime RS, backend, frontend and deployable smart
contract are built in the role branches.
