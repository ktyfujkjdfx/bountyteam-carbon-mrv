"""The carbon passport: one canonical, hashable record of one analysis.

The passport has two layers on purpose.

`content` is the scientific record — geometry hash, period, pool, parameters snapshot,
source checksums, method and code version, stock, E, interval, baseline, Q and the claim
comparison. It is deterministic: the same analysis produces the same bytes, so
`content_hash` identifies the science and nothing else.

`envelope` carries what changes between two identical runs — the moment of creation and
the run identifier. Those never enter the content hash. Mixing them in would give every
rerun a new hash and make the hash useless as an identity.

Versions are linked by `previous_content_hash`, and the link is inside the content, so a
chain cannot be rewritten without changing every later hash. Comparability of two versions
is assessed and stated, never assumed: a different period is a new observation of the same
place, not a correction of the earlier one, and it never writes off the earlier Q.

Four hashes travel with a result and they answer four different questions. They are named
apart so that nobody has to guess which one they are looking at:

* `scientific_passport_content_hash` — this canonical scientific record;
* `source_manifest_hash` — the official input files and the parameters it was built from;
* `api_result_content_hash` — the public representation Backend serves (Backend's to
  compute; the passport only names the field);
* `report_file_hash` — the bytes of a downloaded report, which differ between two renders
  of the same analysis because the page prints its run time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import canonical, notes, reasons
from .analysis import Analysis
from .interval import INTERVAL_KIND
from .parameters import METHOD_VERSION

# The four hash fields, named once so no consumer has to infer which is which.
SCIENTIFIC_CONTENT_HASH = "scientific_passport_content_hash"
SOURCE_MANIFEST_HASH = "source_manifest_hash"
API_RESULT_CONTENT_HASH = "api_result_content_hash"
REPORT_FILE_HASH = "report_file_hash"

# How two passports of the same place relate to each other.
VERSION_INITIAL = "INITIAL"
VERSION_REVISION = "REVISION_OF_SAME_SCOPE"
VERSION_NEW_OBSERVATION = "NEW_OBSERVATION"
VERSION_NOT_COMPARABLE = "NOT_COMPARABLE"

LIMITATIONS = (
    "Учитывается только живая надземная древесная биомасса (пул AGB).",
    "Оценки биомассы — модельный продукт ESA CCI, а не наземные измерения.",
    "Интервал сценарный: вероятностное покрытие не заявляется, эмпирической калибровки нет.",
    "Базовая линия, утечка и цены заданы условиями кейса и не являются рыночным прогнозом.",
    "Потенциальные единицы кейса не являются единицами официального реестра.",
    "Совпадение контрольных сумм подтверждает исходные файлы, а не правильность оценки.",
    "Даты начала проектной деятельности в наборе неизвестны, поэтому результат описывается "
    "относительно сценария, а не как установленный эффект действий владельца участка.",
)


@dataclass(frozen=True)
class Passport:
    """Stable scientific content plus its own hash."""

    content: dict[str, Any]
    content_hash: str
    format: str = canonical.FORMAT

    @property
    def canonical_bytes(self) -> bytes:
        return canonical.canonical_bytes(self.content)

    @property
    def source_manifest_hash(self) -> str:
        """Hash of the inputs alone, so a reader can check them without the whole record."""
        return self.content["provenance"]["source_manifest_hash"]

    def hashes(self) -> dict[str, str | None]:
        """Every hash this role owns, under the name the contract uses."""
        return {
            SCIENTIFIC_CONTENT_HASH: self.content_hash,
            SOURCE_MANIFEST_HASH: self.source_manifest_hash,
        }


@dataclass(frozen=True)
class PassportEnvelope:
    """The passport as it is stored or sent: content plus the volatile run metadata."""

    passport: Passport
    created_at: str
    run_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.passport.format,
            SCIENTIFIC_CONTENT_HASH: self.passport.content_hash,
            SOURCE_MANIFEST_HASH: self.passport.source_manifest_hash,
            "content": self.passport.content,
            "run": {
                "created_at": self.created_at,
                "run_id": self.run_id,
                "note": (
                    "Эти поля не входят в content_hash: один и тот же расчёт, выполненный "
                    "дважды, даёт один и тот же content_hash."
                ),
            },
        }


def _interval_block(analysis: Analysis) -> dict[str, Any]:
    interval = analysis.interval
    return {
        "status": interval.status,
        "unavailable_reason": interval.unavailable_reason,
        "kind": INTERVAL_KIND,
        "cells": interval.cells,
        "area_ha": interval.area_ha,
        "stock_start_tc": interval.stock_start_tc,
        "stock_end_tc": interval.stock_end_tc,
        "mean_start_tc_ha": interval.mean_start_tc_ha,
        "mean_end_tc_ha": interval.mean_end_tc_ha,
        "delta_stock_tc": interval.delta_stock_tc,
        "e_proj_tco2e": interval.e_proj_tco2e,
        "e_per_ha_year_tco2e": interval.e_per_ha_year_tco2e,
        "sd_tco2e": interval.sd_tco2e,
        "lower_tco2e": interval.lower_tco2e,
        "upper_tco2e": interval.upper_tco2e,
        "assumptions": dict(interval.assumptions),
        "sensitivity": [
            {
                "label": variant.label,
                "spatial_dependence": variant.spatial_dependence,
                "temporal_correlation": variant.temporal_correlation,
                "sd_tco2e": variant.sd_tco2e,
                "lower_tco2e": variant.lower_tco2e,
                "upper_tco2e": variant.upper_tco2e,
                "half_width_tco2e": variant.half_width_tco2e,
            }
            for variant in interval.sensitivity
        ],
    }


def _baseline_block(analysis: Analysis) -> dict[str, Any]:
    baseline = analysis.baseline
    return {
        "status": baseline.status,
        "unavailable_reason": baseline.unavailable_reason,
        "source": "data/methodology/baseline.csv",
        "area_ha": baseline.area_ha,
        "delta_tc": baseline.delta_tc,
        "delta_tc_ha": baseline.delta_tc_ha,
        "e_base_tco2e": baseline.e_base_tco2e,
        "parts": [
            {
                "aoi_id": part.aoi_id,
                "area_ha": part.area_ha,
                "stock_start_tc_ha": part.stock_start_tc_ha,
                "stock_end_tc_ha": part.stock_end_tc_ha,
                "delta_tc_ha": part.delta_tc_ha,
                "delta_tc": part.delta_tc,
                "clipped_at_zero": part.clipped_at_zero,
            }
            for part in baseline.parts
        ],
    }


def _units_block(analysis: Analysis) -> dict[str, Any]:
    units = analysis.units
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
        "scenario_values": [
            {"price_rub": value.price_rub, "value_rub": value.value_rub}
            for value in units.scenario_values
        ],
    }


def _claim_block(analysis: Analysis) -> dict[str, Any]:
    claim = analysis.claim
    return {
        "status": claim.status,
        "reason": claim.reason,
        "comparable": claim.comparable,
        "mismatch_reasons": list(claim.mismatch_reasons),
        "claimed_units": claim.claimed_units,
        "source": claim.source,
        "units": claim.units,
        "unsupported_gap": claim.unsupported_gap,
        "supported_share": claim.supported_share,
        "gap_values": [
            {"price_rub": value.price_rub, "value_rub": value.value_rub}
            for value in claim.gap_values
        ],
    }


def build_content(
    analysis: Analysis,
    *,
    provenance: dict[str, Any],
    previous_content_hash: str | None = None,
) -> dict[str, Any]:
    """The hashable scientific record of one analysis. No timestamps, no run identifiers."""
    request = analysis.request
    area = analysis.area
    return {
        "format": canonical.FORMAT,
        "method_version": analysis.method_version,
        "engine_method_version": METHOD_VERSION,
        "previous_content_hash": previous_content_hash,
        "request": {
            "request_id": request.request_id,
            # the geometry travels with its hash: a hash nobody can recompute proves nothing
            "geometry": request.geometry,
            "geometry_hash": analysis.geometry_hash,
            "year_start": request.year_start,
            "year_end": request.year_end,
            "pool": request.pool,
            "unit": request.unit,
            "baseline_parts": [
                {"aoi_id": part.aoi_id, "area_ha": part.area_ha} for part in request.parts
            ],
        },
        "input_status": analysis.input_status,
        "method_options": {
            "temporal_correlation": analysis.options.temporal_correlation,
            "coverage_factor": analysis.options.coverage_factor,
            "spatial_dependence": analysis.options.spatial_dependence,
        },
        "area": None if area is None else {
            "requested_ha": area.requested_ha,
            "calculated_ha": area.calculated_ha,
            "missing_ha": area.missing_ha,
            "complete": area.complete,
        },
        "coverage": {
            "biomass": analysis.coverage.biomass,
            "baseline": analysis.coverage.baseline,
            "uncertainty": analysis.coverage.uncertainty,
            "raw": analysis.coverage_raw,
            "excluded_cells": analysis.excluded_cells,
            "note": (
                "Публичные доли ограничены [0, 1]; raw сохранён как есть, потому что "
                "геодезическая площадь не аддитивна по разбиению."
            ),
        },
        "cross_check": {
            "declared_e_tco2e": analysis.declared_e_tco2e,
            "recomputed_e_tco2e": analysis.interval.e_proj_tco2e,
            "agrees": analysis.declared_e_agrees,
            "note": (
                "Изменение запаса принадлежит поставщику растровых данных. Пересчёт по "
                "пер-клеточному слою — сверка, а не второе мнение."
            ),
        },
        "optical_quality": analysis.optical_quality,
        "timeline": [
            {
                "year": point.year,
                "mean_tc_ha": point.mean_tc_ha,
                "total_tc": point.total_tc,
                "mean_agb_t_ha": point.mean_agb_t_ha,
                "cells": point.cells,
                "covered_ha": point.covered_ha,
            }
            for point in analysis.timeline
        ],
        "interval": _interval_block(analysis),
        "baseline": _baseline_block(analysis),
        "units": _units_block(analysis),
        "claim": _claim_block(analysis),
        "provenance": dict(
            provenance,
            source_manifest_hash=canonical.content_hash({
                "files": provenance.get("files", []),
                "parameters": provenance.get("parameters", {}),
                "method_version": provenance.get("method_version"),
            }),
        ),
        "notes": [{"code": item.code, "text": item.text} for item in analysis.notes],
        "limitations": list(LIMITATIONS),
    }


def build_passport(
    analysis: Analysis,
    *,
    provenance: dict[str, Any],
    previous_content_hash: str | None = None,
) -> Passport:
    content = build_content(
        analysis, provenance=provenance, previous_content_hash=previous_content_hash
    )
    return Passport(content=content, content_hash=canonical.content_hash(content))


def seal(passport: Passport, *, created_at: str, run_id: str) -> PassportEnvelope:
    """Attach the volatile run metadata without touching the content hash."""
    return PassportEnvelope(passport=passport, created_at=created_at, run_id=run_id)


@dataclass(frozen=True)
class VersionLink:
    status: str
    previous_content_hash: str | None
    content_hash: str
    changed: tuple[str, ...] = ()
    notes: tuple[notes.Note, ...] = ()


def link_versions(previous: Passport | None, current: Passport) -> VersionLink:
    """State how a new passport relates to the previous one; never assume it replaces it."""
    if previous is None:
        return VersionLink(VERSION_INITIAL, None, current.content_hash)

    old = previous.content["request"]
    new = current.content["request"]
    changed = tuple(
        field for field in ("geometry_hash", "year_start", "year_end", "pool", "unit")
        if old.get(field) != new.get(field)
    )
    if old.get("geometry_hash") != new.get("geometry_hash") or old.get("pool") != new.get("pool") \
            or old.get("unit") != new.get("unit"):
        status = VERSION_NOT_COMPARABLE
        attached: tuple[notes.Note, ...] = ()
    elif (old.get("year_start"), old.get("year_end")) != (new.get("year_start"), new.get("year_end")):
        status = VERSION_NEW_OBSERVATION
        attached = (notes.note(notes.PASSPORT_NEW_OBSERVATION),)
    else:
        status = VERSION_REVISION
        attached = ()
    return VersionLink(
        status=status,
        previous_content_hash=previous.content_hash,
        content_hash=current.content_hash,
        changed=changed,
        notes=attached,
    )


def units_for_reader(passport: Passport) -> tuple[str, int | None]:
    """The two fields a reader must not confuse: availability status and Q."""
    block = passport.content["units"]
    status = block["status"]
    return status, (block["units"] if status == reasons.AVAILABLE else None)
