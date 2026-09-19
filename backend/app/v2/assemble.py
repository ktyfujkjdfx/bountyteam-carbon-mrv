"""Assembling the public result from what the two computation owners returned.

Every number here is copied. This module decides names, nullability, ordering and which
hash covers what; it decides nothing scientific. If a value is not in the raster payload
or in the carbon assessment, it is `null` with a reason, never a value this module
reconstructed because it seemed reasonable.

Two hashes and one timestamp, deliberately separated:

- `passport.content_hash` covers the scientific content only. The run id, the analysis id,
  the run time and every URL are outside it, so the same request replayed next week on
  another machine produces the same hash, and a reader can tell a genuine replay from a
  coincidence.
- `passport.report_hash` identifies the report by its content, not by its rendering, so
  the HTML can print the hash it is identified by without the reference becoming circular.
- `run.created_at` is when this execution happened, and it is in neither hash.
"""
from __future__ import annotations

from typing import Any

from . import catalog
from .adapters import carbon as carbon_adapter
from .contracts import BACKEND_METHOD_VERSION, SCHEMA_VERSION, digest
from .report import REPORT_SCHEMA_VERSION

POOL = carbon_adapter.POOL
UNIT = carbon_adapter.UNIT
SIGN_CONVENTION = "POSITIVE_E_MEANS_POOL_LOSS"
COMPARISON_SCOPE = "geometry_hash+year_start+year_end+pool+method_version"
PRICE_KEYS = ("low", "base", "high")
PRICE_REF = "data/methodology/parameters.csv#price_low,price_base,price_high"

# The keys are the role names the raster owner writes into its manifest. A role that is
# not mapped here means a product was used and not credited, so an unmapped role is a
# blocking warning rather than a silently shorter source list.
ROLE_TO_SOURCE = {
    "biomass": "CCI_V7",
    "cci_biomass": "CCI_V7",
    "cci_cell_layer": "CCI_V7",
    "sentinel2_reflectance": "S2_L2A",
    "sentinel2_scl": "S2_L2A",
    "sentinel2:reflectance_path": "S2_L2A",
    "sentinel2:scl_path": "S2_L2A",
    "gfc": "GFC_2025_V113",
    "gfc_lossyear": "GFC_2025_V113",
    "modis_burn": "MODIS_MCD64A1_061",
    "modis_burn_date": "MODIS_MCD64A1_061",
    "table": "CASE_RULES_V1",
    "case_table": "CASE_RULES_V1",
}
ALWAYS_CITED = ("IPCC_FOREST_2006", "IPCC_GENERIC_2006", "CASE_RULES_V1")

BASE_LIMITATIONS = (
    ("POOL_SCOPE",
     "Учитывается только живая надземная древесная биомасса; это не полный баланс "
     "экосистемы."),
    ("SIGN_CONVENTION",
     "Положительное E — потеря учитываемого пула за период, а не мгновенный выброс всего "
     "углерода в атмосферу."),
    ("BASELINE_IS_A_SCENARIO",
     "Базовая линия задана сценарными правилами кейса по истории 2015–2019; она не "
     "доказывает дополнительность и не описывает действия владельца участка."),
    ("SCENARIO_VALUE_ONLY",
     "Сценарная стоимость использует заданные кейсом цены. Это не рыночная котировка, не "
     "установленный ущерб и не гарантированная выручка."),
)
STUB_LIMITATION = (
    "STUB_FIXTURE",
    "Растровые значения получены из размеченного вектора-заглушки, а не измерены по "
    "предоставленным растрам. Результат демонстрирует формат и правила, а не состояние "
    "участка.",
)
RASTER_LIMITATION = "RASTER_LIMITATION"

CLAIM_SCOPE_NOTE = (
    "Сравнение возможно только при совпадении контура, периода, пула и единиц. "
    "Заявленный объём — пользовательский или демонстрационный ввод, а не установленный факт."
)


