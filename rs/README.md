# RS module

Owner: Remote Sensing developer. Implements the reproducible evidence pipeline
described in `docs/roles/02_RS_PLAN.md` and Issue #2. Never emits token/credit
states or `evidence_hash`; Backend owns those.

## What this delivers (P0)

A config-driven pipeline that turns cached, AOI-windowed Sentinel-2 L2A bands
into a schema-valid `VerificationEvidence` bundle:

```bash
python -m rs.verify --request <request.json> --output <bundle_dir>
```

`request.json` must validate against `contracts/rs-request.schema.json` and
reference local files under its own `data_root` (never fetched over the
network by `rs.verify` itself — acquisition and verification are separate
steps, so a bundle can be reproduced fully offline).

## Real event used for the primary AOI

**Evros wildfires, Greece, August 2023** — Dadia-Lefkimi-Soufli Forest National
Park (Copernicus EMS activation `EMSR686`, ignition 2023-08-21; widely reported
as having burned parts of the park, e.g.
[Dadia Forest — Wikipedia](https://en.wikipedia.org/wiki/Dadia_Forest)). The
exact AOI polygon (`rs/configs/aoi_dadia.json`, plot_id `GR-EVROS-DADIA-001`,
~1864 ha) is a hand-picked rectangle inside the park confirmed forested by ESA
WorldCover; it is **not** taken from an official EMSR686 damage-delineation
vector (not fetched in this environment). Treat the AOI boundary as
`ASSUMPTION`-class; treat the computed outcome as this pipeline's own real
measurement, confirmed empirically below.

| Scenario | Before | After | Real result |
|---|---|---|---|
| `no_change` (T0→T1) | `S2A_35TMF_20220726_0_L2A` (2022-07-26) | `S2B_35TMF_20230805_0_L2A` (2023-08-05) | `NO_CHANGE`, dNBR mean 0.026, 0 ha affected after MMU |
| `fire` (T1→T2) | `S2B_35TMF_20230805_0_L2A` (2023-08-05) | `S2A_35TMF_20230830_0_L2A` (2023-08-30) | `DISTURBANCE_DETECTED`, 84.24 ha / 6.0% of baseline forest affected |

Both scenes come from Element84 Earth Search (`sentinel-2-l2a` collection, AWS
Open Data, no auth). Data source: `docs/roles/02_RS_PLAN.md`, primary provider.

## Reserve AOI (data-access insurance, not a second demo)

Per manifest section 1 ("one backup site as insurance, not a second mandatory
demonstration"): **northern Evia island, Greece**, the August 2021 wildfire
(started 2021-08-03, ~50,000 ha, the largest in modern Greek recorded history)
that burned the pine forest around Pefki/Gouves. AOI: `rs/configs/aoi_evia_reserve.json`,
plot_id `GR-EVIA-PEFKI-RESERVE-001`, ~1539 ha, tile `34SFJ`.

| Scenario | Before | After | Real result |
|---|---|---|---|
| `no_change` (pre-fire baseline pair) | `S2B_34SFJ_20200724_0_L2A` (2020-07-24, baseline `02.14`) | `S2A_34SFJ_20210727_0_L2A` (2021-07-27, baseline `03.01`) | `DISTURBANCE_DETECTED`: a small real 1.68 ha / 0.26%-of-baseline-forest signal (42 px), well under the 5 ha backend policy threshold |

Reported honestly as `DISTURBANCE_DETECTED`, not forced to `NO_CHANGE`: 11
smaller candidate components were correctly dropped by the 25-pixel MMU filter,
and the surviving 1.68 ha is far below `freeze_min_area_ha=5` in
`config/policy.v1.json`, so Backend policy recomputation resolves it to
`REVIEW_REQUIRED`, never a freeze — see
`test_real_bundle_below_policy_area_threshold_is_not_over_claimed`. Both scenes
predate the 2022-01-25 BOA offset baseline change (`04.00`), so this pair is
also the real-data regression test for the **no-offset** harmonization branch
(`rs/harmonize.py::from_baseline`) — `dnbr_mean` over the whole 650 ha analysed
forest is 0.0004, i.e. no systematic bias from that code path.

## Reproduce it

Cached AOI-windowed source bands are committed under `rs/sources/` (~21 MB;
never a full scene/SAFE archive) together with the finished bundles under
`rs/bundles/`, so the exact same results reproduce with **no internet
connection**:

```bash
$env:PYTHONUTF8='1'  # Windows PowerShell
.\.venv\Scripts\python.exe -m rs.verify --request rs/configs/request_no_change.json --output rs/bundles/no_change
.\.venv\Scripts\python.exe -m rs.verify --request rs/configs/request_fire.json --output rs/bundles/fire
.\.venv\Scripts\python.exe -m rs.verify --request rs/configs/request_evia_reserve_no_change.json --output rs/bundles/evia_reserve_no_change
```

To re-acquire from scratch (network + AWS Open Data required):

```bash
.\.venv\Scripts\python.exe -m rs.build_bundles all
.\.venv\Scripts\python.exe -m rs.build_bundles all --config rs/configs/aoi_evia_reserve.json
```

Backend imports either bundle directory with:

```bash
python -m backend.tools.import_bundle --bundle rs/bundles/fire
```

## Tests

```bash
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest rs/tests -q
```

Covers: BOA offset selection by processing baseline and by the Earth Search
`earthsearch:boa_offset_applied` provider flag, SCL exclusion list and
dark/burnt-pixel preservation, north-up 20 m UTM grid construction, exact
pixel-area/MMU accounting, `NO_CHANGE` / `DISTURBANCE_DETECTED` /
`INSUFFICIENT_DATA` classification on synthetic local rasters, forbidden-field
absence, NaN/Infinity absence, OS-independent relative paths, run-to-run
reproducibility, tampered-artifact rejection, and full schema + semantic
validation (`tools/contract_helpers.validate_evidence`) of all three real
committed bundles (primary no_change, primary fire, reserve).

## Known limitations

- FIRMS attribution is honestly `NOT_CHECKED`: the NASA FIRMS area API needs a
  free self-service `MAP_KEY` (`FIRMS_MAP_KEY` env var), not configured here.
  Backend policy already routes unattributed disturbance to
  `REVIEW_REQUIRED`, not an automatic freeze, so this does not block P0.
- `quality.temporal_comparability` uses a documented `DEMO_LOGIC` heuristic
  (day-of-year gap + AOI cloud ratio), not a phenology model.
- Both AOI polygons are hand-picked boxes confirmed forested by ESA WorldCover,
  not official fire-perimeter delineation vectors (not fetched in this
  environment); treat their boundaries as `ASSUMPTION`-class, and the computed
  outcomes as this pipeline's own real measurement.
- Reserve/fallback provider (`sentinel-2-c1-l2a`) and a real-data
  `INSUFFICIENT_DATA` run (real cloudy scene) are not built in this pass;
  `rs/tests/test_rs_pipeline.py::test_insufficient_data_when_coverage_below_gate`
  covers the `INSUFFICIENT_DATA` branch on synthetic local rasters instead.
- Every real bundle here uses `COMPUTED` mode: each `python -m rs.verify` run
  recomputes indices/masks/components from the cached local source rasters
  rather than replaying a stored decision, and reproduces bit-identical
  scientific fields (`rs/tests/test_rs_pipeline.py::test_reproducible_rerun_produces_identical_canonical_bytes`).
  The schema has no `CACHED_REPLAY` field; RS has not needed that fallback.

## Next handoff

Backend: import `rs/bundles/no_change`, `rs/bundles/fire`, and
`rs/bundles/evia_reserve_no_change` via `python -m backend.tools.import_bundle`,
confirm `NO_CHANGE`/`DISTURBANCE_DETECTED` policy evaluation (the reserve
bundle should resolve to `REVIEW_REQUIRED`, not a freeze), and report back
schema/semantic acceptance or a concrete diff. Frontend: aligned
`before.png`/`after.png`/`dnbr_preview.png` in each bundle are ready for the
dashboard once Backend serves them via `/api/v1/artifacts/{artifact_id}`.
