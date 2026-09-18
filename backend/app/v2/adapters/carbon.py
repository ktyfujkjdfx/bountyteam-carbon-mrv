"""The carbon port: interval, baseline, potential units and the claim comparison.

The engine of record is the `carbon/` package owned by Trust. It is imported here whenever
it is importable, and only when it is absent does this module fall back to
`reference_carbon`, which is labelled as a stand-in in the adapter name and in every
result. Both paths run through exactly the same call sequence below, so the fallback
cannot quietly acquire behaviour of its own.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from ..contracts import internal_validator, validate
from ..ports import CarbonRequest, CarbonResult

log = logging.getLogger("backend.lens.carbon")

POOL = "AGB_LIVE_WOODY"
UNIT = "POTENTIAL_UNIT_OF_THE_CASE"
SCHEMA = "carbon.case2.assessment/1"
# RS treats a request as fully covered below this many hectares of gap, because geodesic
# area is not additive over a partition. Passing the raw fraction to an engine that wants
# an exact 1.0 would turn seventh-digit arithmetic into "incomplete coverage".
COMPLETE = 1.0

try:  # pragma: no cover - which branch runs depends on what is merged into the branch
    import carbon as _engine

    ENGINE_NAME = f"carbon/{_engine.METHOD_VERSION}"
    IS_REFERENCE_FALLBACK = False
except ImportError:  # pragma: no cover
    from . import reference_carbon as _engine

    ENGINE_NAME = f"backend-reference/{_engine.METHOD_VERSION}"
    IS_REFERENCE_FALLBACK = True


def engine() -> Any:
    return _engine


def const(api: Any, name: str) -> Any:
    """A status or reason string, wherever the engine keeps it.

    The `carbon` package gathers them in `carbon.reasons`; the reference stand-in keeps
    them at module level. Looking in both is how one call sequence serves both.
    """
    if hasattr(api, name):
        return getattr(api, name)
    reasons = getattr(api, "reasons", None)
    if reasons is not None and hasattr(reasons, name):
        return getattr(reasons, name)
    raise AttributeError(f"the carbon engine does not define {name}")


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _notes(*results: Any) -> list[str]:
    """Flatten whatever note objects the engine attached into plain sentences."""
    collected: list[str] = []
    for result in results:
        for note in getattr(result, "notes", ()) or ():
            text = getattr(note, "text", None) or getattr(note, "message", None)
            if text is None and isinstance(note, dict):
                text = note.get("text") or note.get("message") or note.get("code")
            if text is None:
                text = str(note)
            if text not in collected:
                collected.append(text)
    return collected


def cell_observations(cells: dict, year_start: int, year_end: int):
    """Project the per-cell layer onto the five sequences the interval needs."""
    area, agb_start, agb_end, sd_start, sd_end = [], [], [], [], []
    start, end = str(year_start), str(year_end)
    for feature in cells.get("features", ()):
        properties = feature["properties"]
        if not properties.get("valid", True):
            continue
        agb = properties["agb_t_ha"]
        sd = properties["agb_sd_t_ha"]
        if start not in agb or end not in agb:
            continue
        area.append(float(properties["weight_ha"]))
        agb_start.append(float(agb[start]))
        agb_end.append(float(agb[end]))
        sd_start.append(float(sd.get(start, 0.0)))
        sd_end.append(float(sd.get(end, 0.0)))
    return area, agb_start, agb_end, sd_start, sd_end


def baseline_parts(cells: dict, fallback_parents: list[str], calculated_ha: float):
    """Non-overlapping parts by parent area, from the cell weights that produced the stock.

    Using the cell weights rather than the polygon means a request spanning two supplied
    areas cannot count the same hectare twice: each cell belongs to exactly one parent.
    """
    totals: dict[str, float] = {}
    for feature in cells.get("features", ()):
        properties = feature["properties"]
        if not properties.get("valid", True):
            continue
        parent = properties.get("parent_aoi_id")
        if not parent:
            continue
        totals[parent] = totals.get(parent, 0.0) + float(properties["weight_ha"])
    if not totals and fallback_parents:
        share = calculated_ha / len(fallback_parents)
        totals = {parent: share for parent in fallback_parents}
    return [(parent, totals[parent]) for parent in sorted(totals)]


class CarbonAdapter:
    """Composes the engine's four pure functions; contains no arithmetic of its own."""

    def __init__(self, module: Any | None = None, name: str | None = None):
        self._engine = module or _engine
        self.name = name or ENGINE_NAME

    def assess(self, request: CarbonRequest) -> CarbonResult:
        api = self._engine
        parameters = api.load_parameters()
        raster = request.raster
        coverage = raster["coverage"]

        area, agb_start, agb_end, sd_start, sd_end = cell_observations(
            request.cells, request.year_start, request.year_end)
        if area:
            interval = api.compute_interval(
                api.CellObservations.from_sequences(
                    area_ha=area, agb_start=agb_start, agb_end=agb_end,
                    sd_start=sd_start, sd_end=sd_end),
                year_start=request.year_start, year_end=request.year_end,
                parameters=parameters)
        else:
            # No usable cell is an answer about the inputs, not a crash in the engine.
            interval = api.IntervalResult(const(api, "UNAVAILABLE"),
                                          const(api, "MISSING_INPUT"))

        parts = baseline_parts(request.cells, list(raster["request"]["parents"]),
                               coverage["calculated_ha"])
        baseline = api.compute_baseline(
            [api.BaselinePart(aoi_id=aoi_id, area_ha=area_ha) for aoi_id, area_ha in parts],
            year_start=request.year_start, year_end=request.year_end, parameters=parameters)

        biomass_share = COMPLETE if coverage.get("complete") else \
            min(1.0, max(0.0, float(coverage["biomass"]["fraction"])))
        available = const(api, "AVAILABLE")
        baseline_share = COMPLETE if getattr(baseline, "status", None) == available else 0.0
        units = api.compute_units(
            e_proj_tco2e=getattr(interval, "e_proj_tco2e", None),
            e_base_tco2e=getattr(baseline, "e_base_tco2e", None),
            lower_tco2e=getattr(interval, "lower_tco2e", None),
            upper_tco2e=getattr(interval, "upper_tco2e", None),
            area_ha=getattr(interval, "area_ha", None),
            year_start=request.year_start, year_end=request.year_end,
            coverage=api.Coverage(biomass=biomass_share, baseline=baseline_share),
            parameters=parameters)

        context = api.AnalysisContext(geometry_hash=request.geometry_hash,
                                      year_start=request.year_start, year_end=request.year_end,
                                      pool=POOL, unit=UNIT)
        claim = api.compare_claim(self._claim_input(api, request), analysis=context,
                                  units=units.units, parameters=parameters)

        assessment = {
            "schema": SCHEMA,
            "method_version": getattr(api, "METHOD_VERSION", self.name),
            "parameters": _plain(parameters),
            "interval": _interval_payload(api, interval),
            "baseline": _baseline_payload(api, baseline),
            "units": _units_payload(units),
            "claim": _claim_payload(claim),
            "notes": _notes(interval, baseline, units, claim),
        }
        validate(internal_validator("CarbonAssessment"), assessment, "CarbonAssessment")
        return CarbonResult(assessment=assessment, adapter=self.name)

    @staticmethod
    def _claim_input(api: Any, request: CarbonRequest):
        if request.claimed_units is None:
            return None
        scope = request.claim_scope or {}
        return api.ClaimInput(
            claimed_units=request.claimed_units,
            source=request.claim_origin or const(api, "CLAIM_SOURCE_USER"),
            geometry_hash=scope.get("geometry_hash", request.geometry_hash),
            year_start=int(scope.get("year_start", request.year_start)),
            year_end=int(scope.get("year_end", request.year_end)),
            pool=scope.get("pool", POOL),
            unit=scope.get("unit", UNIT))


