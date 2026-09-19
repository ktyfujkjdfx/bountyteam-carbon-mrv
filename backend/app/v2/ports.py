"""The two computation boundaries Backend calls across.

Backend owns the API, the jobs, the storage and the files. It does not own a single
number in a result. Everything numeric arrives through one of these two ports, is
validated against `contracts/v2/internal-models.v2.schema.json`, and is then copied into
the public model without being recomputed.

Each port has a real implementation that delegates to the owning package, and a clearly
labelled stand-in used only while that package is absent from the branch. A stand-in
always reports itself in `run.raster_adapter` / `run.carbon_adapter` and always sets
`run.dataset_origin` to `STUB_FIXTURE`, so no reader can mistake it for a measurement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class RasterRequest:
    geometry: BaseGeometry
    canonical_geometry: dict
    geometry_hash: str
    area_ha: float
    year_start: int
    year_end: int
    include_optical: bool = True


@dataclass(frozen=True)
class RasterResult:
    """What the raster owner produced, exactly as its own schema describes it."""

    analysis: dict
    cells: dict
    manifest: dict
    adapter: str
    dataset_origin: str
    fixture: dict | None = None
    artifact_files: dict[str, bytes] = field(default_factory=dict)


class RasterUnavailable(RuntimeError):
    """The raster owner cannot answer this request; the reason is a result, not a crash."""

    def __init__(self, reason: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class CarbonRequest:
    raster: dict
    cells: dict
    geometry: dict
    geometry_hash: str
    year_start: int
    year_end: int
    claimed_units: float | None
    claim_origin: str | None
    claim_scope: dict | None


@dataclass(frozen=True)
class CarbonResult:
    assessment: dict
    adapter: str


@runtime_checkable
class RasterAnalysisPort(Protocol):
    name: str

    def analyse(self, request: RasterRequest) -> RasterResult:
        """Areas, annual stocks, the stock change, per-cell uncertainty, zones, evidence."""


@runtime_checkable
class CarbonAssessmentPort(Protocol):
    name: str

    def assess(self, request: CarbonRequest) -> CarbonResult:
        """Interval, baseline, potential units of the case and the claim comparison."""


@runtime_checkable
class ReportBuilderPort(Protocol):
    name: str

    def build(self, result: dict) -> tuple[dict, str]:
        """The passport as a JSON document and as a self-contained HTML string."""


def describe(port: Any) -> str:
    return getattr(port, "name", type(port).__name__)
