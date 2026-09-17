# Frontend module — MRV credit dashboard

Owner: Frontend developer and Demo Operator (Issue #5, branch `feat/frontend-dashboard`).
One SPA built against the frozen `contracts/openapi.yaml` (`contracts-v1.0.0`). The UI never
calls RS providers, STAC/CDSE/FIRMS or blockchain RPC: only Backend `/api/v1` or the
contract-compatible fixture adapter.

## Stack

React 19 + TypeScript 5.9 (strict) + Vite 8, Leaflet 1.9 without remote tiles, Vitest + Testing Library,
Playwright (system Microsoft Edge, no browser download). Node `24.19.0` (root `.nvmrc`).

## Commands

Run from `frontend/` (Windows PowerShell: use `npm.cmd` if `npm.ps1` is blocked).

```bash
npm ci
npm run dev            # http://127.0.0.1:5173, fixture adapter by default
npm run verify         # check:api + lint + typecheck + unit/component tests + build + check:dist
npm run e2e            # Playwright on built dist via vite preview (needs npm run build first)
npm run preview        # serve dist at http://127.0.0.1:4173
```

| Script | What it proves |
|---|---|
| `gen:api` / `check:api` | `src/api/generated/openapi.ts` is regenerated from `contracts/openapi.yaml`, check fails on drift |
| `lint` | ESLint strict TS + React hooks rules; literal `SIGNING` forbidden in `src/` |
| `typecheck` | `strict`, `exactOptionalPropertyTypes`, `noUncheckedIndexedAccess` |
| `test` | 88 tests: status mapping vs schema enums, both adapters, polling, geometry, components, golden-fixture flow |
| `build` + `check:dist` | offline `dist/` with relative paths, no remote hosts, no GeoTIFF |
| `e2e` | full demo flow in a real browser + HTTP failure → manual offline fallback; `e2e/backend-integration.spec.ts` (opt-in) runs the real SPA against a live Backend incl. CORS |

## Adapter selection (config only, never automatic)

| Mode | How | Data |
|---|---|---|
| Fixture (default) | `VITE_API_MODE=fixture` or `?api=fixture` | SYNTHETIC golden fixtures from `fixtures/http_examples.json`, `fixtures/assets`, `config/demo-authorizations.json`; Backend/chain behaviour emulated in the browser |
| Backend HTTP | `VITE_API_MODE=http` or `?api=http` | Backend `VITE_API_BASE_URL` (must end with `/api/v1`) with `X-Demo-Session: VITE_DEMO_SESSION` |

Copy `.env.example` to `.env.local` (not committed). The active mode is always shown in the top bar
and banner. If Backend fails, the UI shows the error and a manual “offline fallback” link; it never
silently substitutes fixtures.

Both adapters implement `MrvApiClient` (`src/api/client.ts`), which maps 1:1 to the 16 OpenAPI
operations. Fixture adapter responses are validated against `contracts/api-models.schema.json`
in `tests/fixtureAdapter.test.ts`.

### Fixture adapter honesty

- Evidence, decisions, hashes and proof values are copied from golden fixtures; the UI never computes
  policy or hashes.
- Only operation gates from `docs/common/status-machine.md` are emulated so the P0 flow can be rehearsed
  offline (issue → buy → post_fire → FREEZE → FROZEN → transfer rejected).
- Tx hashes, receipts, block numbers and balances in fixture mode are synthetic placeholders; every
  such screen carries a FIXTURE label. Nothing is on-chain.

## Backend handoff (Integration Owner)

1. Start Backend (see `backend/README.md`), e.g. CONTRACT_FIXTURE:
   ```powershell
   $env:PYTHONUTF8='1'; $env:BACKEND_MODE='CONTRACT_FIXTURE'
   $env:BACKEND_DEMO_SESSION='<at least 16 characters>'
   $env:BACKEND_CORS_ORIGINS='http://127.0.0.1:5173,http://127.0.0.1:4173'
   .\.venv\Scripts\python.exe -m backend.migrate; .\.venv\Scripts\python.exe -m backend.tools.seed; .\.venv\Scripts\python.exe -m backend.serve
   ```
2. CORS is closed by default; `BACKEND_CORS_ORIGINS` must list the exact SPA origin
   (`localhost` ≠ `127.0.0.1`). The SPA sends `credentials: 'omit'`; it needs methods `GET, POST`
   and headers `Content-Type, X-Demo-Session, X-Demo-Actor, Idempotency-Key`.
3. Frontend `.env.local`:
   ```
   VITE_API_MODE=http
   VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
   VITE_DEMO_SESSION=<value accepted by Backend>
   ```
4. `npm run dev` and open `http://127.0.0.1:5173/?api=http`.
5. Browser integration against the running Backend (uses a fresh Backend DB; the demo authorization is single-use):
   ```powershell
   $env:VITE_API_MODE='http'; $env:VITE_API_BASE_URL='http://127.0.0.1:8000/api/v1'; $env:VITE_DEMO_SESSION='<session>'
   npm run build
   $env:E2E_BACKEND_URL='http://127.0.0.1:8000/api/v1'; $env:E2E_DEMO_SESSION='<session>'
   npx playwright test e2e/backend-integration.spec.ts
   ```

In Backend `CONTRACT_FIXTURE` mode `/health.chain` and receipts describe Backend's **mock ledger**;
the UI shows a “MOCK LEDGER / не on-chain” banner and note whenever `/health.mode` is `CONTRACT_FIXTURE`.

Frontend relies on: `status_url` / `artifacts[].url` beginning with `/api/v1/`; `/credits.credit_status`
as the only source of ACTIVE/FROZEN; oracle FREEZE operations appearing in `/events` as
`TX_SUBMITTED` / `TX_CONFIRMED` / `TX_FAILED` with `operation_id`; artifacts served with
`X-Demo-Session` (fetched as blobs, not `<img src>`).

## Demo

See [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) for the ≤90 s scenario, operator script and frame list.
