"""Carbon stock from the ESA CCI Biomass maps.

Both bands of the annual file are used: AGB and its standard deviation. The
product carries no NoData tag and zero is a published value - burned ground
reads as zero biomass, not as missing data - so a cell is invalid here only
when the map does not reach it at all.
"""
import numpy
import rasterio

from rs.case2.catalog import DatasetError
from rs.case2.grid import grid_spec, weigh
from rs.case2.models import (
    CARBON_FRACTION,
    HISTORY_YEAR_MIN,
    ANALYSIS_YEAR_MAX,
    CarbonCell,
    StockYear,
)

AGB_BAND = 1
AGB_SD_BAND = 2


def available_years(dataset, aoi_id, first=HISTORY_YEAR_MIN, last=ANALYSIS_YEAR_MAX):
    """Years of this AOI that actually have a biomass file on disk."""
    years = []
    for year in range(first, last + 1):
        try:
            dataset.biomass_path(aoi_id, year)
        except DatasetError:
            continue
        years.append(year)
    return years


def read_year(dataset, aoi_id, year):
    """Return `(agb, agb_sd, grid)` for one AOI-year, as published."""
    with rasterio.open(dataset.biomass_path(aoi_id, year)) as source:
        if source.count < AGB_SD_BAND:
            raise DatasetError(
                f"{aoi_id} {year}: expected AGB and AGB_SD bands, found {source.count}"
            )
        agb = source.read(AGB_BAND).astype("float64")
        agb_sd = source.read(AGB_SD_BAND).astype("float64")
        grid = grid_spec(source, units="degree")
        nodata = source.nodatavals[0]
    if nodata is not None:
        agb = numpy.where(agb == nodata, numpy.nan, agb)
        agb_sd = numpy.where(agb_sd == nodata, numpy.nan, agb_sd)
    return agb, agb_sd, grid


def build_cells(dataset, geometry, parents, years, validity_years=None):
    """Weigh the request against the CCI grid and attach the yearly values.

    A cell is kept when the biomass map covers it in every year of
    `validity_years` - the two dates of the analysis. The same set of cells is
    then used for every year, so a stock difference is always compared on
    identical ground, including ground that lost its cover in between. Extra
    `years` are read for the timeline and cannot invalidate a cell.
    """
    validity_years = tuple(validity_years if validity_years is not None else years)
    cells = []
    grids = {}
    for aoi_id in parents:
        part = geometry.intersection(dataset.geometries[aoi_id])
        if part.is_empty:
            continue
        layers = {}
        for year in years:
            agb, agb_sd, grid = read_year(dataset, aoi_id, year)
            layers[year] = (agb, agb_sd)
            grids[f"cci_biomass:{aoi_id}"] = grid
        grid = grids[f"cci_biomass:{aoi_id}"]
        transform = rasterio.Affine.from_gdal(*grid.transform)
        for row, col, weight_ha, cell in weigh(
                transform, grid.width, grid.height, part):
            values = {year: float(layers[year][0][row, col]) for year in years}
            deviations = {year: float(layers[year][1][row, col]) for year in years}
            valid = all(numpy.isfinite(values[year]) for year in validity_years)
            centroid = cell.centroid
            cells.append(CarbonCell(
                cell_id=f"{aoi_id}:{row:04d}:{col:04d}",
                parent_aoi_id=aoi_id,
                row=row,
                col=col,
                centroid=(centroid.x, centroid.y),
                bounds=tuple(cell.bounds),
                weight_ha=weight_ha,
                agb=values,
                agb_sd=deviations,
                valid=valid,
            ))
    cells.sort(key=lambda item: item.cell_id)
    return cells, grids


def stock(cells, year):
    """Carbon stock of the valid cells in one model year.

    C_year = sum(AGB_i * CF * area_i_ha); the mean is that total over the
    covered area, so it is a real area weighted mean and not an average of
    per-cell means.
    """
    usable = [cell for cell in cells if cell.valid and year in cell.agb]
    covered = sum(cell.weight_ha for cell in usable)
    if covered <= 0:
        raise DatasetError(f"no covered area to compute stock for {year}")
    total_agb = sum(cell.agb[year] * cell.weight_ha for cell in usable)
    total_tc = total_agb * CARBON_FRACTION
    return StockYear(
        year=year,
        mean_tc_ha=total_tc / covered,
        total_tc=total_tc,
        mean_agb_t_ha=total_agb / covered,
        cells=len(usable),
        covered_ha=covered,
    )


def sd_available(cells, years):
    """Area whose uncertainty band is present in every requested year.

    Tracked apart from biomass coverage on purpose. For CCI v7 the two bands
    travel in one file, so the two areas coincide; a source that ships them
    separately would not, and the consumer must not have to assume either way.
    """
    covered = 0.0
    for cell in cells:
        if not cell.valid:
            continue
        if all(numpy.isfinite(cell.agb_sd.get(year, numpy.nan)) for year in years):
            covered += cell.weight_ha
    return covered
