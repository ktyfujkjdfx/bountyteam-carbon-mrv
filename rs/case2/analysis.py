"""The raster analysis itself: request in, typed result out.

No identifier is special. A supplied AOI and a contour drawn by hand take the
same path; the only thing an `aoi_id` buys the caller is not having to paste a
polygon. Nothing here computes a baseline, an uncertainty interval, potential
units or an investment conclusion - those belong to other owners and are
deliberately absent.
"""
from rs.case2 import biomass, notices, optical
from rs.case2.catalog import Dataset, DatasetError, sha256_file
from rs.case2.geometry import geodesic_area_ha, validate, validate_years
from rs.case2.models import (
    ANALYSIS_YEAR_MAX,
    ANALYSIS_YEAR_MIN,
    CARBON_FRACTION,
    CO2_PER_C,
    Coverage,
    RasterAnalysis,
    SourceFile,
    StockChange,
)

METHOD_VERSION = "rs-case2-raster-core/1.0.0"
# A request is treated as fully covered when the gap is below this many
# hectares. Geodesic area is not additive over a partition, so the sum of cell
# weights and the polygon area differ in the seventh significant digit even
# when every cell is present; that is arithmetic, not missing data.
COVERAGE_TOLERANCE_HA = 1e-4


def analyse(geometry, year_start, year_end, *, dataset=None, include_optical=True):
    """Run the raster analysis for one request.

    `geometry` is GeoJSON in WGS84 lon/lat order. Returns a `RasterAnalysis`;
    serialisation happens elsewhere so this stays free of contract field names.
    """
    data = dataset if dataset is not None else Dataset()
    request = validate(geometry)
    year_start, year_end = validate_years(
        year_start, year_end, minimum=ANALYSIS_YEAR_MIN, maximum=ANALYSIS_YEAR_MAX)

    parents = data.parents_for(request)
    change_years = (year_start, year_end)
    timeline_years = _timeline_years(data, parents)
    read_years = sorted(set(timeline_years) | set(change_years))
    for year in change_years:
        if year not in read_years:
            raise DatasetError(
                f"biomass map for {year} is not available for {', '.join(parents)}")

    cells, grids = biomass.build_cells(
        data, request, parents, read_years, validity_years=change_years)
    if not any(cell.valid for cell in cells):
        raise DatasetError(
            "no biomass cell covers the request in both requested years")

    request_area_ha = geodesic_area_ha(request)
    weight_sum = sum(cell.weight_ha for cell in cells)
    biomass_ha = sum(cell.weight_ha for cell in cells if cell.valid)
    sd_ha = biomass.sd_available(cells, change_years)

    timeline = [biomass.stock(cells, year) for year in timeline_years]
    start = biomass.stock(cells, year_start)
    end = biomass.stock(cells, year_end)
    change = _change(start, end, biomass_ha)

    scenes, paired, optical_ha, scene_sources = _optical(
        data, request, parents, change_years, biomass_ha, include_optical)

    raw_change, change_evidence, change_sources = _change_evidence(
        data, request, parents, change_years, scenes, cells, change.delta_tc,
        include_optical)
    scene_sources.extend(change_sources)

    missing_ha = max(0.0, request_area_ha - biomass_ha)
    coverage = Coverage(
        requested_ha=request_area_ha,
        calculated_ha=biomass_ha,
        biomass_ha=biomass_ha,
        biomass_sd_ha=sd_ha,
        optical_paired_ha=optical_ha,
        biomass_fraction=biomass_ha / request_area_ha,
        biomass_sd_fraction=sd_ha / request_area_ha,
        optical_paired_fraction=optical_ha / request_area_ha,
        missing_ha=missing_ha,
        area_difference_ha=biomass_ha - request_area_ha,
        complete=missing_ha <= COVERAGE_TOLERANCE_HA,
    )

    sources = _sources(data, parents, read_years) + scene_sources
    return RasterAnalysis(
        request_area_ha=request_area_ha,
        cell_weight_sum_ha=weight_sum,
        parents=tuple(parents),
        years=tuple(change_years),
        change=change,
        timeline=tuple(timeline),
        coverage=coverage,
        cells=tuple(cells),
        scenes=tuple(scenes),
        paired_optical=paired,
        grids=dict(sorted(grids.items())),
        sources=tuple(sorted(sources, key=lambda item: item.relative_path)),
        parameters={
            "carbon_fraction": CARBON_FRACTION,
            "co2_per_c": CO2_PER_C,
            "pool": "living above-ground woody biomass",
            "method": "stock-difference",
            "area_method": "geodesic on WGS84, per-cell intersection",
            "biomass_product": "ESA CCI Biomass v7.0, AGB and AGB_SD",
            "usable_scl_classes": sorted(optical.USABLE_SCL_CLASSES),
            "negative_reflectance_policy": "preserved, never clamped",
            "method_version": METHOD_VERSION,
        },
        limitations=_limitations(coverage, paired, timeline_years, cells,
                                 change_years, include_optical, change_evidence),
        warnings=_warnings(coverage, paired, cells, change_years, include_optical,
                           change_evidence, scenes, weight_sum, parents),
        change_evidence=change_evidence,
        raw_change=raw_change,
    )


