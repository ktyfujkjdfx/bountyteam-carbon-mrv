# Cross-platform development readiness audit

Audit date: 2026-09-17. Result: **NOT READY for unconditional parallel-development
sign-off**. The shared package passes locally, but the documentation conflicts
below need owner decisions and the new OS matrix has not run yet.
This is an infrastructure/contract audit, not application acceptance.

## Scope and starting state

- Repository: `ktyfujkjdfx/bountyteam-carbon-mrv`; origin is the expected GitHub repository.
- Starting `main`: `380914925b0a7b778e9ff3d71776344eca62d652`, clean and identical
  to `origin/main` after `git fetch origin --tags` (ahead/behind: 0/0).
- Changes are isolated to `chore/readiness-audit`; no participant branches created.
- Baseline tag: `contracts-v1.0.0`; annotated tag object
  `3e7b7fe7702ff94754edb8f21ab8897696cc5bac`, target commit `6c650d5`.
  The tag is neither moved nor recreated.
- Reviewed repository instructions, common documents, all five role plans,
  module instructions, CODEOWNERS, PR template/workflow, CI, dependency manifests,
  attributes/ignore rules, validators, ABI compiler, and contract tests.

## Findings and disposition

### Critical

No tracked secret exposure or baseline mutation was found in the checks performed.
No application security or runtime readiness claim is made: there is no implementation.

### Important

1. **Windows locale failure — addressed in setup and CI.**
   `test_openapi_validates` without UTF-8 mode fails under cp1252:
   `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81 in position 454`.
   Some frozen tests call `read_text()` without an encoding. README and both
   workflows now set `PYTHONUTF8=1`. Tests/contracts are unchanged; errors are
   not suppressed. This environment setting is required on each new terminal.
2. **Cross-platform evidence incomplete — CI added, execution pending.**
   Previously only Ubuntu/Python 3.12 ran in CI. The new `readiness` matrix covers
   Ubuntu 3.12/3.13, Windows 3.12, and macOS 3.12 on PRs to `main` and manual
   dispatch, without feature-branch push triggers, secrets, or deployment.
   A local Windows 3.13 pass cannot substitute for these four results.
3. **Public operation enum conflicts — owner decision required.**
   `docs/roles/03_BACKEND_PLAN.md` section 6 and
   `docs/roles/05_FRONTEND_PLAN.md` section 4 include `SIGNING`. Frozen
   `contracts/api-models.schema.json`, `contracts/openapi.yaml`, the manifest
   section 6, and `docs/common/status-machine.md` expose only `QUEUED`,
   `SUBMITTED`, `CONFIRMED`, `FAILED`. Minimal proposal: align role-plan public
   states to the baseline; if an internal signing phase is needed, explicitly
   distinguish it from the public enum. Do not add a public state during this audit.
   Approvals: Backend, Frontend, Team Lead; consumers: API clients and operation UI.
4. **Event-name conflicts — owner decision required.**
   Blockchain plan section 2 lists `IssuerUpdated` / `OracleUpdated`, while the
   frozen Solidity source and compiled ABI use `IssuerPermissionChanged` /
   `OraclePermissionChanged`. Minimal proposal: correct role-plan wording to
   the compiled interface after Blockchain, Backend, and Team Lead agree.
   Do not rename or extend ABI events. Consumers: deploy tooling and chain adapter.
5. **Repeated-freeze semantics ambiguous — owner decision required.**
   Manifest section 6 and `status-machine.md` show a `FROZEN -> FROZEN` transition
   for repeated/newer observations. Manifest section 11 and the Blockchain plan
   require ACTIVE for `freeze`; the Blockchain acceptance checklist also says
   repeat freeze is rejected. The abstract Solidity interface cannot test the
   intended runtime behavior. Minimal proposal: owners explicitly distinguish
   off-chain handling of observations from permitted on-chain calls, preserving
   the baseline unless a separate contract change is approved. Approvals:
   Blockchain, Backend, Team Lead; consumers: oracle, reconciliation, and UI.

