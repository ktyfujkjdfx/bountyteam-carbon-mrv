# Carbon Lens raster core (RS-1)

Turns a WGS84 contour and a pair of years into carbon stock, its change, the
coverage that result rests on, and the per-cell layer the carbon engine needs.

Inputs come only from `data/`, the set supplied by the organizers. Nothing here
computes a baseline, an uncertainty interval, potential units or an investment
statement; those belong to other owners and are deliberately absent, so that
every number this package emits can be traced to a raster.

## Running it

From the repository root:

```bash
python -m rs.case2 --aoi RU_TVER_01      --start 2019 --end 2024 --out runs/tver
python -m rs.case2 --geometry plot.geojson --start 2020 --end 2024 --out runs/plot
```

Naming a supplied AOI is a shortcut for pasting its polygon. A contour drawn by
hand takes the same code path, and no identifier is ever special-cased.

| Flag | Meaning |
|---|---|
| `--aoi` / `--geometry` | the request, one or the other |
| `--start`, `--end` | integer model years, `2019 <= start < end <= 2024` |
| `--out` | output directory; writing inside `data/` is refused |
| `--data-root` | point at another copy of the supplied set |
| `--no-optical` | skip Sentinel-2 reading; biomass results are unchanged |

Three files are written: `analysis.json`, `cells.geojson` and `manifest.json`.

## Method

For cell *i* of the ESA CCI Biomass grid, with `a_i` the geodesic area in
hectares of its intersection with the request:

```
C_t   = sum( AGB_i,t * CF * a_i )          CF = 0.47 t C / t dry matter
dC    = C_end - C_start
E     = -dC * 44/12                        t CO2e, positive means loss
e     = E / (A * years)                    t CO2e/ha/year
```

`A` is the area the stocks were actually summed over, and it is reported next to
the geodesic area of the requested polygon. The two differ in the seventh
significant digit because geodesic area is not additive over a partition; both
are published rather than silently reconciled.

### Decisions worth knowing

**Area is geodesic, never a pixel count.** The CCI grid is in degrees and one
cell measures about 0.6 ha at these latitudes, not 1 ha. Every area in the
result comes from the WGS84 ellipsoid.

**Zero AGB is a value.** The product carries no NoData tag and publishes zero for
burned ground. A cell is invalid here only when the map does not reach it. Any
reader that treats zero as missing deletes exactly the area the analysis exists
to measure.

**Both dates use the same ground.** Cells are selected once, by presence in both
requested years, and every year is then summed over that same set - including
ground that lost its cover in between.

**The raster frame is not coverage.** A request is clipped to the parent AOI
polygon, not to the wider raster frame. Outside that polygon there is no
baseline to compare against, so that area is reported as missing rather than
quietly included.

**Negative reflectance is preserved.** From processing baseline 04.00 Sentinel-2
L2A carries a -0.1 radiometric offset, which the supplied rasters already apply.
Dark targets are therefore legitimately below zero, and clamping them would bias
every index computed later. Usability is decided by scene classification and
finiteness, never by sign.

**Coverage is three numbers, not one.** Biomass, biomass SD and paired-valid
optical coverage answer different questions. A clouded scene says nothing about
whether the biomass map covers the plot, and merging them into a single quality
score would hide that.

## Outputs

`analysis.json` carries the request, the stock change, a 2015-2024 timeline on
the requested period's support, the three coverages, per-scene optical quality
and the limitations that apply to this particular result.

`cells.geojson` is the native CCI grid clipped to the request: `cell_id`,
parent, centroid, `weight_ha`, and AGB with its standard deviation for every
year read. A summary standard deviation cannot express spatial dependence, so
the consumer gets the cells themselves.

`manifest.json` records the method version, the resolved code commit, every
input file with its SHA-256, the parameters, and a content hash over the
canonical JSON of `analysis.json`. The run time is stored outside that hash, so
the same request reproduces the same hash on another machine on another day.
The code commit is `null` when the analysis code has uncommitted changes:
naming a commit whose tree cannot reproduce the bytes would be a false claim.

## Tests

```bash
python -m pytest rs/tests/case2 -q
```

The strongest tests check our arithmetic against numbers the organizers
published. `data/methodology/baseline.csv` states that its reference means were
computed from CCI with weights by pixel intersection area and CF = 0.47, so
recomputing them tests our area weighting: it reproduces all four AOIs for both
2015 and 2019 to nine decimals.

Scene classification codes 0, 1 and 11 do not occur in any supplied scene, so
their exclusion cannot be demonstrated on real data. Those cases are covered by
constructed arrays, marked `SYNTHETIC_TEST_ONLY` and carrying the
`synthetic_test_only` pytest marker. They exercise the rule and are never an
observation of no-data, defective pixels or snow on any of the four plots; a
further test asserts those classes really are absent, so the synthetic vectors
get replaced if the data ever changes.

## Limits of this stage

Scene *selection* is provisional. RS-1 reports the pair of scenes that sees the
most of the request on both dates, and says so in the payload; the
seasonal-comparability rule is RS-2 work, as is change-zone detection.

The serialisation boundary lives in `payload.py` alone. When G0 fixes the shared
v2 contract, that module changes and the raster core does not.

## Attribution

ESA CCI Biomass v7.0 - Santoro M.; Cartus O. (2026), NERC EDS CEDA, DOI
`10.5285/6429d1aafe1e43b9b414e4a5a7f8b903`; acknowledges the ESA Climate Change
Initiative and the Biomass CCI team. Contains modified Copernicus Sentinel data
2019-2024, accessed via Element 84 Earth Search. CF and the stock-difference
method follow IPCC 2006, Volume 4, Chapter 4 Table 4.3 and Chapter 2
equation 2.8. Baseline, deductions, reserve and prices are scenario rules of the
case, not external scientific values.
