# Contribution rules

1. Pull latest `main` and create the assigned feature branch.
2. Work primarily inside the directory owned by your role.
3. Keep every commit small and testable.
4. Open a PR to `main`; describe changed files, checks, limitations and handoff.
5. Do not edit schema, OpenAPI, ABI, enums, units, thresholds or state semantics
   without a contract change proposal and approval from both interface owners.
6. A contract change must update specifications, fixtures, tests and docs in one PR.
7. Never commit `.env`, private keys, runtime databases, `.venv`, `node_modules`
   or unnecessary raw satellite archives.
8. `main` must remain demonstrable. Tag successful E2E states as
   `demo-stable-HHMM`.

## Pull request evidence

- What P0/P1 issue is solved?
- Which files changed?
- How can another person run it?
- Which tests passed?
- Which role consumes the output next?
- Does it modify a shared contract?
