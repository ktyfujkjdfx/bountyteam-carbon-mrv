"""Intersecting a request with a raster grid, by area rather than by pixel count.

The CCI grid is in degrees, so cell area varies with latitude and no constant
hectares-per-pixel exists. Weights are geodesic areas of the intersection
between each cell and the request.
"""
import math

from rasterio.transform import rowcol
from shapely.geometry import box
from shapely.prepared import prep

from rs.case2.geometry import geodesic_area_ha
from rs.case2.models import GridSpec


def grid_spec(dataset, units="degree"):
    """Describe an open rasterio dataset's native grid."""
    return GridSpec(
        crs=str(dataset.crs),
        transform=tuple(dataset.transform.to_gdal()),
        width=int(dataset.width),
        height=int(dataset.height),
        pixel_size=(abs(dataset.transform.a), abs(dataset.transform.e)),
        units=units,
    )


def cell_polygon(transform, row, col):
    """Polygon of one grid cell in the raster's own coordinates."""
    x0, y0 = transform @ (col, row)
    x1, y1 = transform @ (col + 1, row + 1)
    return box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def window(transform, width, height, bounds):
    """Row/column range of the cells that can touch `bounds`, clamped to the grid."""
    lon_min, lat_min, lon_max, lat_max = bounds
    top, left = rowcol(transform, lon_min, lat_max, op=math.floor)
    bottom, right = rowcol(transform, lon_max, lat_min, op=math.ceil)
    return (max(0, min(top, bottom)), min(height, max(top, bottom) + 1),
            max(0, min(left, right)), min(width, max(left, right) + 1))


def weigh(transform, width, height, geometry):
    """Weight every cell of the grid by its geodesic overlap with `geometry`.

    Yields `(row, col, weight_ha, cell)`. Cells the request fully contains take
    the whole cell area, which on a lon/lat grid depends only on the row, so the
    geodesic call is made once per row instead of once per cell.
    """
    prepared = prep(geometry)
    row_start, row_stop, col_start, col_stop = window(
        transform, width, height, geometry.bounds)
    full_area_by_row = {}
    for row in range(row_start, row_stop):
        for col in range(col_start, col_stop):
            cell = cell_polygon(transform, row, col)
            if not prepared.intersects(cell):
                continue
            if prepared.contains(cell):
                if row not in full_area_by_row:
                    full_area_by_row[row] = geodesic_area_ha(cell)
                weight = full_area_by_row[row]
            else:
                piece = cell.intersection(geometry)
                if piece.is_empty:
                    continue
                weight = geodesic_area_ha(piece)
            if weight > 0:
                yield row, col, weight, cell


def pixel_centres_inside(transform, width, height, geometry):
    """Boolean mask of pixels whose centre falls inside `geometry`.

    Used for the metric Sentinel grid, where a 20 m pixel is small against the
    request and centre membership is an honest, cheap rule. It is stated rather
    than assumed because it is not the rule used for the coarse CCI grid, where
    partial overlap carries real area and is weighted instead.

    The test is a GEOS predicate rather than a rasterisation, so the mask does
    not depend on which GDAL build happens to be installed.
    """
    import numpy
    import shapely

    row_start, row_stop, col_start, col_stop = window(
        transform, width, height, geometry.bounds)
    mask = numpy.zeros((height, width), dtype=bool)
    if row_start >= row_stop or col_start >= col_stop:
        return mask
    rows = numpy.arange(row_start, row_stop) + 0.5
    cols = numpy.arange(col_start, col_stop) + 0.5
    col_grid, row_grid = numpy.meshgrid(cols, rows)
    x = transform.c + transform.a * col_grid + transform.b * row_grid
    y = transform.f + transform.d * col_grid + transform.e * row_grid
    mask[row_start:row_stop, col_start:col_stop] = shapely.contains_xy(
        geometry, x, y)
    return mask
