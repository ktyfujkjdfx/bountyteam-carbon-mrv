"""Observation quality inside the request, counted by category.

The counters are kept by what the class means, not just by its code, because
"how much of this plot was under cloud" and "how much was water" lead to
different conclusions and a single unusable-fraction hides both.

Every count uses one denominator: pixels of the Sentinel grid whose centre
falls inside the request. That denominator is reported alongside the counts so
a reader never has to guess what a fraction is a fraction of.
"""
import numpy

# Codes as published in the data description, grouped by what they mean for a
# change analysis. Names are ours; the codes are the product's.
SCL_CATEGORIES = {
    "nodata": (0,),
    "defective": (1,),
    "dark_or_topographic_shadow": (2,),
    "cloud_shadow": (3,),
    "vegetation": (4,),
    "bare_surface": (5,),
    "water": (6,),
    "unclassified": (7,),
    "cloud": (8, 9, 10),
    "snow_and_ice": (11,),
}
USABLE_CATEGORIES = ("vegetation", "bare_surface")


def category_counts(scl, footprint):
    """Pixels per category inside the footprint, plus the denominator."""
    counts = {}
    for name, codes in SCL_CATEGORIES.items():
        counts[name] = int((numpy.isin(scl, codes) & footprint).sum())
    counts["total_in_request"] = int(footprint.sum())
    accounted = sum(counts[name] for name in SCL_CATEGORIES)
    counts["unaccounted"] = counts["total_in_request"] - accounted
    return counts


def fractions(counts):
    """Category shares of the request, on the one stated denominator."""
    total = counts["total_in_request"]
    if not total:
        return {name: 0.0 for name in SCL_CATEGORIES}
    return {name: counts[name] / total for name in SCL_CATEGORIES}


def paired_valid(before_mask, after_mask, footprint):
    """Pixels usable on both dates.

    A change can only be measured where both observations exist, so this
    intersection - not either date on its own - is the area a spectral result
    may speak about.
    """
    return before_mask & after_mask & footprint


def summary(before_counts, after_counts, paired_mask, footprint):
    total = int(footprint.sum())
    paired = int(paired_mask.sum())
    return {
        "denominator_pixels": total,
        "denominator_rule": (
            "Sentinel-2 pixels whose centre falls inside the request polygon"),
        "before": before_counts,
        "after": after_counts,
        "paired_valid_pixels": paired,
        "paired_valid_fraction": (paired / total) if total else 0.0,
        "usable_categories": list(USABLE_CATEGORIES),
        "excluded_note": (
            "classes 2 and 7 are excluded from the main mask and are admitted "
            "only in a signed sensitivity variant"),
    }
