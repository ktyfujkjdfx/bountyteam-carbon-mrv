"""Exact, platform-independent resampling onto the analysis grid.

Sentinel-2 assets and the 20 m analysis grid share a CRS and a common origin
lattice, so going from a 10 m or 20 m band to the 20 m grid is not a warp at
all: it is either a window slice (20 m -> 20 m) or an exact 2x2 block mean
(10 m -> 20 m). Doing it that way instead of calling GDAL's warper matters for
reproducibility.

`Resampling.average` was measured to differ between platforms by ~6e-7 in
reflectance — far above float64 rounding, so it is the warper's own source-
pixel weighting, not arithmetic noise. It is invisible in the float32 dNBR
raster and in every derived metric, but it flips previews: on macOS ~0.6% of
preview samples landed on the other side of a uint8 boundary (max delta 1 grey
level). No amount of rounding fixes that, because the lattice needed to absorb
6e-7 reflectance would have to be coarser than the previews themselves.

A block mean of integer DNs has no such freedom: the sum is exact in int64 and
the division by 4 is exact in binary, so every platform gets the same bits.

This only applies when the grids genuinely line up. `plan` returns None for
anything else (different CRS, non-integral offset, a grid extending past the
cached window), and the caller falls back to `rasterio.warp.reproject`.
"""
import numpy as np

TOLERANCE = 1e-9  # metres; transforms come from GeoTIFF headers, not arithmetic


def _is_integral(value):
    return abs(value - round(value)) < TOLERANCE


def plan(src_transform, src_crs, src_shape, dst_transform, dst_width, dst_height, dst_crs):
    """Describe an exact slice/block-mean, or None if one does not exist.

    Returns (row_offset, col_offset, factor): the source window starts at
    (row_offset, col_offset) and each destination pixel covers a
    factor x factor block.
    """
    if src_crs is None or dst_crs is None or str(src_crs) != str(dst_crs):
        return None
    src_res_x, src_res_y = src_transform.a, -src_transform.e
    dst_res_x, dst_res_y = dst_transform[0], -dst_transform[4]
    if src_res_x <= 0 or src_res_y <= 0 or src_transform.b or src_transform.d:
        return None
    if abs(src_res_x - src_res_y) > TOLERANCE or abs(dst_res_x - dst_res_y) > TOLERANCE:
        return None

    factor = dst_res_x / src_res_x
    if not _is_integral(factor) or round(factor) < 1:
        return None
    factor = round(factor)

    col_offset = (dst_transform[2] - src_transform.c) / src_res_x
    row_offset = (src_transform.f - dst_transform[5]) / src_res_y
    if not (_is_integral(col_offset) and _is_integral(row_offset)):
        return None
    col_offset, row_offset = round(col_offset), round(row_offset)
    if col_offset < 0 or row_offset < 0:
        return None

    src_height, src_width = src_shape
    if row_offset + dst_height * factor > src_height or col_offset + dst_width * factor > src_width:
        return None
    return row_offset, col_offset, factor


def block_mean(native, plan_, dst_width, dst_height):
    """Exact mean of each factor x factor block of integer DNs.

    Summed in int64 (exact) and divided by a power-of-two-friendly count; for
    the 2x2 case the division is exact in binary too, so the result carries no
    platform-dependent rounding at all.
    """
    row_offset, col_offset, factor = plan_
    window = native[row_offset:row_offset + dst_height * factor,
                    col_offset:col_offset + dst_width * factor]
    if factor == 1:
        return window.astype("float64")
    blocks = window.astype("int64").reshape(dst_height, factor, dst_width, factor)
    return blocks.sum(axis=(1, 3)).astype("float64") / (factor * factor)


def window_slice(native, plan_, dst_width, dst_height):
    """Categorical/identity case: the destination pixels are source pixels."""
    row_offset, col_offset, factor = plan_
    if factor != 1:
        return None
    return native[row_offset:row_offset + dst_height, col_offset:col_offset + dst_width].copy()


def describe(plan_):
    """Short label for the limitation text when the exact path is unavailable."""
    if plan_ is None:
        return "GDAL_WARP"
    return "EXACT_SLICE" if plan_[2] == 1 else f"EXACT_BLOCK_MEAN_{plan_[2]}X"
