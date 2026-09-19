"""Stock difference and the scenario interval of the result.

Formulas (Постановка задачи, с. 4–5):

    c_i,t = b_i,t × CF;  C_t = Σ a_i × c_i,t;  c̄_t = C_t / A
    ΔC = C_t1 − C_t0;  E = −ΔC × 44/12;  e = E / (A × Δt)

Positive E means a loss from the accounted pool, negative means accumulation.

The interval is scenario-based (Team Lead decision). Per-cell error propagation:

    var(Δb_i) = s0_i² + s1_i² − 2 ρ_t s0_i s1_i
    independent cells:     sd(E) = sqrt(Σ (w_i sd_i)²)
    fully dependent cells:  sd(E) = Σ w_i sd_i          (mandatory sensitivity)
    w_i = a_i × CF × 44/12
    L = E − k sd(E);  U = E + k sd(E)

The main mode is independent native CCI cells with ρ_t as an explicit signed scenario
assumption; ρ_t is not an empirical calibration. Errors are summed with area weights,
never divided by sqrt(N).
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from . import notes, reasons
from .parameters import DEFAULT_PARAMETERS, METHOD_VERSION, CaseParameters

INDEPENDENT_NATIVE_CELLS = "INDEPENDENT_NATIVE_CELLS"
FULL_SPATIAL_CORRELATION = "FULL_SPATIAL_CORRELATION"
SPATIAL_MODES = (INDEPENDENT_NATIVE_CELLS, FULL_SPATIAL_CORRELATION)
SENSITIVITY_TEMPORAL_CORRELATIONS = (0.0, 1.0)
INTERVAL_KIND = "SCENARIO"


@dataclass(frozen=True)
class CellObservations:
    """Per-cell payload from RS on the native CCI grid, in t dry matter/ha and ha."""

    area_ha: np.ndarray
    agb_start: np.ndarray
    agb_end: np.ndarray
    sd_start: np.ndarray
    sd_end: np.ndarray

    @classmethod
    def from_sequences(
        cls,
        *,
        area_ha: Sequence[float],
        agb_start: Sequence[float],
        agb_end: Sequence[float],
        sd_start: Sequence[float],
        sd_end: Sequence[float],
    ) -> "CellObservations":
        arrays = tuple(
            np.asarray(values, dtype=float)
            for values in (area_ha, agb_start, agb_end, sd_start, sd_end)
        )
        if any(array.ndim != 1 for array in arrays):
            raise ValueError("per-cell inputs must be one-dimensional")
        if len({array.size for array in arrays}) != 1:
            raise ValueError("per-cell inputs must have the same length")
        if arrays[0].size == 0:
            raise ValueError("at least one cell is required")
        return cls(*arrays)

    @property
    def count(self) -> int:
        return int(self.area_ha.size)


@dataclass(frozen=True)
class IntervalVariant:
    label: str
    spatial_dependence: str
    temporal_correlation: float
    sd_tco2e: float
    lower_tco2e: float
    upper_tco2e: float
    half_width_tco2e: float


@dataclass(frozen=True)
class IntervalResult:
    status: str
    unavailable_reason: str | None = None
    area_ha: float | None = None
    cells: int | None = None
    years: tuple[int, int] | None = None
    stock_start_tc: float | None = None
    stock_end_tc: float | None = None
    mean_start_tc_ha: float | None = None
    mean_end_tc_ha: float | None = None
    delta_stock_tc: float | None = None
    e_proj_tco2e: float | None = None
    e_per_ha_year_tco2e: float | None = None
    sd_tco2e: float | None = None
    lower_tco2e: float | None = None
    upper_tco2e: float | None = None
    interval_kind: str = INTERVAL_KIND
    method_version: str = METHOD_VERSION
    assumptions: dict[str, object] = field(default_factory=dict)
    sensitivity: tuple[IntervalVariant, ...] = ()
    notes: tuple[notes.Note, ...] = ()


def _variant(
    *,
    spatial_dependence: str,
    temporal_correlation: float,
    weights: np.ndarray,
    sd_start: np.ndarray,
    sd_end: np.ndarray,
    estimate: float,
    coverage_factor: float,
) -> IntervalVariant:
    variance = sd_start**2 + sd_end**2 - 2 * temporal_correlation * sd_start * sd_end
    cell_sd = np.sqrt(np.clip(variance, 0.0, None))
    scaled = weights * cell_sd
    if spatial_dependence == INDEPENDENT_NATIVE_CELLS:
        sd_total = float(math.sqrt(float(np.sum(scaled**2))))
    else:
        sd_total = float(np.sum(scaled))
    half_width = coverage_factor * sd_total
    return IntervalVariant(
        label=f"{spatial_dependence}_RHO_{temporal_correlation:g}",
        spatial_dependence=spatial_dependence,
        temporal_correlation=float(temporal_correlation),
        sd_tco2e=sd_total,
        lower_tco2e=estimate - half_width,
        upper_tco2e=estimate + half_width,
        half_width_tco2e=half_width,
    )


def compute_interval(
    cells: CellObservations,
    *,
    year_start: int,
    year_end: int,
    parameters: CaseParameters = DEFAULT_PARAMETERS,
    temporal_correlation: float = 0.0,
    coverage_factor: float = 1.0,
    spatial_dependence: str = INDEPENDENT_NATIVE_CELLS,
) -> IntervalResult:
    """Stock difference with a scenario interval and its mandatory sensitivity table."""
    if not -1.0 <= temporal_correlation <= 1.0:
        raise ValueError("temporal_correlation must lie in [-1, 1]")
    if coverage_factor <= 0.0:
        raise ValueError("coverage_factor must be positive")
    if spatial_dependence not in SPATIAL_MODES:
        raise ValueError(f"spatial_dependence must be one of {SPATIAL_MODES}")

    if year_end <= year_start:
        return IntervalResult(reasons.UNAVAILABLE, reasons.NON_POSITIVE_PERIOD)

    values = (cells.area_ha, cells.agb_start, cells.agb_end, cells.sd_start, cells.sd_end)
    if not all(bool(np.all(np.isfinite(array))) for array in values):
        return IntervalResult(reasons.UNAVAILABLE, reasons.NON_FINITE_INPUT)
    if bool(np.any(cells.area_ha < 0.0)) or float(np.sum(cells.area_ha)) <= 0.0:
        return IntervalResult(reasons.UNAVAILABLE, reasons.NON_POSITIVE_AREA)
    if bool(np.any(cells.sd_start < 0.0)) or bool(np.any(cells.sd_end < 0.0)):
        return IntervalResult(reasons.UNAVAILABLE, reasons.INVALID_UNCERTAINTY_INPUT)

    area_total = float(np.sum(cells.area_ha))
    span_years = year_end - year_start
    carbon_start = cells.agb_start * parameters.cf_agb
    carbon_end = cells.agb_end * parameters.cf_agb
    stock_start = float(np.sum(cells.area_ha * carbon_start))
    stock_end = float(np.sum(cells.area_ha * carbon_end))
    delta_stock = stock_end - stock_start
    estimate = -delta_stock * parameters.co2_per_c

    weights = cells.area_ha * parameters.cf_agb * parameters.co2_per_c
    main = _variant(
        spatial_dependence=spatial_dependence,
        temporal_correlation=temporal_correlation,
        weights=weights,
        sd_start=cells.sd_start,
        sd_end=cells.sd_end,
        estimate=estimate,
        coverage_factor=coverage_factor,
    )
    grid = tuple(
        _variant(
            spatial_dependence=mode,
            temporal_correlation=rho,
            weights=weights,
            sd_start=cells.sd_start,
            sd_end=cells.sd_end,
            estimate=estimate,
            coverage_factor=coverage_factor,
        )
        for mode in SPATIAL_MODES
        for rho in SENSITIVITY_TEMPORAL_CORRELATIONS
    )

    return IntervalResult(
        status=reasons.AVAILABLE,
        area_ha=area_total,
        cells=cells.count,
        years=(year_start, year_end),
        stock_start_tc=stock_start,
        stock_end_tc=stock_end,
        mean_start_tc_ha=stock_start / area_total,
        mean_end_tc_ha=stock_end / area_total,
        delta_stock_tc=delta_stock,
        e_proj_tco2e=estimate,
        e_per_ha_year_tco2e=estimate / (area_total * span_years),
        sd_tco2e=main.sd_tco2e,
        lower_tco2e=main.lower_tco2e,
        upper_tco2e=main.upper_tco2e,
        assumptions={
            "spatial_dependence": spatial_dependence,
            "temporal_correlation": float(temporal_correlation),
            "coverage_factor": float(coverage_factor),
            "cells": cells.count,
            "grid": "native CCI cells",
            "pool": "AGB",
            "cf_agb": parameters.cf_agb,
            "co2_per_c": parameters.co2_per_c,
            "empirically_calibrated": False,
        },
        sensitivity=grid,
        notes=(notes.note(notes.SCENARIO_INTERVAL), notes.note(notes.POOL_LIMITED)),
    )