def _number(value: Any) -> float:
    """The unclamped value as the owning component reported it."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number == number and abs(number) != float("inf") else 0.0


def _fraction(value: Any) -> float:
    """The public share. Geodesic arithmetic can land a hair outside [0, 1]; the raw
    value is published beside this one rather than being lost to the clamp."""
    return min(1.0, max(0.0, _number(value)))


def warning(code: str, message: str, severity: str = "WARNING", **details: Any) -> dict:
    return {"code": code, "severity": severity, "message": message, "details": details}


def limitation(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def identity(*, analysis_id: str, input_hash: str, geometry_hash: str, raster: dict,
             carbon: dict, manifest: dict) -> dict:
    method = "+".join(part for part in (
        BACKEND_METHOD_VERSION,
        raster["parameters"].get("method_version") or manifest.get("method_version"),
        carbon["method_version"]) if part)
    return {
        "analysis_id": analysis_id,
        "input_hash": input_hash,
        "geometry_hash": geometry_hash,
        "schema_version": SCHEMA_VERSION,
        "method_version": method,
        "dataset_version": catalog.DATASET_VERSION,
        "dataset_hash": catalog.dataset_hash(),
        "source_manifest_hash": catalog.source_manifest_hash(
            list(manifest["dataset"]["files"])),
        "parameters_hash": catalog.parameters_hash(),
        "code_sha": manifest.get("code_commit"),
    }


def areas_block(raster: dict, cells: dict) -> dict:
    coverage = raster["coverage"]
    parts = carbon_adapter.baseline_parts(cells, list(raster["request"]["parents"]),
                                          coverage["calculated_ha"])
    requested = _number(coverage["requested_ha"])
    calculated = _number(coverage["calculated_ha"])
    return {
        "requested_ha": coverage["requested_ha"],
        "calculated_ha": coverage["calculated_ha"],
        # Two different questions: how much was not covered, and how far the two geodesic
        # sums are apart. The first is never negative; the second keeps its sign.
        "missing_ha": max(0.0, requested - calculated),
        "area_difference_ha": calculated - requested,
        "complete": bool(coverage["complete"]),
        "parent_parts": [{"aoi_id": aoi_id, "area_ha": area_ha} for aoi_id, area_ha in parts],
    }


def coverage_block(raster: dict, baseline: dict) -> dict:
    coverage = raster["coverage"]
    requested = coverage["requested_ha"] or 0.0
    baseline_area = baseline.get("area_ha") or 0.0
    raw = {
        "biomass": _number(coverage["biomass"]["fraction"]),
        "uncertainty": _number(coverage["biomass_sd"]["fraction"]),
        "baseline": _number(baseline_area / requested) if requested else 0.0,
        "optical_paired_valid": _number(coverage["optical_paired"]["fraction"]),
    }
    return {
        "biomass_fraction": _fraction(raw["biomass"]),
        "uncertainty_fraction": _fraction(raw["uncertainty"]),
        "baseline_fraction": _fraction(raw["baseline"]),
        "optical_paired_valid_fraction": _fraction(raw["optical_paired_valid"]),
        "coverage_fraction_raw": raw,
    }


def timeline_block(raster: dict, curve: dict) -> list[dict]:
    """The observed stock per year, beside the baseline trajectory the engine supplied.

    The baseline line is the engine's own; this module places it on the timeline and does
    not recompute its shape.
    """
    cf = float(raster["parameters"].get("carbon_fraction") or 0.0)
    year_start, year_end = raster["request"]["year_start"], raster["request"]["year_end"]
    entries = list(raster["timeline"])
    requested = raster["coverage"]["requested_ha"] or 0.0
    out = []
    for entry in entries:
        mean_agb = entry.get("mean_agb_t_ha")
        if mean_agb is None and cf:
            mean_agb = entry["mean_tc_ha"] / cf
        out.append({
            "year": entry["year"],
            "mean_agb_tdm_ha": mean_agb,
            "mean_carbon_tc_ha": entry["mean_tc_ha"],
            "total_carbon_tc": entry["total_tc"],
            "baseline_carbon_tc_ha": curve.get(str(entry["year"])),
            "area_ha": entry["covered_ha"],
            "coverage": _fraction(entry["covered_ha"] / requested) if requested else 0.0,
            "in_period": year_start <= entry["year"] <= year_end,
            "source_ref": "CCI_V7",
        })
    return out


def change_block(raster: dict, eproj_tco2e: float | None) -> dict:
    """Stocks and their difference. The emission figure itself lives in `units` only.

    The raster owner also computes an emission from the same stocks; publishing both
    would give a reader two numbers for one quantity. The canonical one is the carbon
    engine's, this block points at it, and `eproj_disagreement` below checks that the two
    derivations still agree.
    """
    change = raster["stock_change"]
    request = raster["request"]
    area = change["normalisation_area_ha"]
    span = request["year_end"] - request["year_start"]
    intensity = None
    if eproj_tco2e is not None and area and span > 0:
        intensity = eproj_tco2e / (area * span)
    return {
        "year_start": request["year_start"],
        "year_end": request["year_end"],
        "mean_carbon_start_tc_ha": (change["stock_start_tc"] / area) if area else None,
        "mean_carbon_end_tc_ha": (change["stock_end_tc"] / area) if area else None,
        "total_carbon_start_tc": change["stock_start_tc"],
        "total_carbon_end_tc": change["stock_end_tc"],
        "delta_carbon_tc": change["delta_tc"],
        "eproj_ref": "units.eproj_tco2e",
        "eproj_tco2e_ha_year": intensity,
        "normalisation_area_ha": area,
        "sign_convention": SIGN_CONVENTION,
        "pool": POOL,
    }


def eproj_disagreement(raster: dict, eproj_tco2e: float | None) -> dict | None:
    """Do the two independent derivations of Eproj still describe the same quantity?

    They are computed by different owners from the same stocks, so they should agree to
    floating-point noise. A real disagreement is reported, never averaged away.
    """
    other = raster.get("stock_change", {}).get("e_tco2e")
    if eproj_tco2e is None or other is None:
        return None
    scale = max(abs(float(other)), abs(float(eproj_tco2e)), 1.0)
    difference = abs(float(other) - float(eproj_tco2e))
    if difference / scale <= 1e-9:
        return None
    return warning(
        "EPROJ_DISAGREEMENT",
        "Растровое ядро и углеродный движок дали разные значения Eproj из одних и тех же "
        "запасов; опубликовано значение движка, расхождение показано как есть.",
        "BLOCKING", raster_tco2e=float(other), carbon_tco2e=float(eproj_tco2e),
        difference_tco2e=difference)


def uncertainty_block(interval: dict) -> dict:
    assumptions = dict(interval["assumptions"])
    return {
        "status": interval["status"],
        "unavailable_reason": interval["unavailable_reason"],
        "lower_tco2e": interval["lower_tco2e"],
        "upper_tco2e": interval["upper_tco2e"],
        "sd_tco2e": interval["sd_tco2e"],
        "method": str(assumptions.get("spatial_dependence", "UNSPECIFIED")),
        "interval_kind": interval["interval_kind"],
        "assumptions": assumptions,
        "sensitivity": list(interval["sensitivity"]),
    }


def baseline_block(baseline: dict) -> dict:
    return {
        "status": baseline["status"],
        "unavailable_reason": baseline["unavailable_reason"],
        "baseline_id": baseline["baseline_id"],
        "kind": "сценарное допущение кейса по истории 2015–2019",
        "area_ha": baseline["area_ha"],
        "delta_tc": baseline["delta_tc"],
        "delta_tc_ha": baseline["delta_tc_ha"],
        "ebase_tco2e": baseline["e_base_tco2e"],
        "parts": [{
            "aoi_id": part["aoi_id"], "area_ha": part["area_ha"],
            "stock_start_tc_ha": part["stock_start_tc_ha"],
            "stock_end_tc_ha": part["stock_end_tc_ha"],
            "delta_tc_ha": part["delta_tc_ha"], "delta_tc": part["delta_tc"],
            "clipped_at_zero": bool(part["clipped_at_zero"]),
        } for part in baseline["parts"]],
    }


def units_block(units: dict) -> dict:
    reasons = [code for code in (units["unavailable_reason"], units["zero_reason"]) if code]
    return {
        "status": units["status"],
        "unavailable_reason": units["unavailable_reason"],
        "zero_reason": units["zero_reason"],
        "eproj_tco2e": units["e_proj_tco2e"],
        "ebase_tco2e": units["e_base_tco2e"],
        "lk_tco2e": units["leakage_tco2e"],
        "lower_tco2e": units["lower_tco2e"],
        "upper_tco2e": units["upper_tco2e"],
        "h_tco2e": units["h_tco2e"],
        "r_tco2e": units["r_tco2e"],
        "ratio": units["ratio"],
        "unc": units["uncertainty_share"],
        "uncertainty_deduction_tco2e": units["uncertainty_deduction_tco2e"],
        "radj_tco2e": units["r_adj_tco2e"],
        "buffer_tco2e": units["buffer_tco2e"],
        "rounding_residual_tco2e": units["rounding_residual_tco2e"],
        "q": units["units"],
        "reason_codes": reasons,
    }


def _values(entries: list[dict], key: str) -> dict:
    """Three scenario prices in the order the parameter table lists them."""
    block = {"price_parameters_ref": PRICE_REF, "unit": "RUB",
             "low": None, "base": None, "high": None}
    for name, entry in zip(PRICE_KEYS, entries):
        block[name] = {"price_rub": entry["price_rub"], "value_rub": entry[key]}
    return block


def scenario_values_block(units: dict) -> dict:
    if units["units"] is None:
        return {"price_parameters_ref": PRICE_REF, "unit": "RUB",
                "low": None, "base": None, "high": None}
    return _values(list(units["scenario_values"]), "value_rub")


def claim_block(claim: dict, *, geometry_hash: str, year_start: int, year_end: int,
                scope: dict | None) -> dict:
    # A claim of zero is NOT_APPLICABLE and deliberately not in this list: nothing
    # positive was stated, so nothing was compared.
    comparable = claim["status"] in (
        "SUPPORTED_BY_CASE", "PARTIALLY_SUPPORTED_BY_CASE", "NOT_SUPPORTED_BY_CASE",
        "UNASSESSABLE")
    gap_values = None
    if claim["gap_values"]:
        gap_values = _values(list(claim["gap_values"]), "value_rub")
    return {
        "status": claim["status"],
        "origin": claim["source"],
        "comparable": comparable,
        "claimed_units": claim["claimed_units"],
        "q": claim["units"],
        "reason": claim.get("reason"),
        "unsupported_gap": claim["unsupported_gap"],
        "supported_share": claim["supported_share"],
        "mismatch_reasons": list(claim["mismatch_reasons"]),
        "scope": scope or {"geometry_hash": geometry_hash, "year_start": year_start,
                           "year_end": year_end, "pool": POOL, "unit": UNIT},
        "scenario_gap_values": gap_values,
        "scope_note": CLAIM_SCOPE_NOTE,
    }


def _fire_window(aoi_id: str | None) -> dict | None:
    if not aoi_id:
        return None
    for row in catalog.events():
        if row["aoi_id"] == aoi_id:
            return {
                "start": row["date_min_product"], "end": row["date_max_product"],
                "uncertainty_days_min": int(row["date_uncertainty_days_min"] or 0),
                "uncertainty_days_max": int(row["date_uncertainty_days_max"] or 0),
            }
    return None


def zones_block(raster: dict, artifacts: list[dict]) -> list[dict]:
    evidence = raster.get("change_evidence") or {}
    rows = evidence.get("zones") or []
    parent = evidence.get("analysed_parent")
    window = _fire_window(parent)
    zone_artifact = next((item["artifact_id"] for item in artifacts
                          if item["role"] in ("zones", "change_zones")), None)
    out = []
    for row in rows:
        cause = row.get("cause", "UNKNOWN")
        refs = ["GFC_2025_V113"]
        if cause == "FIRE_SUPPORTED":
            refs.append("MODIS_MCD64A1_061")
        out.append({
            "zone_id": str(row["zone_id"]),
            "fact": row["fact"],
            "cause": cause,
            "cause_reason": str(row.get("cause_reason") or ""),
            "area_ha": float(row.get("detected_area_ha") or 0.0),
            "carbon_overlap_ha": float(row.get("cci_overlap_ha") or 0.0),
            "delta_carbon_tc": float(row.get("delta_tc") or 0.0),
            "contribution_e_tco2e": float(row.get("contribution_tco2e") or 0.0),
            "date_range": window if cause == "FIRE_SUPPORTED" else None,
            "evidence_refs": refs,
            "evidence": dict(row.get("evidence") or {}),
            "artifact_ref": zone_artifact,
        })
    return out


def evidence_block(raster: dict, coverage: dict) -> dict:
    change = raster.get("change_evidence") or {}
    optical = raster.get("optical") or {}
    paired = _fraction(coverage["optical_paired_valid_fraction"])
    scenes = [{
        "scene_key": scene.get("scene_key", ""),
        "aoi_id": scene.get("aoi_id"),
        "datetime_utc": scene.get("datetime_utc", ""),
        "year": int(scene.get("year") or 0),
        "usable_fraction": _fraction(scene.get("usable_fraction")),
        "note": "доля пригодных пикселей по SCL в пределах запроса",
    } for scene in optical.get("scenes", ())]

    warnings: list[dict] = []
    if not change.get("available"):
        warnings.append(warning(
            "CHANGE_EXPLANATION_UNAVAILABLE",
            "Объяснение изменения недоступно: "
            f"{change.get('reason') or 'подходящая пара сцен не найдена'}.",
            reason=str(change.get("reason") or "")))
    if paired <= 0.0:
        warnings.append(warning(
            "NO_PAIRED_OPTICAL_COVERAGE",
            "Нет парных валидных оптических пикселей за период; причина изменения по "
            "оптике не устанавливалась.", fraction=paired))
    elif paired < 0.8:
        warnings.append(warning(
            "LOW_PAIRED_OPTICAL_COVERAGE",
            f"Парное валидное оптическое покрытие {paired:.2f}; объяснение изменения "
            "ограничено.", fraction=paired, threshold=0.8))
    unknown = sum(1 for zone in (change.get("zones") or ())
                  if zone.get("cause") == "UNKNOWN")
    if unknown:
        warnings.append(warning(
            "ZONE_CAUSE_UNKNOWN",
            "Для части зон причина изменения не установлена и остаётся UNKNOWN.",
            "INFO", zones=unknown))

    if not change.get("available") or paired <= 0.0:
        status = "INSUFFICIENT"
    elif warnings:
        status = "REVIEW_REQUIRED"
    else:
        status = "SUFFICIENT"
    return {
        "status": status,
        "optical_paired_valid_fraction": paired,
        "analysed_parent": change.get("analysed_parent"),
        "scenes": scenes,
        "reconciliation": change.get("reconciliation"),
        "warnings": warnings,
    }


def uncredited_roles(manifest: dict) -> list[str]:
    """Product roles used by the calculation for which no source entry was found.

    A licence obligation cannot be met by a shorter list, so this is surfaced rather than
    swallowed by the `.get` that builds the citation list.
    """
    registry = catalog.sources_by_id()
    missing: list[str] = []
    for entry in manifest["dataset"]["files"]:
        role = str(entry.get("role", ""))
        source_id = ROLE_TO_SOURCE.get(role)
        if (source_id is None or source_id not in registry) and role not in missing:
            missing.append(role)
    return missing


def sources_block(manifest: dict) -> list[dict]:
    registry = catalog.sources_by_id()
    wanted: list[str] = []
    for entry in manifest["dataset"]["files"]:
        source_id = ROLE_TO_SOURCE.get(entry.get("role", ""))
        if source_id and source_id not in wanted:
            wanted.append(source_id)
    for source_id in ALWAYS_CITED:
        if source_id not in wanted:
            wanted.append(source_id)
    return [registry[source_id] for source_id in wanted if source_id in registry]


def content_view(result: dict) -> dict:
    """The deterministic scientific content: no ids, no run time, no URLs."""
    identity_block = dict(result["identity"])
    identity_block.pop("analysis_id", None)
    # How the caller addressed the contour is not part of what was measured: naming a
    # supplied area is a shortcut for pasting its polygon, so both must hash the same.
    request_block = dict(result["request"])
    request_block.pop("aoi_id", None)
    return {
        "identity": identity_block,
        "request": request_block,
        "calculation_status": result["calculation_status"],
        "evidence_status": result["evidence_status"],
        "areas": result["areas"],
        "coverage": result["coverage"],
        "timeline": result["timeline"],
        "change": result["change"],
        "uncertainty": result["uncertainty"],
        "baseline": result["baseline"],
        "units": result["units"],
        "scenario_values": result["scenario_values"],
        "claim": result["claim"],
        "zones": result["zones"],
        "risks": result["risks"],
        "projection": result["projection"],
        "evidence": result["evidence"],
        "sources": result["sources"],
        "artifacts": [{key: item[key] for key in
                       ("artifact_id", "role", "media_type", "sha256", "size_bytes",
                        "bbox_wgs84", "crs", "resolution", "resolution_units", "unit",
                        "provenance")}
                      for item in result["artifacts"]],
        "limitations": result["limitations"],
        "notes": result["notes"],
        "fixture": result["fixture"],
    }


def compare(previous: dict | None, content_hash: str,
            units: dict) -> tuple[str, str, str | None, str]:
    """The version link of this passport, and separately how q moved.

    The link vocabulary is the carbon engine's, because passports are its model. Whether
    q rose or fell is a presentational summary and is published as its own field, so that
    "a later observation" is never read as "the earlier passport was wrong".
    """
    if previous is None:
        return "INITIAL", "NOT_COMPARED", None, (
            "Первое наблюдение в этой области сравнения.")
    previous_hash = previous["content_hash"]
    before, after = previous.get("q"), units["q"]
    if previous_hash == content_hash:
        return "REVISION_OF_SAME_SCOPE", "UNCHANGED", previous_hash, (
            "Содержание расчёта совпадает с предыдущим наблюдением той же области.")
    if before is None or after is None:
        return "NEW_OBSERVATION", "NOT_COMPARED", previous_hash, (
            "Одно из наблюдений не даёт числа единиц, поэтому сравнение по величине "
            "не проводится.")
    if after > before:
        return "REVISION_OF_SAME_SCOPE", "INCREASED", previous_hash, (
            f"Потенциальные единицы выросли с {before} до {after} при той же области "
            "сравнения.")
    if after < before:
        return "REVISION_OF_SAME_SCOPE", "DECREASED", previous_hash, (
            f"Потенциальные единицы снизились с {before} до {after} при той же области "
            "сравнения. Это не аннулирование ранее выпущенных единиц.")
    return "REVISION_OF_SAME_SCOPE", "UNCHANGED", previous_hash, (
        "Число единиц не изменилось, изменились сопутствующие величины.")


def passport_block(*, content_hash: str, report_hash: str, previous: dict | None,
                   units: dict, created_at: str) -> dict:
    """The passport of a freshly computed result is always a draft.

    Its status is about this document and says nothing about a blockchain record: an
    anchor lives in `Proof.anchor` and has a status of its own.
    """
    comparison_result, direction, previous_hash, note = compare(previous, content_hash, units)
    return {
        "status": "DRAFT",
        "finalized_at": None,
        "content_hash": content_hash,
        "report_hash": report_hash,
        "previous_hash": previous_hash,
        "comparison_scope": COMPARISON_SCOPE,
        "comparison_result": comparison_result,
        "comparison_direction": direction,
        "comparison_note": note,
        "created_at": created_at,
    }


def build_result(*, analysis_id: str, run_id: str, created_at: str, request_snapshot: dict,
                 geometry_hash: str, input_hash: str, raster: Any, carbon: dict,
                 artifacts: list[dict], previous: dict | None, dataset_origin: str,
                 raster_adapter: str, carbon_adapter_name: str,
                 claim_scope: dict | None = None,
                 extra_limitations: tuple[tuple[str, str], ...] = ()) -> dict:
    payload, cells, manifest = raster.analysis, raster.cells, raster.manifest
    interval, baseline, units, claim = (carbon["interval"], carbon["baseline"],
                                        carbon["units"], carbon["claim"])

    areas = areas_block(payload, cells)
    coverage = coverage_block(payload, baseline)
    limitations = [limitation(code, message) for code, message in BASE_LIMITATIONS]
    limitations.extend(limitation(RASTER_LIMITATION, message)
                       for message in (payload.get("limitations") or ()))
    if dataset_origin == "STUB_FIXTURE":
        limitations.insert(0, limitation(*STUB_LIMITATION))
    limitations.extend(limitation(code, message) for code, message in extra_limitations)

    result = {
        "fixture": raster.fixture,
        "identity": identity(analysis_id=analysis_id, input_hash=input_hash,
                             geometry_hash=geometry_hash, raster=payload, carbon=carbon,
                             manifest=manifest),
        "run": {"run_id": run_id, "created_at": created_at,
                "dataset_origin": dataset_origin, "raster_adapter": raster_adapter,
                "carbon_adapter": carbon_adapter_name},
        "request": request_snapshot,
        "calculation_status": units["status"],
        "evidence_status": "INSUFFICIENT",
        "areas": areas,
        "coverage": coverage,
        "timeline": timeline_block(payload, baseline.get("curve_tc_ha") or {}),
        "change": change_block(payload, units["e_proj_tco2e"]),
        "uncertainty": uncertainty_block(interval),
        "baseline": baseline_block(baseline),
        "units": units_block(units),
        "scenario_values": scenario_values_block(units),
        "claim": claim_block(claim, geometry_hash=geometry_hash,
                             year_start=request_snapshot["year_start"],
                             year_end=request_snapshot["year_end"],
                             scope=claim_scope),
        "zones": zones_block(payload, artifacts),
        "risks": [],
        "projection": projection_block(baseline, []),
        "evidence": evidence_block(payload, coverage),
        "passport": {},
        "sources": sources_block(manifest),
        "artifacts": artifacts,
        "limitations": _unique(limitations),
        "notes": list(carbon.get("notes") or ()),
    }
    result["projection"] = projection_block(baseline, result["timeline"])
    result["risks"] = risks_block(payload, result["zones"], coverage, result["evidence"])
    disagreement = eproj_disagreement(payload, units["e_proj_tco2e"])
    if disagreement is not None:
        result["evidence"]["warnings"].append(disagreement)
    uncredited = uncredited_roles(manifest)
    if uncredited:
        result["evidence"]["warnings"].append(warning(
            "SOURCE_ATTRIBUTION_INCOMPLETE",
            "Использован продукт, для которого не найдена запись об источнике; "
            "атрибуция неполная.", "BLOCKING", roles=uncredited))
    if result["zones"] and any(zone["artifact_ref"] is None for zone in result["zones"]):
        result["evidence"]["warnings"].append(warning(
            "ZONE_GEOMETRY_UNAVAILABLE",
            "Зоны изменения опубликованы без файла с их геометрией; на карте они "
            "не отображаются.", "BLOCKING",
            zones=sum(1 for zone in result["zones"] if zone["artifact_ref"] is None)))
    result["evidence_status"] = result["evidence"]["status"]

    content_hash = digest(content_view(result))
    report_hash = digest({"report": REPORT_SCHEMA_VERSION, "content": content_view(result)})
    result["passport"] = passport_block(content_hash=content_hash, report_hash=report_hash,
                                        previous=previous, units=result["units"],
                                        created_at=created_at)
    return result


def unavailable_result(*, analysis_id: str, run_id: str, created_at: str,
                       request_snapshot: dict, geometry_hash: str, input_hash: str,
                       area_ha: float, reason: str, message: str, raster_adapter: str,
                       carbon_adapter_name: str, previous: dict | None,
                       claim_scope: dict | None = None) -> dict:
    """A result for a request the raster owner could not answer.

    It is a result, not an error: the request is echoed, the reason is named, `q` is null
    and no money is attached to it.
    """
    empty_units = {"status": "UNAVAILABLE", "unavailable_reason": reason, "zero_reason": None,
                   "e_proj_tco2e": None, "e_base_tco2e": None, "leakage_tco2e": None,
                   "lower_tco2e": None, "upper_tco2e": None, "h_tco2e": None, "r_tco2e": None,
                   "ratio": None, "uncertainty_share": None,
                   "uncertainty_deduction_tco2e": None, "r_adj_tco2e": None,
                   "buffer_tco2e": None, "units": None, "rounding_residual_tco2e": None,
                   "scenario_values": [], "method_version": carbon_adapter_name}
    claim = carbon_adapter.no_positive_claim({
        "status": "NOT_PROVIDED" if request_snapshot["claimed_units"] is None
        else "UNASSESSABLE",
        "mismatch_reasons": [], "claimed_units": request_snapshot["claimed_units"],
        "source": request_snapshot["claim_origin"], "units": None,
        "unsupported_gap": None, "supported_share": None, "gap_values": [],
        "reason": None})
    year_start, year_end = request_snapshot["year_start"], request_snapshot["year_end"]
    result = {
        "fixture": None,
        "identity": {
            "analysis_id": analysis_id, "input_hash": input_hash,
            "geometry_hash": geometry_hash, "schema_version": SCHEMA_VERSION,
            "method_version": BACKEND_METHOD_VERSION,
            "dataset_version": catalog.DATASET_VERSION,
            "dataset_hash": catalog.dataset_hash(),
            "source_manifest_hash": catalog.source_manifest_hash([]),
            "parameters_hash": catalog.parameters_hash(), "code_sha": None,
        },
        "run": {"run_id": run_id, "created_at": created_at,
                "dataset_origin": "STUB_FIXTURE", "raster_adapter": raster_adapter,
                "carbon_adapter": carbon_adapter_name},
        "request": request_snapshot,
        "calculation_status": "UNAVAILABLE",
        "evidence_status": "INSUFFICIENT",
        "areas": {"requested_ha": area_ha, "calculated_ha": 0.0, "missing_ha": area_ha,
                  "area_difference_ha": -area_ha, "complete": False, "parent_parts": []},
        "coverage": {"biomass_fraction": 0.0, "uncertainty_fraction": 0.0,
                     "baseline_fraction": 0.0, "optical_paired_valid_fraction": 0.0,
                     "coverage_fraction_raw": {"biomass": 0.0, "uncertainty": 0.0,
                                               "baseline": 0.0,
                                               "optical_paired_valid": 0.0}},
        "timeline": [],
        "change": {"year_start": year_start, "year_end": year_end,
                   "mean_carbon_start_tc_ha": None, "mean_carbon_end_tc_ha": None,
                   "total_carbon_start_tc": None, "total_carbon_end_tc": None,
                   "delta_carbon_tc": None, "eproj_ref": "units.eproj_tco2e",
                   "eproj_tco2e_ha_year": None, "normalisation_area_ha": None,
                   "sign_convention": SIGN_CONVENTION, "pool": POOL},
        "uncertainty": {"status": "UNAVAILABLE", "unavailable_reason": reason,
                        "lower_tco2e": None, "upper_tco2e": None, "sd_tco2e": None,
                        "method": "UNSPECIFIED", "interval_kind": "SCENARIO",
                        "assumptions": None, "sensitivity": []},
        "baseline": {"status": "UNAVAILABLE", "unavailable_reason": reason,
                     "baseline_id": None, "kind": "сценарное допущение кейса",
                     "area_ha": None, "delta_tc": None, "delta_tc_ha": None,
                     "ebase_tco2e": None, "parts": []},
        "units": units_block(empty_units),
        "scenario_values": scenario_values_block(empty_units),
        "claim": claim_block(claim, geometry_hash=geometry_hash, year_start=year_start,
                             year_end=year_end, scope=claim_scope),
        "zones": [],
        # Data quality is knowable even when nothing else is, and it is exactly what a
        # reader of an empty result needs to see.
        "risks": [],
        "projection": {"status": "UNAVAILABLE", "unavailable_reason": reason,
                       "horizon_year": PROJECTION_HORIZON, "points": [],
                       "q_projection": None, "q_projection_note": PROJECTION_Q_NOTE,
                       "note": "Расчёт недоступен, продолжать нечего."},
        "evidence": {"status": "INSUFFICIENT", "optical_paired_valid_fraction": 0.0,
                     "analysed_parent": None, "scenes": [], "reconciliation": None,
                     "warnings": [warning(reason, message, "BLOCKING")]},
        "passport": {},
        "sources": [catalog.sources_by_id()[source_id] for source_id in ALWAYS_CITED
                    if source_id in catalog.sources_by_id()],
        "artifacts": [],
        "limitations": _unique([*(limitation(code, text) for code, text in BASE_LIMITATIONS),
                                limitation(reason, message)]),
        "notes": [],
    }
    result["risks"] = risks_block({}, [], result["coverage"], result["evidence"])
    content_hash = digest(content_view(result))
    report_hash = digest({"report": REPORT_SCHEMA_VERSION, "content": content_view(result)})
    result["passport"] = passport_block(content_hash=content_hash, report_hash=report_hash,
                                        previous=previous, units=result["units"],
                                        created_at=created_at)
    return result


def _unique(values: list[dict]) -> list[dict]:
    seen: list[dict] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


# -- risks, kept beside q rather than inside it -------------------------------------------
RISK_NOTE = (
    "Риск показан рядом с расчётом и не входит в Q. Он не переоценивается на стороне "
    "Backend и не является вероятностью."
)
PROJECTION_HORIZON = 2029


def risks_block(raster: dict, zones: list[dict], coverage: dict,
                evidence: dict) -> list[dict]:
    """What the supplied products say about three risks, and nothing more.

    There is no aggregate score. Adding a fire indication to an optical coverage fraction
    would produce a number that means nothing, and a reader who is handed one tends to
    stop asking what it was made of.
    """
    parent = (raster.get("change_evidence") or {}).get("analysed_parent")
    event = next((row for row in catalog.events() if row["aoi_id"] == parent), None)
    fire_basis: dict[str, Any] = {}
    if event is not None:
        burned = float(event["burned_pixel_centers_in_aoi"] or 0.0)
        total = float(event["all_pixel_centers_in_aoi"] or 0.0)
        fire_basis = {
            "event_id": event["event_id"],
            "burned_pixel_centers": burned,
            "all_pixel_centers": total,
            "burned_share": round(burned / total, 6) if total else None,
            "date_min_product": event["date_min_product"],
            "date_max_product": event["date_max_product"],
            "date_uncertainty_days_min": int(event["date_uncertainty_days_min"] or 0),
            "date_uncertainty_days_max": int(event["date_uncertainty_days_max"] or 0),
        }

    loss_zones = [zone for zone in zones if zone["fact"] == "TREE_COVER_LOSS"]
    loss_basis = {
        "zones": len(loss_zones),
        "detected_area_ha": round(sum(zone["area_ha"] for zone in loss_zones), 6),
        "fire_supported_zones": sum(1 for zone in loss_zones
                                    if zone["cause"] == "FIRE_SUPPORTED"),
        "cause_unknown_zones": sum(1 for zone in loss_zones
                                   if zone["cause"] == "UNKNOWN"),
    }

    quality_basis = {
        "biomass_fraction": coverage["biomass_fraction"],
        "baseline_fraction": coverage["baseline_fraction"],
        "optical_paired_valid_fraction": coverage["optical_paired_valid_fraction"],
        "evidence_status": evidence["status"],
        "blocking_warnings": sum(1 for item in evidence["warnings"]
                                 if item["severity"] == "BLOCKING"),
    }
    return [
        {"code": "FIRE", "observed": event is not None, "basis": fire_basis,
         "source_ref": "MODIS_MCD64A1_061" if event is not None else None,
         "note": "Признак горения по внешнему продукту гарей. Точный контур пожара и "
                 "наземные измерения отсутствуют. " + RISK_NOTE},
        {"code": "FOREST_LOSS", "observed": bool(loss_zones), "basis": loss_basis,
         "source_ref": "GFC_2025_V113" if loss_zones else None,
         "note": "Потеря древесного покрова по продукту года потери. Факт потери и её "
                 "причина — разные утверждения. " + RISK_NOTE},
        {"code": "DATA_QUALITY", "observed": True, "basis": quality_basis,
         "source_ref": None,
         "note": "Полнота данных и качество объяснения изменения. " + RISK_NOTE},
    ]


def projection_block(baseline: dict, timeline: list[dict],
                     horizon: int = PROJECTION_HORIZON) -> dict:
    """The baseline of the case continued to the horizon year.

    Only the baseline is continued, and only because the rules of the case define it for
    any year. The observed stock is not extrapolated: nothing in the supplied data
    supports a statement about what this plot will actually do, and `q_projection` is
    permanently null for the same reason.
    """
    curve = baseline.get("curve_tc_ha") or {}
    if baseline["status"] != "AVAILABLE" or not curve:
        return {
            "status": "UNAVAILABLE",
            "unavailable_reason": baseline["unavailable_reason"] or "MISSING_INPUT",
            "horizon_year": horizon, "points": [], "q_projection": None,
            "q_projection_note": PROJECTION_Q_NOTE,
            "note": "Базовая линия недоступна, поэтому продолжать нечего.",
        }
    observed = {entry["year"] for entry in timeline}
    last_fact = max(observed) if observed else 0
    points = []
    for year in sorted({*observed, *range(last_fact + 1, horizon + 1)}):
        value = curve.get(str(year))
        if value is None and year > last_fact:
            value = _extend(curve, year)
        points.append({
            "year": year,
            "series_kind": "FACT" if year <= last_fact else "PROJECTION",
            "baseline_carbon_tc_ha": value,
        })
    return {
        "status": "AVAILABLE", "unavailable_reason": None, "horizon_year": horizon,
        "points": points, "q_projection": None,
        "q_projection_note": PROJECTION_Q_NOTE,
        "note": "Продолжение базовой линии по правилам кейса. Это сценарное допущение, "
                "а не прогноз состояния участка.",
    }


PROJECTION_Q_NOTE = (
    "Прогноз потенциальных единиц не строится: предоставленные данные не дают основания "
    "для утверждения о будущем состоянии участка."
)


def _extend(curve: dict, year: int) -> float | None:
    """Continue the baseline line at the rate it already has.

    The trajectory the engine supplied is linear in the year, so two of its own points
    fix the rate. This places a point on a line the engine drew; it does not choose one.
    """
    known = sorted((int(key), value) for key, value in curve.items() if value is not None)
    if len(known) < 2:
        return known[0][1] if known else None
    (year_a, value_a), (year_b, value_b) = known[0], known[-1]
    if year_b == year_a:
        return value_b
    rate = (value_b - value_a) / (year_b - year_a)
    return value_b + rate * (year - year_b)
