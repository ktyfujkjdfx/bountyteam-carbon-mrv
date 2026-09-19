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
                report, api, auth, verification, demo
backend/tests/case2/  contract, API, job, decision, passport, adapter, auth, request,
                risk/value, demo, report and acceptance suites
backend/tools/live_composition.py  one real end-to-end run, refusing to use fixtures
.github/workflows/case2.yml        the pipeline, not each owner's corner of it
```

Nothing under `contracts/`, `fixtures/`, `backend/app/` or `backend/tests/` that belonged to
`contracts-v1.0.0` was modified. `create_app` still builds exactly the frozen v1
application and `/openapi.json` is still byte-for-byte `contracts/openapi.yaml`; the two
services are composed only in `backend/serve.py`.

## Running it

```bash
python -m pip install -r requirements-contracts.txt -r backend/requirements-backend.txt
export BACKEND_DEMO_SESSION="<at least 16 characters>"
python -m backend.migrate            # applies migrations 2-5 alongside the P0 schema
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

Demo sign-ins exist only where a deployment asked for them. Both the switch and a
password of its own are required, and there are no defaults:

```bash
export BACKEND_LENS_DEMO_ACCOUNTS=1
export BACKEND_LENS_DEMO_PASSWORD_OWNER="..."      # at least 12 characters
export BACKEND_LENS_DEMO_PASSWORD_VERIFIER="..."
export BACKEND_LENS_DEMO_PASSWORD_INVESTOR="..."
```

The Lens needs no chain, no deployment and no private key. `/lens` opens without any of
them.

## The endpoints

| Route | Notes |
|---|---|
| `POST /api/v2/auth/login` | Username and password for an opaque token; wrong user and wrong password are the same 401, repeats are 429 |
| `GET /api/v2/auth/me` | The signed-in person and the role the server holds |
| `POST /api/v2/auth/logout` | Revokes the session immediately |
| `GET /api/v2/catalog` | Areas, polygons, available years, the sample sub-request, the three scenario prices, the source register, the adapters and the engine mode |
| `POST /api/v2/areas/measure` | Geodesic area before anything is queued; over the limit is a reported measurement, not an exception |
| `POST /api/v2/requests` · `GET` | Verification requests: create a draft, list the ones this role may see |
| `GET/PATCH /api/v2/requests/{id}` | Read one; an owner may change the stated volume while it is a draft |
| `POST /api/v2/requests/{id}/submit` | Hand a draft over for verification |
| `POST /api/v2/requests/{id}/analysis` | Queue the calculation; `Idempotency-Key` required |
| `POST /api/v2/requests/{id}/finalize` | A verifier pins a passport version. No number moves |
| `GET /api/v2/requests/{id}/demo` + `/issue`, `/transfer`, `/retire` | The demonstration lifecycle. `q = 0` and `q = null` refuse |
| `POST /api/v2/analyses` | `Idempotency-Key` required; 202 with `analysis_id` and `status_url` |
| `GET /api/v2/analyses/{id}` | `job_state` and, once finished, `result`; `report_url` and `proof_url` appear only when there is something to link to |
| `GET /api/v2/analyses/{id}/artifacts/{artifact_id}` | Manifest-listed files only, re-hashed on the way out |
| `GET /api/v2/analyses/{id}/report?format=json\|html` | The passport; the HTML is self-contained |
| `GET /api/v2/analyses/{id}/value?price_rub=` | q times each price, with an optional price of the caller's own labelled `USER_SCENARIO` |
| `GET /api/v2/analyses/{id}/proof` | Hashes, versions and the anchor status |

`Authorization: Bearer <token>` on every route except `/auth/login`. There is no
`X-Demo-Actor` and no `X-Demo-Session` on `/api/v2`: a role a client can set is not an
authorization, so the caller and the role come from the session row.
`/api/v2/openapi.json` serves `contracts/v2/openapi.v2.yaml` unchanged, and a test
compares the served document with the file.

Failures: 401 unauthenticated, 404 unknown analysis or artifact, 409 idempotency conflict,
422 invalid geometry, period or claim, 503 source unavailable or artifact integrity
failure. No error carries a stack trace, a secret or a local path.

## Two engine modes, and no path between them

A deployment is in one of them by configuration, never by accident.

`BACKEND_LENS_ENGINE_MODE=REAL` is the default. `rs.case2` and `carbon` answer, or nothing
does. There is no fallback: if either package is missing, `create_lens_context` raises,
and the process either refuses to start (`BACKEND_LENS_REQUIRE_REAL=1`) or serves
`/api/v1` with the Lens unmounted. An engine that disappears mid-flight fails the job with
`DEPENDENCY_UNAVAILABLE` and no result. The one thing that never happens is a number
nobody measured.

`BACKEND_LENS_ENGINE_MODE=FIXTURE` has to be asked for by name. It replays labelled
raster vectors, stamps every result `run.dataset_origin = "STUB_FIXTURE"` with a `fixture`
label the UI must display, and adds a limitation saying in plain words that the biomass
values were not measured. `BACKEND_MODE=LOCAL_DEMO` refuses it outright, because a
replayed vector and a measurement are indistinguishable once they are on a screen. Note
that fixture mode still needs the real carbon engine: the vectors replay a raster payload,
never a recorded Q.