def _interval_payload(api: Any, interval: Any) -> dict:
    return {
        "status": interval.status,
        "unavailable_reason": interval.unavailable_reason,
        "lower_tco2e": interval.lower_tco2e,
        "upper_tco2e": interval.upper_tco2e,
        "sd_tco2e": interval.sd_tco2e,
        "interval_kind": _interval_kind(api, interval),
        "method_version": interval.method_version,
        "assumptions": _plain(interval.assumptions),
        "sensitivity": [_plain(variant) for variant in interval.sensitivity],
    }


def _interval_kind(api: Any, interval: Any) -> str:
    """The contract spells the scenario interval `SCENARIO`; an engine may spell it longer."""
    kind = str(getattr(interval, "interval_kind", "SCENARIO")).upper()
    return "PROBABILISTIC" if kind.startswith("PROB") else "SCENARIO"


def _baseline_payload(api: Any, baseline: Any) -> dict:
    return {
        "status": baseline.status,
        "unavailable_reason": baseline.unavailable_reason,
        "baseline_id": baseline.baseline_id,
        "area_ha": baseline.area_ha,
        "delta_tc": baseline.delta_tc,
        "delta_tc_ha": baseline.delta_tc_ha,
        "e_base_tco2e": baseline.e_base_tco2e,
        "parts": [_plain(part) for part in baseline.parts],
    }


def _units_payload(units: Any) -> dict:
    return {
        "status": units.status,
        "unavailable_reason": units.unavailable_reason,
        "zero_reason": units.zero_reason,
        "e_proj_tco2e": units.e_proj_tco2e,
        "e_base_tco2e": units.e_base_tco2e,
        "leakage_tco2e": units.leakage_tco2e,
        "lower_tco2e": units.lower_tco2e,
        "upper_tco2e": units.upper_tco2e,
        "h_tco2e": units.h_tco2e,
        "r_tco2e": units.r_tco2e,
        "ratio": units.ratio,
        "uncertainty_share": units.uncertainty_share,
        "uncertainty_deduction_tco2e": units.uncertainty_deduction_tco2e,
        "r_adj_tco2e": units.r_adj_tco2e,
        "buffer_tco2e": units.buffer_tco2e,
        "units": units.units,
        "rounding_residual_tco2e": units.rounding_residual_tco2e,
        "scenario_values": [_plain(value) for value in units.scenario_values],
        "method_version": units.method_version,
    }


def _claim_payload(claim: Any) -> dict:
    return {
        "status": claim.status,
        "mismatch_reasons": list(claim.mismatch_reasons),
        "claimed_units": claim.claimed_units,
        "source": claim.source,
        "units": claim.units,
        "gap_units": claim.gap_units,
        "supported_share": claim.supported_share,
        "gap_values": [_plain(value) for value in claim.gap_values],
    }
