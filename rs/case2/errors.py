"""Refusals a caller can act on.

A request that cannot be analysed has to say so in a form a program can branch
on. "the request does not intersect any supplied area" is true and useless to
anything but a human reader: a consumer needs to know whether to ask for a
different contour, a different period, or nothing at all.

So every refusal carries three things beyond its message: a stable `code`, an
`outcome` saying what kind of refusal it is, and `details` holding the numbers
the decision was made from. The message stays, unchanged, for the reader.

Two outcomes, and the difference matters:

* ``INVALID_REQUEST`` - the request itself cannot be accepted. Nothing was
  measured because nothing could be. Fixing it means changing the request.
* ``INSUFFICIENT_DATA`` - the request is well formed and the supplied products
  do not reach it. This is a statement about coverage, never about the forest,
  and it must not be reported as an absence of change.
"""

INVALID_REQUEST = "INVALID_REQUEST"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

ERROR_SCHEMA = "rs.case2.request-error/1"

# Request geometry and period.
GEOMETRY_UNREADABLE = "RS_GEOMETRY_UNREADABLE"
GEOMETRY_EMPTY = "RS_GEOMETRY_EMPTY"
GEOMETRY_TYPE_UNSUPPORTED = "RS_GEOMETRY_TYPE_UNSUPPORTED"
GEOMETRY_SELF_INTERSECTING = "RS_GEOMETRY_SELF_INTERSECTING"
GEOMETRY_NOT_WGS84 = "RS_GEOMETRY_NOT_WGS84"
GEOMETRY_NO_AREA = "RS_GEOMETRY_NO_AREA"
AREA_LIMIT_EXCEEDED = "RS_AREA_LIMIT_EXCEEDED"
REQUEST_NOT_SINGLE_FEATURE = "RS_REQUEST_NOT_SINGLE_FEATURE"
PERIOD_NOT_INTEGER = "RS_PERIOD_NOT_INTEGER"
PERIOD_NOT_ORDERED = "RS_PERIOD_NOT_ORDERED"
PERIOD_OUT_OF_RANGE = "RS_PERIOD_OUT_OF_RANGE"

# Coverage of the supplied products.
NO_SOURCE_COVERAGE = "RS_NO_SOURCE_COVERAGE"
SOURCE_AREAS_OVERLAP = "RS_SOURCE_AREAS_OVERLAP"
BIOMASS_YEAR_UNAVAILABLE = "RS_BIOMASS_YEAR_UNAVAILABLE"
NO_VALID_BIOMASS_CELL = "RS_NO_VALID_BIOMASS_CELL"
UNKNOWN_AREA_ID = "RS_UNKNOWN_AREA_ID"
DATASET_FILE_MISSING = "RS_DATASET_FILE_MISSING"
OUTPUT_INSIDE_DATASET = "RS_OUTPUT_INSIDE_DATASET"
SOURCE_BANDS_UNEXPECTED = "RS_SOURCE_BANDS_UNEXPECTED"
SOURCE_OFFSETS_MIXED = "RS_SOURCE_OFFSETS_MIXED"


class StructuredError(Exception):
    """A refusal with a code, an outcome and the numbers behind it."""

    default_code = "RS_REQUEST_REFUSED"
    outcome = INVALID_REQUEST

    def __init__(self, message, *, code=None, **details):
        super().__init__(message)
        self.code = code or type(self).default_code
        self.details = dict(sorted(details.items()))

    def as_document(self):
        """The refusal as a document a consumer can store next to a result."""
        return {
            "schema": ERROR_SCHEMA,
            "outcome": self.outcome,
            "code": self.code,
            "message": str(self),
            "details": self.details,
            "note": (
                "INSUFFICIENT_DATA is a statement about the coverage of the "
                "supplied products over this request; it is never a statement "
                "that nothing changed on the ground"
            ),
        }
