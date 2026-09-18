# Frontend module — MRV credit dashboard

Owner: Frontend developer and Demo Operator (Issue #5, branch `feat/frontend-dashboard`).
One SPA built against the frozen `contracts/openapi.yaml` (`contracts-v1.0.0`). The UI never
calls RS providers, STAC/CDSE/FIRMS or blockchain RPC: only Backend `/api/v1` or the
contract-compatible fixture adapter.

## Stack

React 19 + TypeScript 5.9 (strict) + Vite 8, Leaflet 1.9 without remote tiles, Vitest + Testing Library,
Playwright (system Microsoft Edge, no browser download). Node `24.19.0` (root `.nvmrc`).
IBM Plex Sans / Plex Mono are bundled via `@fontsource` (OFL-1.1), so the offline `dist` loads no remote fonts.

## Carbon Lens workspace (`/lens`)

Separate route for the Carbon Lens case; the P0 MRV dashboard stays on `/`. Open `http://127.0.0.1:5173/lens`
in dev, `http://127.0.0.1:4173/lens` on the built `dist`, or `index.html#/lens` when the offline bundle is
opened from a folder. Demo script: [DEMO_LENS.md](DEMO_LENS.md). Integration assumptions for G0:
[docs/LENS_INTEGRATION.md](docs/LENS_INTEGRATION.md).

| Zone | Content |
|---|---|
| Запрос | four AOI from `data/areas.csv`, drawn rectangle, GeoJSON import, official sub-request `CHECK_TRANSFER_01`, years 2019–2024, optional `claimed_units` labelled as user input |
| Карта | contour from `data/areas.geojson`, zone outlines, coverage-gap layer, WGS84 cursor readout, scale, no remote tiles |
| Слои карты | per-layer availability with a reason — a layer the service cannot supply reads «нет данных», never an empty map |
| Краткий результат | Q with `null` and `0` kept apart, scenario value at 500/1500/4000 ₽, unsupported part of the claim, four independent badges |
| Разбор расчёта | Eproj / Ebase / R, then UNC → Radj → reserve → rounding → Q, each step exposing its formula and inputs |
| Покрытие | biomass CCI, baseline table and optical paired-valid as separate axes |
| Наблюдения | Sentinel-2 scenes with cloud share and SCL validity, MODIS event rows with their uncertainty, baseline rows — all from `data/` |
| Зоны | area, dates, ΔC, contribution to E, cause status, linked event record, source; no per-zone Q |
| Сравнение | runs of the session side by side with the limits of the comparison; no ranking |
| Паспорт | versions, hashes, sources with licences, JSON and HTML download, integrity check of a received file |

Data boundary: `src/lens/adapter.ts` defines the only interface the screens know. Territories, geometry,
areas, the baseline table, scenes, fire events, coefficients, prices and the source registry are read from
the official `data/` archive through `src/lens/data.ts`. Computed values (stock, E, R, uncertainty, Q) come
from the adapter: either `createFixtureLensClient` over labelled sets — the conditional example printed in
`doc/Постановка_задачи` (Q = 395) and `UNIT_TEST_VECTOR` logic vectors — or `createHttpLensClient` once G0
is published. The UI never computes scientific values: it formats them, multiplies Q by a scenario price and
shows the claim gap.

| Lens mode | How | Data |
|---|---|---|
| Labelled set (default) | `VITE_LENS_API_MODE=fixture` or `?lensapi=fixture` | official `data/` plus the labelled result sets, offline |
| Live service | `VITE_LENS_API_MODE=http` + `VITE_LENS_API_BASE_URL=<origin>/api/v2`, credential via `?token=` or the access panel | Backend v2; the credential is a runtime value and is never baked into `dist` |

Failures of the live service are shown as errors; the labelled set is never substituted automatically.

## Interface

One map-first monitoring workspace (desktop-first, collapses to a single column ≤ 900 px):

| Area | Content (Backend fields only) |
|---|---|
| Top bar | wordmark, methodology dialog, service health, `/health.mode`, demo actor |
| Source bar | FIXTURE adapter, Backend URL, CONTRACT_FIXTURE → MOCK LEDGER disclaimer |
| Project header | `plot_id`, name, centroid of the real geometry, area, last scene date/provider, `dataset_kind` / `computation_mode` / `observation_mode` |
| Status pipeline | RS outcome → evidence quality → decision → transaction state → credit status (`/credits` readback only) |
| Left rail | Evidence Quality Score (coverage indicator, not a probability) with quality fields; action gate from `can_*` / `action_block_reason`; scenarios and history |
| Map | graticule, cursor WGS84 readout, scale, overlay layer panel (plot boundary, previews, dNBR preview, affected area, FIRMS points — only when the artifact exists), on-map before/after divider (pointer, touch, keyboard) |
| Right rail | MRV evidence sections (scenes, quality, SCL mask, forest metrics, dNBR legend, FIRMS, method, limitations, artifacts, decision record) · registry record · proof/anchors |
| Journal | observation → decision → transaction → event timeline plus local log of Backend rejections |

Not shown because API v1 does not provide them: control area, leakage buffer, carbon/tCO₂e estimates,
token ids, NDVI time series. Missing numeric values render as `N/A`, never as zero.

Screenshots: [`docs/screenshots/`](docs/screenshots/) — real Dadia before/after and disturbance, real Evia
review-required, synthetic no-change / freeze-requested / FROZEN registry, artifact integrity failure, unknown-enum contract drift, mobile.

Unknown enum values (contract drift) never crash the UI: every status table is read through `metaFor` in
[src/domain/status.ts](src/domain/status.ts), which falls back to a neutral `UNKNOWN: <received>` badge with a plain
explanation, and [RootErrorBoundary](src/components/RootErrorBoundary.tsx) keeps `#root` populated with a recovery UI
for any unexpected render error.

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
| `test` | 144 tests: status mapping vs schema enums, both adapters, polling, geometry, artifact pairing, components, unknown-enum resilience, root error boundary, golden-fixture flow, Carbon Lens adapter and workspace |
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

6. Optional real evidence on the same stand (Backend CLIs, no contract change):
   ```powershell
   .\.venv\Scripts\python.exe -m backend.tools.seed --rs-request rs/configs/request_fire.json --name 'Dadia-Lefkimi-Soufli Forest NP, Evros'
   .\.venv\Scripts\python.exe -m backend.tools.import_bundle --bundle rs/bundles/no_change --computation-mode COMPUTED
   .\.venv\Scripts\python.exe -m backend.tools.import_bundle --bundle rs/bundles/fire --computation-mode COMPUTED
   .\.venv\Scripts\python.exe -m backend.tools.seed --rs-request rs/configs/request_evia_reserve_no_change.json --name 'Pefki reserve AOI, North Evia'
   .\.venv\Scripts\python.exe -m backend.tools.import_bundle --bundle rs/bundles/evia_reserve_no_change --computation-mode COMPUTED
   ```
   Backend namespaces reused artifact ids (`<rs id>.<sha prefix>`); the SPA pairs `artifacts[]` with
   `evidence.artifacts[]` by role + sha256, so real previews keep their `bounds_wgs84`.

In Backend `CONTRACT_FIXTURE` mode `/health.chain` and receipts describe Backend's **mock ledger**;
the UI shows a “MOCK LEDGER / не on-chain” banner and note whenever `/health.mode` is `CONTRACT_FIXTURE`.

Frontend relies on: `status_url` / `artifacts[].url` beginning with `/api/v1/`; `/credits.credit_status`
as the only source of ACTIVE/FROZEN; oracle FREEZE operations appearing in `/events` as
`TX_SUBMITTED` / `TX_CONFIRMED` / `TX_FAILED` with `operation_id`; artifacts served with
`X-Demo-Session` (fetched as blobs, not `<img src>`).

## Demo

See [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) for the ≤90 s scenario, operator script and frame list.
