"""Putting the change evidence together for one request.

Reads the selected pair of scenes, forms the indices, stacks the evidence from
three independent products, draws the zones, classifies them, attributes the
stock change to them and checks that the attribution adds up.
"""
import numpy
import rasterio

from rs.case2 import disturbance, indices, optical, quality, scenes, zones
from rs.case2.grid import pixel_centres_inside
from rs.case2.models import CO2_PER_C

SENSITIVITY_MASKS = {
    "strict": "scene classification 4 and 5 only",
    "extended": "classes 4 and 5 plus 2 and 7, a signed sensitivity variant",
}


def _footprint(grid, request):
    transform = rasterio.Affine.from_gdal(*grid.transform)
    return transform, pixel_centres_inside(
        transform, grid.width, grid.height,
        optical.to_scene_crs(request, grid.crs))


def _usable(scl, reflectance, extended=False):
    accepted = numpy.isin(scl, [4, 5, 2, 7] if extended else [4, 5])
    return accepted & numpy.isfinite(reflectance).all(axis=0)


def analyse_change(dataset, request, aoi_id, year_start, year_end,
                   scene_quality_by_key):
    """Full change evidence for one parent AOI, or an explanation of its absence."""
    part = request.intersection(dataset.geometries[aoi_id])
    rows = {row["scene_key"]: row
            for row in dataset.scenes_for(aoi_id, (year_start, year_end))}
    candidates = [scene_quality_by_key[key] for key in rows
                  if key in scene_quality_by_key]
    if not candidates:
        return {"available": False,
                "reason": f"no Sentinel-2 scene of {year_start} or {year_end} "
                          f"covers {aoi_id}"}

    cache = {}

    def load(scene_key):
        if scene_key not in cache:
            cache[scene_key] = optical.read_scene(dataset, rows[scene_key])
        return cache[scene_key]

    grid = load(candidates[0].scene_key)[2]
    transform, footprint = _footprint(grid, part)

    def paired_area(before_key, after_key):
        before = load(before_key)
        after = load(after_key)
        return int((_usable(before[1], before[0]) & _usable(after[1], after[0])
                    & footprint).sum())

    before_scene, after_scene, report = scenes.select(
        candidates, year_start, year_end, paired_area)
    if before_scene is None:
        return {"available": False,
                "reason": report["outcome"], "selection": report}

    before_reflectance, before_scl, _grid, _bands = load(before_scene.scene_key)
    after_reflectance, after_scl, _grid, _bands = load(after_scene.scene_key)

    before_usable = _usable(before_scl, before_reflectance)
    after_usable = _usable(after_scl, after_reflectance)
    paired = quality.paired_valid(before_usable, after_usable, footprint)

    dnbr = indices.difference(indices.nbr(before_reflectance),
                              indices.nbr(after_reflectance))
    dndvi = indices.difference(indices.ndvi(before_reflectance),
                               indices.ndvi(after_reflectance))

    gfc = disturbance.gfc_on_grid(dataset, aoi_id, transform, grid.width,
                                  grid.height, grid.crs, year_start, year_end)
    fire = disturbance.fire_on_grid(dataset, aoi_id, transform, grid.width,
                                    grid.height, grid.crs, year_start, year_end)

    spectral_change = paired & (
        (numpy.nan_to_num(dnbr, nan=0.0) >= indices.DNBR_DISTURBANCE)
        | (numpy.nan_to_num(dndvi, nan=0.0) >= indices.DNDVI_DISTURBANCE))
    gfc_loss = gfc["loss_in_interval"] & footprint
    evidence = {
        "paired_valid": paired,
        "spectral_change": spectral_change,
        "gfc_loss": gfc_loss,
        # Carried so a zone can report how large its change is, on the same
        # array the zone was drawn from.
        "dnbr": dnbr,
        # A zone may rest on spectral change, on the loss-year product, or on
        # both; which one is recorded per zone so a reader can tell them apart.
        "loss_candidate": spectral_change | gfc_loss,
        "recovery_candidate": paired & (
            numpy.nan_to_num(dnbr, nan=0.0) <= indices.DNBR_RECOVERY),
    }

    gaps = zones.observation_gaps(before_scl, after_scl, paired, footprint,
                                  transform)
    detected = zones.detect(evidence, transform)
    classifications = [zones.classify(zone, evidence, fire)
                       for zone in detected["zones"]]
    zone_mask = numpy.zeros(paired.shape, dtype=bool)
    for zone in detected["zones"]:
        zone_mask |= zone["pixel_mask"]

    report.update(_radiometric_check(before_scene, after_scene))
    report.update(_extent_check(zone_mask, footprint))

    return {
        "available": True,
        "aoi_id": aoi_id,
        "grid": grid,
        "transform": transform,
        "footprint": footprint,
        "pair": {
            "before_scene_key": before_scene.scene_key,
            "after_scene_key": after_scene.scene_key,
            "before_datetime_utc": before_scene.datetime_utc,
            "after_datetime_utc": after_scene.datetime_utc,
        },
        "selection": report,
        "quality": quality.summary(
            quality.category_counts(before_scl, footprint),
            quality.category_counts(after_scl, footprint),
            paired, footprint),
        "indices": {
            "dnbr_undefined_pixels": indices.undefined_count(dnbr, footprint),
            "dndvi_undefined_pixels": indices.undefined_count(dndvi, footprint),
            "denominator_floor": indices.DENOMINATOR_FLOOR,
            "undefined_policy": (
                "an index whose denominator is below the floor is left "
                "undefined; it is not clamped and not set to zero"),
            "dnbr_threshold": indices.DNBR_DISTURBANCE,
            "dndvi_threshold": indices.DNDVI_DISTURBANCE,
            "recovery_threshold": indices.DNBR_RECOVERY,
        },
        "gfc": {
            "loss_year_codes": list(gfc["codes"]),
            "loss_pixels_in_request": int(gfc_loss.sum()),
            "covered_pixels": int((gfc["covered"] & footprint).sum()),
        },
        "fire": fire,
        "zones": detected["zones"],
        "gaps": gaps,
        "classifications": classifications,
        "dropped_below_mmu": detected["dropped_below_mmu"],
        "dropped_below_mmu_ha": detected["dropped_below_mmu_ha"],
        "zone_mask": zone_mask,
        "paired_valid": paired,
        "dnbr": dnbr,
        "dndvi": dndvi,
        "reflectance": (before_reflectance, after_reflectance),
        "scl": (before_scl, after_scl),
    }


