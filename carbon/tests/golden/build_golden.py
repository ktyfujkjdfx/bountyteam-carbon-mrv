"""Regenerate the golden results of the five official requests.

The golden file is the record of what this engine currently answers on the supplied data,
down to the passport content hash. `test_golden.py` compares against it, so any change to
a formula, to the composition order or to the passport shape shows up as a reviewable diff
instead of passing quietly.

Regenerate only when a change is intended, and read the diff before committing it:

    python -m carbon.tests.golden.build_golden

The numbers come from the provisional per-cell extraction under `carbon/tests/fixtures/`.
They must be regenerated once the RS payload is available, and the golden file says so.
"""
from __future__ import annotations

import json

from carbon import build_passport
from carbon.parameters import METHOD_VERSION, REPO_ROOT
from carbon.tests.conftest import (
    ALL_REQUESTS,
    GOLDEN_DIR,
    build_case,
    load_json,
    read_csv,
)

GOLDEN_FILE = GOLDEN_DIR / "results.json"


def _row(request_id: str, areas: dict, sample_requests: dict) -> dict:
    _, inputs, analysis, provenance = build_case(request_id, areas, sample_requests)
    passport = build_passport(analysis, provenance=provenance)
    interval, baseline, units = analysis.interval, analysis.baseline, analysis.units
    return {
        "request_id": request_id,
        "year_start": analysis.request.year_start,
        "year_end": analysis.request.year_end,
        "input_status": analysis.input_status,
        "cells": interval.cells,
        "area_ha": interval.area_ha,
        "stock_start_tc": interval.stock_start_tc,
        "stock_end_tc": interval.stock_end_tc,
        "delta_stock_tc": interval.delta_stock_tc,
        "e_proj_tco2e": interval.e_proj_tco2e,
        "e_per_ha_year_tco2e": interval.e_per_ha_year_tco2e,
        "sd_tco2e": interval.sd_tco2e,
        "lower_tco2e": interval.lower_tco2e,
        "upper_tco2e": interval.upper_tco2e,
        "e_base_tco2e": baseline.e_base_tco2e,
        "baseline_delta_tc_ha": baseline.delta_tc_ha,
        "r_tco2e": units.r_tco2e,
        "h_tco2e": units.h_tco2e,
        "ratio": units.ratio,
        "uncertainty_share": units.uncertainty_share,
        "r_adj_tco2e": units.r_adj_tco2e,
        "buffer_tco2e": units.buffer_tco2e,
        "units": units.units,
        "rounding_residual_tco2e": units.rounding_residual_tco2e,
        "status": units.status,
        "unavailable_reason": units.unavailable_reason,
        "zero_reason": units.zero_reason,
        "geometry_hash": analysis.geometry_hash,
        "passport_content_hash": passport.content_hash,
        "note_codes": sorted(note.code for note in analysis.notes),
    }


def main() -> None:
    areas = {row["aoi_id"]: row for row in read_csv(REPO_ROOT / "data" / "areas.csv")}
    sample_requests = {
        feature["properties"]["request_id"]: feature
        for feature in load_json(REPO_ROOT / "data" / "sample_requests.geojson")["features"]
    }
    payload = {
        "note": (
            "Golden results of the carbon engine on the supplied data. Produced from the "
            "provisional per-cell extraction in carbon/tests/fixtures/, not from an RS "
            "payload; regenerate once RS is available."
        ),
        "method_version": METHOD_VERSION,
        "results": [_row(request_id, areas, sample_requests) for request_id in ALL_REQUESTS],
    }
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    GOLDEN_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for row in payload["results"]:
        print(f"{row['request_id']:20s} Q={row['units']!s:>6s} {row['passport_content_hash']}")


if __name__ == "__main__":
    main()
