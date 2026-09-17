# Demo walkthrough

Status: rehearsed against the merged Backend in `CONTRACT_FIXTURE` mode (mock ledger) and against the
fixture adapter. The final video is recorded only on the release stand; never present fixture or
mock-ledger receipts as on-chain.

Setup (Backend stand): Backend from `main` with CORS for the SPA origin, SYNTHETIC plot plus real Dadia and
Evia bundles imported (see README → Backend handoff). Frontend built with `VITE_API_MODE=http`,
`npm run preview`, open `http://127.0.0.1:4173/`, 1920×1080, zoom 100 %, devtools closed.
Offline fallback: `?api=fixture` (SYNTHETIC, labelled).

| # | Operator action | What the audience must see | Screenshot |
|---|---|---|---|
| 1 | Select `GR-EVROS-DADIA-001` | REAL · COMPUTED · HISTORICAL_REPLAY; real Sentinel-2 scene ids and dates; affected area and 37 FIRMS points on the map | `real-dadia-disturbance` |
| 2 | Map → «До / после», drag the divider | 2023-08-05 forest on the left, 2023-08-30 burn scar on the right; FIRMS points are thermal anomalies, not a perimeter | `real-dadia-before-after` |
| 3 | Point at the status pipeline | DISTURBANCE_DETECTED · SUFFICIENT (EQS is coverage, not probability) · FREEZE_REQUESTED / FIRE_REVERSAL; no credit series on this plot | — |
| 4 | Select `GR-EVIA-PEFKI-RESERVE-001` | Real disturbance below policy threshold → REVIEW_REQUIRED (amber, not a violation), FIRMS NOT_FOUND | `real-evia-review-required` |
| 5 | Select `SYNTHETIC-PLOT-001`, actor issuer → «Historical replay · T0 → T1» | Job QUEUED → SUCCEEDED; NO_CHANGE · SUFFICIENT · NO_RESTRICTION | `synthetic-no-change-full` |
| 6 | Реестр → «Выпустить серию»; actor buyer → «Купить» 10 | ISSUE / BUY CONFIRMED with receipt + readback (MOCK LEDGER note); seller 90, buyer 10 | — |
| 7 | Actor issuer → «Historical replay · T1 → T2» | FREEZE_REQUESTED shown as requested, credit still ACTIVE until the freeze operation confirms | `synthetic-freeze-requested-full` |
| 8 | Wait for the journal | FREEZE TX_SUBMITTED → TX_CONFIRMED; credit status FROZEN from `/credits` | `synthetic-frozen-registry` |
| 9 | Actor buyer → Реестр → «Отправить попытку в Backend» | Transfer disabled in UI; Backend returns 409 BATCH_NOT_ACTIVE, logged; balances unchanged | — |
| 10 | Proof tab; select the older baseline in history | Frozen anchor only for the fire evidence; baseline keeps its own Issued anchor | — |
| 11 | If an artifact is corrupted | Map and scene pair show HTTP 503 ARTIFACT_INTEGRITY_FAILED with request id; the rest of the dashboard stays usable | `artifact-integrity-failed` |
| 12 | If Backend fails live | Error banner + manual «Открыть offline fallback (FIXTURE, synthetic)»; say it is the synthetic rehearsal | — |

Say: “Evidence quality is a coverage indicator, not a probability. FROZEN is a temporary restriction of this
prototype, not legal cancellation; the contract enforces it, the disabled button only mirrors it.”

Never say: “simulate fire”, “probability”, “certified”, “carbon stock”, or that mock/fixture receipts are on-chain.
