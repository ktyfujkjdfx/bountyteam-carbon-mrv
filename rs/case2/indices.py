"""Spectral indices used as evidence of change.

The supplied product has no B08, so NDVI is formed from the narrow near
infrared band B8A. Both indices are therefore named for the band they use, and
neither is interchangeable with a B08 version from another study.

    NDVI_B8A = (B8A - B04) / (B8A + B04)
    NBR_B8A  = (B8A - B12) / (B8A + B12)
    dNBR     = NBR_before - NBR_after        positive means a burn-like loss
    dNDVI    = NDVI_before - NDVI_after      positive means a loss of greenness

The denominator policy is explicit because the alternative is a silent one.
From processing baseline 04.00 the product carries a -0.1 radiometric offset,
so individual reflectances are legitimately negative and a sum of two bands can
approach zero. Where it does, the index is undefined and is returned as NaN
rather than clamped, divided by an epsilon, or quietly set to zero - each of
which would invent a value where the data does not support one. The count of
such pixels travels with the result.
"""
import numpy

# A denominator this close to zero makes the ratio meaningless long before it
# makes it infinite: at 1e-4 a one-DN change moves the index by more than its
# whole range. Pixels below it are reported undefined, not repaired.
DENOMINATOR_FLOOR = 1e-4

BAND_INDEX = {"B02": 0, "B03": 1, "B04": 2, "B8A": 3, "B11": 4, "B12": 5}

# Key & Benson burn-severity class boundaries, used unchanged. The threshold is
# fixed here and in the method manifest so it cannot be tuned per request; the
# sensitivity variants below exist to show what a different choice would do.
DNBR_DISTURBANCE = 0.27
DNBR_SENSITIVITY = (0.10, 0.27, 0.44)
# A greenness drop this large is a change worth polygonising even where the
# burn index stays quiet, which is the usual signature of clearing rather than
# fire. Also fixed, also carried in the manifest.
DNDVI_DISTURBANCE = 0.20
# Regrowth is reported as an indication only; it is not evidence of recovered
# carbon and is never counted as one.
DNBR_RECOVERY = -0.10


def ratio(numerator, denominator):
    """Normalised difference with an explicit undefined region."""
    numerator = numpy.asarray(numerator, dtype="float64")
    denominator = numpy.asarray(denominator, dtype="float64")
    defined = numpy.isfinite(numerator) & numpy.isfinite(denominator) & (
        numpy.abs(denominator) >= DENOMINATOR_FLOOR)
    out = numpy.full(numerator.shape, numpy.nan, dtype="float64")
    numpy.divide(numerator, denominator, out=out, where=defined)
    return out


def ndvi(reflectance):
    b04 = reflectance[BAND_INDEX["B04"]]
    b8a = reflectance[BAND_INDEX["B8A"]]
    return ratio(b8a - b04, b8a + b04)


def nbr(reflectance):
    b12 = reflectance[BAND_INDEX["B12"]]
    b8a = reflectance[BAND_INDEX["B8A"]]
    return ratio(b8a - b12, b8a + b12)


def difference(before, after):
    """`before - after`, so a loss of signal is positive."""
    return numpy.asarray(before, dtype="float64") - numpy.asarray(after, dtype="float64")


def undefined_count(index_array, footprint=None):
    """Pixels where the index could not be formed, inside the footprint."""
    undefined = ~numpy.isfinite(index_array)
    if footprint is not None:
        undefined = undefined & footprint
    return int(undefined.sum())
