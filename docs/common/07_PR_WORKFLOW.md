# Pull Request workflow

This is the mandatory team workflow for contributors and Claude Code/Codex.
Read it together with [Git and integration rules](04_GIT_AND_INTEGRATION.md).

## A. Main rules

- Never push directly to `main`. Work only in your assigned role branch.
- One PR delivers one verifiable task or one P0 artifact. Do not mix unrelated
  refactoring, a new feature, and a contract change in one PR.
- The PR author must not self-merge. A human Team Lead or Backend Integration
  Owner performs the merge; if one is the author, the other merges.
- Use **Squash and merge** only. Keep the latest working `main` demonstrable.
- Never change, move, delete, or recreate `contracts-v1.0.0`.

## B. Assigned branches

| Role | GitHub username | Branch |
|---|---|---|
| Team Lead / Repository Owner | @ktyfujkjdfx | `docs/teamlead` |
| RS | @csihwrcv | `feat/rs-pipeline` |
| Backend / Integration Owner | @ahadniyozov | `feat/backend-api` |
| Blockchain | @efimchuk20006-pixel | `feat/chain-registry` |
| Frontend / Demo Operator | @KI-24-ATAKA | `feat/frontend-dashboard` |

Short-lived fixes use `fix/<short-name>` only when assigned by the Team Lead.
Do not create arbitrary long-lived branches without the Team Lead's decision.
Each participant creates their own branch; agents must not create branches for others.

## C. Start work

Read the manifest first, then all applicable instructions before editing:

- [Root CLAUDE.md](../../CLAUDE.md) and your module's `CLAUDE.md`.
- [Manifest](00_BOUNTYTEAM_MANIFEST.md).
- [Architecture](01_ARCHITECTURE_AND_FLOW.md).
- [Shared contracts](02_JSON_API_ABI_CONTRACTS.md).
- [State machines](status-machine.md).
- Your personal plan in `docs/roles/`.
- This `docs/common/07_PR_WORKFLOW.md` document.

Check `git status` first. Preserve any uncommitted work before switching branches.
For a new assigned branch, replace `<assigned-branch>` with your assigned name:

```bash
git switch main
git pull --ff-only origin main
git switch -c <assigned-branch>
git push -u origin <assigned-branch>
```

If your assigned branch already exists:

```bash
git fetch origin
git switch <assigned-branch>
git pull --ff-only
```

If it exists only on origin and automatic tracking is unavailable, use
`git switch --track origin/<assigned-branch>`. If fast-forward fails, stop and
inspect the divergence; do not reset or force-push.

## D. Commit format

Each commit describes one logical result. Use:

```text
feat(rs): ...
feat(backend): ...
feat(chain): ...
feat(frontend): ...
fix(scope): ...
test(scope): ...
docs(scope): ...
chore(scope): ...
```

Replace `scope` with the affected module or documentation area.

## E. Prepare a PR

1. Check `git status` and confirm you are on your assigned branch.
2. Fetch current `main` with `git fetch origin`.
3. Never use destructive reset or force-push.
4. With a clean working tree, merge `origin/main` into your feature branch if
   needed: `git merge origin/main`. If a conflict occurs, stop and propose a
   resolution; do not silently rewrite shared contracts.
5. Run relevant unit and integration tests for the changed role.
6. Run all shared checks from the repository root using the project `.venv`:

   ```bash
   python -m pytest -q
   npm run check:abi
   git diff --check
   ```

   On Windows PowerShell, use the following if activation or `npm.ps1` is blocked:

   ```powershell
   $env:PYTHONUTF8='1'
   .\.venv\Scripts\python.exe -m pytest -q
   npm.cmd run check:abi
   git diff --check
   ```

   Expected shared baseline: 68 passed; ABI `ok: true`, 9 functions, 7 events,
   `specification_only: true`. These checks do not prove runtime/E2E readiness.
7. Inspect the complete PR diff (`git diff origin/main...HEAD`) and any uncommitted
   changes. Exclude `.env`, private keys, `.venv`, `node_modules`, runtime databases,
   and unnecessary satellite archives.
8. Show the summary, tests/results, and contract impact before pushing. Push only
   your assigned branch: `git push origin <assigned-branch>`.

Rerun affected checks after changing code or resolving integration problems.
Open the PR against `main` only after the required checks pass.

## F. PR title

Use a clear result-oriented title with prefix `feat`, `fix`, `test`, `docs`, or `chore`:

