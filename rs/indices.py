"""NDVI/NBR/dNBR on reflectance arrays. Bands are the frozen contract choice:
NDVI = (B08 - B04) / (B08 + B04); NBR = (B8A - B12) / (B8A + B12).
"""
import numpy as np


def _ratio_index(numerator_band, denominator_band):
    denom = numerator_band + denominator_band
    with np.errstate(divide="ignore", invalid="ignore"):
        value = np.where(denom != 0, (numerator_band - denominator_band) / denom, np.nan)
    return value


def ndvi(b08, b04):
    return _ratio_index(b08, b04)


def nbr(b8a, b12):
    return _ratio_index(b8a, b12)


def dnbr(nbr_before, nbr_after):
    """Positive dNBR indicates loss of near-infrared / gain of SWIR (burn signal)."""
    return nbr_before - nbr_after


DNBR_VISUAL_CLASSES = (
    (0.10, "unburned/regrowth signal"),
    (0.27, "low"),
    (0.44, "moderate-low"),
    (0.66, "moderate-high"),
    (float("inf"), "high"),
)


def dnbr_class(value):
    if value is None or not np.isfinite(value):
        return None
    for threshold, label in DNBR_VISUAL_CLASSES:
        if value < threshold:
            return label
    return "high"
