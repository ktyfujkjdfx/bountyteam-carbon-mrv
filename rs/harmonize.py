"""Sentinel-2 L2A DN -> surface reflectance.

ESA introduced a per-band additive BOA_ADD_OFFSET in processing baseline 04.00
(2022-01-25): reflectance = (DN + BOA_ADD_OFFSET) / QUANTIFICATION_VALUE, with
BOA_ADD_OFFSET = -1000 and QUANTIFICATION_VALUE = 10000. Earlier baselines encode
reflectance directly as DN / QUANTIFICATION_VALUE with no offset. This must never
be applied unconditionally: it is keyed off the scene's own processing baseline
UNLESS the hosting provider states it already harmonized the values (see
`from_provider_metadata`), in which case applying baseline-only offset again
would double-correct and must not happen.
"""
import numpy as np

QUANTIFICATION_VALUE = 10000
BOA_ADD_OFFSET = -1000
OFFSET_INTRODUCED_AT_BASELINE = 4.00


def _baseline_number(processing_baseline):
    if not processing_baseline:
        raise ValueError("processing_baseline is required to harmonize reflectance")
    return float(processing_baseline)


def from_baseline(processing_baseline):
    """Return (scale_applied, offset_applied, transform_origin) from the
    documented per-baseline ESA rule alone (no provider hint available)."""
    baseline = _baseline_number(processing_baseline)
    offset = BOA_ADD_OFFSET if baseline >= OFFSET_INTRODUCED_AT_BASELINE else 0
    return 1.0 / QUANTIFICATION_VALUE, offset, "PRODUCT_METADATA"


def from_provider_metadata(processing_baseline, provider_boa_offset_applied):
    """Prefer an explicit provider harmonization flag over the baseline guess.

    Element84 Earth Search sets `earthsearch:boa_offset_applied` on each item:
    when True, the hosted COG values are already offset-corrected and applying
    BOA_ADD_OFFSET again would double-subtract 1000. When the flag is absent
    (None), fall back to the documented per-baseline rule.
    """
    if provider_boa_offset_applied is True:
        return 1.0 / QUANTIFICATION_VALUE, 0, "PROVIDER_HARMONIZED"
    if provider_boa_offset_applied is False:
        return from_baseline(processing_baseline)
    return from_baseline(processing_baseline)


def apply_scale_offset(dn, scale_applied, offset_applied):
    """reflectance = (DN + offset_applied) * scale_applied, per the recorded
    per-asset transform (the single source of truth once request.json exists).
    """
    return (dn.astype("float64") + offset_applied) * scale_applied
