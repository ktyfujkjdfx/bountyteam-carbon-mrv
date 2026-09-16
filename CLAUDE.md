# Agent workspace rules

These instructions apply to all Claude/Codex agents in this repository.

## Read before working

1. Read [the manifest](docs/common/00_BOUNTYTEAM_MANIFEST.md) first.
2. Read [architecture](docs/common/01_ARCHITECTURE_AND_FLOW.md),
   [shared contracts](docs/common/02_JSON_API_ABI_CONTRACTS.md),
   [state machines](docs/common/status-machine.md),
   [timeline](docs/common/03_SHARED_TIMELINE.md),
   [Git and integration rules](docs/common/04_GIT_AND_INTEGRATION.md), and
   [Definition of Done](docs/common/06_DEFINITION_OF_DONE.md).
3. Read your personal plan in `docs/roles/` and your module's `CLAUDE.md`.

## Frozen boundaries

- The shared contract baseline is `contracts-v1.0.0`. Never move, delete, or
  recreate this tag. The baseline is a specification, not a working application.
- Do not independently change JSON Schema, OpenAPI, ABI, the Solidity interface,
  fixtures, policy, enums, units, thresholds, statuses, hashing, or contract semantics.
- On a conflict, stop the affected work and submit a contract change proposal:
  problem, minimal change, affected files/roles/consumers, compatibility,
  fixture/test changes, owner, deadline, and required approvals. Preserve
  compatibility until the producer, consumer, and team lead agree under the
  Git and integration rules. Do not silently resolve conflicting documents.
- Work primarily inside your role's directory: `rs/`, `backend/`, `blockchain/`,
  or `frontend/`. Coordinate changes across role boundaries with their owners.
- Keep `main` demonstrable and passing shared checks. Follow the documented
  branch, PR, review, and merge rules.

## Integration invariants

- Frontend accesses data and operations only through backend `/api/v1`.
- RS produces observations and evidence bundles; it never sends `FROZEN` or
  `evidence_hash`.
- Backend is the Integration Owner and the sole runtime oracle. It owns
  validation, canonical evidence hashes, policy decisions, and chain operations.
- Blockchain enforces permissions and state; it does not decide whether a fire occurred.
- Frontend must not declare a transaction confirmed or a freeze completed until
  backend verifies a successful receipt, the expected event, and state readback.

## Validation and handoff

- Run relevant role tests plus `python -m pytest -q` and `npm run check:abi`
  from the repository root. Use the project `.venv`, not global Python packages.
  On Windows PowerShell, set `$env:PYTHONUTF8='1'`, use
  `.\.venv\Scripts\python.exe -m pytest -q`, and use `npm.cmd run check:abi`
  if execution policy blocks `npm.ps1`.
- Shared checks validate specifications and synthetic fixtures; they do not
  establish runtime or E2E readiness.
- Before finishing, report changed files, exact run commands, tests and results,
  limitations/blockers, and the next handoff (artifact, consumer, and deadline).
- Never commit secrets, `.env`, private keys, `.venv`, `node_modules`, runtime
  databases, caches, or unnecessary satellite archives. Follow the release plan
  for packaging frontend build output.
