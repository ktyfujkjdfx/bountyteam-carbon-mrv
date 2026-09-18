"""Sampling one raster onto another grid without warping it.

Three products, three coordinate systems, three resolutions, and nothing lines
up: CCI in degrees at 0.00088889, GFC in degrees at 0.00025, Sentinel-2 in UTM
at 20 m, MODIS in a sinusoidal projection on a sphere at about 463 m.

The obvious tool is a GDAL warp. It is not used here. A warp resamples with
weights that differ between GDAL builds, which is exactly the failure that made
the same bundle hash differently on macOS and Windows during P0. Instead each
target pixel centre is projected into the source's own index space and the
covering source pixel is read. That is nearest-neighbour by construction, it is
pure pyproj plus integer indexing, and it gives the same answer everywhere.

Nearest neighbour is also the right choice on merits here: loss year, burn date
and quality bits are categorical, and averaging them would be meaningless.
"""
import numpy
import rasterio
from pyproj import Transformer


def sample_on_grid(source_path, target_transform, target_width, target_height,
                   target_crs, band=1, fill=None):
    """Read `source_path` at every target pixel centre.

    Returns `(values, inside)` where `inside` marks the target pixels that fall
    within the source raster at all. Target pixels outside the source keep
    `fill` and are never silently treated as a zero reading.
    """
    with rasterio.open(source_path) as source:
        data = source.read(band)
        source_transform = source.transform
        source_crs = source.crs
        source_height, source_width = data.shape
        nodata = source.nodatavals[band - 1]

    cols = numpy.arange(target_width) + 0.5
    rows = numpy.arange(target_height) + 0.5
    col_grid, row_grid = numpy.meshgrid(cols, rows)
    x = target_transform.c + target_transform.a * col_grid + target_transform.b * row_grid
    y = target_transform.f + target_transform.d * col_grid + target_transform.e * row_grid

    transformer = Transformer.from_crs(target_crs, source_crs, always_xy=True)
    src_x, src_y = transformer.transform(x, y)

    inverse = ~source_transform
    src_col = inverse.a * src_x + inverse.b * src_y + inverse.c
    src_row = inverse.d * src_x + inverse.e * src_y + inverse.f
    col_index = numpy.floor(src_col).astype("int64")
    row_index = numpy.floor(src_row).astype("int64")

    inside = ((col_index >= 0) & (col_index < source_width)
              & (row_index >= 0) & (row_index < source_height))
    values = numpy.full(
        (target_height, target_width),
        fill if fill is not None else 0,
        dtype=data.dtype if fill is None or isinstance(fill, (int, numpy.integer))
        else "float64")
    values[inside] = data[row_index[inside], col_index[inside]]
    if nodata is not None:
        inside = inside & (values != nodata)
    return values, inside
