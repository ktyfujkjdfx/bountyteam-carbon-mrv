# G0 — the shared Carbon Lens v2 contract

Owner: Backend (Integration Owner). Consumers: RS, Trust, Frontend, Team Lead.

Frozen `contracts-v1.0.0` is untouched. Everything below lives in `contracts/v2/` and
`fixtures/v2/`, beside the v1 documents and never on top of them.

| Document | What it fixes |
|---|---|
| `contracts/v2/api-models.v2.schema.json` | Every public wire model of `/api/v2` |
| `contracts/v2/internal-models.v2.schema.json` | The adapter boundary: `RasterAnalysis`, `CellLayer`, `CarbonAssessment`, `ArtifactManifest` |
| `contracts/v2/openapi.v2.yaml` | The HTTP shape: six routes, their headers and their failure codes |
| `fixtures/v2/` | Labelled examples; see `fixtures/v2/README.md` |

## Routes

```
GET  /api/v2/catalog
POST /api/v2/analyses                                   -> 202 {analysis_id, job_state, status_url}
GET  /api/v2/analyses/{analysis_id}
GET  /api/v2/analyses/{analysis_id}/artifacts/{artifact_id}
GET  /api/v2/analyses/{analysis_id}/report?format=json|html
GET  /api/v2/analyses/{analysis_id}/proof
```

`X-Demo-Session` on every route. `X-Demo-Actor` and `Idempotency-Key` additionally on the
one mutation, reusing the P0 discipline rather than inventing a second auth model. Path
identifiers are opaque and must not be parsed.

## The five status axes never collapse into one

| Axis | Values | Answers |
|---|---|---|
| `job_state` | `QUEUED` `RUNNING` `SUCCEEDED` `FAILED` | did the worker finish |
| `calculation_status` | `AVAILABLE` `UNAVAILABLE` | is there a number for Q |
| `evidence_status` | `SUFFICIENT` `REVIEW_REQUIRED` `INSUFFICIENT` | how well the change is explained |
| `claim.status` | `NOT_PROVIDED` `NOT_COMPARABLE` `UNASSESSABLE` `SUPPORTED_BY_CASE` `PARTIALLY_SUPPORTED_BY_CASE` `NOT_SUPPORTED_BY_CASE` | how a stated volume compares with Q |
| `anchor.status` | `NOT_REQUESTED` `PENDING` `CONFIRMED` `FAILED` | is the passport hash anchored |

A job that succeeds with `q = null` is a success. Partial coverage is a scientific
outcome, not a worker failure. Poor optical quality lowers `evidence_status` and by
itself never makes `q` null.

## `q = null` and `q = 0` are different answers

`units.status = UNAVAILABLE` carries `unavailable_reason` and `q = null`: a mandatory
input was missing or unusable. `units.status = AVAILABLE` with `q = 0` carries
`zero_reason` — one of `NON_POSITIVE_RELATIVE_RESULT`, `UNCERTAINTY_TOO_HIGH`,
`ROUNDED_TO_ZERO` — and means the rules of the case were applied and gave zero. The two
vocabularies do not overlap, and a test enforces that. Frontend must not render them the
same way, and `scenario_values` is all-null whenever `q` is null.

## Field groups of `AnalysisResult`

`fixture` · `identity` · `run` · `request` · `calculation_status` · `evidence_status` ·
`areas` · `coverage` · `timeline[]` · `change` · `uncertainty` · `baseline` · `units` ·
`scenario_values` · `claim` · `zones[]` · `evidence` · `passport` · `sources[]` ·
`artifacts[]` · `limitations[]` · `notes[]`.

Three deliberate separations:

- `identity` holds the deterministic description of the calculation; `run` holds the run
  time, the run id and which adapter answered. The passport content hash covers the
  scientific content and never the run time, so a genuine replay is distinguishable from
  a coincidence.
- `coverage` has four independent fractions — biomass, uncertainty, baseline and
  optical-paired-valid. They are never averaged into one "coverage" number.
- A zone reports `fact` and `cause` separately. Cover loss is something the loss-year
  product can establish; why it was lost needs its own evidence, and without it `cause`
  stays `UNKNOWN`.

## Language the contract will not carry

No public `INVESTABLE`, no "approved for purchase", no "proven fraud". A gap value is the
scenario value of the unsupported part of a claim: not an established loss, not a
probabilistic Value at Risk, not guaranteed savings. A hash anchor detects a changed file
against a trusted record; it does not prevent double selling and does not certify that
the calculation is true. A test greps the schema for the forbidden vocabulary.

## Who produces what

| Owner | Produces | Backend consumes it as |
|---|---|---|
| RS (`rs/case2/`) | `analysis_payload`, `cells_payload`, `manifest.build` | `RasterAnalysis`, `CellLayer`, `ArtifactManifest` |
| Trust (`carbon/`) | `compute_interval`, `compute_baseline`, `compute_units`, `compare_claim` | `CarbonAssessment` |
| Backend (`backend/`) | API, jobs, persistence, artifact and report serving, passports | — |
| Frontend (`frontend/`) | `/lens`, generated v2 types | the public models only |

Backend calls those functions and copies their numbers. It contains no stock-difference,
no interval, no baseline and no Q arithmetic of its own, and a test asserts that the
adapter output validates against the internal schema before any of it reaches a passport.

## Answers to the open questions consumers raised

**RS.** The internal schema matches `rs.case2.payload` as it stands today; Backend added
no field and renamed none. The models are additive: adding a key is always safe, removing
or retyping a required key is a contract change. `change_evidence` is passed through
opaquely apart from the zone rows Backend projects into `zones[]`.

**Trust.** `carbon.reasons` is the source of truth for the status and reason strings; the
schema enumerations are pinned to it by a test that runs as soon as `carbon/` is on the
branch. `carbon` keeps `units`, Backend keeps nullability and presentation.

**Frontend.** The provisional shapes in `src/lens/types.ts` were the right vocabulary;
the differences are structural, not semantic. Job and result are one resource
(`GET /analyses/{id}` returns `job_state` and, when ready, `result`), so the separate
`result_id` round trip is gone; `coverage` is an object of four named fractions rather
than an array; `units` uses `r_tco2e`, `ratio`, `unc`, `radj_tco2e`, `buffer_tco2e`,
`rounding_residual_tco2e`; the zero and unavailable reasons are two fields rather than
one. `fixture` stays exactly as proposed and must stay visible on screen.

**Team Lead.** The method freeze covers the interval mode and the sensitivity grid owned
by Trust, and the zone attribution rule owned by RS. Backend records
`identity.method_version` as the composition of the three versions, so a passport names
the method it was produced under.

## Changing this contract

One Backend PR with consumer review, never an edit by a consumer to a shared file. A
change that removes or retypes a required field needs the producer, the consumer and the
Team Lead to agree, and the fixtures move in the same commit.
