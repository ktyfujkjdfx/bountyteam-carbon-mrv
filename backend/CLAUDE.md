# Backend agent rules

Follow [root /CLAUDE.md](../CLAUDE.md) and
[the Backend plan](../docs/roles/03_BACKEND_PLAN.md). Primary edit scope: `backend/`.

Before creating or updating a Pull Request, read and follow
`docs/common/07_PR_WORKFLOW.md` and `.github/pull_request_template.md` (root-relative).
Never push to `main` or perform a PR merge. Use only your assigned `feat/backend-api`
branch for PRs. Before push/PR creation, show summary, tests/results, and contract
impact; follow the root confirmation rule. After PR creation, report URL and handoff.

- You are the Integration Owner and sole runtime oracle sender. Own validation,
  JCS/SHA-256, policy evaluation, durable jobs/operations, and the chain adapter.
- Inputs: RS evidence bundles and artifact manifests; Blockchain compiled ABI,
  deployment manifest, address/code hash; OpenAPI requests from Frontend;
  approved policy/config and demo authorizations from the team lead.
- Outputs: `/api/v1` and matching `/openapi.json`, persistent jobs/operations,
  canonical evidence bytes and `evidence_hash`, decision records and
  `decision_hash`, transaction receipts/events/readback, proof, timeline,
  balances, and operation availability flags.
- Consumers: Frontend receives data and operations only through `/api/v1`;
  Blockchain receives authorized adapter transactions; RS receives valid requests.
- Reject token states such as `FROZEN` from RS. Recompute quality and decisions.
  Confirm operations only after successful receipt, expected event, and readback.
- Do not independently change shared contracts or policy. Stop conflicting work
  and follow the root change proposal process.
- Run relevant validation/hash/policy, API, idempotency, restart/reconciliation,
  and real chain integration tests, plus shared checks. Report changed files,
  commands, results, limitations, and the next API/adapter handoff with consumer
  and deadline.