def _timeline_years(data, parents):
    """Years every parent can supply, so the series stays comparable."""
    per_parent = [set(biomass.available_years(data, aoi)) for aoi in parents]
    shared = set.intersection(*per_parent) if per_parent else set()
    return tuple(sorted(shared))


def _change(start, end, area_ha):
    delta_tc = end.total_tc - start.total_tc
    e_tco2e = -delta_tc * CO2_PER_C
    years = end.year - start.year
    return StockChange(
        year_start=start.year,
        year_end=end.year,
        years=years,
        stock_start_tc=start.total_tc,
        stock_end_tc=end.total_tc,
        delta_tc=delta_tc,
        e_tco2e=e_tco2e,
        e_per_ha_per_year=e_tco2e / (area_ha * years),
        normalisation_area_ha=area_ha,
    )


def _optical(data, request, parents, change_years, biomass_ha, include_optical):
    """Per-scene usability and the best paired-valid coverage of the two years."""
    if not include_optical:
        return (), None, 0.0, []
    scenes = []
    sources = []
    masks = {}
    pixels_in_request = 0
    for aoi_id in parents:
        part = request.intersection(data.geometries[aoi_id])
        if part.is_empty:
            continue
        for row in data.scenes_for(aoi_id, change_years):
            quality, usable, _grid = optical.scene_quality(data, row, part)
            scenes.append(quality)
            masks[quality.scene_key] = (quality.year, usable)
            pixels_in_request = max(pixels_in_request, quality.pixels_in_request)
            for key, role in (("reflectance_path", "sentinel2_reflectance"),
                              ("scl_path", "sentinel2_scl")):
                sources.append(_source(data, row[key], role))
    paired = optical.best_pair(
        masks, change_years[0], change_years[1], pixels_in_request)
    # Optical coverage is expressed on the same hectare scale as the other two
    # so a consumer can compare them, but it is measured on the Sentinel grid.
    optical_ha = (paired.paired_usable_fraction * biomass_ha) if paired else 0.0
    return tuple(scenes), paired, optical_ha, sources


def _change_evidence(data, request, parents, change_years, scenes, cells,
                     total_delta_tc, include_optical):
    """Zones, their evidence and their share of the stock change.

    Only the first parent is analysed for change in this stage: a request that
    spans two source areas has two grids and two scene pairs, and merging zones
    across them needs a partition rule that does not exist yet. The limitation
    is reported rather than papered over.
    """
    if not include_optical:
        return None, None, []
    from rs.case2 import change as change_module

    by_key = {scene.scene_key: scene for scene in scenes}
    raw = change_module.analyse_change(
        data, request, parents[0], change_years[0], change_years[1], by_key)
    if not raw.get("available"):
        return None, {"available": False, "reason": raw.get("reason"),
                      "selection": raw.get("selection")}, []

    contribution = change_module.attribute(
        raw, cells, request, change_years[0], change_years[1], total_delta_tc)
    raw["contribution"] = contribution
    raw["zones_geojson"] = zones_module_geojson(raw, contribution)

    sources = [_source(data, f"{parents[0]}/GFC_2025_v1_13.tif", "gfc_lossyear")]
    if raw["fire"]["available"]:
        for detection in raw["fire"]["detections"]:
            stem = detection["granule"]
            for suffix in ("Burn_Date", "QA", "Burn_Date_Uncertainty"):
                sources.append(_source(
                    data, f"{parents[0]}/MODIS/{stem}_{suffix}.tif",
                    "modis_burn_date"))

    evidence = {
        "available": True,
        "analysed_parent": parents[0],
        "pair": raw["pair"],
        "scene_selection": raw["selection"],
        "observation_quality": raw["quality"],
        "indices": raw["indices"],
        "gfc": raw["gfc"],
        "fire": {key: value for key, value in raw["fire"].items()
                 if key != "burned"},
        "zones": change_module.zone_payload(raw, contribution),
        "zone_summary": _zone_summary(raw, contribution),
        "reconciliation": contribution["reconciliation"],
        "sensitivity": change_module.sensitivity(raw),
        "method_note": zones_method_note(),
    }
    return raw, evidence, sources


