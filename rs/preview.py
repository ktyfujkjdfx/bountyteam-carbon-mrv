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


def _stretch(band, low_pct=2, high_pct=98):
    finite = band[np.isfinite(band)]
    if finite.size == 0:
        return np.zeros(band.shape, dtype="uint8")
    lo, hi = np.percentile(finite, [low_pct, high_pct])
    if hi <= lo:
        hi = lo + 1e-6
    scaled = np.clip((band - lo) / (hi - lo), 0, 1)
    scaled = np.where(np.isfinite(band), scaled, 0)
    return (scaled * 255).astype("uint8")


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
