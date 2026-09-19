# Backend G0 contract, copied for testing

These two files are **copies**, byte for byte, of Backend's v2 contract as it
stands in PR #15 at `e9817d0144569731e3a98c7af6c916cf55a510cf`:

| file | copied from |
|---|---|
| `internal-models.v2.schema.json` | `contracts/v2/internal-models.v2.schema.json` |
| `api-models.v2.schema.json` | `contracts/v2/api-models.v2.schema.json` |

They live here so the RS tests can check a **real** payload against the schema
its consumer will validate it with, on a branch where `contracts/` does not yet
carry the v2 files. Nothing here is an RS contract and nothing here may be
edited to make a test pass: Backend owns these documents, and a mismatch is a
finding to report, not a file to adjust.

`test_contract_payload.py` prefers the repository's own
`contracts/v2/internal-models.v2.schema.json` whenever it exists, so once PR #15
lands the tests validate against the live contract and these copies stop being
read. When that happens, delete the directory.

## Known divergences from the frozen method, as of this copy

Reported in the RS consumer review of PR #15 and expected to change in
Backend's next revision. The tests here assert what RS produces, not these gaps.

1. `CellFeature.properties.agb_t_ha` is `{"type": "number"}` and cannot express
   a cell the biomass map does not reach. RS emits `null` with `valid: false`,
   which is strict JSON; NaN is not. The per-cell schema needs a nullable value.
2. `coverage_fraction_raw`, `area_difference_ha` and a structured `warnings[]`
   are absent from the public API schema. RS publishes all three.
3. `ClaimStatus` has no `NOT_APPLICABLE` and there is no `NO_POSITIVE_CLAIM`
   reason, so METHOD FREEZE v1 item 12 cannot be expressed. This one is not an
   RS field and is listed only so the copy is not mistaken for agreement.