def zones_module_geojson(raw, contribution):
    from rs.case2 import zones

    return zones.to_geojson(raw["zones"], raw["classifications"], contribution,
                            raw["grid"].crs)


def zones_method_note():
    from rs.case2 import zones

    return zones.METHOD_NOTE


def _zone_summary(raw, contribution):
    from rs.case2 import zones

    counts = {}
    for classification in raw["classifications"]:
        key = f"{classification['fact']}/{classification['cause']}"
        counts[key] = counts.get(key, 0) + 1
    detected_ha = sum(zone["pixel_count"] for zone in raw["zones"]) * zones.PIXEL_AREA_HA
    return {
        "zone_count": len(raw["zones"]),
        "detected_area_ha": round(detected_ha, 6),
        "by_fact_and_cause": dict(sorted(counts.items())),
        "dropped_below_mmu": raw["dropped_below_mmu"],
        "dropped_below_mmu_ha": round(raw["dropped_below_mmu_ha"], 6),
        "minimum_mapping_unit_ha": zones.MIN_ZONE_PIXELS * zones.PIXEL_AREA_HA,
        "morphology": "none applied; the minimum mapping unit is the only filter",
    }


def _sources(data, parents, years):
    files = []
    for aoi_id in parents:
        for year in years:
            files.append(_source(
                data, f"{aoi_id}/CCI_Biomass_{year}.tif", "cci_biomass"))
    for name in ("areas.geojson", "areas.csv", "scenes.csv", "scene_metadata.json"):
        files.append(_source(data, name, "case_table"))
    return files


def _source(data, relative, role):
    from rs.case2.artifacts import SOURCE_ROLES

    if role not in SOURCE_ROLES:
        raise DatasetError(
            f"unknown source role {role!r}; the agreed vocabulary is "
            f"{', '.join(SOURCE_ROLES)}")
    path = data.path(relative)
    return SourceFile(
        relative_path=data.relative(path),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        role=role,
    )


