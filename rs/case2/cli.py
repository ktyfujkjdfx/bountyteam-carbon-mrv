"""Command line entry point for the raster core.

    python -m rs.case2 --aoi RU_TVER_01 --start 2019 --end 2024 --out runs/tver
    python -m rs.case2 --geometry my_plot.geojson --start 2020 --end 2024 --out runs/mine

Naming a supplied AOI is a shortcut for pasting its polygon, nothing more: both
forms run exactly the same analysis.
"""
import argparse
import json
import sys
from pathlib import Path

from rs.case2 import artifacts
from rs.case2 import manifest as manifest_module
from rs.case2 import payload as payload_module
from rs.case2.analysis import analyse
from rs.case2.catalog import Dataset, DatasetError
from rs.case2.geometry import GeometryError
from rs.determinism import write_json

OUTPUT_ANALYSIS = "analysis.json"
OUTPUT_CELLS = "cells.geojson"
OUTPUT_MANIFEST = "manifest.json"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m rs.case2",
        description="Carbon stock and change of a forest plot from the supplied rasters.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--aoi", help="identifier of a supplied area, e.g. RU_TVER_01")
    source.add_argument("--geometry", type=Path,
                        help="path to a WGS84 GeoJSON polygon, feature or collection")
    parser.add_argument("--start", type=int, required=True, help="first model year")
    parser.add_argument("--end", type=int, required=True, help="last model year")
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    parser.add_argument("--data-root", type=Path, default=None,
                        help="override the supplied dataset root (default: data/)")
    parser.add_argument("--no-optical", action="store_true",
                        help="skip Sentinel-2 reading; biomass results are unaffected")
    parser.add_argument("--quiet", action="store_true", help="print nothing on success")
    return parser


def resolve_geometry(args, dataset):
    if args.aoi:
        if args.aoi not in dataset.geometries:
            raise DatasetError(
                f"unknown area {args.aoi}; the dataset supplies "
                f"{', '.join(sorted(dataset.geometries))}")
        return dataset.geometries[args.aoi]
    with open(args.geometry, encoding="utf-8") as handle:
        return json.load(handle)


def _artifact_prefix(payload):
    """Namespace artifact ids by request so two results can share one store."""
    request = payload["request"]
    return (f"{'+'.join(request['parents'])}:"
            f"{request['year_start']}-{request['year_end']}")


def run(argv=None):
    args = build_parser().parse_args(argv)
    dataset = Dataset(args.data_root)

    if not manifest_module.outputs_are_safe(args.out, dataset.root):
        raise DatasetError(
            f"refusing to write results inside the supplied dataset: {args.out}")

    geometry = resolve_geometry(args, dataset)
    analysis = analyse(geometry, args.start, args.end, dataset=dataset,
                       include_optical=not args.no_optical)

    payload = payload_module.analysis_payload(analysis)
    cells = payload_module.cells_payload(analysis)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    prefix = _artifact_prefix(payload)
    records = artifacts.write_cell_artifacts(
        out, prefix, cells,
        analysis.grids[f"cci_biomass:{analysis.parents[0]}"])
    if analysis.raw_change is not None:
        records.extend(artifacts.write_change_artifacts(
            out, prefix, analysis.raw_change, analysis.raw_change["grid"], out))
    payload["artifacts"] = records

    manifest = manifest_module.build(analysis, payload)
    write_json(out / OUTPUT_ANALYSIS, payload)
    write_json(out / OUTPUT_MANIFEST, manifest)

    if not args.quiet:
        change = payload["stock_change"]
        coverage = payload["coverage"]
        print(f"parents        : {', '.join(payload['request']['parents'])}")
        print(f"area           : {payload['request']['area_ha']:.4f} ha "
              f"(calculated {coverage['calculated_ha']:.4f} ha, "
              f"complete={coverage['complete']})")
        print(f"stock {payload['request']['year_start']}     : "
              f"{change['stock_start_tc']:.2f} t C")
        print(f"stock {payload['request']['year_end']}     : "
              f"{change['stock_end_tc']:.2f} t C")
        print(f"E              : {change['e_tco2e']:+.2f} t CO2e "
              f"({change['e_per_ha_per_year']:+.4f} t CO2e/ha/year)")
        print(f"coverage       : biomass {coverage['biomass']['fraction']:.4f} | "
              f"sd {coverage['biomass_sd']['fraction']:.4f} | "
              f"optical paired {coverage['optical_paired']['fraction']:.4f}")
        print(f"content sha256 : {manifest['content_sha256']}")
        print(f"written        : {out / OUTPUT_ANALYSIS}, {out / OUTPUT_CELLS}, "
              f"{out / OUTPUT_MANIFEST}")
    return 0


def main(argv=None):
    try:
        return run(argv)
    except (GeometryError, DatasetError) as exc:
        print(f"rs.case2: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
