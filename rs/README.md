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

## Reproduce it

Cached AOI-windowed source bands are committed under `rs/sources/` (~13 MB;
never a full scene/SAFE archive) together with the finished bundles under
`rs/bundles/{no_change,fire}/`, so the exact same result reproduces with **no
internet connection**:

```bash
$env:PYTHONUTF8='1'  # Windows PowerShell
.\.venv\Scripts\python.exe -m rs.verify --request rs/configs/request_no_change.json --output rs/bundles/no_change
.\.venv\Scripts\python.exe -m rs.verify --request rs/configs/request_fire.json --output rs/bundles/fire
```

To re-acquire from scratch (network + AWS Open Data required):

```bash
.\.venv\Scripts\python.exe -m rs.build_bundles all
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
reproducibility, and full schema + semantic validation
(`tools/contract_helpers.validate_evidence`) of both real committed bundles.

## Known limitations

- FIRMS attribution is honestly `NOT_CHECKED`: the NASA FIRMS area API needs a
  free self-service `MAP_KEY` (`FIRMS_MAP_KEY` env var), not configured here.
  Backend policy already routes unattributed disturbance to
  `REVIEW_REQUIRED`, not an automatic freeze, so this does not block P0.
- `quality.temporal_comparability` uses a documented `DEMO_LOGIC` heuristic
  (day-of-year gap + AOI cloud ratio), not a phenology model.
- The AOI polygon is a hand-picked box, not an official fire-perimeter vector
  (see above); the reserve AOI from the RS plan (section 6B) was not selected
  in this pass — primary real data was already sufficient for both branches.
- Reserve/fallback provider (`sentinel-2-c1-l2a`, or a different AOI) and the
  `insufficient` scenario against real cloudy data are not built in this pass;
  `rs/tests/test_rs_pipeline.py::test_insufficient_data_when_coverage_below_gate`
  covers the `INSUFFICIENT_DATA` branch on synthetic local rasters instead.

## Next handoff

Backend: import `rs/bundles/no_change` and `rs/bundles/fire` via
`python -m backend.tools.import_bundle`, confirm `NO_CHANGE`/`DISTURBANCE_DETECTED`
policy evaluation, and report back schema/semantic acceptance or a concrete
diff. Frontend: aligned `before.png`/`after.png`/`dnbr_preview.png` in each
bundle are ready for the dashboard once Backend serves them via
`/api/v1/artifacts/{artifact_id}`.
