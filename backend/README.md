# Backend module — `/api/v1`, oracle policy, durable jobs and chain operations

Owner: Backend developer and Integration Owner (@ahadniyozov). Issue: #3. Contract baseline:
`contracts-v1.0.0` (unchanged by this module).

Backend is the only runtime oracle. It validates RS evidence, computes the canonical JCS
bytes, `evidence_hash`, the policy decision and `decision_hash`. It is the only sender of chain
transactions, and it reports a transaction as `CONFIRMED` only after it verifies a successful
receipt, the expected decoded event and contract readback. Frontend reaches everything through
`/api/v1`.

## Layout

| Path | Purpose |
|---|---|
| `app/config.py` | Settings from environment. Secrets (demo session, private keys) come only from the environment |
| `app/db.py` | SQLite schema and recorded migrations (`schema_migrations`) |
| `app/contracts.py` | Frozen schemas, OpenAPI, ABI, and RFC 8785 JCS + SHA-256 |
| `app/evidence.py` | Evidence acceptance: schema, cross-field checks, geometry, safe paths, file hashes. Kept equivalent to `tools/contract_helpers.py`; a parity test checks this |
| `app/policy.py` | Policy v1 from `config/policy.v1.json`: quality, decision, decision record, action flags |
| `app/ingest.py` | Import pipeline, artifact store, deduplication, oracle freeze planning |
| `app/operations.py` | `verify`/`issue`/`buy`/`transfer` gates and request idempotency |
| `app/worker.py` | Durable jobs and the operation lifecycle (sign, broadcast, reconcile, confirm) |
| `app/chain/` | One `ChainAdapter` interface: `web3_adapter.py` (real Anvil) and `mock.py` (CONTRACT_FIXTURE only) |
| `app/main.py`, `app/views.py` | FastAPI routes and response models for exactly the frozen OpenAPI |
| `tools/seed.py`, `tools/import_bundle.py` | Plot seed command and the RS bundle import command |
| `migrate.py`, `worker.py`, `serve.py` | `python -m backend.migrate`, `python -m backend.worker`, `python -m backend.serve` |
| `tests/` | Role tests (unit, API, persistence, reconciliation, E2E) |

## Setup

From the repository root, using Python 3.12 or 3.13:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements-contracts.txt -r backend/requirements-backend.txt
npm ci --ignore-scripts
```

On Windows PowerShell, use `.\.venv\Scripts\python.exe`, `npm.cmd`, and `$env:PYTHONUTF8='1'`.

## Cold start: CONTRACT_FIXTURE (mock ledger, no chain required)

```bash
export PYTHONUTF8=1 BACKEND_MODE=CONTRACT_FIXTURE BACKEND_DEMO_SESSION=local-demo-session-change-me
./.venv/bin/python -m backend.migrate               # idempotent schema migrations
./.venv/bin/python -m backend.tools.seed            # registers fixtures/plot.json (idempotent)
./.venv/bin/python -m backend.serve                 # http://127.0.0.1:8000/api/v1 plus embedded worker
# or run two processes: backend.serve --no-worker and backend.worker
```

Smoke test:

```bash
H='X-Demo-Session: local-demo-session-change-me'
curl -s http://127.0.0.1:8000/api/v1/health
curl -s -H "$H" -H 'X-Demo-Actor: issuer' -H 'Idempotency-Key: verify-baseline-1' \
     -H 'Content-Type: application/json' -d '{"scenario_id":"baseline"}' \
     http://127.0.0.1:8000/api/v1/plots/SYNTHETIC-PLOT-001/verify          # 202 + job
curl -s -H "$H" http://127.0.0.1:8000/api/v1/jobs/<job_id>                # SUCCEEDED + verification_id
```

In CONTRACT_FIXTURE mode, `/health` reports `mode: CONTRACT_FIXTURE`. Its `chain`/`deployment_id`
describe the **mock ledger**, which is not a blockchain. Mock receipts and anchors are never
on-chain proof. The mock uses chain ID `0` and refuses to run in LOCAL_DEMO.

## LOCAL_DEMO: real local Anvil (Blockchain module deployment)

1. Blockchain (see `blockchain/README.md`) runs `anvil --port 8545 --chain-id 31337` and
   `npm run deploy`. The deploy writes the deployment manifest (validated against
   `contracts/deployment.schema.json`).
2. Backend starts against that manifest, with the dev keys of the **distinct** issuer, oracle,
   buyer and recipient roles:

```bash
export BACKEND_MODE=LOCAL_DEMO BACKEND_CHAIN_ADAPTER=web3 BACKEND_RPC_URL=http://127.0.0.1:8545 \
       BACKEND_DEPLOYMENT_PATH=runtime/deployment.json BACKEND_DEMO_SESSION=... \
       BACKEND_PRIVATE_KEY_ISSUER=... BACKEND_PRIVATE_KEY_ORACLE=... \
       BACKEND_PRIVATE_KEY_BUYER=... BACKEND_PRIVATE_KEY_RECIPIENT=...