def _radiometric_check(before_scene, after_scene):
    """Flag a pair whose two scenes were produced by different L2A conventions.

    From processing baseline 04.00 the product carries a -0.1 offset, and the
    surrounding processor versions differ in more than that one constant. Both
    scenes are valid surface reflectance, but a systematic difference between
    the two versions lands in every index difference computed from them and
    looks exactly like a gradual change across the whole plot.
    """
    if before_scene.processing_baseline == after_scene.processing_baseline:
        return {}
    same_convention = (before_scene.reflectance_offset_applied
                       == after_scene.reflectance_offset_applied)
    if same_convention:
        warning = (
            "the two scenes come from different processing baselines on the "
            "same radiometric offset convention; part of any uniform index "
            "difference is a processor difference rather than a change on the "
            "ground, though the large offset artefact does not apply")
    else:
        warning = (
            "the two scenes straddle the 04.00 offset change and no pair on a "
            "single convention was available; on a control plot this alone "
            "produces a median dNBR near -0.86 and flags the whole area as "
            "regrowth, so this comparison is not safe to read as change")
    return {
        "radiometric_note": {
            "before_baseline": before_scene.processing_baseline,
            "after_baseline": after_scene.processing_baseline,
            "before_offset": before_scene.reflectance_offset_applied,
            "after_offset": after_scene.reflectance_offset_applied,
            "same_offset_convention": same_convention,
            "warning": warning,
        }
    }


def _extent_check(zone_mask, footprint, share=0.5):
    """Flag a change that covers most of the request.

    A disturbance rarely covers a whole plot uniformly. When the zones do, the
    likeliest explanation is a difference between the two observations - season
    or radiometry - and the reader should be told before reading the map as a
    disturbance.
    """
    total = int(footprint.sum())
    covered = int((zone_mask & footprint).sum())
    if not total or covered / total < share:
        return {}
    return {
        "extent_warning": (
            f"change zones cover {covered / total:.0%} of the request; a change "
            f"this uniform is more often a difference between the two "
            f"observations than a disturbance on the ground")
    }


def sensitivity(change, dataset=None):
    """What a different mask or threshold would have selected.

    Reported so the fixed choices can be judged, not so they can be swapped for
    whichever produces a better number.
    """
    if not change.get("available"):
        return []
    before_reflectance, after_reflectance = change["reflectance"]
    before_scl, after_scl = change["scl"]
    footprint = change["footprint"]
    dnbr = numpy.nan_to_num(change["dnbr"], nan=0.0)
    rows = []
    for name, extended in (("strict", False), ("extended", True)):
        paired = (_usable(before_scl, before_reflectance, extended)
                  & _usable(after_scl, after_reflectance, extended) & footprint)
        for threshold in indices.DNBR_SENSITIVITY:
            candidate = paired & (dnbr >= threshold)
            labels, counts = zones.label_components(candidate)
            kept = [size for size in counts.values()
                    if size >= zones.MIN_ZONE_PIXELS]
            rows.append({
                "mask": name,
                "mask_note": SENSITIVITY_MASKS[name],
                "dnbr_threshold": threshold,
                "usable_pixels": int(paired.sum()),
                "usable_fraction": (float(paired.sum()) / int(footprint.sum())
                                    if footprint.any() else 0.0),
                "zones": len(kept),
                "zone_area_ha": round(sum(kept) * zones.PIXEL_AREA_HA, 6),
                "is_published_choice": (name == "strict"
                                        and threshold == indices.DNBR_DISTURBANCE),
            })
    return rows


def attribute(change, cells, request, year_start, year_end, total_delta_tc):
    """Attribute the stock change to the zones and check the balance."""
    if not change.get("available") or not change["zones"]:
        return {
            "per_zone_delta_tc": {},
            "per_zone_overlap_ha": {},
            "remainder_delta_tc": total_delta_tc,
            "reconciliation": zones.reconcile(
                {"per_zone_delta_tc": {}, "remainder_delta_tc": total_delta_tc},
                total_delta_tc),
        }
    contribution = zones.contributions(
        change["zones"], cells, request, change["grid"].crs,
        year_start, year_end)
    contribution["reconciliation"] = zones.reconcile(contribution, total_delta_tc)
    return contribution


def observed_between(change):
    """The window the pair could see, which is when the change is known to fit."""
    pair = change["pair"]
    return {
        "start": pair["before_datetime_utc"],
        "end": pair["after_datetime_utc"],
        "note": ("the change happened somewhere inside this window; the two "
                 "acquisitions are the only dates that were observed"),
    }


def zone_payload(change, contribution):
    """Zone rows for the result document, without the pixel masks.

    Built from the same function that fills the GeoJSON properties, so a zone
    opened from the map and a zone read from the result say the same thing.
    """
    window = observed_between(change)
    return [zones.properties(zone, classification, contribution, window)
            for zone, classification
            in zip(change["zones"], change["classifications"])]