`backend/app/` contains no second implementation of the method, and a test walks every
module under `backend/app/v2/` to prove it: no `0.85`, no `44/12`, no `0.47`, no
`math.floor`, and no import of a stand-in. The test double that lets this suite run before
`carbon/` is merged lives at `backend/tests/case2/reference_engine.py`, inside the test
tree, and is injected explicitly by `conftest.engine_override`. It is deleted when
`carbon/` lands.

| Piece | Today | Why |
|---|---|---|
| Areas, polygons, geodesic area, coverage arithmetic | real | read from `data/`, measured with `pyproj.Geod` |
| Baseline, parameters, prices | real | read from `data/methodology/*.csv` |
| Interval, baseline result, units, claim | real formulas, **test double** | `carbon/` is not on this branch; the suite injects `tests/case2/reference_engine.py` and production refuses to run without the real engine |
| Biomass per cell, uncertainty per cell, zones, optical evidence | **replayed vectors** | `rs/case2/` is not on this branch, so `fixtures/v2/replay/` answers in FIXTURE mode only |
| Jobs, persistence, artifacts, passports, reports, proof | real | this module |
| Chain anchor | not implemented | `anchor.status` is `NOT_REQUESTED` and says so |

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
load; once the import succeeds, `REAL` mode stops raising and `run.dataset_origin` becomes
`COMPUTED_FROM_SUPPLIED_DATA`, with no call site changing. The adapter
already calls `analyse`, `analysis_payload`, `cells_payload`, `write_cell_artifacts`,
`write_change_artifacts` and `manifest.build` exactly as `rs/case2/cli.py` does, and
validates the result against `internal-models.v2.schema.json` before anything else sees it.
What RS must not change without a contract PR: the keys listed as required in that schema.
Adding keys is always safe.

**2. Trust.** Merge `carbon/`. `adapters/carbon.py` imports it at module load and it
becomes the only engine in play; `conftest.engine_override` stops firing, so the suite
moves onto the production path by itself. Delete `backend/tests/case2/reference_engine.py`
in that same PR. The adapter calls `load_parameters`, `compute_interval`, `compute_baseline`,
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

## Authorization is a working feature, not a theme switch

Three roles — `PROJECT_OWNER`, `VERIFIER`, `INVESTOR` — held on the server and read from
the session row on every request. Passwords are scrypt with a per-password salt and the
cost recorded next to each digest; only the hash of a session token is stored, so a copy
of the database hands nobody a working session. Sessions survive a restart because they
live in the database. There is no refresh token and no silent restoration: keep the token
in memory, and a reload signs the person in again rather than relying on a secret that
survives the page.

Every permission is checked by the server and the suite asserts each cell of the matrix
over HTTP. An analysis the caller may not read answers **404, not 403**, so probing
identifiers cannot reveal which ones exist.

The audit trail records sign-ins and failures, requests created and submitted, analyses
started, passports finalized, reports and artifacts downloaded, and every demonstration
step. It lives beside the passports and never inside them: who read a report cannot
change what the report says.

## Two engine modes, and nothing between them

`BACKEND_LENS_ENGINE_MODE=REAL` is the default. `rs.case2` and `carbon` answer, or
nothing does. A missing package raises at build time, so the process either refuses to
start under `BACKEND_LENS_REQUIRE_REAL=1` or serves `/api/v1` with the Lens unmounted. An
engine that vanishes mid-flight fails the job with `DEPENDENCY_UNAVAILABLE`.

`FIXTURE` has to be asked for by name, is refused outright under `BACKEND_MODE=LOCAL_DEMO`,
and still needs the real carbon engine: the vectors replay a raster payload, never a
recorded Q. The catalog publishes which mode answered.

`backend/app/v2/` contains no second implementation of the method. A test walks every
module there with docstrings stripped and fails on `0.85`, `44/12`, `0.47` or
`math.floor`. The test double that lets the suite run before `carbon/` is merged lives at
`backend/tests/case2/reference_engine.py`, inside the test tree, and is deleted when that
package lands.

## How the pipeline is proved

The unit suite is pinned to fixture mode and says why: it asserts outcomes only a
controlled vector can guarantee — a q above zero, a q of exactly zero, a q that is null —
and running it against whatever the rasters happen to say would make it a test of the
data instead.

The real pipeline is proved once, separately, by `backend/tools/live_composition.py`. It
refuses to start unless both owning packages import, substitutes nothing when they are
missing, and on `main` a missing package fails the job rather than skipping it. It walks
sign-in, a request, the calculation over the supplied rasters, the artifacts, passport
determinism, finalization, the role checks, the report and the demonstration refusal.

Verified in an isolated tree holding all three components:

| Suite | Without the engines | With them |
|---|---|---|
| `backend/tests/case2` | 321 passed, 3 skipped | 318 passed, 6 skipped |
| `rs/tests/case2` | — | 133 passed, 2 skipped |
| `carbon/tests` | — | 306 passed |
| `live_composition.py` | `NOT RUN`, nothing substituted | `LIVE COMPOSITION OK` |

The live run over `RU_TVER_01` 2019–2024 produced `q = 0` with
`NON_POSITIVE_RELATIVE_RESULT`, `COMPUTED_FROM_SUPPLIED_DATA`, 20 change zones, 7
artifacts all served, `CCI_V7` credited, the two engines agreeing on Eproj, a stable
content hash across two runs, and a demonstration issue correctly refused.
