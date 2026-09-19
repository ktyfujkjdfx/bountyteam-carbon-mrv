"""Measured cost of an analysis, on this machine, with the machine named.

A benchmark that does not say what it ran on is a number without a unit. These
figures are measured, not estimated, and they are not a service level: they say
what one process took on one host, which is what a reviewer needs in order to
decide whether the approach is viable at all.
"""
import argparse
import json
import platform
import time
import tracemalloc
from pathlib import Path

from rs.case2.analysis import analyse
from rs.case2.catalog import Dataset

# A contour nobody supplied, so the benchmark covers the path a user takes.
HAND_DRAWN = {
    "type": "Polygon",
    "coordinates": [[[43.18, 54.86], [43.21, 54.86], [43.21, 54.875],
                     [43.18, 54.875], [43.18, 54.86]]],
}


def environment():
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
    }


def measure(label, geometry, year_start, year_end, dataset, include_optical):
    tracemalloc.start()
    started = time.perf_counter()
    analysis = analyse(geometry, year_start, year_end, dataset=dataset,
                       include_optical=include_optical)
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    evidence = analysis.change_evidence or {}
    return {
        "case": label,
        "period": [year_start, year_end],
        "optical": include_optical,
        "seconds": round(elapsed, 3),
        "peak_python_memory_mb": round(peak / (1024 * 1024), 1),
        "area_ha": round(analysis.request_area_ha, 4),
        "cells": len(analysis.cells),
        "zones": evidence.get("zone_summary", {}).get("zone_count"),
    }


def run(dataset=None, include_optical=True):
    data = dataset if dataset is not None else Dataset()
    rows = []
    for aoi_id in sorted(data.geometries):
        rows.append(measure(aoi_id, data.geometries[aoi_id], 2019, 2024,
                            data, include_optical))
    sample = json.loads(
        (data.root / "sample_requests.geojson").read_text(encoding="utf-8"))
    rows.append(measure("CHECK_TRANSFER_01", sample["features"][0], 2020, 2024,
                        data, include_optical))
    rows.append(measure("hand-drawn contour", HAND_DRAWN, 2020, 2022,
                        data, include_optical))
    return {
        "schema": "rs.case2.benchmark/1",
        "environment": environment(),
        "measurements": rows,
        "note": ("measured on one machine in one process; these are observed "
                 "costs, not a service level"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m rs.case2.bench")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--no-optical", action="store_true")
    args = parser.parse_args(argv)
    result = run(Dataset(args.data_root), include_optical=not args.no_optical)
    print(f"{'case':24s} {'sec':>7s} {'peak MB':>9s} {'cells':>7s} {'zones':>6s}")
    for row in result["measurements"]:
        print(f"{row['case']:24s} {row['seconds']:7.2f} "
              f"{row['peak_python_memory_mb']:9.1f} {row['cells']:7d} "
              f"{str(row['zones'] if row['zones'] is not None else '-'):>6s}")
    print(f"\n{result['environment']['platform']} / Python "
          f"{result['environment']['python']}")
    if args.out:
        from rs.determinism import write_json

        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, result)
        print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