./.venv/bin/python -m backend.migrate && ./.venv/bin/python -m backend.tools.seed && ./.venv/bin/python -m backend.serve
```

Chain operations run only while all of these identity checks pass. Otherwise `/health` shows
`chain: DOWN` and operations are held or failed without broadcast:
- `eth_chainId` equals the manifest chain ID.
- keccak256 of the runtime code equals `contract_code_hash`. The code is empty after an Anvil restart.
- SHA-256 of `contracts/contract-abi.json` equals `abi_sha256`.
- Each signer key derives the manifest address for its role.

Batches are stored per `deployment_id`. A new deployment never reuses old batches.

## Recovery and restart

- All state lives in SQLite. After a crash, restart `backend.serve` and/or `backend.worker`.
  The worker re-queues interrupted `RUNNING` jobs (the import is idempotent by evidence hash).
  It then reconciles `QUEUED` and `SUBMITTED` operations using their **stored** intent, signed
  bytes, nonce and tx hash. It never re-signs with a new nonce.
- A single worker lease (`worker_leases`) keeps a second worker from sending transactions.
- A receipt timeout keeps the operation `SUBMITTED` (`error.code = RECEIPT_PENDING`). If the node
  has forgotten the transaction, the same bytes are re-broadcast.
- A demo reset is explicit: stop the services, then move `backend/runtime/` aside. Nothing is
  deleted silently.

## Handoffs

### RS
- **Register the plot first:** `python -m backend.tools.seed --rs-request <request.json> [--name NAME] [--area-ha HA]`.
  It uses the request's approved geometry and `plot_geometry_hash` (checked against JCS SHA-256).
  By default the area is the WGS84 geodesic area.
- **Import command:** `python -m backend.tools.import_bundle --bundle <bundle_dir> [--evidence <file>] [--computation-mode COMPUTED|CACHED_REPLAY] [--plot-id ID]`.
  The bundle root must contain `source-index.json` and every relative artifact and source path.
- **Accepted:** exit code 0 and `{"accepted": true, "created", "verification_id", "evidence_hash", "decision", "reason", "decision_hash"}`.
  A repeated import returns `created: false` with the same ID. It creates no new decision or event.
- **Rejected:** exit code 2 and `{"accepted": false, "error": {"code": "INVALID_EVIDENCE", "message", "details"}}`
  on stderr. Rejections cover schema errors (including `FROZEN`, `evidence_hash` or `confidence`
  fields), chronology, CRS/grid/units, counts and areas, geometry hash, FIRMS window, path
  traversal or symlinks, artifact/source hash or size, oversized files, and outcome/count
  disagreement. No decision is recorded.
- **Computed mode:** `BACKEND_RS_MODE=rs_cli` runs `python -m rs.verify --request <scenario rs_request> --output <job dir>`
  per job and marks the result `COMPUTED`. Real scenes need `config/scenarios.json` entries
  (Team Lead/RS config).
- **Artifact IDs:** RS `artifact_id` values only need to be unique within a bundle. When a later
  bundle reuses an ID with different bytes, Backend publishes a deterministic namespaced ID
  (`<artifact_id>.<first 12 hex of sha256>`). Consumers use `Verification.artifacts[].url`.
- **Verified against `feat/rs-pipeline@f094a6e`** (real bundles, no edits; plots registered from
  the request geometry and hash). All three bundles are accepted as REAL/COMPUTED, and served
  artifacts pass hash checks.

  | Bundle | Quality | Decision |
  |---|---|---|
  | Dadia `no_change` | SUFFICIENT (97) | `NO_RESTRICTION` |
  | Dadia `fire` | SUFFICIENT (97); 84.24 ha, 6.0% of forest | `REVIEW_REQUIRED / DISTURBANCE_UNATTRIBUTED` |
  | Evia `evia_reserve_no_change` | SUFFICIENT (100); 1.68 ha | `REVIEW_REQUIRED / BELOW_POLICY_THRESHOLD` |

  The Dadia fire bundle has FIRMS `NOT_CHECKED`, so frozen policy v1 does not auto-freeze it.
  A real freeze demo needs RS to deliver `firms.support = SUPPORTED` with a matched-points
  artifact.

### Blockchain
- **ABI and events:** the adapter uses only the frozen `contracts/contract-abi.json` and exact
  names (`issue`, `buy`, `transfer`, `freeze`, `getBatch`, `balanceOf`, `Issued`, `Purchased`,
  `Transferred`, `Frozen`). Custom error selectors are decoded from the ABI.
- **Hashes:** `bytes32` arguments are raw SHA-256 digests, never `keccak(text=hex)`. The issuance
  key is `SHA-256(JCS({plot_id, demo_authorization_id, deployment_id}))`.
- **Freeze:** Backend sends `freeze(batchId, evidenceHash, decisionHash, observedAt, 1)` only for
  an ACTIVE batch, and at most once per batch.
- **Confirmation:** a receipt with status 1, then the matching decoded event, then
  `getBatch`/`balanceOf` readback **at the receipt block** (and the previous block for balance deltas).
- **Verified against `feat/chain-registry@5bc947c`** on a local Anvil (see the PR for evidence):
  - issue, buy, transfer and freeze confirmed
  - a direct transfer reverts with `BatchNotActive`
  - exactly one `Frozen` event
  - after an Anvil restart, identity fails with `CODE_HASH_MISMATCH`

### Frontend
- **Base URL:** `http://127.0.0.1:8000/api/v1`. The OpenAPI document is `GET /openapi.json`,
  identical to `contracts/openapi.yaml`, so types can be generated from either.
