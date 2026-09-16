# RS agent rules

Follow [root /CLAUDE.md](../CLAUDE.md) and
[the RS plan](../docs/roles/02_RS_PLAN.md). Primary edit scope: `rs/`.

Before creating or updating a Pull Request, read and follow
`docs/common/07_PR_WORKFLOW.md` and `.github/pull_request_template.md` (root-relative).
Never push to `main` or perform a PR merge. Use only your assigned `feat/rs-pipeline`
branch for PRs. Before push/PR creation, show summary, tests/results, and contract
impact; follow the root confirmation rule. After PR creation, report URL and handoff.

- Inputs: backend request matching `contracts/rs-request.schema.json` (AOI,
  plot ID, observation windows, mode), team-approved primary/reserve AOIs,
  local source scenes/metadata, `contracts/verification.schema.json`, and golden fixtures.
- Outputs: reproducible evidence bundle with `verification.json`, source index,
  source hashes, artifact manifest, affected-area GeoJSON, dNBR GeoTIFF and
  preview, aligned before/after previews, and FIRMS GeoJSON when used, as
  applicable to the schema and observation outcome. Preserve explicit limitations.
- Consumer: Backend imports and validates the bundle; provide a reproducible
  CLI command and resolvable relative asset paths for its handoff.
- Emit only `NO_CHANGE`, `DISTURBANCE_DETECTED`, or `INSUFFICIENT_DATA` outcomes.
  Never emit `FROZEN`, `ACTIVE`, `REVOKED`, `FREEZE_REQUESTED`, or `evidence_hash`.
- Do not independently change shared contracts, methods, units, or thresholds.
  Stop conflicting work and follow the root change proposal process.
- Run relevant schema, geometry/grid/mask, area, source integrity, reproducibility,
  and insufficient-data tests, plus shared checks. Report changed files, commands,
  results, limitations, and the next bundle handoff to Backend with its deadline.
