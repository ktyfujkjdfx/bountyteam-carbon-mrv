"""The raster analysis itself: request in, typed result out.

No identifier is special. A supplied AOI and a contour drawn by hand take the
same path; the only thing an `aoi_id` buys the caller is not having to paste a
polygon. Nothing here computes a baseline, an uncertainty interval, potential
units or an investment conclusion - those belong to other owners and are
deliberately absent.
"""
from rs.case2 import biomass, optical
from rs.case2.catalog import Dataset, DatasetError, sha256_file
from rs.case2.geometry import geodesic_area_ha, validate, validate_years
from rs.case2.models import (
    ANALYSIS_YEAR_MAX,
    ANALYSIS_YEAR_MIN,
    CARBON_FRACTION,
    CO2_PER_C,
    Coverage,
    RasterAnalysis,
    SourceFile,
    StockChange,
)

METHOD_VERSION = "rs-case2-raster-core/1.0.0"
# A request is treated as fully covered when the gap is below this many
# hectares. Geodesic area is not additive over a partition, so the sum of cell
# weights and the polygon area differ in the seventh significant digit even
# when every cell is present; that is arithmetic, not missing data.
COVERAGE_TOLERANCE_HA = 1e-4


def analyse(geometry, year_start, year_end, *, dataset=None, include_optical=True):
    """Run the raster analysis for one request.

    `geometry` is GeoJSON in WGS84 lon/lat order. Returns a `RasterAnalysis`;
    serialisation happens elsewhere so this stays free of contract field names.
    """
    data = dataset if dataset is not None else Dataset()
    request = validate(geometry)
    year_start, year_end = validate_years(
        year_start, year_end, minimum=ANALYSIS_YEAR_MIN, maximum=ANALYSIS_YEAR_MAX)

    parents = data.parents_for(request)
    change_years = (year_start, year_end)
    timeline_years = _timeline_years(data, parents)
    read_years = sorted(set(timeline_years) | set(change_years))
    for year in change_years:
        if year not in read_years:
            raise DatasetError(
                f"biomass map for {year} is not available for {', '.join(parents)}")

    cells, grids = biomass.build_cells(
        data, request, parents, read_years, validity_years=change_years)
    if not any(cell.valid for cell in cells):
        raise DatasetError(
            "no biomass cell covers the request in both requested years")

    request_area_ha = geodesic_area_ha(request)
    weight_sum = sum(cell.weight_ha for cell in cells)
    biomass_ha = sum(cell.weight_ha for cell in cells if cell.valid)
    sd_ha = biomass.sd_available(cells, change_years)

    timeline = [biomass.stock(cells, year) for year in timeline_years]
    start = biomass.stock(cells, year_start)
    end = biomass.stock(cells, year_end)
    change = _change(start, end, biomass_ha)

    scenes, paired, optical_ha, scene_sources = _optical(
        data, request, parents, change_years, biomass_ha, include_optical)

    missing_ha = max(0.0, request_area_ha - biomass_ha)
    coverage = Coverage(
        requested_ha=request_area_ha,
        calculated_ha=biomass_ha,
        biomass_ha=biomass_ha,
        biomass_sd_ha=sd_ha,
        optical_paired_ha=optical_ha,
        biomass_fraction=biomass_ha / request_area_ha,
        biomass_sd_fraction=sd_ha / request_area_ha,
        optical_paired_fraction=optical_ha / request_area_ha,
        missing_ha=missing_ha,
        complete=missing_ha <= COVERAGE_TOLERANCE_HA,
    )

    sources = _sources(data, parents, read_years) + scene_sources
    return RasterAnalysis(
        request_area_ha=request_area_ha,
        cell_weight_sum_ha=weight_sum,
        parents=tuple(parents),
        years=tuple(change_years),
        change=change,
        timeline=tuple(timeline),
        coverage=coverage,
        cells=tuple(cells),
        scenes=tuple(scenes),
        paired_optical=paired,
        grids=dict(sorted(grids.items())),
        sources=tuple(sorted(sources, key=lambda item: item.relative_path)),
        parameters={
            "carbon_fraction": CARBON_FRACTION,
            "co2_per_c": CO2_PER_C,
            "pool": "living above-ground woody biomass",
            "method": "stock-difference",
            "area_method": "geodesic on WGS84, per-cell intersection",
            "biomass_product": "ESA CCI Biomass v7.0, AGB and AGB_SD",
            "usable_scl_classes": sorted(optical.USABLE_SCL_CLASSES),
            "negative_reflectance_policy": "preserved, never clamped",
            "method_version": METHOD_VERSION,
        },
        limitations=_limitations(coverage, paired, timeline_years, cells,
                                 change_years, include_optical),
    )


