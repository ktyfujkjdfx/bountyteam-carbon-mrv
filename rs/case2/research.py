"""Two experiments on the supplied data, and the evidence pack they produce.

The case asks for at least one substantive question investigated on equal
terms, with a disturbed plot and a control. These are the two that came out of
actually running the pipeline rather than from planning it.

**How does the publisher transfer uncertainty between years?** The set ships a
CCI change product for 2019-2020 alongside the annual maps, so the publisher's
own answer can be recovered instead of assumed. This matters because the choice
of error dependence swings the uncertainty of a carbon result by more than an
order of magnitude, and it belongs to whoever owns the interval - this module
supplies the measurement, not the decision.

**How much of an apparent change is the instrument rather than the forest?**
The control plot flags change zones across almost its whole area between 2019
and 2024, which no growth can explain. The two scenes come from different L2A
processing baselines. The experiment compares matched and mixed baseline pairs
on the control plot and on the disturbed plot, on equal terms.

Neither experiment is ground truth. Comparing two satellite products to each
other is a consistency check; the set contains no independent field
measurement of carbon, and none is implied here.
"""
import json
from pathlib import Path

import numpy
import rasterio

from rs.case2 import indices, optical, quality, scenes
from rs.case2.analysis import analyse
from rs.case2.catalog import Dataset
from rs.case2.grid import pixel_centres_inside
from rs.determinism import write_json

CONTROL_AOI = "RU_TVER_01"
DISTURBED_AOI = "RU_MORDOVIA_03"


# --------------------------------------------------------------------------
# Experiment 1: what the publisher's own change product implies
# --------------------------------------------------------------------------

def uncertainty_transfer(dataset, aoi_id):
    """Compare the published 2019-2020 change product with our own transfer.

    Two questions at once. Is the published difference the plain difference of
    the annual maps, or an independently modelled change? And does the
    published difference SD match an independent combination of the two annual
    SDs, or something tighter that would imply correlated errors?
    """
    with rasterio.open(dataset.biomass_path(aoi_id, 2019)) as source:
        agb_2019 = source.read(1).astype("float64")
        sd_2019 = source.read(2).astype("float64")
    with rasterio.open(dataset.biomass_path(aoi_id, 2020)) as source:
        agb_2020 = source.read(1).astype("float64")
        sd_2020 = source.read(2).astype("float64")
    with rasterio.open(dataset.path(f"{aoi_id}/CCI_Change_2019_2020.tif")) as source:
        published_difference = source.read(1).astype("float64")
        published_sd = source.read(2).astype("float64")
        flag = source.read(3)

    our_difference = agb_2020 - agb_2019
    independent = numpy.sqrt(sd_2019 ** 2 + sd_2020 ** 2)
    # Perfect positive correlation between the two years would leave only the
    # difference of the deviations.
    correlated = numpy.abs(sd_2020 - sd_2019)
    usable = (sd_2019 > 0) & (sd_2020 > 0) & (published_sd > 0)

    ratio_independent = published_sd[usable] / independent[usable]
    return {
        "aoi_id": aoi_id,
        "cells": int(agb_2019.size),
        "difference": {
            "identical_to_annual_difference": bool(
                (published_difference == our_difference).all()),
            "matching_share": float((published_difference == our_difference).mean()),
            "max_abs_deviation": float(
                numpy.abs(published_difference - our_difference).max()),
        },
        "sd_transfer": {
            "compared_cells": int(usable.sum()),
            "published_mean": float(published_sd[usable].mean()),
            "independent_mean": float(independent[usable].mean()),
            "fully_correlated_mean": float(correlated[usable].mean()),
            "ratio_to_independent_mean": float(ratio_independent.mean()),
            "ratio_to_independent_p05": float(numpy.percentile(ratio_independent, 5)),
            "ratio_to_independent_p95": float(numpy.percentile(ratio_independent, 95)),
        },
        "flag_histogram": {str(code): int((flag == code).sum())
                           for code in sorted(numpy.unique(flag).tolist())},
    }


# --------------------------------------------------------------------------
# Experiment 2: instrument versus forest
# --------------------------------------------------------------------------

