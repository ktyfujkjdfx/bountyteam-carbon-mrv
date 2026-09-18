"""Typed results of a raster analysis.

These dataclasses are the internal adapter between the raster core and whatever
the shared v2 contract turns out to be. Nothing here knows about JSON, HTTP or
field names in the contract; `payload.py` is the only place that does, so a G0
rename changes one module instead of the whole core.
"""
from dataclasses import dataclass, field
from typing import Mapping, Sequence

# Published in data/methodology/parameters.csv; IPCC 2006 Vol. 4 Table 4.3.
CARBON_FRACTION = 0.47
# Molar mass ratio CO2 / C.
CO2_PER_C = 44.0 / 12.0
# Analysis periods the case allows; the CCI history reaches further back.
ANALYSIS_YEAR_MIN = 2019
ANALYSIS_YEAR_MAX = 2024
HISTORY_YEAR_MIN = 2015
# Maximum requested area, 20 km^2 stated in the task description.
MAX_AREA_HA = 2000.0


@dataclass(frozen=True)
class GridSpec:
    """Native grid of one source raster, kept so consumers never guess it."""

    crs: str
    transform: Sequence[float]          # GDAL order, six coefficients
    width: int
    height: int
    pixel_size: Sequence[float]
    units: str


@dataclass(frozen=True)
class CarbonCell:
    """One CCI model cell intersected with the request.

    `weight_ha` is the geodesic area of the intersection, not the area of the
    whole cell. `agb` and `agb_sd` are the published values in t/ha; zero is a
    real value and is kept, so `valid` speaks only about data presence.
    """

    cell_id: str
    parent_aoi_id: str
    row: int
    col: int
    centroid: Sequence[float]
    bounds: Sequence[float]
    weight_ha: float
    agb: Mapping[int, float]
    agb_sd: Mapping[int, float]
    valid: bool


@dataclass(frozen=True)
class StockYear:
    """Carbon stock of the analysed support in one model year."""

    year: int
    mean_tc_ha: float
    total_tc: float
    mean_agb_t_ha: float
    cells: int
    covered_ha: float


@dataclass(frozen=True)
class Coverage:
    """Coverage of the request, as three independent fractions.

    They answer different questions and are never merged into one quality
    number: a cloudy optical scene says nothing about biomass coverage.
    """

    requested_ha: float
    calculated_ha: float
    biomass_ha: float
    biomass_sd_ha: float
    optical_paired_ha: float
    biomass_fraction: float
    biomass_sd_fraction: float
    optical_paired_fraction: float
    missing_ha: float
    complete: bool


@dataclass(frozen=True)
class SceneQuality:
    """Optical usability of one Sentinel-2 scene inside the request."""

    scene_key: str
    item_id: str
    aoi_id: str
    datetime_utc: str
    year: int
    processing_baseline: str
    reflectance_offset_applied: float
    pixels_in_request: int
    usable_pixels: int
    usable_fraction: float
    scl_class_pixels: Mapping[int, int]
    negative_reflectance_pixels: int
    non_finite_pixels: int


@dataclass(frozen=True)
class PairedOptical:
    """Best paired-valid optical coverage between two analysis years.

    Scene *selection* is RS-2 work. RS-1 reports the best available pair under
    a stated provisional rule so the number is defined rather than absent.
    """

    before_scene_key: str
    after_scene_key: str
    paired_usable_pixels: int
    pixels_in_request: int
    paired_usable_fraction: float
    selection_rule: str


@dataclass(frozen=True)
class StockChange:
    """Stock difference between the two requested model years."""

    year_start: int
    year_end: int
    years: int
    stock_start_tc: float
    stock_end_tc: float
    delta_tc: float
    e_tco2e: float
    e_per_ha_per_year: float
    # The area E was actually summed over. Per-hectare figures are normalised by
    # this rather than by the requested polygon, so a partial result never mixes
    # a total from one support with an area from another.
    normalisation_area_ha: float
    sign_convention: str = (
        "positive e_tco2e is a loss from the accounted pool; negative is accumulation"
    )


@dataclass(frozen=True)
class SourceFile:
    """One input file, with the checksum that makes a replay checkable."""

    relative_path: str
    sha256: str
    size_bytes: int
    role: str


@dataclass(frozen=True)
class RasterAnalysis:
    """Everything the raster core produces for one request."""

    request_area_ha: float
    cell_weight_sum_ha: float
    parents: Sequence[str]
    years: Sequence[int]
    change: StockChange
    timeline: Sequence[StockYear]
    coverage: Coverage
    cells: Sequence[CarbonCell]
    scenes: Sequence[SceneQuality]
    paired_optical: PairedOptical | None
    grids: Mapping[str, GridSpec]
    sources: Sequence[SourceFile]
    parameters: Mapping[str, object]
    limitations: Sequence[str] = field(default_factory=tuple)
