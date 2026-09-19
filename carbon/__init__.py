"""Carbon Lens engine: stock difference, scenario interval, baseline, units, claim, passport.

Pure functions over typed inputs. The package computes numbers and states their limits;
it performs no I/O beyond reading the official tables of `data/`, and it imports no HTTP,
web framework, database or chain library.

`analyse` composes one full result, `build_passport` seals it into a canonical hashable
record, `build_manifest`/`verify` establish that published bytes are the sealed bytes, and
`research_rows` shows how the answer moves when the signed assumptions move.
"""
from __future__ import annotations

from . import canonical, notes, reasons
from .analysis import (
    Analysis,
    AnalysisRequest,
    AreaCoverage,
    MethodOptions,
    TimelinePoint,
    analyse,
    geometry_hash,
)
from .baseline import (
    BaselinePart,
    BaselinePartResult,
    BaselineResult,
    BaselineRow,
    baseline_stock,
    compute_baseline,
    load_baseline_table,
)
from .claim import AnalysisContext, ClaimInput, ClaimResult, compare_claim
from .integrity import (
    ArtifactRecord,
    IntegrityReport,
    build_manifest,
    describe,
    manifest_hash,
    verify,
)
from .interval import (
    FULL_SPATIAL_CORRELATION,
    INDEPENDENT_NATIVE_CELLS,
    CellObservations,
    IntervalResult,
    IntervalVariant,
    compute_interval,
)
from .parameters import DEFAULT_PARAMETERS, METHOD_VERSION, CaseParameters, load_parameters
from .passport import Passport, PassportEnvelope, build_passport, link_versions, seal
from .projection import (
    OBSERVED,
    SCENARIO_PROJECTION,
    ProjectionPoint,
    ProjectionResult,
    project_baseline,
)
from .provenance import build_provenance, parameters_snapshot, verify_files
from .report import build_report, render_html
from .research import ResearchRow, research_rows, research_table
from .risk import Risk, RiskReport, assess_risks
from .rs_adapter import RasterInputs, RsPayloadError, from_fixture, from_rs_payload
from .units import Coverage, ScenarioValue, UnitsResult, compute_units
from .workflow import (
    Actor,
    Lifecycle,
    WorkflowError,
    opaque_actor_ref,
    passport_workflow_block,
)
from .value import (
    OFFICIAL_CASE_PRICE,
    USER_SCENARIO,
    PriceScenario,
    ScenarioValuation,
    ValueResult,
    official_prices,
    scenario_values,
    user_price,
)

__all__ = [
    "METHOD_VERSION",
    "Actor",
    "Analysis",
    "AnalysisContext",
    "AnalysisRequest",
    "AreaCoverage",
    "ArtifactRecord",
    "BaselinePart",
    "BaselinePartResult",
    "BaselineResult",
    "BaselineRow",
    "CaseParameters",
    "CellObservations",
    "ClaimInput",
    "ClaimResult",
    "Coverage",
    "DEFAULT_PARAMETERS",
    "FULL_SPATIAL_CORRELATION",
    "INDEPENDENT_NATIVE_CELLS",
    "IntegrityReport",
    "IntervalResult",
    "IntervalVariant",
    "Lifecycle",
    "MethodOptions",
    "OBSERVED",
    "OFFICIAL_CASE_PRICE",
    "Passport",
    "PriceScenario",
    "PassportEnvelope",
    "ProjectionPoint",
    "ProjectionResult",
    "RasterInputs",
    "ResearchRow",
    "Risk",
    "RiskReport",
    "RsPayloadError",
    "SCENARIO_PROJECTION",
    "ScenarioValuation",
    "ScenarioValue",
    "TimelinePoint",
    "USER_SCENARIO",
    "UnitsResult",
    "ValueResult",
    "WorkflowError",
    "analyse",
    "assess_risks",
    "baseline_stock",
    "build_manifest",
    "build_passport",
    "build_provenance",
    "build_report",
    "canonical",
    "compare_claim",
    "compute_baseline",
    "compute_interval",
    "compute_units",
    "describe",
    "from_fixture",
    "from_rs_payload",
    "geometry_hash",
    "link_versions",
    "load_baseline_table",
    "load_parameters",
    "manifest_hash",
    "notes",
    "official_prices",
    "opaque_actor_ref",
    "passport_workflow_block",
    "parameters_snapshot",
    "project_baseline",
    "reasons",
    "render_html",
    "scenario_values",
    "research_rows",
    "research_table",
    "seal",
    "verify",
    "user_price",
    "verify_files",
]
