# Carbon Lens Backend MVP

Written for RS, Trust, Frontend and the Team Lead. It says what `/api/v2` does today, where
the seams are, and exactly what happens when the real raster core and the real carbon
engine arrive.

The shared contract is in [G0_CONTRACT.md](G0_CONTRACT.md); this document is about the
running service.

## What exists

```
contracts/v2/   api-models.v2.schema.json, internal-models.v2.schema.json, openapi.v2.yaml
fixtures/v2/    labelled contract examples, and replay/ for the raster stand-in
backend/app/v2/ geometry, catalog, ports, adapters/, assemble, store, service, worker,
                report, api
backend/tests/case2/  contract, API, job, decision, passport and adapter suites
```

Nothing under `contracts/`, `fixtures/`, `backend/app/` or `backend/tests/` that belonged to
`contracts-v1.0.0` was modified. `create_app` still builds exactly the frozen v1
application and `/openapi.json` is still byte-for-byte `contracts/openapi.yaml`; the two
services are composed only in `backend/serve.py`.

## Running it

```bash
python -m pip install -r requirements-contracts.txt -r backend/requirements-backend.txt
export BACKEND_DEMO_SESSION="<at least 16 characters>"
python -m backend.migrate            # applies migration 2 alongside the P0 schema
python -m backend.serve              # /api/v1 and /api/v2 with both embedded workers
```

Separate processes instead of the embedded workers:

```bash
python -m backend.serve --no-worker
python -m backend.worker             # P0: jobs and chain operations
python -m backend.lens_worker        # Carbon Lens analyses
```

`--no-lens` serves only the frozen v1 contract. On Windows PowerShell, set
`$env:PYTHONUTF8='1'` and use `.\.venv\Scripts\python.exe`.

The Lens needs no chain, no deployment and no private key. `/lens` opens without any of
them.

## The endpoints

| Route | Notes |
|---|---|
| `GET /api/v2/catalog` | Areas, polygons, available years, the sample sub-request, the three scenario prices, the source register and which adapters are running |
| `POST /api/v2/analyses` | `X-Demo-Actor` and `Idempotency-Key` required; 202 with `analysis_id` and `status_url` |
| `GET /api/v2/analyses/{id}` | `job_state` and, once finished, `result`; `report_url` and `proof_url` appear only when there is something to link to |
| `GET /api/v2/analyses/{id}/artifacts/{artifact_id}` | Manifest-listed files only, re-hashed on the way out |
| `GET /api/v2/analyses/{id}/report?format=json\|html` | The passport; the HTML is self-contained |
| `GET /api/v2/analyses/{id}/proof` | Hashes, versions and the anchor status |

`X-Demo-Session` on every route. `/api/v2/openapi.json` serves `contracts/v2/openapi.v2.yaml`
unchanged, and a test compares the served document with the file.

Failures: 401 unauthenticated, 404 unknown analysis or artifact, 409 idempotency conflict,
422 invalid geometry, period or claim, 503 source unavailable or artifact integrity
failure. No error carries a stack trace, a secret or a local path.

## What is real and what is a stand-in

| Piece | Today | Why |
|---|---|---|
| Areas, polygons, geodesic area, coverage arithmetic | real | read from `data/`, measured with `pyproj.Geod` |
| Baseline, parameters, prices | real | read from `data/methodology/*.csv` |
| Interval, baseline result, units, claim | real formulas, **temporary engine** | `carbon/` is not on this branch, so `adapters/reference_carbon.py` answers |
| Biomass per cell, uncertainty per cell, zones, optical evidence | **stand-in** | `rs/case2/` is not on this branch, so `fixtures/v2/replay/` answers |
| Jobs, persistence, artifacts, passports, reports, proof | real | this module |
| Chain anchor | not implemented | `anchor.status` is `NOT_REQUESTED` and says so |

Both stand-ins announce themselves. Every result carries
`run.dataset_origin = "STUB_FIXTURE"`, `run.raster_adapter = "backend-replay"`, a
`fixture` label the UI must display, and a limitation saying in plain words that the
biomass values were not measured.

The replay adapter answers exactly four contour-and-period keys and nothing else. Every
other request gets `RASTER_ANALYSIS_UNAVAILABLE`, which becomes a successful job with
`q = null` — never a plausible number for a place nobody measured.

| Replay key | Outcome it exercises |
|---|---|
| `RU_TVER_01` 2019–2024 | `q > 0` through the uncertainty deduction |
| `RU_TVER_01` 2019–2022 | `q = 0`, `NON_POSITIVE_RELATIVE_RESULT` |
| `RU_MORDOVIA_03` 2020–2022 | `q = 0`, `UNCERTAINTY_TOO_HIGH` (the stop rule) |
| `CHECK_TRANSFER_01` 2020–2024 | `q = null`, `INCOMPLETE_COVERAGE`, parent baseline on the sub-plot area |