For findings 3-5, stop the affected implementation and open `contract-change`
Issues using the existing template. This report supplies the problem, minimal
proposal, affected documents, and reviewers; it does not approve a resolution.
No fixture changes are proposed for documentation-only alignment. Any semantic
change requires coordinated fixtures/tests and a separately approved version.
Resolve these before the first interface implementation handoff.

### Minor

- Node was pinned only to major 24 in CI; `.nvmrc` now pins **24.19.0**, consumed
  by both workflows and documented for local setup. Python 3.12 is the explicit
  reference; 3.13 is the compatibility target. `package.json`/lockfile remain
  frozen: an `engines` addition is deferred to a separately approved change.
- Missing `.DS_Store`, `venv`, general build/coverage directories and `.env.*`
  ignores are added; `.env.example` remains trackable. Existing runtime/database
  ignores remain. Release `frontend/dist` is packaged, not committed by default.
- `.nvmrc` and CODEOWNERS now have explicit LF rules, supplementing existing
  UTF-8 text/source and binary-fixture policies.
- `contract_helpers.utc()` parses fixed UTC `Z` strings into naive datetime
  objects. Current validation only compares them and performs no local-time
  conversion; no timezone-dependent result was found. Future runtime code must
  use explicit UTC-aware datetimes before converting timestamps.
- Generator scripts write text using platform-default newline handling. They
  are not part of onboarding/CI validation and were not run against the frozen
  tree. JCS fixture reproduction is checked in memory against committed bytes;
  complete byte-identical regeneration of all rasters across OSes is not claimed.

## Parallel work and ownership

All four role directories, their `CLAUDE.md` files, and personal plans exist.
Root and role agent rules agree on the baseline, module boundaries, shared
approvals, tests, handoff, no direct push to `main`, and no agent PR merge.
The user explicitly assigned this audit's `chore/readiness-audit` branch.

| Role | Owner | Assigned implementation branch |
|---|---|---|
| RS | @csihwrcv | `feat/rs-pipeline` |
| Backend / Integration Owner | @ahadniyozov | `feat/backend-api` |
| Blockchain | @efimchuk20006-pixel | `feat/chain-registry` |
| Frontend / Demo Operator | @KI-24-ATAKA | `feat/frontend-dashboard` |

Team Lead: @ktyfujkjdfx. CODEOWNERS has the expected 23 rules, valid tracked paths,
and the five expected usernames. GitHub's CODEOWNERS errors API returned
`{"errors": []}` for starting `main`. This does not establish accepted invitations,
write permissions for every collaborator, or ruleset enforcement.

Ordinary implementation stays in each module. Shared contracts, config, fixtures,
tests, and tools are intentional integration points requiring coordinated PRs;
CODEOWNERS and the reviewer matrix identify the relevant producers/consumers,
Team Lead, and Integration Owner. Multiple listed owners are reviewers, not a
license for competing edits. Backend owns the runtime chain adapter; Blockchain
supplies deployment/ABI and jointly validates the boundary, not a second oracle.

The PR workflow requires a linked Issue, tests/results, contract impact,
limitations/fallback, handoff, independent review, and human squash merge without
self-merge. No instructions authorize ordinary direct pushes to `main` or a
second API/schema/ABI. However, findings 3-5 mean the prose is not yet a fully
consistent restatement of the frozen machine contracts.

## Portability and security evidence

- Checked 108 starting tracked files: 69 UTF-8 text files and 39 PNG/TIFF binary
  fixtures. No case-only or Unicode-normalization path collisions, Windows-invalid
  names, broken local Markdown links, or absolute user-specific paths found.
- Python uses `pathlib`; JavaScript uses `node:path` and explicit UTF-8. Imports
  and tracked asset references use matching case. Fixed UTC strings and RFC 8785
  canonicalization do not depend on OS sorting or the current clock.
- No tracked shell scripts or executable-bit requirements. Test/build entry
  points are `python -m pytest` and `npm run check:abi`; PowerShell activation
  and POSIX `source` are alternative onboarding steps, not build requirements.
