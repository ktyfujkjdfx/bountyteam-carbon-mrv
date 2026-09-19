# Carbon Lens v2 integration status

Branch: `integration/carbon-lens-v2`
Draft PR: [#16](https://github.com/ktyfujkjdfx/bountyteam-carbon-mrv/pull/16)
Integration checkpoint: `ec7231aec85fd6cd9e94966e2612eb4f53de643d`
Checkpoint tag: `carbon-lens-v2-integration-start`

This document follows the integration branch. A roadmap item is not complete
until its local checks and the applicable GitHub jobs pass on the same pushed
HEAD.

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

Verification after this change:

```text
python -m pytest rs/tests/case2 -q  -> 260 passed, 2 skipped
python -m pytest rs/tests -q        -> 331 passed, 2 skipped
python -m pytest -q                 -> 871 passed, 2 skipped
```

The two RS skips are the opt-in network catalogue checks. They are not counted
as passed.

## Open integration work

- Align the Frontend login request with the OpenAPI `username` contract.
- Finish server-authenticated role flows and live browser checks.
- Connect authoritative polygon measurement and generated v2 types.
- Verify zones, structured warnings, four coverage axes and reviewed RS goldens.
- Remove the obsolete test reference engine when no test imports it.
- Prove REAL mode fails closed.
- Make Playwright terminate without manual interruption.
- Complete the real three-role browser scenario and rerun every CI gate.
