# Blockchain agent rules

Follow [root /CLAUDE.md](../CLAUDE.md) and
[the Blockchain plan](../docs/roles/04_BLOCKCHAIN_PLAN.md).
Primary edit scope: `blockchain/`.

- Inputs: `contracts/contract-interface.sol`, frozen ABI,
  `contracts/deployment.schema.json`, approved deployment roles/configuration,
  and Backend adapter calls with evidence/decision hashes.
- Outputs: deployable contract matching the agreed interface, ABI generated
  from compiled source, reproducible local Anvil deployment, deployment manifest
  with address/code hash, events/readback, tests, and run instructions.
- Consumer: Backend uses the compiled ABI and deployment manifest for its chain
  adapter and verifies receipts, events, balances, and state readback.
- Backend is the only runtime oracle sender. Do not create a second oracle
  script or independently evaluate fire evidence or policy.
- Enforce access control, real balances, test purchases, and rejection of direct
  buy/transfer on frozen batches. Do not hand-edit ABI.
- Do not independently change shared contracts, including signatures, events,
  errors, or enum meanings. Stop conflicts and follow the root proposal process.
- Run relevant permissions, unknown-batch, duplicate-issuance, balances/payment,
  freeze, direct-transfer rejection, and adapter integration tests, plus shared
  checks. Report changed files, commands, results, limitations, and the next
  deployment/ABI handoff to Backend with its deadline.
