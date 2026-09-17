"""Web-ready preview rasters. Previews are illustrative; metrics come from the
reflectance/index arrays, never from the stretched preview pixels.
"""
import numpy as np
from PIL import Image

# dNBR class boundaries -> RGB, matching rs.indices.DNBR_VISUAL_CLASSES.
DNBR_LEGEND = (
    (0.10, (34, 139, 34)),   # unburned/regrowth signal
    (0.27, (173, 209, 92)),  # low
    (0.44, (255, 215, 0)),   # moderate-low
    (0.66, (255, 140, 0)),   # moderate-high
    (float("inf"), (178, 24, 43)),  # high
)


# Reflectance is scaled back onto the integer DN lattice it came from before
# any preview arithmetic happens. See _quantize.
DN_SCALE = 10000.0
# Larger than the ~1e-12 spread observed between CPU architectures, far smaller
# than the lattice step of 1. See _quantize.
QUANTISATION_EPSILON = 1e-9


def _quantize(band):
    """Snap reflectance onto its integer DN lattice, tie-stably.

    Reprojection (`Resampling.average`) sums in an order that depends on the
    CPU's SIMD width and FMA availability, so the same scene yields values
    differing in the last ULP on arm64 versus x86-64. That is invisible in the
    float32 dNBR raster but not in a preview, where a pixel sitting on a
    quantisation boundary flips to a different byte and changes the file hash.

    Snapping to the lattice removes it, but plain round-half-to-even does not:
    averaging integer DNs lands on exact .5 constantly, and whether the float
    actually *is* .5 or .5 +/- 1 ULP is precisely what differs. Adding a fixed
    epsilon before flooring sends every value within 1e-9 of a boundary the
    same way on every platform, while being far too small to move a value that
    genuinely belongs to another lattice point.
    """
    scaled = np.asarray(band, dtype="float64") * DN_SCALE
    return np.floor(scaled + 0.5 + QUANTISATION_EPSILON)


def _stretch(band, low_pct=2, high_pct=98):
    """Percentile stretch to uint8, pinned to be bit-identical across platforms.

    Once the input sits on an exact lattice (`_quantize`), the rest follows:
    IEEE-754 division and multiplication are correctly rounded, so identical
    inputs give identical results everywhere. `method="nearest"` keeps the
    cutoffs themselves on the lattice instead of interpolating between two
    samples, and `np.rint` states the half-way rule rather than inheriting
    whatever the preceding arithmetic happened to produce.
    """
    band = _quantize(band)
    finite = band[np.isfinite(band)]
    if finite.size == 0:
        return np.zeros(band.shape, dtype="uint8")
    lo, hi = np.percentile(finite, [low_pct, high_pct], method="nearest")
    if hi <= lo:
        hi = lo + 1.0
    scaled = np.clip((band - lo) / (hi - lo), 0, 1)
    scaled = np.where(np.isfinite(band), scaled, 0)
    return np.rint(scaled * 255).astype("uint8")


def false_color_preview(nir, swir, red):
    """SWIR/NIR/Red false-color composite: burn scars render dark red/brown."""
    rgb = np.dstack([_stretch(swir), _stretch(nir), _stretch(red)])
    return Image.fromarray(rgb)


def dnbr_preview(dnbr_array, valid_mask):
    height, width = dnbr_array.shape
    rgb = np.zeros((height, width, 3), dtype="uint8")
    rgb[~valid_mask] = (200, 200, 200)
    for threshold, color in DNBR_LEGEND:
        band_mask = valid_mask & (dnbr_array < threshold) & (rgb.sum(axis=2) == 0)
        rgb[band_mask] = color
    return Image.fromarray(rgb)


def save_png(image, path):
    """Deterministic PNG write; see rs/determinism.py for why it is pinned."""
    from pathlib import Path

    from rs import determinism

    return determinism.write_png(image, Path(path))