```text
feat(rs): produce schema-valid evidence bundle
feat(backend): import evidence and apply policy
feat(chain): implement registry balances and freeze
feat(frontend): render evidence and confirmed credit state
```

## G. PR body

Fill in [the existing PR template](../../.github/pull_request_template.md).
Every PR must include:

- Priority (P0/P1/P2), linked Issue, and owner.
- Concrete result, changed files, and consumer/handoff.
- Exact test commands and actual results, including failures or limitations.
- Applicable evidence: screenshot, API response, transaction receipt/event/readback,
  or artifact manifest. Explain when an evidence type is not applicable.
- Contract impact and linked approvals when a shared contract changes.
- Known limitations, fallback/rollback, and the next handoff.

Use `Closes #<issue-number>` only if the PR fully resolves the Issue.
Otherwise use `Related to #<issue-number>`.

## H. Reviewer matrix

| PR | Required reviewers |
|---|---|
| RS | Backend + Team Lead |
| Backend | Team Lead + affected consumer |
| Blockchain | Backend + Team Lead |
| Frontend | Backend + Team Lead |
| Common evidence contract | RS + Backend + Team Lead |
| OpenAPI | Backend + Frontend + Team Lead |
| Solidity interface/ABI | Blockchain + Backend + Team Lead |
| Policy/state machine | Team Lead + Backend + RS when scientific thresholds are affected |

Usernames are listed in section B and [.github/CODEOWNERS](../../.github/CODEOWNERS).
For shared changes, the author supplies their role's agreement in the proposal;
the other required roles review it. An author's own agreement is not an independent approval.

The team's ruleset requirement is at least one independent approval, but the full
matrix governs the actual review process. One approval does not waive other
required roles. CODEOWNERS lists owners; it does not establish that every listed
owner approved. On a free private personal repository, CODEOWNERS/ruleset
enforcement may be unavailable. These team rules remain mandatory regardless of
technical enforcement. This document does not assert that a ruleset is enabled.

## I. Contract change protocol

For schema, OpenAPI, ABI, enum, units, thresholds, or status semantics changes:

1. Open an Issue using the `contract-change` template.
2. Describe the problem, minimal proposed change, and affected roles.
3. Obtain agreement from both sides of the interface and the Team Lead before
   implementing the contract change.
4. Update the source specification.
5. Regenerate derived artifacts.
6. Update fixtures, tests, and documentation in one compatible PR.
7. Never introduce the change in only one module.
8. After merge, the Team Lead decides on a new contract version/tag. Preserve
   the existing `contracts-v1.0.0` tag unchanged.

A chat message does not change the contract. Record approvals in the Issue/PR.

## J. Merge and handoff

After the required approvals and green CI:

- The human Team Lead or Backend Integration Owner merges, never the author.
- Use **Squash and merge**; the squash commit title must match the clear PR title.
- Delete the feature branch after merge.
- The consumer updates a clean local `main`:

  ```bash
  git switch main
  git pull --ff-only origin main
  ```

- The author sends a handoff: commit/PR, artifact, run command, tests/results,
  limitations, and next step with consumer and deadline.

For the next task, recreate the same assigned branch name from updated `main`.
Do not continue the old branch history after a squash merge. If its local branch
still exists, preserve any unpublished work and ask the Team Lead to review safe
cleanup before recreating it. Do not use destructive reset or force-push.

## K. Claude Code / Codex behavior

- Read this document before creating or updating a PR.
- Never independently change shared contracts. On a conflict, stop the affected
  work and produce a change proposal.
- Never push to `main`. Create PRs only from the contributor's assigned role branch.
- Do not create a PR before required tests pass.
- Before each push and before PR creation, show the user the change summary,
  test commands/results, and contract impact.
- Use `gh pr create` only if GitHub CLI is already authenticated and the user
  has confirmed PR creation. Do not initiate a new login or create tokens.
- If `gh` is unavailable, provide a ready PR title/body and exact commands for
  the assigned branch, plus the browser comparison URL. Do not claim a PR exists.
  Example command for an already authenticated CLI, using the prepared body file:

  ```bash
  gh pr create --base main --head <assigned-branch> --title "<type(scope): result>" --body-file <pr-body-file>
  ```

- Never perform a PR merge. The safe `origin/main` synchronization merge in
  section E is distinct from merging a PR into `main`.
- After creating a PR, report its URL and the handoff to the named consumer.