def _scene_index_stats(dataset, aoi_id, row, geometry):
    reflectance, scl, grid, _bands = optical.read_scene(dataset, row)
    transform = rasterio.Affine.from_gdal(*grid.transform)
    footprint = pixel_centres_inside(
        transform, grid.width, grid.height, optical.to_scene_crs(geometry, grid.crs))
    usable = optical.usable_mask(scl, reflectance) & footprint
    return {
        "scene_key": row["scene_key"],
        "datetime_utc": row["datetime_utc"],
        "processing_baseline": row["processing_baseline"],
        "offset": dataset.reflectance_offset(row["scene_key"]),
        "nbr": indices.nbr(reflectance),
        "usable": usable,
        "footprint": footprint,
    }


def baseline_effect(dataset, aoi_id, year_start, year_end):
    """dNBR between every eligible scene pair, grouped by baseline agreement.

    If a change is on the ground, it appears whichever pair of scenes is used.
    If it tracks whether the two scenes share a processing baseline, it is the
    processor.
    """
    geometry = dataset.geometries[aoi_id]
    before_rows = dataset.scenes_for(aoi_id, (year_start,))
    after_rows = dataset.scenes_for(aoi_id, (year_end,))
    if not before_rows or not after_rows:
        return {"aoi_id": aoi_id, "pairs": [],
                "note": "no scene pair spans the requested years"}

    before = [_scene_index_stats(dataset, aoi_id, row, geometry)
              for row in before_rows]
    after = [_scene_index_stats(dataset, aoi_id, row, geometry)
             for row in after_rows]

    pairs = []
    for left in before:
        for right in after:
            paired = left["usable"] & right["usable"]
            if not paired.any():
                continue
            dnbr = indices.difference(left["nbr"], right["nbr"])[paired]
            dnbr = dnbr[numpy.isfinite(dnbr)]
            if not dnbr.size:
                continue
            pairs.append({
                "before_scene_key": left["scene_key"],
                "after_scene_key": right["scene_key"],
                "before_baseline": left["processing_baseline"],
                "after_baseline": right["processing_baseline"],
                "same_baseline": left["processing_baseline"] == right["processing_baseline"],
                "same_offset_convention": (left["offset"] == right["offset"]),
                "seasonal_gap_days": abs(
                    scenes.day_of_year(left["datetime_utc"])
                    - scenes.day_of_year(right["datetime_utc"])),
                "paired_pixels": int(paired.sum()),
                "dnbr_median": float(numpy.median(dnbr)),
                "dnbr_mean": float(dnbr.mean()),
                "share_above_disturbance": float(
                    (dnbr >= indices.DNBR_DISTURBANCE).mean()),
                "share_below_recovery": float(
                    (dnbr <= indices.DNBR_RECOVERY).mean()),
            })

    matched = [pair for pair in pairs if pair["same_offset_convention"]]
    mixed = [pair for pair in pairs if not pair["same_offset_convention"]]

    def summarise(group):
        if not group:
            return None
        return {
            "pairs": len(group),
            "dnbr_median_mean": float(numpy.mean([p["dnbr_median"] for p in group])),
            "share_above_disturbance_mean": float(
                numpy.mean([p["share_above_disturbance"] for p in group])),
            "share_below_recovery_mean": float(
                numpy.mean([p["share_below_recovery"] for p in group])),
        }

    return {
        "aoi_id": aoi_id,
        "period": [year_start, year_end],
        "pairs": pairs,
        "matched_offset_convention": summarise(matched),
        "mixed_offset_convention": summarise(mixed),
    }


# --------------------------------------------------------------------------
# Evidence pack
# --------------------------------------------------------------------------

