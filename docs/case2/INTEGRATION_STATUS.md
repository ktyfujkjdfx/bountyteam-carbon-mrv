# Carbon Lens v2 integration status

Branch: `integration/carbon-lens-v2`
Draft PR: [#16](https://github.com/ktyfujkjdfx/bountyteam-carbon-mrv/pull/16)
Integration checkpoint: `ec7231aec85fd6cd9e94966e2612eb4f53de643d`
Checkpoint tag: `carbon-lens-v2-integration-start`

This document follows the integration branch. A roadmap item is not complete
until its local checks and the applicable GitHub jobs pass on the same pushed
HEAD.

Change set continuing the server-backed Lens workflow, on top of
`5a5b7ef861ab490934aaf8f89a0a0659e091fdd1`:

| Commit | What it closes |
|---|---|
| `fix(lens): let the service own the request state` | five server states no longer collapse into three; no server state in `sessionStorage` |
| `fix(lens): check the passport the way the service hashes it` | the integrity check now reproduces the service hash instead of always refusing |
| `fix(lens): end the session where the service says it is over` | `401` and `403` differ in behaviour, not only in wording |
| `test(e2e): walk the three roles through a live service` | the live browser scenario, with per-role credentials from the environment |
| `refactor(lens): carry the fields the contract declares` | `risks` and `projection` declared and carried; docs brought up to the branch |

## Initial CI investigation

The first PR #16 run contained ten failed checks. Job step metadata and failed
logs show one shared root cause rather than ten independent component failures:
the RS test compared a stale vendored copy of
`internal-models.v2.schema.json` with the final root contract.

| Failed check | Platform | First failed step | Classification | Owner |
|---|---|---|---|---|
| Carbon Lens / contract schemas and fixtures | Ubuntu, Python 3.12 | frozen v1/shared pytest | schema-copy assertion | Integration / RS consumer |
| Carbon Lens / rs.case2 and carbon | Ubuntu, Python 3.12 | RS case 2 tests | root cause | Integration / RS consumer |
| Carbon Lens / backend v2 | Ubuntu, Python 3.12 | shared contract checks | cascade after Backend-specific checks passed | Integration / RS consumer |
| Carbon Lens / backend v2 | macOS, Python 3.12 | shared contract checks | cascade after Backend-specific checks passed | Integration / RS consumer |
| Carbon Lens / backend v2 | Windows, Python 3.12 | shared contract checks | cascade after Backend-specific checks passed | Integration / RS consumer |
| Cross-platform readiness | Ubuntu, Python 3.12 | shared contract tests | cascade | Integration / RS consumer |
| Cross-platform readiness | Ubuntu, Python 3.13 | shared contract tests | cascade | Integration / RS consumer |
| Cross-platform readiness | macOS, Python 3.12 | shared contract tests | cascade | Integration / RS consumer |
| Cross-platform readiness | Windows, Python 3.12 | shared contract tests | cascade | Integration / RS consumer |
| Shared contracts / validate | Ubuntu, Python 3.12 | shared contract tests | cascade | Integration / RS consumer |

The passing jobs were Frontend on Windows and Ubuntu, Blockchain, and real
RS + Carbon live composition. This classification records the initial run; it
does not claim later gates are green.

## Completed integration fixes

### One authoritative v2 schema

- `contracts/v2/` is the only schema authority in the integrated repository.
- RS resolves `contracts/v2/internal-models.v2.schema.json` from the test file,
  independent of the shell working directory.
- Missing shared contracts fail with a clear error.
- The stale RS copies of the API and internal schemas were removed.
- Real RS payload, cells and manifest are validated against the final root
  internal schema, including nullable invalid-cell biomass values, raw coverage,
  signed area difference, structured warnings and traceability fields.

Verification after that change: `rs/tests/case2` 260 passed / 2 skipped, `rs/tests` 331 / 2,
root 871 / 2. The two RS skips are the opt-in network catalogue checks; they are not counted as
passed. Current numbers for the whole branch are in the last section.

### The server owns the request lifecycle

The Frontend held request state in `sessionStorage` and collapsed the service's five states into
three, so a request the service was calculating looked exactly like one waiting for a verifier: the
queue offered a second run and the service answered 409. State is now a projection of
`/requests/...`, each state maps one to one, and a state the client does not recognise is shown as
unknown with its actions closed rather than guessed into a known one. `sessionStorage` keeps request
state in the offline mode only.

`401` and `403` were both an error string. They now differ in behaviour: `403` refuses the action
and the screen keeps working; `401` ends the session and returns to sign-in, because nothing else
will succeed.

### The passport integrity check was decoration

Found on the live stand and fixed. The service computes
`sha256(rfc8785.dumps(content_view))`. The Frontend hashed `JSON.stringify(view, null, 2)` of a view
that was missing `risks` and `projection`, and built the report hash with the content as a string
where the service uses the object. Both checks therefore refused every genuine passport.

It went unnoticed because the offline set computed its own hashes with the same helpers — both sides
wrong in the same way — and because the browser assertion was `toContainText('совпадает')`, which is
also satisfied by `не совпадает` and so could never fail.

`frontend/tests/passportIntegrity.test.ts` closes it against a golden captured from a live run: the
client now reproduces both the `content_hash` and the `report_hash` that service published.

### The live three-role scenario runs

`frontend/e2e/lens-backend.spec.ts` was rewritten. The committed version could not have passed: it
signed all three roles in with one `E2E_LENS_SESSION` used as a password, from before the service had
password login, and waited on four test ids that no longer exist. Credentials now come from three
per-role environment variables and nothing else.

### What the live stand answered

One request, `RU_TVER_01`, 2019–2024, against `backend.serve` from this branch with
`BACKEND_LENS_ENGINE_MODE=REAL` and `BACKEND_LENS_REQUIRE_REAL=1`:

```text
POST /areas/measure        1750.4731237442018 ha   (geodesic, the authoritative figure)
POST /requests             201 DRAFT -> /submit -> SUBMITTED
owner POST .../analysis    403   (running the analysis belongs to the verifier)
logout, then /auth/me      401   (the session is revoked on the service, not only in the tab)
verifier POST .../analysis 202 ANALYSING -> SUCCEEDED
units.q                    0, status AVAILABLE, reason NON_POSITIVE_RELATIVE_RESULT
eproj / ebase / r tCO2e    -6484.726681340418 / -11031.621664285249 / -4546.894982944831
claim                      NOT_SUPPORTED_BY_CASE, supported_share 0.0, gap 1000.0 of 1000 claimed
coverage_fraction_raw      baseline 1.0000001134561782 beside the clamped 1.0
zones / artifacts          20 zones; change_zones and observation_gap_zones served separately
risks                      FIRE, FOREST_LOSS, DATA_QUALITY — none of them enters q
projection.horizon_year    2029, q_projection null
run.dataset_origin         COMPUTED_FROM_SUPPLIED_DATA
finalize                   FINALIZED, passport pinned; no number moved
investor POST .../analysis 403; POST /areas/measure 403; no token at all 401
```

`eproj_tco2e` is the same figure the raster core published for this contour, carried through the
carbon engine and the service without being restated. The real result is a Q of zero, and it is
preserved as a result rather than presented as a failure to compute.

## Open integration work

- Rerun every GitHub gate on the pushed HEAD and record the result. The local suites are green; CI
  on this HEAD has not been observed from here.
- The screens derive their risk cards and projection series from the official `data/` archive
  instead of the service's `risks[]` and `projection` blocks. Both sources are official, so no
  number is wrong, but two answers to one question is a divergence. See L10 in
  `frontend/docs/LENS_INTEGRATION.md`.
- `e2e/backend-integration.spec.ts` (5 tests) stays skipped: it belongs to the frozen `/api/v1`
  dashboard and needs its own seeded demo data, not the Lens service.
- Blockchain functionality is out of scope until a separate Team Lead GO.

## Verification

Run locally on Windows, Python 3.12.5 in `.venv`, Node 24.18.0, Microsoft Edge:

```text
python -m pytest -q                       871 passed,   2 skipped
python -m pytest rs/tests -q              331 passed,   2 skipped
python -m pytest rs/tests/case2 -q        260 passed,   2 skipped
python -m pytest carbon -q                472 passed
python -m pytest backend -q -rs           467 passed,  11 skipped
npm run check:abi                         ok, 9 functions, 7 events, specification only
git diff --check                          clean
frontend: npm run verify                  check:api ok (both contracts), lint, typecheck,
                                          204 tests, build, check:dist ok
frontend: npx playwright test              21 passed,   5 skipped, exit code 0
backend.tools.live_composition            LIVE COMPOSITION OK (LIVE_REQUIRED=1)
```

`python -m pytest -q` from the root does not collect `backend/` by design: the shared root command
validates the frozen contract baseline and must not require `backend/requirements-backend.txt`.
Backend tests run when `backend/` is named explicitly, which is why both commands are listed.

Skips, none of them counted as passed:

- 2 in RS — the opt-in network catalogue checks.
- 11 in Backend — merged-engine guards, a replay vector with no change zones, two Anvil end-to-end
  checks needing a real local deployment, and one symlink check Windows cannot run.
- 5 in Playwright — `e2e/backend-integration.spec.ts`, the frozen `/api/v1` dashboard, gated on its
  own `E2E_BACKEND_URL` and `E2E_DEMO_SESSION`.

Playwright finished on its own with exit code 0 and left no browser process behind. CI on this HEAD
has not been observed from this machine and is not claimed green here.
