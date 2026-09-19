"""Three experiments on the supplied data, and the evidence pack they produce.

The case asks for at least one substantive question investigated on equal
terms, with a disturbed plot and a control. The first two came out of actually
running the pipeline rather than from planning it; the third reports what four
products say about three sites without reconciling them.

Three sites carry the pack. A control with nothing to detect. A plot with
pronounced cover loss that the products date but do not explain - every
disturbance zone there is UNKNOWN, which is the case the method exists to
report honestly. And the one plot where a trusted burn date establishes a
cause, on the dates the official event table records.

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
# Pronounced loss with no established cause: the case where three products see
# a real change and none of them explains it. Treating that as fire because
# fire is the likeliest story is the failure this site exists to prevent.
LOSS_AOI = "RU_VOLOGDA_02"

SITES = (
    {"aoi_id": CONTROL_AOI, "role": "control",
     "why": "a plot with no disturbance to detect, used to measure what the "
            "method reports when nothing happened"},
    {"aoi_id": LOSS_AOI, "role": "pronounced loss, cause not established",
     "why": "real cover loss that the supplied products date but do not "
            "explain; every disturbance zone here is UNKNOWN"},
    {"aoi_id": DISTURBED_AOI, "role": "confirmed fire",
     "why": "the one site where a trusted MODIS burn date establishes a cause, "
            "on the dates the official event table records"},
)


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
# Experiment 3: what four independent products say about the same ground
# --------------------------------------------------------------------------

def product_agreement(analysis):
    """What CCI, GFC, Sentinel-2 and MODIS each say about one site.

    Four products, four different claims, reported side by side without being
    reconciled into one number. Where they agree that is worth knowing; where
    they do not, the disagreement is the finding. None of it is validation:
    agreement between two satellite products is agreement between two models of
    the same ground, and the set contains no field measurement of carbon.
    """
    evidence = analysis.change_evidence or {}
    quality = evidence.get("observation_quality", {})
    gfc = evidence.get("gfc", {})
    fire = evidence.get("fire", {})
    zones = evidence.get("zones", [])
    covered = gfc.get("covered_pixels") or 0
    denominator = quality.get("denominator_pixels") or 0
    return {
        "aoi_id": analysis.parents[0],
        "period": [analysis.change.year_start, analysis.change.year_end],
        "cci_biomass": {
            "claim": "how much carbon the stock difference says left the pool",
            "e_tco2e": analysis.change.e_tco2e,
            "delta_tc": analysis.change.delta_tc,
            "direction": "loss" if analysis.change.e_tco2e > 0 else "accumulation",
        },
        "gfc_lossyear": {
            "claim": "what share of the request lost canopy inside the period",
            "loss_fraction": (gfc.get("loss_pixels_in_request", 0) / covered)
            if covered else None,
            "loss_pixels": gfc.get("loss_pixels_in_request"),
            "covered_pixels": covered or None,
        },
        "sentinel2_spectral": {
            "claim": "what share of the comparable request changed spectrally",
            "zone_fraction": (
                sum(zone["pixel_count"] for zone in evidence.get("zones", ()))
                / denominator) if denominator else None,
            "paired_valid_fraction": quality.get("paired_valid_fraction"),
            "zones": len(zones),
        },
        "modis_burn": {
            "claim": "whether a trusted burn date covers any of the request",
            "available": fire.get("available"),
            "reason": fire.get("reason"),
            "episodes": len(fire.get("detections", ())) if fire.get("available")
            else None,
            "zones_supported": sum(1 for zone in zones
                                   if zone["cause"] == "FIRE_SUPPORTED"),
        },
        "zones_by_fact_and_cause": evidence.get("zone_summary", {}).get(
            "by_fact_and_cause"),
    }


# --------------------------------------------------------------------------
# Coverage and insufficient data
# --------------------------------------------------------------------------

def coverage_cases(dataset):
    """What the method does when the products do not reach the whole request.

    Three outcomes, all real runs: a complete request, a request half outside
    its source area, and a request no product covers at all. The third is a
    refusal with a code rather than a result with zeros, because the difference
    between "nothing changed" and "nothing was measured" is the difference
    between a carbon credit and a fabrication.
    """
    from shapely.geometry import box, mapping, shape

    from rs.case2.catalog import InsufficientData

    rows = []
    with open(dataset.root / "sample_requests.geojson", encoding="utf-8") as handle:
        sub_plot = json.load(handle)["features"][0]["geometry"]

    complete = analyse(shape(sub_plot), 2020, 2024, dataset=dataset,
                       include_optical=False)
    rows.append(_coverage_row("a sub-plot inside its source area", complete))

    bounds = shape(sub_plot).bounds
    overhanging = box(bounds[0], bounds[1], bounds[2],
                      bounds[3] + (bounds[3] - bounds[1]))
    partial = analyse(mapping(overhanging), 2020, 2024, dataset=dataset,
                      include_optical=False)
    rows.append(_coverage_row("a contour hanging outside its source area",
                              partial))

    try:
        analyse(mapping(box(37.60, 55.75, 37.62, 55.77)), 2019, 2024,
                dataset=dataset)
        refusal = None
    except InsufficientData as exc:
        refusal = exc.as_document()

    return {
        "cases": rows,
        "outside_every_product": refusal,
        "rule": (
            "a request whose mandatory coverage is incomplete must reach the "
            "unit owner with complete=false and a measured shortfall, so that "
            "potential units are reported as null rather than computed on the "
            "part that happened to be covered"),
    }


def _coverage_row(label, analysis):
    coverage = analysis.coverage
    return {
        "case": label,
        "requested_ha": coverage.requested_ha,
        "calculated_ha": coverage.calculated_ha,
        "missing_ha": coverage.missing_ha,
        "area_difference_ha": coverage.area_difference_ha,
        "biomass_fraction_raw": coverage.biomass_fraction,
        "complete": coverage.complete,
        "units_may_be_computed": coverage.complete,
    }


# --------------------------------------------------------------------------
# Threshold sensitivity
# --------------------------------------------------------------------------

def threshold_sensitivity(analysis):
    """What other mask and threshold choices would have selected.

    Reported so the fixed choices can be judged, not so they can be swapped for
    whichever produces a better number. The published choice is marked in the
    table and nothing downstream reads any other row.
    """
    rows = (analysis.change_evidence or {}).get("sensitivity", [])
    published = next((row for row in rows if row["is_published_choice"]), None)
    return {
        "aoi_id": analysis.parents[0],
        "period": [analysis.change.year_start, analysis.change.year_end],
        "published_choice": published,
        "grid": rows,
        "effect_on_the_official_result": (
            "none; the stock difference comes from the CCI maps and does not "
            "read any of these rows, and no threshold here enters a unit count"),
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
    loss = analyse(data.geometries[LOSS_AOI], year_start, year_end, dataset=data)
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
        "question_3": {
            "question": (
                "Where do four independent products agree about the same "
                "ground, and where do they not?"),
            "method": (
                "report what CCI, Global Forest Change, Sentinel-2 and MODIS "
                "each claim about each site, side by side and unreconciled"),
            "results": [product_agreement(analysis)
                        for analysis in (control, loss, disturbed)],
            "status": (
                "agreement between two satellite products is agreement between "
                "two models of the same ground; the set contains no field "
                "measurement of carbon, so nothing here is ground truth"),
        },
        "sites": list(SITES),
        "control_vs_disturbed": {
            CONTROL_AOI: _summary(control),
            LOSS_AOI: _summary(loss),
            DISTURBED_AOI: _summary(disturbed),
        },
        "coverage_and_insufficient_data": coverage_cases(data),
        "threshold_sensitivity": [threshold_sensitivity(analysis)
                                  for analysis in (control, disturbed)],
        "dnbr_limitations": {
            "finding": (
                "a multi-year dNBR is not a reliable absolute measure. Even on "
                "matched offset conventions the control plot reads about -0.25 "
                "over five years, which is not growth; mixing conventions takes "
                "it to about -0.86 and flags the whole forest as regrowth"),
            "what_survives": (
                "detection does. Every eligible pair over the burned plot shows "
                "a loss, so the presence of a disturbance is robust to the "
                "scene choice even where its absolute level is not"),
            "consequence": (
                "recovery is reported as RECOVERY_INDICATION and never as "
                "recovered carbon, and scene selection prefers a matched offset "
                "convention ahead of the seasonal-gap rule"),
        },
        "satellite_support_is_not_ground_truth": (
            "every statement in this pack rests on published satellite "
            "products. A MODIS burn date supports a cause; it does not "
            "establish one in the way a field visit would. No plot in the set "
            "carries an independent measurement of biomass or of a fire "
            "perimeter, so no number here has been validated against the "
            "ground, and none is presented as if it had"),
        "limitations": [
            "comparing two satellite products is a consistency check and not "
            "an independent validation",
            "the spatial dependence of errors between cells is not settled by "
            "either experiment; only the temporal transfer between two years is",
            "no baseline, uncertainty interval or unit count is computed here",
            "the threshold sensitivity grid is reported so the fixed choices "
            "can be judged; no row of it reaches the official result",
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
    third = pack["question_3"]
    lines += ["", f"## 3. {third['question']}", "", third["method"], "",
              "| AOI | period | CCI E tCO2e | GFC loss share | S2 zone share "
              "| paired-valid | MODIS |", "|---|---|---|---|---|---|---|"]
    for row in third["results"]:
        modis = row["modis_burn"]
        state = (f"{modis['episodes']} episode(s)" if modis["available"]
                 else "not supplied")
        lines.append(
            f"| {row['aoi_id']} | {row['period'][0]}-{row['period'][1]} "
            f"| {row['cci_biomass']['e_tco2e']:+.1f} "
            f"| {_share(row['gfc_lossyear']['loss_fraction'])} "
            f"| {_share(row['sentinel2_spectral']['zone_fraction'])} "
            f"| {_share(row['sentinel2_spectral']['paired_valid_fraction'])} "
            f"| {state} |")
    lines += ["", f"Status: {third['status']}", ""]

    lines += ["## Sites", "",
              "| AOI | role | why it is in the pack |", "|---|---|---|"]
    lines += [f"| {site['aoi_id']} | {site['role']} | {site['why']} |"
              for site in pack["sites"]]

    coverage = pack["coverage_and_insufficient_data"]
    lines += ["", "## Coverage and insufficient data", "",
              "| case | requested ha | calculated ha | missing ha "
              "| signed difference ha | complete | units may be computed |",
              "|---|---|---|---|---|---|---|"]
    for row in coverage["cases"]:
        lines.append(
            f"| {row['case']} | {row['requested_ha']:.4f} "
            f"| {row['calculated_ha']:.4f} | {row['missing_ha']:.4f} "
            f"| {row['area_difference_ha']:+.6f} | {row['complete']} "
            f"| {row['units_may_be_computed']} |")
    refusal = coverage["outside_every_product"]
    if refusal:
        lines += ["", f"A contour no product covers is refused as "
                      f"`{refusal['outcome']}` with code `{refusal['code']}`, "
                      f"not answered with zeros.", ""]
    lines += [coverage["rule"], ""]

    lines += ["## Threshold sensitivity", "",
              "| AOI | mask | dNBR threshold | zones | zone area ha "
              "| published choice |", "|---|---|---|---|---|---|"]
    for block in pack["threshold_sensitivity"]:
        for row in block["grid"]:
            lines.append(
                f"| {block['aoi_id']} | {row['mask']} | {row['dnbr_threshold']} "
                f"| {row['zones']} | {row['zone_area_ha']:.2f} "
                f"| {'yes' if row['is_published_choice'] else ''} |")
    lines += ["", pack["threshold_sensitivity"][0][
        "effect_on_the_official_result"], ""]

    dnbr = pack["dnbr_limitations"]
    lines += ["## What dNBR can and cannot say", "",
              f"**Finding.** {dnbr['finding']}", "",
              f"**What survives.** {dnbr['what_survives']}", "",
              f"**Consequence.** {dnbr['consequence']}", ""]

    lines += ["## Satellite support is not ground truth", "",
              pack["satellite_support_is_not_ground_truth"], ""]

    lines += ["## Limitations", ""]
    lines += [f"- {note}" for note in pack["limitations"]]
    lines.append("")
    return "\n".join(lines)


def _share(value):
    return "n/a" if value is None else f"{value:.2%}"


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
