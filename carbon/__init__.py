"""Carbon Lens engine: stock difference, scenario interval, baseline, units, claim.

Pure functions over typed inputs. The package computes numbers and states their limits;
it performs no I/O beyond reading the official CSV tables of data/methodology/, and it
imports no HTTP, web framework, database or chain library.
"""
from __future__ import annotations

from . import notes, reasons
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
from .interval import (
    FULLY_DEPENDENT_CELLS,
    INDEPENDENT_CELLS,
    CellObservations,
    IntervalResult,
    IntervalVariant,
    compute_interval,
)
from .parameters import DEFAULT_PARAMETERS, METHOD_VERSION, CaseParameters, load_parameters
from .units import Coverage, ScenarioValue, UnitsResult, compute_units

__all__ = [
    "AnalysisContext",
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
    "FULLY_DEPENDENT_CELLS",
    "INDEPENDENT_CELLS",
    "IntervalResult",
    "IntervalVariant",
    "METHOD_VERSION",
    "ScenarioValue",
    "UnitsResult",
    "baseline_stock",
    "compare_claim",
    "compute_baseline",
    "compute_interval",
    "compute_units",
    "load_baseline_table",
    "load_parameters",
    "notes",
    "reasons",
]
