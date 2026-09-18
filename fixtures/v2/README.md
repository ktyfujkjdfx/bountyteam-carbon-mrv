# Carbon Lens v2 fixtures

None of the files here is a scientific result for a real area. Every one of them
carries a label, and `backend/tests/case2/test_g0_contracts.py` fails if a label is
missing or unknown. The UI shows the label next to the numbers, so a reader can never
mistake a format example for a measurement.

| Label | Meaning |
|---|---|
| `DOC_EXAMPLE` | Numbers taken from the organizers' statement (`doc/`). Authoritative for arithmetic, not for any particular area. |
| `UNIT_TEST_VECTOR` | Values chosen to sit on a rule boundary. A logical test, never an alternative dataset. |
| `CONTRACT_FIXTURE` | Illustrates the shape and the nullability of the wire fields. The numbers are decorative. |

Real golden results for `RU_TVER_01`, `RU_VOLOGDA_02`, `RU_MORDOVIA_03`, `RU_MORDOVIA_04`
and `CHECK_TRANSFER_01` can only be produced by the raster core and the carbon engine over
`data/`. They belong in the RS and Trust suites, and this directory must not grow
invented substitutes for them.

## Files

| File | Model | Label |
|---|---|---|
| `doc_example_units.json` | arithmetic vector | `DOC_EXAMPLE` |
| `analysis_result_available.json` | `AnalysisResult` | `DOC_EXAMPLE` |
| `analysis_result_zero_units.json` | `AnalysisResult` | `UNIT_TEST_VECTOR` |
| `analysis_result_unavailable.json` | `AnalysisResult` | `CONTRACT_FIXTURE` |
| `raster_analysis.json` | `RasterAnalysis` | `CONTRACT_FIXTURE` |
| `cell_layer.geojson` | `CellLayer` | `CONTRACT_FIXTURE` |
| `carbon_assessment.json` | `CarbonAssessment` | `CONTRACT_FIXTURE` |
| `artifact_manifest.json` | `ArtifactManifest` | `CONTRACT_FIXTURE` |
| `http_examples.v2.json` | request/response envelopes | `CONTRACT_FIXTURE` |

## The three answers that must stay distinct

`analysis_result_available.json` is the official worked example: 100 ha over one year,
mean AGB 100 → 104 t/ha, and therefore `q = 395`. It is the reference the carbon adapter
is pinned to.

`analysis_result_zero_units.json` has valid inputs whose relative result is not positive,
so `q = 0` with `zero_reason = NON_POSITIVE_RELATIVE_RESULT`. Zero is an answer.

`analysis_result_unavailable.json` has a contour that reaches outside the available
biomass coverage, so `q = null` with `unavailable_reason = INCOMPLETE_COVERAGE`. Null is
the absence of an answer. A consumer that renders these two the same way is wrong.

## Frozen v1

`fixtures/` above this directory belongs to `contracts-v1.0.0` and is not touched by the
Lens work. Nothing here replaces or shadows it.