def _warnings(coverage, paired, cells, change_years, include_optical,
              change_evidence, scenes, weight_sum, parents):
    """Every caution the run raised, as `{code, severity, message, details}`.

    This is the machine-readable twin of `_limitations`. Nothing is summarised
    away: a rejected scene, a mixed radiometric pair and an absent burn product
    each keep their own code and their own measurement, because a consumer that
    collapses them into one quality number cannot tell a cloudy request from a
    comparison that must not be read at all.
    """
    items = []
    if not coverage.complete:
        items.append(notices.warning(
            notices.INCOMPLETE_COVERAGE,
            f"{coverage.missing_ha:.4f} ha of the request has no biomass map; "
            f"potential units must not be computed for a partial request",
            missing_ha=coverage.missing_ha,
            requested_ha=coverage.requested_ha,
            calculated_ha=coverage.calculated_ha,
            biomass_fraction_raw=coverage.biomass_fraction,
            tolerance_ha=COVERAGE_TOLERANCE_HA))
    elif coverage.area_difference_ha > 0:
        items.append(notices.warning(
            notices.CELL_WEIGHT_SUM_DIFFERS,
            f"the summed cell weights exceed the polygon area by "
            f"{coverage.area_difference_ha:.9f} ha; geodesic area is not "
            f"additive over a partition, so the raw coverage fraction is "
            f"slightly above 1 and the published one is clamped",
            area_difference_ha=coverage.area_difference_ha,
            biomass_fraction_raw=coverage.biomass_fraction,
            cell_weight_sum_ha=weight_sum))

    valid = [cell for cell in cells if cell.valid]
    invalid = len(cells) - len(valid)
    if invalid:
        items.append(notices.warning(
            notices.INVALID_CELLS,
            f"{invalid} of {len(cells)} cells have no biomass value in both "
            f"requested years and carry null values with valid=false; they are "
            f"excluded from the stock, not counted as zero",
            invalid_cells=invalid, total_cells=len(cells)))
    zero_cells = sum(1 for cell in valid
                     if any(cell.agb[year] == 0 for year in change_years))
    if zero_cells:
        items.append(notices.warning(
            notices.ZERO_AGB_CELLS,
            f"{zero_cells} of {len(valid)} cells carry a published AGB of zero "
            f"on at least one date; zero is a value in this product and is "
            f"summed as zero, not dropped",
            zero_cells=zero_cells, valid_cells=len(valid)))

    items.append(notices.warning(
        notices.MODEL_YEARS_NOT_OBSERVATIONS,
        "CCI years are annual model estimates, not observations on a date; the "
        "Sentinel acquisition dates are reported separately",
        year_start=change_years[0], year_end=change_years[1]))

    if not include_optical:
        items.append(notices.warning(
            notices.OPTICAL_DISABLED,
            "optical reading was switched off for this run; optical coverage is "
            "absent rather than zero, and the biomass result is unaffected"))
    elif paired is None:
        items.append(notices.warning(
            notices.NO_SCENE_PAIR,
            "no Sentinel-2 pair spans the requested years; optical coverage is "
            "reported as zero, which says nothing about biomass coverage",
            scenes_read=len(scenes)))
    elif paired.paired_usable_fraction < 0.5:
        items.append(notices.warning(
            notices.LOW_PAIRED_COVERAGE,
            f"paired-valid optical coverage is only "
            f"{paired.paired_usable_fraction:.1%}; change interpretation from "
            f"imagery is limited on this request",
            paired_usable_fraction=paired.paired_usable_fraction,
            before_scene_key=paired.before_scene_key,
            after_scene_key=paired.after_scene_key))

    if len(parents) > 1:
        items.append(notices.warning(
            notices.ZONES_FIRST_PARENT_ONLY,
            f"the request spans {len(parents)} source areas; the stock covers "
            f"every one of them, but change zones are produced for "
            f"{parents[0]} only, because two grids and two scene pairs need a "
            f"partition rule that is not defined",
            parents=list(parents), zones_parent=parents[0]))

    items.extend(_change_warnings(change_evidence))
    return tuple(items)


