# Cross-platform development readiness audit

Audit date: 2026-09-17. Result: **READY FOR PARALLEL DEVELOPMENT**, conditional on:

- Approval of the existing PR by Backend / Integration Owner.
- Human squash merge of the PR.
- Green checks on `main` after merge.

The three discrepancies were resolved as **DOCS_ONLY**: instructions now match
the frozen technical baseline. These conditions are release gates, not a claim
that approval or merge has already happened. Required PR checks must remain green.
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
2. **Cross-platform coverage — CI added and passed for the initial audit commit.**
   Previously only Ubuntu/Python 3.12 ran in CI. The new `readiness` matrix covers
   Ubuntu 3.12/3.13, Windows 3.12, and macOS 3.12 on PRs to `main` and manual
   dispatch, without feature-branch push triggers, secrets, or deployment.
   The four-job workflow and Shared contracts passed for `adcd200`; links below.
   Checks must rerun for the documentation update and remain green before merge.
3. **Public operation enum — corrected in documentation.**
   Backend plan section 6 and Frontend plan section 4 now expose only `QUEUED`,
   `SUBMITTED`, `CONFIRMED`, `FAILED`, matching OpenAPI and API models.
   `SIGNING` is explicitly not a public API state. Signing happens within
   `QUEUED`; persisted signed bytes plus broadcast lead to `SUBMITTED`.
   Reconciliation uses saved intent, signed bytes, and tx hash without a separate
   signing state or duplicate transactions. No technical enum changed.
4. **Permission-event names — corrected in documentation.**
   Blockchain plan section 2 now uses
   `IssuerPermissionChanged(address indexed account, bool allowed)` and
   `OraclePermissionChanged(address indexed account, bool allowed)`.
   Solidity and its compiler-generated ABI already agreed and remain unchanged.
5. **Repeated freeze — clarified in documentation.**
   Manifest section 6 and `status-machine.md` now explicitly describe
   `FROZEN -> FROZEN` as retained state, not another on-chain call. Backend
   deduplicates requests/evidence; new evidence is stored separately without
   a second freeze transaction for an already FROZEN batch. On-chain freeze
   requires an existing ACTIVE batch; a repeated call for FROZEN is rejected
   without a new Frozen event. Pending/timeout reconciliation reuses the existing
   operation without a new-nonce transaction. Frontend must not attribute an old
   anchor to new evidence; RS supplies observations only.

Findings 3-5 are closed by documentation alignment (DOCS_ONLY). No new technical
contract version, fixture change, or tag is needed. Future semantic changes still
require the existing coordinated contract-change process.

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
second API/schema/ABI. The three identified prose discrepancies now agree with
the frozen machine contracts and the baseline's idempotency requirements.

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
| Ubuntu 3.12 / Ubuntu 3.13 / Windows 3.12 / macOS 3.12 matrix | PR workflow on `adcd200` | Success; rerun required for the updated PR head |

Existing CI evidence: [Shared contracts run 35130636808](https://github.com/ktyfujkjdfx/bountyteam-carbon-mrv/actions/runs/35130636808).
PR evidence on `adcd200`: [Cross-platform readiness](https://github.com/ktyfujkjdfx/bountyteam-carbon-mrv/actions/runs/35132375323)
and [Shared contracts](https://github.com/ktyfujkjdfx/bountyteam-carbon-mrv/actions/runs/35132375257), both successful.
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

1. Backend / Integration Owner reviews and approves the updated
   [existing PR #1](https://github.com/ktyfujkjdfx/bountyteam-carbon-mrv/pull/1).
   If Team Lead authors the PR, Backend performs the approved human squash merge;
   the agent does not merge.
2. Wait for all four `readiness` jobs and Shared contracts on the updated PR head
   to pass before merge, then verify green checks on `main` after merge.
   The readiness workflow runs on PR updates/manual dispatch, not ordinary pushes;
   use manual dispatch on `main` if post-merge matrix verification is needed.
3. Preserve `contracts-v1.0.0`; the three documentation corrections do not
   authorize any technical contract change or new tag.
4. Repository owner verifies collaborator access and available branch protection
   or ruleset enforcement. No account invitations or settings were changed here.
5. After review and human merge, participants clone/update, follow the single
   [README setup section](../../README.md#validate-the-shared-package), and create
   their assigned feature branches using [the PR workflow](07_PR_WORKFLOW.md).

Fallback: leave `main` at its reviewed state and revise or close this audit PR;
do not reset others' work or alter the baseline tag. Infrastructure readiness
does not imply an end-to-end pass of the still-unimplemented application.
