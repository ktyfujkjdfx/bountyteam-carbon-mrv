# Carbon Lens raster core

Turns a WGS84 contour and a pair of years into carbon stock, its change, where
the change is and what supports it, the coverage the result rests on, and the
per-cell layer the carbon engine needs.

Inputs come only from `data/`, the set supplied by the organizers. Nothing here
computes a baseline, an uncertainty interval, potential units or an investment
statement; those belong to other owners and are deliberately absent, so that
every number this package emits can be traced to a raster.

## Running it

From the repository root:

```bash
python -m rs.case2 --aoi RU_TVER_01      --start 2019 --end 2024 --out runs/tver
python -m rs.case2 --geometry plot.geojson --start 2020 --end 2024 --out runs/plot
python -m rs.case2.bench      --out runs/benchmark.json
python -m rs.case2.research   --out runs/research
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
score would hide that. The fourth coverage the contract names - baseline - is
computed by the consumer that owns the baseline, not here.

**Every fraction is published twice.** `fraction` is clamped to `[0, 1]` and is
what a display may use; `fraction_raw` is the measurement. They differ on a
fully covered request: geodesic area is not additive over a partition, so the
summed cell weights exceed the polygon area by about 2e-4 ha and the raw
fraction reads 1.000000113. `missing_ha` is the clamped shortfall a consumer
acts on; `area_difference_ha` is the signed `calculated_ha - requested_ha` that
explains it. Four numbers, because collapsing them to one loses either the
honesty or the usability.

**A missing value is null, never NaN and never zero.** A cell the biomass map
does not reach keeps its geometry and its weight, carries `valid: false` and
null AGB. NaN is not JSON, and zero is a published biomass value in this
product - writing either would be a measurement the map never made.

## Any admissible contour

A Polygon or MultiPolygon in WGS84, up to 2000 ha, is a request. A supplied
AOI, the `CHECK_TRANSFER_01` sub-plot and a contour drawn by hand take the same
path; no identifier is special, and nothing on the analysis path knows the name
of any plot. A request touching two source areas is cut into one disjoint piece
per area, published as `request.parts`, and the pairwise overlap is measured
rather than assumed - an area counted twice is the one arithmetic error here
that nothing downstream could see.

Change zones, though, are produced for the first source area only, and the
result says so in `change_evidence.scope` rather than leaving it to be
inferred. Each area has its own Sentinel grid and its own scene pair, and a
zone spanning two grids needs a partition rule that does not exist. The stock
result still covers every part.

**A refusal is a document.** Nothing is repaired: a self-intersecting contour
is a different polygon once fixed, and analysing the fixed one under the hash
of the one that was asked for would be a lie about provenance. Every refusal
carries a stable code, the numbers the decision was made from, and one of two
outcomes. `INVALID_REQUEST` means the request cannot be accepted - it is too
large, self-intersecting, or left in a projected CRS. `INSUFFICIENT_DATA` means
the request is well formed and the products do not reach it; that is a
statement about coverage and never about the forest, so it must not be read as
an absence of change. The CLI prints the document on stdout beside the human
line on stderr.

## Change zones

Zones are drawn on the paired-valid part of the 20 m Sentinel grid, from three
independent products: the burn and greenness index differences, the Global
Forest Change loss year, and - where it was supplied - the MODIS burn date.
Thresholds are fixed constants (dNBR 0.27, the Key & Benson class boundary;
dNDVI 0.20; recovery at -0.10), a one hectare minimum mapping unit is the only
filter, and a sensitivity table shows what other choices would have selected.
None of it is tuned per request.

**Fact and cause are separate properties.** `TREE_COVER_LOSS` means the
loss-year product flags most of the zone. `FIRE_SUPPORTED` means a trusted
MODIS burn date covers most of it, where QA bits 0 and 1 are set. With no such
evidence the cause is `UNKNOWN`, and where the burn product was not supplied at
all the reason says so - an absent product is not an absence of fire.
`RECOVERY_INDICATION` is a regrowth signal, not evidence of recovered carbon.

**Contributions reconcile.** Each zone's share of the stock change comes from
its geodesic overlap with the CCI cells, and zone shares plus the remainder
outside every zone add back to the same total, checked against a stated
tolerance. They are never added to a separately computed fire emission, which
would count one loss twice.

**Detection resolution is not carbon resolution.** Zones are 20 m outlines;
their carbon comes from cells about 100 m across, assuming the change is spread
evenly inside each cell. That assumption ships with every result, and both
resolutions travel with every zone so neither can be read as the other.

**A zone is something you can open.** `zone_id` is stable for a request and
unique within it, and the map layer and the result document are filled from one
function, so a zone opened from the map cannot say something different from the
zone read from the result. Each one carries its fact, cause and reason, the
magnitude of its spectral change with the basis of that number, the window the
pair could see, its detected area, its overlap with the CCI cells and its share
of the stock change. A `FIRE_SUPPORTED` zone also names the MODIS granule that
supports it, with that product's own date range, uncertainty and 463 m
resolution. A zone whose cause was never established names nothing: no event,
and a null date range. The nearest event in the period would be an invented
attribution, which is the one thing a traceable result may not contain.

**Outlines are valid polygons, and the repair is checked.** Eight-connected
labelling admits regions meeting at a pixel corner, whose outline is a ring
touching itself - something GEOS computes with happily and a consumer is
entitled to reject. Such an outline is repaired into the MultiPolygon it always
was, and the area before and after must be identical to the last digit. The
pixel mask stays the authority for every number.

**What was not seen is its own layer.** `observation_gaps.geojson` is the
complement of the change map: the part of the request the two dates could not
be compared over, split by reason - cloud, shadow, snow, water, no data - at
the same one-hectare minimum mapping unit. A change map showing only what was
seen invites the reader to treat the rest as unchanged. The biomass result is
unaffected, because cloud in an optical scene says nothing about the biomass
map.

### Two warnings the data earned

Running this on the control plot produced a change zone across 99% of it, which
no forest growth explains. The cause turned out to be radiometric: the two
scenes came from either side of the processing baseline 04.00 offset change.
Measured on every eligible pair, mixing conventions gives a median dNBR near
-0.86 and flags the whole control forest as regrowth, while pairs on one
convention give about -0.25 over the same ground and years.

Two things follow, both implemented. Scene selection now prefers a pair sharing
the offset convention, ahead of the seasonal-gap rule. And the result carries
an explicit warning when zones cover most of the request, because a change that
uniform is more often a difference between two observations than a disturbance.

The residual matters too: even matched pairs give -0.25 on a control plot over
five years, so a multi-year dNBR is not a reliable absolute measure of recovery.
The disturbance signal is sturdier - every pair over the burned plot shows a
loss, between +0.09 and +0.26 - so detection survives the scene choice even
where the absolute level does not.

## Retrieval from the open source

`rs.case2.retrieve` fetches from Earth Search by geometry and date and reads a
real window of a real asset, not just the catalogue JSON. It exists to satisfy
the case requirement and to check our handling; it never substitutes for
`data/`, and no analysis reads it.

Retrieving the same item the supplied crop came from and applying the STAC
scale and offset reproduces the supplied values to 1.5e-8 - float32 rounding.
That is the version and compatibility check: same product, same version, our
own scaling, their numbers.

Three rules keep it honest. A cache miss with the network disabled is an error,
never a local read presented as an acquisition. Hrefs are recorded without
their query string and a URL carrying signing parameters is refused, so no
temporary token reaches a manifest. And item selection is explicit, because
Earth Search serves the same acquisition twice - at baseline 03.01 with offset
0 and at 05.00 with offset -0.1 - and taking the first result would silently
produce data that does not match the reference.

**One adapter per product.** Four products go into a result and they are not
interchangeable, so each has its own adapter carrying its provider, version,
licence, attribution and the way it is reached. Only Sentinel-2 L2A is
retrievable by this package; ESA CCI Biomass, Global Forest Change and MODIS
MCD64A1 arrive with the case, and that is a recorded property of the adapter
rather than something discovered when a fetch fails.

**A retrieval asks only what the user asked.** A `Scope` bounds every search by
the request's own bounding box and period, padded by one Sentinel pixel so an
edge window is not rejected for rounding. A search that reaches wider is
refused.

**Compatibility is checked, not assumed.** Having the right item id is not
having the right version: an item on the other side of the 04.00 offset change
is a different surface over the same ground, and it is refused rather than
rescaled into the reference.

**The manifest is what makes a run checkable.** `rs.case2.sources` records, for
every input, the identifier or URL, the product and version, the access date,
the licence, the checksum, the cache key, and whether it was served over the
network, replayed from cache, or read from `data/`. Where a cache entry predates
the recorded access date, the manifest says the date is unknown rather than
inventing a plausible one.

`python -m rs.case2.retrieval_demo --out runs/retrieval` runs the five claims
instead of describing them, and prints which were demonstrated. The online
claim is reported as `NOT_ATTEMPTED` unless `--allow-network` is passed: "we did
not try" and "it worked" are different statements.

## Risk flags

Three blocks for an investor panel, and they are an extra page rather than a
step in the method: `fire_risk_evidence`, `forest_loss_evidence` and
`data_quality_risk`. Each carries a level, the measurement it was banded from,
the product it came from, the period, its own limitations, and `affects_q:
false` - repeated on every block, because a block gets quoted on its own.

They stay independent on purpose. A cloudy request is not a risky forest, and a
clear one is not a safe investment; merging observation quality into a hazard
flag is how a dashboard ends up telling an investor something the data never
said. The bands are stated and applied to measured shares, so a reader who
disagrees with a band can use the number instead.

Two levels are deliberately never LOW. Where the burn product was not supplied
the fire level is `UNKNOWN`, because LOW would claim an absence of fire from an
absence of a product. Where optical reading was off, data quality is `UNKNOWN`
rather than zero.

What these flags may not become is a probability of fire or a financial
discount. Turning "one confirmed episode in this period" into a chance of
burning needs a hazard model, a calibration set and a validation that none of
this package contains.

## Outputs

`analysis.json` carries the request, the stock change, a 2015-2024 timeline on
the requested period's support, the three coverages, per-scene optical quality,
the change evidence with its zones and reconciliation, the artifact records,
and two separate accounts of what constrains the result.

`limitations[]` is prose for a reader. `warnings[]` is the machine-readable
twin: every caution carries a stable `code`, a `severity` fixed by that code,
a `message` and a `details` object holding the measurement it was raised from.
Nothing is summarised away - a rejected scene, a mixed radiometric pair and an
absent burn product each keep their own code, because a consumer that collapses
them into one quality number cannot tell a cloudy request from a comparison
that must not be read as change at all. That last case is the only `CRITICAL`
severity the module defines.

`zones.geojson`, `observation_gaps.geojson`, `before.png`, `after.png`,
`dnbr_preview.png`, `paired_valid_mask.png` and `zone_mask.png` are the change
artifacts. Each is
listed in `analysis.json` with its SHA-256, its bounds in both the native grid
and WGS84, its resolution and its unit, under an id namespaced by request. The
records carry an API route, never a path from the machine that produced them.

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

Retrieval tests run offline against a committed cache fixture, so a cache miss,
a replay and a refused signed URL are all covered without a network. The tests
that reach the open catalogue are opt-in:

```bash
RS_CASE2_NETWORK=1 python -m pytest rs/tests/case2 -q
```

## Research

`python -m rs.case2.research --out runs/research` runs two experiments and
writes both a JSON pack and a readable report.

**How does the publisher transfer uncertainty between years?** The set ships a
CCI change product for 2019-2020 next to the annual maps, so the publisher's
own answer can be recovered rather than assumed. Two findings, on all four
areas: the published difference is exactly the difference of the annual maps,
pixel for pixel; and its difference SD matches an independent combination of
the two annual SDs to within 1%, against a fully correlated combination that
would be roughly four times tighter. On the temporal axis, the publisher treats
the two years as independent per pixel. The spatial axis between cells is not
settled by this and remains the open question - it is the one that moves a
carbon interval by more than an order of magnitude.

**How much of an apparent change is the instrument?** Described above; the
numbers are in the pack.

Neither is ground truth. The set contains no independent field measurement of
carbon, so comparing two satellite products is a consistency check and is
labelled as one.

## Limits of this stage

Change zones are produced for the first parent area of a request. A contour
spanning two supplied areas has two grids and two scene pairs, and merging
zones across them needs a partition rule that does not exist yet; the stock
result still covers every parent.

Multi-year dNBR carries a residual even on matched scenes, so recovery zones
are reported as indications and should not be read as recovered carbon.

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
