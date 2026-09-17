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

| Scenario | Before | After | Real result | FIRMS |
|---|---|---|---|---|
| `no_change` (T0→T1) | `S2A_35TMF_20220726_0_L2A` (2022-07-26) | `S2B_35TMF_20230805_0_L2A` (2023-08-05) | `NO_CHANGE`, dNBR mean 0.026, 0 ha affected after MMU | `NOT_FOUND` |
| `fire` (T1→T2) | `S2B_35TMF_20230805_0_L2A` (2023-08-05) | `S2A_35TMF_20230830_0_L2A` (2023-08-30) | `DISTURBANCE_DETECTED`, 84.24 ha / 6.0% of baseline forest affected | `SUPPORTED`, 40 hotspots |

Both scenes come from Element84 Earth Search (`sentinel-2-l2a` collection, AWS
Open Data, no auth). Data source: `docs/roles/02_RS_PLAN.md`, primary provider.

The 40 FIRMS hotspots matched for the `fire` scenario start on **2023-08-21**,
the documented `EMSR686` ignition date, which is independent thermal
confirmation that the detected dNBR signature is a fire and not a harvest,
phenology shift or processing artefact. They are a thermal-anomaly signal only,
not a perimeter: `affected_area_ha` still comes from the dNBR components.

## FIRMS attribution (no API key required)

Attribution uses NASA FIRMS' **open per-country yearly archive**
(`https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/<year>/viirs-snpp_<year>_<country>.csv`),
which needs no account and no `MAP_KEY`. The exact upstream file is cached under
`rs/sources/<plot_id>/firms/` and its SHA-256 is recorded in
`firms.source_refs`, so attribution reproduces offline and is independently
checkable against the public file. Hotspots are filtered to the observation
window (UTC `acq_date`/`acq_time`), to `nominal`/`high` confidence, and to
within the frozen 500 m tolerance of the AOI.

`rs/firms.py` still supports the near-real-time FIRMS "area" API through the
optional `FIRMS_MAP_KEY` env var; the archive is preferred because it is keyless
and reproducible. With neither source present, `support` is honestly
`NOT_CHECKED` and no hotspot count is invented
(`test_firms_is_not_checked_without_an_archive_or_map_key`).

## Reserve AOI (data-access insurance, not a second demo)

