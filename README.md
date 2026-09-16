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

Python 3.12 and Node.js 24:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-contracts.txt
python -m pytest -q

npm ci --ignore-scripts
npm run check:abi
```

Expected baseline:

```text
68 passed
ABI check: OK
```

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
