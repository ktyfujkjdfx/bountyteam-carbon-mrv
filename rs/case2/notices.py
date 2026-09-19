"""Structured warnings: a stable code, a fixed severity, a message and details.

A consumer cannot act on prose. Every caution the analysis raises therefore has
a code that never changes meaning, a severity that is a property of the code
rather than of the run, and a details object carrying the measurement the
caution was raised from. The prose stays too - `limitations` keeps the readable
account - but the two are separate lists and neither is derived from the other.

Severity says what a consumer should do, not how bad the forest looks:

* ``INFO``     - a property of the method the reader should know.
* ``WARNING``  - the result is usable but something about it is limited.
* ``CRITICAL`` - reading this particular result as change would be wrong.

The module deliberately owns no logic beyond the registry. Where a caution is
raised is where it is understood; here it is only given a name.
"""

INFO = "INFO"
WARNING = "WARNING"
CRITICAL = "CRITICAL"

# Coverage and support.
INCOMPLETE_COVERAGE = "RS_INCOMPLETE_COVERAGE"
ZERO_AGB_CELLS = "RS_ZERO_AGB_CELLS"
INVALID_CELLS = "RS_INVALID_CELLS"
CELL_WEIGHT_SUM_DIFFERS = "RS_CELL_WEIGHT_SUM_DIFFERS"
MODEL_YEARS_NOT_OBSERVATIONS = "RS_MODEL_YEARS_NOT_OBSERVATIONS"

# Optical observation.
OPTICAL_DISABLED = "RS_OPTICAL_DISABLED"
NO_SCENE_PAIR = "RS_NO_SCENE_PAIR"
LOW_PAIRED_COVERAGE = "RS_LOW_PAIRED_COVERAGE"
SCENE_REJECTED = "RS_SCENE_REJECTED"
SEASONAL_GAP = "RS_SEASONAL_GAP"
RADIOMETRIC_BASELINE_DIFFERS = "RS_RADIOMETRIC_BASELINE_DIFFERS"
RADIOMETRIC_OFFSET_MIXED = "RS_RADIOMETRIC_OFFSET_MIXED"

# Change evidence.
CHANGE_EVIDENCE_UNAVAILABLE = "RS_CHANGE_EVIDENCE_UNAVAILABLE"
CHANGE_EXTENT_UNIFORM = "RS_CHANGE_EXTENT_UNIFORM"
FIRE_PRODUCT_ABSENT = "RS_FIRE_PRODUCT_ABSENT"
ZONE_CAUSE_UNKNOWN = "RS_ZONE_CAUSE_UNKNOWN"
RECOVERY_NOT_RECOVERED_CARBON = "RS_RECOVERY_NOT_RECOVERED_CARBON"
ZONE_ATTRIBUTION_RESOLUTION = "RS_ZONE_ATTRIBUTION_RESOLUTION"
ZONES_FIRST_PARENT_ONLY = "RS_ZONES_FIRST_PARENT_ONLY"
OBSERVATION_GAP_ZONES = "RS_OBSERVATION_GAP_ZONES"

# Severity belongs to the code, so the same situation never arrives at a
# consumer as WARNING on one request and CRITICAL on another.
SEVERITIES = {
    INCOMPLETE_COVERAGE: WARNING,
    ZERO_AGB_CELLS: INFO,
    INVALID_CELLS: WARNING,
    CELL_WEIGHT_SUM_DIFFERS: INFO,
    MODEL_YEARS_NOT_OBSERVATIONS: INFO,
    OPTICAL_DISABLED: INFO,
    NO_SCENE_PAIR: WARNING,
    LOW_PAIRED_COVERAGE: WARNING,
    SCENE_REJECTED: INFO,
    SEASONAL_GAP: WARNING,
    RADIOMETRIC_BASELINE_DIFFERS: WARNING,
    # The measured case: a pair across the 04.00 offset change reads a control
    # forest as regrowth at a median dNBR near -0.86. Nothing about the result
    # is repairable by the reader, so it is not a WARNING.
    RADIOMETRIC_OFFSET_MIXED: CRITICAL,
    CHANGE_EVIDENCE_UNAVAILABLE: WARNING,
    CHANGE_EXTENT_UNIFORM: WARNING,
    FIRE_PRODUCT_ABSENT: WARNING,
    ZONE_CAUSE_UNKNOWN: INFO,
    RECOVERY_NOT_RECOVERED_CARBON: INFO,
    ZONE_ATTRIBUTION_RESOLUTION: INFO,
    ZONES_FIRST_PARENT_ONLY: WARNING,
    OBSERVATION_GAP_ZONES: INFO,
}


class NoticeError(KeyError):
    """A warning was raised under a code that is not in the registry."""


def warning(code, message, **details):
    """One structured warning: ``{code, severity, message, details}``.

    The severity comes from the registry rather than from the caller, so a code
    cannot arrive with two different severities from two call sites.
    """
    if code not in SEVERITIES:
        raise NoticeError(f"unknown warning code {code!r}")
    if not message:
        raise NoticeError(f"warning {code} carries no message")
    return {
        "code": code,
        "severity": SEVERITIES[code],
        "message": message,
        "details": dict(sorted(details.items())),
    }


def highest_severity(items):
    """Worst severity present, or None for an empty list."""
    order = (INFO, WARNING, CRITICAL)
    present = [item["severity"] for item in items]
    if not present:
        return None
    return max(present, key=order.index)