def _timeline_years(data, parents):
    """Years every parent can supply, so the series stays comparable."""
    per_parent = [set(biomass.available_years(data, aoi)) for aoi in parents]
    shared = set.intersection(*per_parent) if per_parent else set()
    return tuple(sorted(shared))


def _change(start, end, area_ha):
    delta_tc = end.total_tc - start.total_tc
    e_tco2e = -delta_tc * CO2_PER_C
    years = end.year - start.year
    return StockChange(
        year_start=start.year,
        year_end=end.year,
        years=years,
        stock_start_tc=start.total_tc,
        stock_end_tc=end.total_tc,
        delta_tc=delta_tc,
        e_tco2e=e_tco2e,
        e_per_ha_per_year=e_tco2e / (area_ha * years),
        normalisation_area_ha=area_ha,
    )


def _optical(data, request, parents, change_years, biomass_ha, include_optical):
    """Per-scene usability and the best paired-valid coverage of the two years."""
    if not include_optical:
        return (), None, 0.0, []
    scenes = []
    sources = []
    masks = {}
    pixels_in_request = 0
    for aoi_id in parents:
        part = request.intersection(data.geometries[aoi_id])
        if part.is_empty:
            continue
        for row in data.scenes_for(aoi_id, change_years):
            quality, usable, _grid = optical.scene_quality(data, row, part)
            scenes.append(quality)
            masks[quality.scene_key] = (quality.year, usable)
            pixels_in_request = max(pixels_in_request, quality.pixels_in_request)
            for key in ("reflectance_path", "scl_path"):
                sources.append(_source(data, row[key], f"sentinel2:{key}"))
    paired = optical.best_pair(
        masks, change_years[0], change_years[1], pixels_in_request)
    # Optical coverage is expressed on the same hectare scale as the other two
    # so a consumer can compare them, but it is measured on the Sentinel grid.
    optical_ha = (paired.paired_usable_fraction * biomass_ha) if paired else 0.0
    return tuple(scenes), paired, optical_ha, sources


def _sources(data, parents, years):
    files = []
    for aoi_id in parents:
        for year in years:
            files.append(_source(
                data, f"{aoi_id}/CCI_Biomass_{year}.tif", "cci_biomass"))
    for name in ("areas.geojson", "areas.csv", "scenes.csv", "scene_metadata.json"):
        files.append(_source(data, name, "table"))
    return files


def _source(data, relative, role):
    path = data.path(relative)
    return SourceFile(
        relative_path=data.relative(path),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        role=role,
    )


def _limitations(coverage, paired, timeline_years, cells, change_years, include_optical):
    notes = []
    if not coverage.complete:
        notes.append(
            f"partial coverage: {coverage.missing_ha:.4f} ha of the request has no "
            f"biomass map; potential units are not computed for a partial request")
    if not include_optical:
        notes.append(
            "optical reading was switched off for this run; optical coverage is "
            "absent rather than zero, and the biomass result is unaffected")
    elif paired is None:
        notes.append(
            "no Sentinel-2 pair spans the requested years; optical coverage is "
            "reported as zero, which says nothing about biomass coverage")
    elif paired.paired_usable_fraction < 0.5:
        notes.append(
            f"paired-valid optical coverage is only "
            f"{paired.paired_usable_fraction:.1%}; change interpretation from "
            f"imagery is limited on this request")
    zero_cells = sum(1 for cell in cells
                     if cell.valid and any(cell.agb[y] == 0 for y in change_years))
    if zero_cells:
        notes.append(
            f"{zero_cells} of {sum(1 for c in cells if c.valid)} cells carry a "
            f"published AGB of zero on at least one date; zero is a value in this "
            f"product and is summed as zero, not dropped")
    notes.append(
        "CCI years are annual model estimates, not observations on a date; the "
        "Sentinel acquisition dates are reported separately")
    notes.append(
        f"timeline covers {timeline_years[0]}-{timeline_years[-1]} on the support "
        f"of the requested period, so every year is comparable to every other")
    return tuple(notes)