- Binary fixtures are actual Git blobs, not LFS pointers; the shared tests open
  the images/rasters and validate their sizes, geometry, values, and hashes.
- No tracked `.env`, virtual environment, or `node_modules`. A signature scan
  found no private-key blocks, GitHub/AWS token patterns, or concrete secret
  assignments. This is a scoped scan/review, not a guarantee of exhaustive detection.
- `config/demo-authorizations.json` explicitly uses `CONTRACT_FIXTURE` and
  `SYNTHETIC-AUTH-001`, contains no credentials, and marks units uncertified.
  Fixtures are synthetic. No runtime key loading exists yet; README requires
  environment variables for private keys and forbids committed keys/config secrets.
- No dependency upgrades, `npm audit fix`, lockfile rewrite, fixture generation,
  application implementation, deploy, merge, or push to `main` is part of this audit.

## Executed checks and platform coverage

| Environment | Evidence | Result |
|---|---|---|
| Local Windows, Python 3.13.15, Node 24.19.0, npm 11.17.0 | Shared pytest with `PYTHONUTF8=1`; ABI check | 68 passed; ABI OK |
| Local Windows without UTF-8 mode | Isolated OpenAPI test | Reproduced cp1252 failure; setup fix documented |
| Ubuntu, Python 3.12 | Existing Shared contracts run for starting `main` | Success (historical CI evidence) |
| New Ubuntu 3.12 / Ubuntu 3.13 / Windows 3.12 / macOS 3.12 matrix | New PR workflow | Pending PR creation and execution |

Existing CI evidence: [Shared contracts run 35130636808](https://github.com/ktyfujkjdfx/bountyteam-carbon-mrv/actions/runs/35130636808).
Only Python 3.13 was available locally (`py -0p`); no local 3.12/macOS/Linux run
is claimed. Current matrix coverage does not claim all macOS architectures or
all Windows/Python combinations.

Commands used from the root (PowerShell):

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd run check:abi
git diff --check
git diff --exit-code contracts-v1.0.0..main -- contracts config fixtures tests tools package.json package-lock.json requirements-contracts.txt
git diff --exit-code contracts-v1.0.0 -- contracts config fixtures tests tools package.json package-lock.json requirements-contracts.txt
```

Baseline diff checks return exit code 0. Tests validate JSON Schemas, OpenAPI,
all three evidence scenarios, JCS bytes and hashes, synthetic raster metrics,
and negative cases. ABI check recompiles the agreed abstract source with solc
0.8.30 and compares generated artifacts: `ok: true`, 9 functions, 7 events,
`specification_only: true`; no deployable bytecode or deployment address.

Node pin sources: [official 24.19.0 release files](https://nodejs.org/download/release/v24.19.0/)
and [setup-node version-file support](https://github.com/actions/setup-node).

## Required handoff

1. Team Lead opens the audit PR against `main` from `chore/readiness-audit`
   (GitHub CLI is unavailable locally); Backend reviews CI/setup alongside the
   Team Lead. If Team Lead authors the PR, Backend performs any approved merge.
2. Wait for all four `readiness` jobs and Shared contracts to pass. Record the
   run URLs/results before changing this NOT READY verdict. The new workflow
   intentionally does not run merely from pushing this branch.
3. Resolve findings 3-5 through the existing contract-change process. Preserve
   the baseline; do not silently implement the conflicting prose.
4. Repository owner verifies collaborator access and available branch protection
   or ruleset enforcement. No account invitations or settings were changed here.
5. After review and human merge, participants clone/update, follow the single
   [README setup section](../../README.md#validate-the-shared-package), and create
   their assigned feature branches using [the PR workflow](07_PR_WORKFLOW.md).

Fallback: leave `main` at its reviewed state and revise or close this audit PR;
do not reset others' work or alter the baseline tag. Infrastructure readiness
does not imply an end-to-end pass of the still-unimplemented application.
