# Demo walkthrough (fixture rehearsal)

Status: stable fixture walkthrough. The final demo video is recorded only after Backend integration.
In fixture mode everything is SYNTHETIC; do not present numbers as a real fire.

Setup: `npm run build && npm run preview`, open `http://127.0.0.1:4173/?api=fixture`, 1440×900,
browser zoom 100 %, devtools closed. The same flow is automated in `e2e/demo-flow.spec.ts` (~22 s).

| # | Operator action | What the audience must see | Frame |
|---|---|---|---|
| 1 | Open the dashboard | Plot, boundary, area 100 ha, badges FIXTURE / CONTRACT_FIXTURE / SYNTHETIC / CACHED_REPLAY / HISTORICAL_REPLAY | `01-baseline` |
| 2 | Point at the status strip and before/after | NO_CHANGE · SUFFICIENT (EQS 100, not a probability) · NO_RESTRICTION · no operation · no batch; aligned previews with scene IDs and dates | `01-baseline` |
| 3 | Credits → “Выпустить серию” (actor issuer) | ISSUE QUEUED → SUBMITTED → CONFIRMED with receipt; batch #1 ACTIVE, seller 100 | — |
| 4 | Actor buyer → “Купить” 10 | BUY CONFIRMED; buyer 10, seller 90 | `02-active-after-buy` |
| 5 | Actor issuer → “Historical replay: post_fire T1 → T2” | Job QUEUED → RUNNING → SUCCEEDED; map shows affected area + FIRMS point (thermal anomaly, not perimeter) | — |
| 6 | Point at decision vs credit | DISTURBANCE_DETECTED · FREEZE_REQUESTED / FIRE_REVERSAL while credit is still ACTIVE, banner “Приостановка запрошена” | `03-freeze-requested-not-frozen` |
| 7 | Wait ~4 s | Journal: FREEZE TX_SUBMITTED → TX_CONFIRMED; credit becomes FROZEN (red) only after that | — |
| 8 | Actor buyer → Credits | Transfer/buy disabled with reason; “Отправить попытку” → HTTP 409 BATCH_NOT_ACTIVE, logged; balances unchanged | `04-frozen-transfer-rejected` |
| 9 | Proof tab | evidence hash, recomputed hash, decision hash, anchor `Frozen` for the fire evidence only | `05-proof-frozen-anchor` |
| 10 | If Backend fails live | Top banner shows the error; click “Открыть offline fallback (FIXTURE, synthetic)” and say that this is the synthetic rehearsal | — |

Say: “FROZEN is a temporary restriction of this prototype, not legal cancellation. The button is only
disabled in the UI; the contract enforces the prohibition.”

Never say: “simulate fire”, “probability”, “certified”, or that fixture receipts are on-chain.

Reset: reload the page (fixture state lives in browser memory; pending intents are keyed per adapter).