Per manifest section 1 ("one backup site as insurance, not a second mandatory
demonstration"): **northern Evia island, Greece**, the August 2021 wildfire
(started 2021-08-03, ~50,000 ha, the largest in modern Greek recorded history)
that burned the pine forest around Pefki/Gouves. AOI: `rs/configs/aoi_evia_reserve.json`,
plot_id `GR-EVIA-PEFKI-RESERVE-001`, ~1539 ha, tile `34SFJ`.

| Scenario | Before | After | Real result |
|---|---|---|---|
| `no_change` (pre-fire baseline pair) | `S2B_34SFJ_20200724_0_L2A` (2020-07-24, baseline `02.14`) | `S2A_34SFJ_20210727_0_L2A` (2021-07-27, baseline `03.01`) | `DISTURBANCE_DETECTED`: a small real 1.68 ha / 0.26%-of-baseline-forest signal (42 px), well under the 5 ha backend policy threshold; FIRMS `NOT_FOUND` |

The window closes 2021-07-27, a week before the 2021-08-03 ignition, so FIRMS
correctly finds no hotspot: the small signal is real but unattributed, exactly
the case policy v1 routes to `REVIEW_REQUIRED` rather than a freeze.

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

### Determinism

Every byte a bundle contains is hashed, so the same inputs must produce the
same SHA-256 on Windows, macOS and Linux. `rs/determinism.py` pins the three
things that otherwise vary:

- **No text mode.** `Path.write_text` translates `\n` to `\r\n` on Windows and
  nowhere else, which silently changes every JSON hash. All bundle files are
  written as bytes.
- **Canonical serialization.** `verification.json`, `source-index.json`,
  `affected_area.geojson` and `firms.geojson` are written as JCS (RFC 8785)
  bytes through the shared `tools/contract_helpers.py`, so the file on disk
  *is* the byte string Backend hashes into `evidence_hash`.
- **Fixed coordinate precision.** Reprojected GeoJSON coordinates are rounded
  to 7 decimals (~1 cm, far finer than the 20 m grid) because PROJ builds can
  disagree in the last ULP.
- **Rank-selected percentiles.** The preview stretch uses
  `np.percentile(..., method="nearest")` and `np.rint`, not interpolation and
  truncation. Interpolated cutoffs differ in the last ULP between x86-64 and
  arm64, which moved boundary pixels and changed preview hashes on macOS only
  — caught by the CI matrix, not by local testing.
- **Pinned encoders.** PNGs are written with `compress_level=0`, `optimize=False`
  and no `pnginfo`, so no `tIME`/`tEXt` chunk and no build-specific deflate
  stream; the dNBR GeoTIFF states `zlevel`, `predictor`, `interleave` and
  `tiled` explicitly instead of inheriting GDAL build defaults.

`test_rebuilding_a_bundle_twice_gives_byte_identical_files` rebuilds a bundle
twice and compares every file hash, and
`test_real_bundle_rebuilds_byte_identically_on_this_platform` rebuilds each
committed real bundle from the committed sources and requires every byte to
match — which the CI matrix runs on `windows-latest`, `macos-latest` and
`ubuntu-latest`.

### Releasing bundles (two-step, so `code_commit` is a real claim)

`method.code_commit` must name a commit that actually contains the pipeline
that produced the bundle. One commit cannot do that, because the bundle has to
exist before it can be committed. So:

```bash
git add rs/*.py rs/configs rs/sources rs/tests rs/README.md && git commit   # step 1: code + inputs
.\.venv\Scripts\python.exe -m rs.release                                    # step 2: regenerate, stamping step 1's sha
git add rs/bundles && git commit                                            # step 3: artifacts only
```

`rs.release` refuses to run while any RS code or input path is dirty
(`rs/bundles/` excluded — it is the output), so the stamped sha always belongs
to a tree that reproduces the bytes. Outside that flow, `rs.verify` records
`code_commit` from HEAD only when the RS code is committed and records `null`
otherwise, rather than naming a commit that cannot reproduce the bundle; pass
`--code-commit <sha>` to set it explicitly.
`test_real_bundle_code_commit_is_a_commit_that_contains_the_pipeline` checks
each committed bundle's sha with `git ls-tree`.

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
reproducibility, tampered-artifact rejection, FIRMS window/confidence/500 m
filtering and its `SUPPORTED` / `NOT_FOUND` / `NOT_CHECKED` branches, the frozen
policy freeze preconditions on the fire bundle, and full schema + semantic
validation (`tools/contract_helpers.validate_evidence`) of all three real
committed bundles (primary no_change, primary fire, reserve).

## Known limitations

- FIRMS is checked against the keyless yearly archive, not the near-real-time
  API. For a demo over historical events that is strictly better (it is the
  quality-controlled record and it reproduces offline), but it means a *live*
  same-week observation would need the `FIRMS_MAP_KEY` NRT path instead.
  `NOT_FOUND` means "no qualifying hotspot in this window and AOI", which is
  not proof that no disturbance occurred - only that no thermal anomaly
  attributes it.
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

Backend: re-import `rs/bundles/no_change`, `rs/bundles/fire`, and
`rs/bundles/evia_reserve_no_change` via `python -m backend.tools.import_bundle`.
`feat/backend-api` already accepted all three at `feat/rs-pipeline@f094a6e`; the
FIRMS change above is the missing input it asked for, so the **fire** bundle now
carries `firms.support = SUPPORTED` with a `firms-points` artifact and should
move from `REVIEW_REQUIRED / DISTURBANCE_UNATTRIBUTED` to a real
`FREEZE_REQUESTED` under policy v1 (84.24 ha >= 5 ha, 6.0% >= 1%,
`require_firms_support` satisfied). The other two bundles are unchanged in
outcome and should stay `NO_RESTRICTION` and `REVIEW_REQUIRED` respectively.
Frontend: aligned
`before.png`/`after.png`/`dnbr_preview.png` in each bundle are ready for the
dashboard once Backend serves them via `/api/v1/artifacts/{artifact_id}`.
