# Frontend agent rules

Follow [root /CLAUDE.md](../CLAUDE.md) and
[the Frontend plan](../docs/roles/05_FRONTEND_PLAN.md). Primary edit scope: `frontend/`.

Before creating or updating a Pull Request, read and follow
`docs/common/07_PR_WORKFLOW.md` and `.github/pull_request_template.md` (root-relative).
Never push to `main` or perform a PR merge. Use only your assigned `feat/frontend-dashboard`
branch for PRs. Before push/PR creation, show summary, tests/results, and contract
impact; follow the root confirmation rule. After PR creation, report URL and handoff.

- Inputs: `contracts/openapi.yaml`, API models and HTTP examples, and Backend
  `/api/v1` responses: local previews/GeoJSON, evidence, decisions, jobs,
  operations, balances, receipts, events, and availability flags.
- Outputs: one SPA dashboard with evidence/map views, test purchase flow,
  polling/error states, distinct status layers, unified timeline, honest
  REAL/SYNTHETIC and COMPUTED/CACHED_REPLAY labels, offline build, and demo instructions/video.
- Consumers: the team lead and demo audience use the dashboard; Backend as
  Integration Owner consumes the build and instructions for integrated delivery.
- Use only Backend `/api/v1`; never call RS providers or blockchain RPC directly.
- Keep outcome, evidence quality, decision, operation state, and credit state
  distinct. Do not calculate replacement statuses in the UI.
- `SUBMITTED` must never appear as confirmed `FROZEN`. Show confirmation only
  after Backend verifies the successful receipt, expected event, and readback.
- Do not independently change shared contracts or invent fields/statuses. Stop
  conflicting work and follow the root change proposal process.
- Run relevant API compatibility, pending/failed/polling, status display,
  purchase/freeze flow, and offline build tests, plus shared checks. Report
  changed files, commands, results, limitations, and the next build/demo handoff
  with consumer and deadline.