def _change_warnings(change_evidence):
    """Cautions that come out of the change evidence, or its absence."""
    if change_evidence is None:
        return ()
    if not change_evidence.get("available"):
        return (notices.warning(
            notices.CHANGE_EVIDENCE_UNAVAILABLE,
            f"change zones were not produced: {change_evidence.get('reason')}",
            reason=change_evidence.get("reason")),)

    items = []
    selection = change_evidence["scene_selection"]
    for rejected in selection.get("rejected", ()):
        items.append(notices.warning(
            notices.SCENE_REJECTED,
            f"scene {rejected['scene_key']} was not used: {rejected['reason']}",
            scene_key=rejected["scene_key"], reason=rejected["reason"]))
    if selection.get("seasonal_warning"):
        items.append(notices.warning(
            notices.SEASONAL_GAP, selection["seasonal_warning"],
            seasonal_gap_days=selection.get("seasonal_gap_days")))
    if selection.get("extent_warning"):
        items.append(notices.warning(
            notices.CHANGE_EXTENT_UNIFORM, selection["extent_warning"]))
    note = selection.get("radiometric_note")
    if note:
        code = (notices.RADIOMETRIC_BASELINE_DIFFERS
                if note["same_offset_convention"]
                else notices.RADIOMETRIC_OFFSET_MIXED)
        items.append(notices.warning(code, note["warning"], **note))

    fire = change_evidence["fire"]
    if not fire["available"]:
        items.append(notices.warning(
            notices.FIRE_PRODUCT_ABSENT, fire["reason"]))

    zones = change_evidence["zones"]
    disturbances = [zone for zone in zones if zone["fact"] != "RECOVERY_INDICATION"]
    unknown = [zone for zone in disturbances if zone["cause"] == "UNKNOWN"]
    if unknown:
        items.append(notices.warning(
            notices.ZONE_CAUSE_UNKNOWN,
            f"{len(unknown)} of {len(disturbances)} disturbance zones have no "
            f"established cause and are reported as UNKNOWN",
            unknown_zones=len(unknown), disturbance_zones=len(disturbances)))
    recovery = [zone for zone in zones if zone["fact"] == "RECOVERY_INDICATION"]
    if recovery:
        items.append(notices.warning(
            notices.RECOVERY_NOT_RECOVERED_CARBON,
            "recovery zones are a spectral indication of regrowth, not evidence "
            "that carbon has been recovered",
            recovery_zones=len(recovery)))
    if zones:
        items.append(notices.warning(
            notices.ZONE_ATTRIBUTION_RESOLUTION, change_evidence["method_note"],
            detection_resolution_m=20, attribution_source="ESA CCI Biomass v7.0"))
    return tuple(items)


def _limitations(coverage, paired, timeline_years, cells, change_years,
                 include_optical, change_evidence=None):
    notes = []
    if not coverage.complete:
        notes.append(
            f"partial coverage: {coverage.missing_ha:.4f} ha of the request has no "
            f"biomass map; potential units are not computed for a partial request")
    if not include_optical:
        notes.append(
            "optical reading was switched off for this run; optical coverage is "
            "absent rather than zero, and the biomass result is unaffected")
    elif paired is None:
        notes.append(
            "no Sentinel-2 pair spans the requested years; optical coverage is "
            "reported as zero, which says nothing about biomass coverage")
    elif paired.paired_usable_fraction < 0.5:
        notes.append(
            f"paired-valid optical coverage is only "
            f"{paired.paired_usable_fraction:.1%}; change interpretation from "
            f"imagery is limited on this request")
    zero_cells = sum(1 for cell in cells
                     if cell.valid and any(cell.agb[y] == 0 for y in change_years))
    if zero_cells:
        notes.append(
            f"{zero_cells} of {sum(1 for c in cells if c.valid)} cells carry a "
            f"published AGB of zero on at least one date; zero is a value in this "
            f"product and is summed as zero, not dropped")
    notes.append(
        "CCI years are annual model estimates, not observations on a date; the "
        "Sentinel acquisition dates are reported separately")
    notes.append(
        f"timeline covers {timeline_years[0]}-{timeline_years[-1]} on the support "
        f"of the requested period, so every year is comparable to every other")
    if change_evidence and change_evidence.get("available"):
        if not change_evidence["fire"]["available"]:
            notes.append(change_evidence["fire"]["reason"])
        disturbances = [zone for zone in change_evidence["zones"]
                        if zone["fact"] != "RECOVERY_INDICATION"]
        unknown = sum(1 for zone in disturbances if zone["cause"] == "UNKNOWN")
        if unknown:
            notes.append(
                f"{unknown} of {len(disturbances)} disturbance zones have no "
                f"established cause and are reported as UNKNOWN")
        if any(zone["fact"] == "RECOVERY_INDICATION"
               for zone in change_evidence["zones"]):
            notes.append(
                "recovery zones are a spectral indication of regrowth, not "
                "evidence that carbon has been recovered")
        selection = change_evidence["scene_selection"]
        for key in ("seasonal_warning", "extent_warning"):
            if selection.get(key):
                notes.append(selection[key])
        if selection.get("radiometric_note"):
            notes.append(selection["radiometric_note"]["warning"])
        notes.append(change_evidence["method_note"])
    elif change_evidence is not None:
        notes.append(
            f"change zones were not produced: {change_evidence.get('reason')}")
    return tuple(notes)