- **Headers:** every route except `/health` needs `X-Demo-Session`. `/plots/{id}` and `/credits`
  also need `X-Demo-Actor`. Every POST needs `X-Demo-Actor` and a stable `Idempotency-Key`
  (8–128 characters) reused on retries and double clicks.
- **Polling:** `202` means accepted, not success. Poll `status_url` until the job reaches
  `SUCCEEDED`/`FAILED` or the operation reaches `CONFIRMED`/`FAILED`.
  - A `SUBMITTED` operation may carry a diagnostic `error` (`RECEIPT_PENDING`, `EXPECTED_EVENT_MISSING`, `READBACK_MISMATCH`). It is **not** confirmed.
  - Show `FROZEN` only from `/credits` `credit_status`, which is chain readback.
  - A pending freeze makes `/plots/{id}` return `action_block_reason: "Freeze requested; ..."` and all flags false.
- **Errors:** every error uses the `{error: {code, message, details}, request_id}` envelope.
  - 401 `UNAUTHORIZED`
  - 403 `FORBIDDEN`
  - 404 `NOT_FOUND`
  - 409: `IDEMPOTENCY_CONFLICT`, `ACTION_NOT_ALLOWED`, `AUTHORIZATION_ALREADY_USED`, `BATCH_NOT_ACTIVE`, `INSUFFICIENT_BALANCE`, `DEPLOYMENT_MISMATCH`
  - 422: `VALIDATION_ERROR`, `INVALID_RECIPIENT`, `AUTHORIZATION_PLOT_MISMATCH`, `UNKNOWN_SCENARIO`
  - 503: `CHAIN_UNAVAILABLE`, `SERVICE_UNAVAILABLE`, `ARTIFACT_INTEGRITY_FAILED`
  - Job errors use `INVALID_EVIDENCE` or `JOB_ERROR`.
- **Labels:** show `evidence.dataset_kind` (`SYNTHETIC`/`REAL`), `computation_mode`
  (`CACHED_REPLAY`/`COMPUTED`), `observation_mode` (`HISTORICAL_REPLAY`) and `/health` `mode`.
- **Artifacts:** serve only through `/api/v1/artifacts/{artifact_id}`. They are hash-checked
  again on every read.

## Tests

```bash
PYTHONUTF8=1 ./.venv/bin/python -m pytest backend -q      # role tests (they run only when backend/ is targeted)
PYTHONUTF8=1 ./.venv/bin/python -m pytest -q              # shared baseline, still 68 tests
npm run check:abi
git diff --check
```

The real Anvil E2E (`backend/tests/test_e2e.py::test_e2e_local_anvil`) runs when
`BACKEND_E2E_RPC_URL`, `BACKEND_E2E_DEPLOYMENT` and `BACKEND_E2E_KEY_{ISSUER,ORACLE,BUYER,RECIPIENT}`
are set. It is skipped otherwise. One reproducible command (needs `anvil`, `node`, `npm`) does it all:

```bash
./.venv/bin/python -m backend.tools.e2e_local_anvil                          # Blockchain from origin/feat/chain-registry (read-only export)
./.venv/bin/python -m backend.tools.e2e_local_anvil --blockchain-ref worktree # after the Blockchain PR is merged
```

The runner:
1. Starts a throwaway Anvil on port 8547 and deploys with `blockchain/tools/deploy-local.cjs`.
2. Reads the public dev keys from Anvil's own output, so no key is stored.
3. Runs issue → buy → transfer, holding mining and restarting the backend while the transfer is
   `SUBMITTED`, so it must confirm with the same bytes and nonce.
4. Continues with fire decision → oracle freeze → direct transfer revert.
5. Writes receipts, readback and proof to `--evidence-out`.

## Known limitations

- P0 has one plot, one batch per plot, and one demo authorization per deployment (the
  issuance key includes `deployment_id`).
- Demo headers are not production authentication. Keep the API bound to loopback unless CORS
  and access are configured deliberately.
- `/health` has no contract field to label a mock ledger; the only marker is
  `mode: CONTRACT_FIXTURE`, and consumers must use it.
- A status-1 receipt with a missing event or a readback mismatch stays `SUBMITTED` with an error
  until reconciled. It is never promoted to `CONFIRMED`, and it is not auto-failed either.
- `config/scenarios.json` has `real_scenes_configured: false`. Real RS bundles need that
  configuration update from the RS owner and the Team Lead.
