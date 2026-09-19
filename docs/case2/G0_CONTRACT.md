# G0 — the shared Carbon Lens v2 contract

Owner: Backend (Integration Owner). Consumers: RS, Trust, Frontend, Team Lead.

Frozen `contracts-v1.0.0` is untouched. Everything below lives in `contracts/v2/` and
`fixtures/v2/`, beside the v1 documents and never on top of them.

| Document | What it fixes |
|---|---|
| `contracts/v2/api-models.v2.schema.json` | Every public wire model of `/api/v2` |
| `contracts/v2/internal-models.v2.schema.json` | The adapter boundary: `RasterAnalysis`, `CellLayer`, `CarbonAssessment`, `ArtifactManifest` |
| `contracts/v2/openapi.v2.yaml` | The HTTP shape: seven routes, their headers and their failure codes |
| `fixtures/v2/` | Labelled examples; see `fixtures/v2/README.md` |

## Routes

```
GET  /api/v2/catalog
POST /api/v2/areas/measure                              -> 200 AreaMeasurement
POST /api/v2/analyses                                   -> 202 {analysis_id, job_state, status_url}
GET  /api/v2/analyses/{analysis_id}
GET  /api/v2/analyses/{analysis_id}/artifacts/{artifact_id}
GET  /api/v2/analyses/{analysis_id}/report?format=json|html
GET  /api/v2/analyses/{analysis_id}/proof
```

`X-Demo-Session` on every route; `Idempotency-Key` additionally on the one mutation. Path
identifiers are opaque and must not be parsed.

**There is no `X-Demo-Actor` header.** A role a client can set is not an authorization, so
the caller is derived from the authenticated session and nothing else. Anyone who was
sending that header should stop; it is ignored.

`POST /areas/measure` answers "how big is this, and may I submit it" without creating an
analysis. It runs the same normalisation and the same geodesic area as the analysis path,
so a figure shown before submitting cannot disagree with the run that follows. A contour
that may not be used comes back as `200` with `valid: false` and named `errors[]`; `422`
is only for a body that is not a GeoJSON geometry at all.

## The six status axes never collapse into one

| Axis | Values | Answers |
|---|---|---|
| `job_state` | `QUEUED` `RUNNING` `SUCCEEDED` `FAILED` | did the worker finish |
| `calculation_status` | `AVAILABLE` `UNAVAILABLE` | is there a number for Q |
| `evidence_status` | `SUFFICIENT` `REVIEW_REQUIRED` `INSUFFICIENT` | how well the change is explained |
| `claim.status` | `NOT_PROVIDED` `NOT_APPLICABLE` `NOT_COMPARABLE` `UNASSESSABLE` `SUPPORTED_BY_CASE` `PARTIALLY_SUPPORTED_BY_CASE` `NOT_SUPPORTED_BY_CASE` | how a stated volume compares with Q |
| `passport.status` | `DRAFT` `FINALIZED` | has a verifier signed off this document |
| `anchor.status` | `NOT_REQUESTED` `PENDING` `CONFIRMED` `FAILED` | is the passport hash anchored |

`passport.status` and `anchor.status` are separate fields on separate objects and share no
vocabulary. A `FINALIZED` passport with `NOT_REQUESTED` anchor is the normal case: a
verifier signs off documents, a chain records hashes, and neither implies the other.

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

## A claim of zero is `NOT_APPLICABLE`

`claimed_units = 0` gives `claim.status = NOT_APPLICABLE`, `supported_share = null`,
`unsupported_gap = 0` and `mismatch_reasons = ["NO_POSITIVE_CLAIM"]`. Nothing positive was
stated, so nothing was supported; calling that `SUPPORTED_BY_CASE` would let an empty
statement inherit the vocabulary of a confirmed one. The field is named `unsupported_gap`
throughout, and it is never negative.

## Coverage, area and the arithmetic that lands outside the range

Geodesic area is not additive over a partition, so a sum over native cells can land a
hair above the whole. Two rules follow:

- every public fraction is clamped to `[0, 1]`, and the unclamped value is published
  beside it in `coverage.coverage_fraction_raw` — a reader who sees `1.0` can find out it
  was `1.000000113`;
- `areas.missing_ha = max(0, requested - calculated)` is never negative, and
  `areas.area_difference_ha = calculated - requested` keeps its sign. They answer
  different questions and are not interchangeable.

Consumers of `carbon`: pass the **clamped** share into `compute_units`. The raw value
belongs in the report, not in a validator that requires a share.

## Warnings and limitations are structured and separate

`evidence.warnings[]` is `{code, severity, message, details}` with `severity` one of
`INFO`, `WARNING`, `BLOCKING`. `limitations[]` is `{code, message}`. Switch on `code`;
`message` is Russian prose and may be localised, never parsed. A warning is about this
run; a limitation always holds. The two lists never share a code.

## One canonical Eproj

The emission figure is published exactly once, as `units.eproj_tco2e`. `change` carries
the stocks and their difference and points at it with `change.eproj_ref`; it does not
restate it. Backend compares the raster owner's own derivation against it and raises a
`BLOCKING` `EPROJ_DISAGREEMENT` warning if the two ever differ by more than floating-point
noise, rather than averaging them.

## Unknown enumeration values

Every enumeration in the contract is closed, and a value outside it is refused rather than
served — a test proves it. The other half of that bargain is on the consumer: treat an
unrecognised value as unknown and keep rendering, so that adding a value is a contract
change and not an outage.

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
  stays `UNKNOWN`. Whenever zones are published, `zone.artifact_ref` points at the GeoJSON
  artifact whose features carry `zone_id`, so a map can draw them without a second
  contract.

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
branch. `carbon` keeps `units`, Backend keeps nullability and presentation. Four
alignments were settled in Backend's favour of the engine, so that nobody has to translate
twice:

- `pool` is `AGB` and `unit` is `tCO2e`, exactly as the engine emits them. These strings
  are compared for equality when a claim is checked, so a second spelling would
  manufacture a `POOL_MISMATCH` out of nothing.
- `passport.comparison_result` uses the engine's version vocabulary — `INITIAL`,
  `REVISION_OF_SAME_SCOPE`, `NEW_OBSERVATION`, `NOT_COMPARABLE`. Whether Q rose or fell is
  a separate presentational field, `comparison_direction`, so "a later observation" is
  never read as "the earlier passport was wrong".
- `spatial_dependence` uses the method freeze names, `INDEPENDENT_NATIVE_CELLS` and
  `FULL_SPATIAL_CORRELATION`. Backend translates the engine's spelling at the adapter
  boundary and changes no number, so the engine may rename at its own pace.
- `claim.status` gains `NOT_APPLICABLE` and `mismatch_reasons` gains `NO_POSITIVE_CLAIM`.
  Backend normalises a zero claim to these values itself, so an engine that has not
  adopted them yet still cannot publish a zero claim as supported.

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