def build(dataset=None, year_start=2019, year_end=2024):
    data = dataset if dataset is not None else Dataset()
    transfer = [uncertainty_transfer(data, aoi)
                for aoi in sorted(data.geometries)]
    effect = [baseline_effect(data, aoi, year_start, year_end)
              for aoi in (CONTROL_AOI, DISTURBED_AOI)]
    control = analyse(data.geometries[CONTROL_AOI], year_start, year_end,
                      dataset=data)
    disturbed = analyse(data.geometries[DISTURBED_AOI], 2020, 2022, dataset=data)
    return {
        "schema": "rs.case2.research/1",
        "question_1": {
            "question": (
                "How does the publisher of the biomass product transfer "
                "uncertainty from two annual maps to their difference?"),
            "method": (
                "compare the supplied CCI_Change_2019_2020 product against the "
                "plain difference of the 2019 and 2020 annual maps, and its "
                "difference SD against an independent and a fully correlated "
                "combination of the two annual SDs"),
            "results": transfer,
            "status": (
                "a consistency check between two products of the same "
                "publisher; the set contains no independent field measurement, "
                "so this is not a validation of either"),
        },
        "question_2": {
            "question": (
                "How much of an apparent 2019 to 2024 change is a processing "
                "baseline difference rather than a change on the ground?"),
            "method": (
                "compute dNBR for every eligible scene pair on a control plot "
                "and a disturbed plot, and group the pairs by whether the two "
                "scenes share the radiometric offset convention"),
            "results": effect,
            "control_aoi": CONTROL_AOI,
            "disturbed_aoi": DISTURBED_AOI,
        },
        "control_vs_disturbed": {
            CONTROL_AOI: _summary(control),
            DISTURBED_AOI: _summary(disturbed),
        },
        "limitations": [
            "comparing two satellite products is a consistency check and not "
            "an independent validation",
            "the spatial dependence of errors between cells is not settled by "
            "either experiment; only the temporal transfer between two years is",
            "no baseline, uncertainty interval or unit count is computed here",
        ],
    }


def _summary(analysis):
    evidence = analysis.change_evidence or {}
    selection = evidence.get("scene_selection", {})
    return {
        "period": [analysis.change.year_start, analysis.change.year_end],
        "area_ha": analysis.request_area_ha,
        "e_tco2e": analysis.change.e_tco2e,
        "e_per_ha_per_year": analysis.change.e_per_ha_per_year,
        "zone_count": evidence.get("zone_summary", {}).get("zone_count"),
        "zone_area_ha": evidence.get("zone_summary", {}).get("detected_area_ha"),
        "by_fact_and_cause": evidence.get("zone_summary", {}).get("by_fact_and_cause"),
        "extent_warning": selection.get("extent_warning"),
        "radiometric_note": selection.get("radiometric_note"),
        "paired_valid_fraction": evidence.get(
            "observation_quality", {}).get("paired_valid_fraction"),
    }


def write(out_dir, pack):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "research.json", pack)
    (out / "research.md").write_bytes(render(pack).encode("utf-8"))
    return out


def render(pack):
    lines = ["# RS research evidence pack", ""]
    first = pack["question_1"]
    lines += [f"## 1. {first['question']}", "", first["method"], "",
              "| AOI | published diff equals annual diff | published SD / independent SD |",
              "|---|---|---|"]
    for row in first["results"]:
        lines.append(
            f"| {row['aoi_id']} | {row['difference']['matching_share']:.1%} "
            f"| {row['sd_transfer']['ratio_to_independent_mean']:.4f} "
            f"(p05 {row['sd_transfer']['ratio_to_independent_p05']:.3f}, "
            f"p95 {row['sd_transfer']['ratio_to_independent_p95']:.3f}) |")
    lines += ["", f"Status: {first['status']}", ""]

    second = pack["question_2"]
    lines += [f"## 2. {second['question']}", "", second["method"], "",
              "| AOI | pairs | offset convention | median dNBR | share above 0.27 | share below -0.10 |",
              "|---|---|---|---|---|---|"]
    for row in second["results"]:
        for label, key in (("matched", "matched_offset_convention"),
                           ("mixed", "mixed_offset_convention")):
            group = row.get(key)
            if not group:
                continue
            lines.append(
                f"| {row['aoi_id']} | {group['pairs']} | {label} "
                f"| {group['dnbr_median_mean']:+.4f} "
                f"| {group['share_above_disturbance_mean']:.1%} "
                f"| {group['share_below_recovery_mean']:.1%} |")
    lines += ["", "## Limitations", ""]
    lines += [f"- {note}" for note in pack["limitations"]]
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(prog="python -m rs.case2.research")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=None)
    args = parser.parse_args(argv)
    pack = build(Dataset(args.data_root))
    out = write(args.out, pack)
    print(json.dumps(pack["question_1"]["results"][0]["sd_transfer"], indent=2))
    print(f"written: {out / 'research.json'}, {out / 'research.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
