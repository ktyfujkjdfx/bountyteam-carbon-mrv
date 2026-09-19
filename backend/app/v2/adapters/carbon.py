"""The carbon port: interval, baseline, potential units and the claim comparison.

The engine of record is the `carbon/` package owned by Trust, and it is the only engine
this module will load. There is no fallback: if `carbon` is not importable the port
reports itself unavailable and every analysis fails closed, because a number produced by
a stand-in and a number produced by the engine would be indistinguishable to the reader
of a passport.

A test may inject a different module through `CarbonAdapter(module=...)`. That is how the
suite runs before `carbon/` is merged, and it is deliberately the only way: nothing in
`backend/app/` can reach a second implementation of these formulas.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from ..contracts import internal_validator, validate
from ..ports import CarbonRequest, CarbonResult

log = logging.getLogger("backend.lens.carbon")

# The pool and unit strings are the ones the carbon engine emits. They are compared for
# string equality when a claim is checked for comparability, so a second spelling on this
# side would manufacture a POOL_MISMATCH out of nothing.
POOL = "AGB_LIVE_WOODY"
UNIT = "POTENTIAL_UNIT_OF_THE_CASE"
SCHEMA = "carbon.case2.assessment/1"
# RS treats a request as fully covered below this many hectares of gap, because geodesic
# area is not additive over a partition. Passing the raw fraction to an engine that wants
# an exact 1.0 would turn seventh-digit arithmetic into "incomplete coverage".
COMPLETE = 1.0

# The method freeze names the two spatial scenarios; an engine may spell them its own way.
# Translating names is the adapter's job and changes no number.
SPATIAL_NAMES = {
    "INDEPENDENT_CELLS": "INDEPENDENT_NATIVE_CELLS",
    "INDEPENDENT_NATIVE_CELLS": "INDEPENDENT_NATIVE_CELLS",
    "FULLY_DEPENDENT_CELLS": "FULL_SPATIAL_CORRELATION",
    "FULL_SPATIAL_CORRELATION": "FULL_SPATIAL_CORRELATION",
}
CLAIM_NOT_APPLICABLE = "NOT_APPLICABLE"
NO_POSITIVE_CLAIM = "NO_POSITIVE_CLAIM"


def _attr(value: Any, *names: str, default: Any = None) -> Any:
    """The first of these attributes the engine actually has.

    Field names on the engine's result objects are its own to choose. Reading several
    spellings here is what lets a rename land on one side without breaking the other in
    the same commit, and it changes no number.
    """
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default

try:  # pragma: no cover - depends on what is merged into the branch
    import carbon as _engine

    CARBON_AVAILABLE = True
    ENGINE_NAME = f"carbon/{_engine.METHOD_VERSION}"
except ImportError:  # pragma: no cover
    _engine = None
    CARBON_AVAILABLE = False
    ENGINE_NAME = ""


class CarbonEngineUnavailable(RuntimeError):
    """The carbon engine is not installed on this deployment. No number is invented."""


def engine() -> Any:
    if _engine is None:  # pragma: no cover - exercised by the fail-closed tests
        raise CarbonEngineUnavailable(
            "the carbon engine is not available on this deployment")
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
        self._engine = module if module is not None else engine()
        self.name = name or ENGINE_NAME or getattr(
            self._engine, "METHOD_VERSION", type(self._engine).__name__)

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
            "baseline": _baseline_payload(api, baseline, curve=baseline_curve(
                api, parts, [entry["year"] for entry in raster["timeline"]])),
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


def spatial_name(value: Any) -> str:
    """The freeze name of a spatial scenario. An unknown spelling is not invented over."""
    key = str(value or "").upper()
    if key not in SPATIAL_NAMES:
        raise ValueError(f"unknown spatial dependence {value!r}")
    return SPATIAL_NAMES[key]


def _interval_payload(api: Any, interval: Any) -> dict:
    assumptions = _plain(interval.assumptions) or {}
    if assumptions.get("spatial_dependence"):
        assumptions["spatial_dependence"] = spatial_name(assumptions["spatial_dependence"])
    variants = []
    for variant in interval.sensitivity:
        plain = _plain(variant)
        engine_name = str(plain["spatial_dependence"])
        plain["spatial_dependence"] = spatial_name(engine_name)
        plain["label"] = str(plain["label"]).replace(
            engine_name, plain["spatial_dependence"], 1)
        variants.append(plain)
    return {
        "status": interval.status,
        "unavailable_reason": interval.unavailable_reason,
        "lower_tco2e": interval.lower_tco2e,
        "upper_tco2e": interval.upper_tco2e,
        "sd_tco2e": interval.sd_tco2e,
        "interval_kind": _interval_kind(api, interval),
        "method_version": interval.method_version,
        "assumptions": assumptions,
        "sensitivity": variants,
    }


def _interval_kind(api: Any, interval: Any) -> str:
    """The contract spells the scenario interval `SCENARIO`; an engine may spell it longer."""
    kind = str(getattr(interval, "interval_kind", "SCENARIO")).upper()
    return "PROBABILISTIC" if kind.startswith("PROB") else "SCENARIO"


def baseline_curve(api: Any, parts: list[tuple[str, float]],
                   years: list[int]) -> dict[str, float | None]:
    """The area-weighted baseline stock per year, from the engine's own trajectory.

    The timeline draws a baseline line beside the observed one. The shape of that line is
    the engine's, so it is asked for here rather than reconstructed while assembling the
    response.
    """
    if not hasattr(api, "baseline_stock"):
        return {str(year): None for year in years}
    rows = _baseline_rows(api)
    curve: dict[str, float | None] = {}
    for year in years:
        weighted, covered = 0.0, 0.0
        for aoi_id, area_ha in parts:
            row = rows.get(aoi_id)
            if row is None:
                continue
            weighted += area_ha * api.baseline_stock(
                reference_2019_tc_ha=row[0], rate_tc_ha_yr=row[1], year=year)
            covered += area_ha
        curve[str(year)] = weighted / covered if covered > 0.0 else None
    return curve


def _baseline_rows(api: Any) -> dict[str, tuple[float, float]]:
    if hasattr(api, "baseline_rows"):
        return {aoi: (row.reference_mean_2019_tc_ha, row.historical_rate_tc_ha_yr)
                for aoi, row in api.baseline_rows().items()}
    table = api.load_baseline_table()
    return {aoi: (rows[0].reference_mean_2019_tc_ha, rows[0].historical_rate_tc_ha_yr)
            for aoi, rows in table.items() if rows}


def _baseline_payload(api: Any, baseline: Any, *, curve: dict) -> dict:
    return {
        "curve_tc_ha": curve,
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
    payload = {
        "status": claim.status,
        "reason": _attr(claim, "reason"),
        "mismatch_reasons": list(claim.mismatch_reasons),
        "claimed_units": claim.claimed_units,
        "source": claim.source,
        "units": claim.units,
        "unsupported_gap": _attr(claim, "unsupported_gap", "gap_units"),
        "supported_share": claim.supported_share,
        "gap_values": [_plain(value) for value in claim.gap_values],
    }
    return no_positive_claim(payload)


def no_positive_claim(payload: dict) -> dict:
    """A claim of zero is not a supported claim.

    Nothing positive was stated, so nothing was supported and there is no share to report.
    This is a vocabulary rule of the contract rather than a calculation, and it is applied
    here so that an engine which has not yet adopted `NOT_APPLICABLE` cannot publish a
    zero claim as `SUPPORTED_BY_CASE`.
    """
    claimed = payload.get("claimed_units")
    if claimed is None or float(claimed) != 0.0:
        return payload
    payload.update({
        "status": CLAIM_NOT_APPLICABLE,
        # Its own field, not a mismatch. Nothing disagreed; there was nothing to compare.
        "reason": NO_POSITIVE_CLAIM,
        "supported_share": None,
        "unsupported_gap": 0.0,
        "gap_values": [],
    })
    return payload