## Connecting the real components

The order matters, and each step is small because the seam was built for it.

**1. RS.** Merge `rs/case2/`. `adapters/raster.py` imports `rs.case2.analysis` at module
load; if the import succeeds, `RasterCoreAdapter` replaces `ReplayRasterAdapter`
automatically and `run.dataset_origin` becomes `COMPUTED_FROM_SUPPLIED_DATA`. The adapter
already calls `analyse`, `analysis_payload`, `cells_payload`, `write_cell_artifacts`,
`write_change_artifacts` and `manifest.build` exactly as `rs/case2/cli.py` does, and
validates the result against `internal-models.v2.schema.json` before anything else sees it.
What RS must not change without a contract PR: the keys listed as required in that schema.
Adding keys is always safe.

**2. Trust.** Merge `carbon/`. `adapters/carbon.py` imports it at module load and the
reference stand-in becomes dead code; delete `adapters/reference_carbon.py` in that same
PR. The adapter calls `load_parameters`, `compute_interval`, `compute_baseline`,
`compute_units` and `compare_claim` and reads status strings through a small accessor that
looks in `carbon.reasons`, so no call site changes. `test_zero_reasons_are_exactly_the_engine_vocabulary`
stops skipping and pins the contract enumerations to `carbon.reasons`.

**3. Frontend.** Point `src/lens/adapter.ts` at the HTTP client. The differences from the
provisional shapes are listed in G0_CONTRACT.md; the screen components should not need to
change. Generate types from `contracts/v2/api-models.v2.schema.json`.

**4. Then re-run the acceptance scenarios.** The replay directory is deleted in the same
PR as the RS merge, and the suites that address it move to real AOIs.

## Numbers a reviewer will want

Measured on this machine with the replay adapter, `RU_TVER_01` 2019–2024:

| | |
|---|---|
| `GET /catalog` | 22 ms, 12.3 kB |
| `POST /analyses` | 8 ms |
| One worker pass, queue to passport | 14 ms |
| `GET /analyses/{id}` with the result | 9 ms, 19.5 kB |
| JSON report | 12.4 kB |
| HTML report | 10.1 kB |
| Cells artifact | 8.2 kB |
| Peak RSS of the test process | 81 MB |

These are the stand-in's numbers. A real raster analysis reads GeoTIFFs and will be
slower; the shape of the API does not change, and the job is asynchronous precisely so
that it can be.

## Design decisions worth knowing about

**Five status axes, never merged.** A job that finishes with no number is a successful job.
Partial coverage is a scientific outcome, not a worker failure. Poor optical evidence
lowers `evidence_status` and by itself never removes `q`.

**`q = null` and `q = 0` are different answers.** Two non-overlapping reason vocabularies,
enforced by a test. `scenario_values` is all-null whenever `q` is null, so no screen can
price an answer that does not exist.

**Two request hashes.** The request hash binds an Idempotency-Key to the exact body
including the claim, so replaying a key with a different claim is a 409. The input hash
identifies the scientific inputs and excludes the claim, because a stated volume must
never be able to move a measurement.

**One content hash, and what it excludes.** `passport.content_hash` covers the scientific
content. The analysis id, the run id, the run time, every URL and even the way the caller
addressed the contour are outside it, so the same request replayed on another machine next
week produces the same hash. Artifact ids are derived from bytes for the same reason.

**A published result is immutable in the schema.** A worker that wakes up after its job was
finished by someone else finds the trigger in its way and discards its run.

**Comparison needs a scope.** Two passports are compared only when the contour, the period,
the pool and the method version all match. A different period is a new observation, not a
downgrade, and a downgrade says in its own note that it is not an annulment of anything.

## Limitations

- No result on this branch is a measurement of a real area. The biomass values come from
  labelled stand-in vectors.
- The carbon engine is Backend's temporary reference implementation, not Trust's.
- No zone, no optical scene and no change evidence is produced yet; `evidence_status` is
  `INSUFFICIENT` for every replayed analysis, correctly.
- There is no chain anchor. `anchor.status` is `NOT_REQUESTED` on every proof.
- External source retrieval is not implemented here; RS owns it and the case requires it
  as a separate, cached, offline-replayable adapter.
- Browser and end-to-end checks against `/lens` have not been run from this branch: the
  Frontend workspace is on its own branch and is not merged.
- `openapi-spec-validator` validates the v2 document, but no consumer has generated types
  from it yet.
