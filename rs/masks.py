"""SCL-based validity/cloud masking. Thresholds are frozen contract values."""
import numpy as np

# Frozen: contracts/*.schema.json Parameters.excluded_scl_classes.
EXCLUDED_SCL_CLASSES = frozenset({0, 1, 2, 3, 6, 7, 8, 9, 10, 11})
# Cloud-only classes used for the AOI cloud ratio (manifest 10.3): thick/thin
# cirrus + cloud shadow are NOT counted here even though they are excluded from
# validity; this ratio is specifically "cloud", not "all excluded".
CLOUD_SCL_CLASSES = frozenset({8, 9, 10})


def valid_mask(scl):
    """True where a pixel is usable per the frozen SCL exclusion list."""
    return ~np.isin(scl, list(EXCLUDED_SCL_CLASSES))


def cloud_ratio(scl, footprint):
    """Fraction of footprint pixels classified as cloud (SCL 8/9/10)."""
    within = footprint
    total = int(within.sum())
    if total == 0:
        return None
    cloud = np.isin(scl, list(CLOUD_SCL_CLASSES)) & within
    return float(cloud.sum()) / total


def paired_valid(scl_before, scl_after, footprint):
    """Pixels valid on both dates and inside the AOI/forest footprint."""
    return valid_mask(scl_before) & valid_mask(scl_after) & footprint
