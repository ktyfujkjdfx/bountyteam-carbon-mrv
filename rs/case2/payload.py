"""The serialisation boundary.

This is the only module that knows what the fields are called on the wire. When
G0 fixes the shared v2 contract, this file changes and the raster core does not.
Floats are rounded here, once, so the same request produces the same bytes on
every platform and the content hash means something.
"""
import math
from dataclasses import asdict

from rs.case2.models import clamp_fraction
from rs.determinism import COORDINATE_DECIMALS

VALUE_DECIMALS = 9


class PayloadError(ValueError):
    """A value cannot be serialised as strict JSON and must not be smuggled out.

    NaN and Infinity are accepted by Python's json module and rejected by every
    strict reader, including the one on the other side of this contract. A
    non-finite number that reaches here is a defect upstream, so it stops the
    run instead of travelling as the literal `NaN` in a file a consumer will
    fail to parse - or, worse, parse as a number.
    """


def _round(value, decimals=VALUE_DECIMALS):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PayloadError(
                f"non-finite value {value!r} in the payload; strict JSON has no "
                f"NaN or Infinity, and a missing measurement must be null")
        rounded = round(value, decimals)
        # Keep zero unsigned so -0.0 and 0.0 cannot hash differently.
        return rounded + 0.0
    if isinstance(value, dict):
        return {key: _round(item, decimals) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round(item, decimals) for item in value]
    return value


def _nullable(value, decimals=VALUE_DECIMALS):
    """A measurement that may be absent: non-finite becomes null, not NaN.

    Used only where the contract declares the field nullable - a cell the map
    does not reach. Everywhere else a non-finite number is an error, because
    silently nulling a required figure hides the defect that produced it.
    """
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return _round(value, decimals)


def _years(mapping):
    """Year-keyed mapping with string keys, as JSON requires.

    Values are nullable: a cell the biomass map does not reach carries null and
    `valid=false`, never a NaN and never a zero, because zero is a published
    biomass value in this product and would be summed as one.
    """
    return {str(year): _nullable(value) for year, value in sorted(mapping.items())}


def _axis(area_ha, fraction):
    """One coverage axis: the area, the published fraction and the raw one.

    Both fractions are kept. The clamped one is what a consumer may display;
    the raw one is the measurement, and it legitimately exceeds 1 by about
    1e-7 because geodesic area is not additive over a partition.
    """
    return {
        "area_ha": _round(area_ha),
        "fraction": _round(clamp_fraction(fraction)),
        "fraction_raw": _round(fraction),
    }


def grid_payload(grid):
    return {
        "crs": grid.crs,
        "transform": _round(list(grid.transform), 12),
        "width": grid.width,
        "height": grid.height,
        "pixel_size": _round(list(grid.pixel_size), 12),
        "units": grid.units,
    }


def analysis_payload(analysis):
    """Full result without the per-cell layer, which is served as its own file."""
    change = analysis.change
    coverage = analysis.coverage
    return {
        "schema": "rs.case2.raster-analysis/1",
        "request": {
            "area_ha": _round(analysis.request_area_ha),
            "year_start": change.year_start,
            "year_end": change.year_end,
            "years": change.years,
            "parents": list(analysis.parents),
            # One disjoint piece per source area. Their areas add up to the
            # request, so a consumer can show where the hectares came from
            # without any risk of counting one of them twice.
            "parts": _round([dict(part) for part in analysis.parts]),
            "parts_note": (
                "pieces are pairwise disjoint; a hectare belongs to exactly one "
                "of them and the overlap is checked, not assumed"
            ),
        },
        "stock_change": {
            "stock_start_tc": _round(change.stock_start_tc),
            "stock_end_tc": _round(change.stock_end_tc),
            "delta_tc": _round(change.delta_tc),
            "e_tco2e": _round(change.e_tco2e),
            "e_per_ha_per_year": _round(change.e_per_ha_per_year),
            "normalisation_area_ha": _round(change.normalisation_area_ha),
            "sign_convention": change.sign_convention,
            "unit": "t CO2e over the period; t CO2e/ha/year for the rate",
        },
        "timeline": [
            {
                "year": item.year,
                "mean_tc_ha": _round(item.mean_tc_ha),
                "total_tc": _round(item.total_tc),
                "mean_agb_t_ha": _round(item.mean_agb_t_ha),
                "cells": item.cells,
                "covered_ha": _round(item.covered_ha),
            }
            for item in analysis.timeline
        ],
        "coverage": {
            "requested_ha": _round(coverage.requested_ha),
            "calculated_ha": _round(coverage.calculated_ha),
            "missing_ha": _round(coverage.missing_ha),
            "area_difference_ha": _round(coverage.area_difference_ha),
            "complete": coverage.complete,
            # The same number the `cells` block reports, repeated here because
            # this is where a consumer assembles its area view and the summed
            # weights are what make the raw fraction exceed 1.
            "cell_weight_sum_ha": _round(analysis.cell_weight_sum_ha),
            "biomass": _axis(coverage.biomass_ha, coverage.biomass_fraction),
            "biomass_sd": _axis(coverage.biomass_sd_ha,
                                coverage.biomass_sd_fraction),
            "optical_paired": _axis(coverage.optical_paired_ha,
                                    coverage.optical_paired_fraction),
            "note": (
                "the three coverages answer different questions and are never "
                "combined; cloud in an optical scene does not reduce biomass coverage"
            ),
            # The contract names four axes. Three are measured here; the fourth
            # is a property of a baseline this module does not own and must not
            # guess. Naming the owner is better than emitting a null axis that
            # looks measured.
            "axes": ["biomass", "biomass_sd", "optical_paired"],
            "axes_not_produced_here": {
                "baseline": (
                    "the share of the request a baseline covers is computed by "
                    "the owner of the baseline, from the baseline it used; RS "
                    "measures no baseline and will not report a coverage for one"
                )
            },
            "area_note": (
                "missing_ha is the clamped shortfall a consumer acts on; "
                "area_difference_ha is the signed technical difference "
                "calculated_ha - requested_ha and is positive when the summed "
                "cell weights exceed the polygon area"
            ),
            "fraction_note": (
                "fraction is clamped to [0, 1] for display; fraction_raw is the "
                "measurement and may exceed 1 by about 1e-7"
            ),
        },
        "cells": {
            "count": len(analysis.cells),
            "valid_count": sum(1 for cell in analysis.cells if cell.valid),
            "invalid_count": sum(1 for cell in analysis.cells if not cell.valid),
            "weight_sum_ha": _round(analysis.cell_weight_sum_ha),
            "artifact": "cells.geojson",
            "note": (
                "an invalid cell keeps its geometry and weight and carries null "
                "AGB and AGB_SD; null is not zero, and zero is a published "
                "biomass value in this product"
            ),
        },
        "optical": {
            "scenes": [
                {
                    "scene_key": scene.scene_key,
                    "item_id": scene.item_id,
                    "aoi_id": scene.aoi_id,
                    "datetime_utc": scene.datetime_utc,
                    "year": scene.year,
                    "processing_baseline": scene.processing_baseline,
                    "reflectance_offset_applied": _round(
                        scene.reflectance_offset_applied),
                    "pixels_in_request": scene.pixels_in_request,
                    "usable_pixels": scene.usable_pixels,
                    "usable_fraction": _round(scene.usable_fraction),
                    "scl_class_pixels": {
                        str(code): count
                        for code, count in sorted(scene.scl_class_pixels.items())
                    },
                    "negative_reflectance_pixels": scene.negative_reflectance_pixels,
                    "non_finite_pixels": scene.non_finite_pixels,
                }
                for scene in analysis.scenes
            ],
            "paired": (
                None if analysis.paired_optical is None else {
                    "before_scene_key": analysis.paired_optical.before_scene_key,
                    "after_scene_key": analysis.paired_optical.after_scene_key,
                    "paired_usable_pixels":
                        analysis.paired_optical.paired_usable_pixels,
                    "pixels_in_request": analysis.paired_optical.pixels_in_request,
                    "paired_usable_fraction": _round(
                        analysis.paired_optical.paired_usable_fraction),
                    "selection_rule": analysis.paired_optical.selection_rule,
                }
            ),
        },
        "change_evidence": _round(analysis.change_evidence),
        "grids": {name: grid_payload(grid)
                  for name, grid in sorted(analysis.grids.items())},
        "parameters": _round(dict(sorted(analysis.parameters.items()))),
        "limitations": list(analysis.limitations),
        "warnings": _round([dict(item) for item in analysis.warnings]),
        # An informational panel. Nothing in it enters a carbon number, and
        # every block repeats `affects_q: false` so a block that travels alone
        # still says so.
        "risks": _round(dict(analysis.risks)),
    }


def cells_payload(analysis):
    """Per-cell layer for the carbon engine, as GeoJSON on the native CCI grid.

    A summary standard deviation cannot express spatial dependence, so the
    consumer gets the cells themselves: weight, both dates, both deviations.
    """
    features = []
    for cell in analysis.cells:
        lon_min, lat_min, lon_max, lat_max = cell.bounds
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [round(lon_min, COORDINATE_DECIMALS), round(lat_min, COORDINATE_DECIMALS)],
                    [round(lon_max, COORDINATE_DECIMALS), round(lat_min, COORDINATE_DECIMALS)],
                    [round(lon_max, COORDINATE_DECIMALS), round(lat_max, COORDINATE_DECIMALS)],
                    [round(lon_min, COORDINATE_DECIMALS), round(lat_max, COORDINATE_DECIMALS)],
                    [round(lon_min, COORDINATE_DECIMALS), round(lat_min, COORDINATE_DECIMALS)],
                ]],
            },
            "properties": {
                "cell_id": cell.cell_id,
                "parent_aoi_id": cell.parent_aoi_id,
                "row": cell.row,
                "col": cell.col,
                "centroid": [round(cell.centroid[0], COORDINATE_DECIMALS),
                             round(cell.centroid[1], COORDINATE_DECIMALS)],
                "weight_ha": _round(cell.weight_ha),
                "agb_t_ha": _years(cell.agb),
                "agb_sd_t_ha": _years(cell.agb_sd),
                "valid": cell.valid,
            },
        })
    return {
        "type": "FeatureCollection",
        "name": "cci_cells",
        "note": (
            "native ESA CCI model cells; weight_ha is the geodesic area of the "
            "intersection with the request, not the area of the whole cell"
        ),
        "features": features,
    }


def ensure_strict(value, path="$"):
    """Raise unless every number in `value` is finite and every key a string.

    `_round` already refuses a non-finite number as it serialises, but records
    written after that - the artifact rows, for instance - never pass through
    it. This is the last gate before bytes are hashed, so what a consumer
    receives is strict JSON by construction rather than by inspection.
    """
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PayloadError(f"non-finite value at {path}: {value!r}")
        return value
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PayloadError(f"non-string key at {path}: {key!r}")
            ensure_strict(item, f"{path}.{key}")
        return value
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            ensure_strict(item, f"{path}[{index}]")
        return value
    raise PayloadError(f"unserialisable type at {path}: {type(value).__name__}")


def as_dict(analysis):
    """Raw dataclass view, for callers that want the internal shape."""
    return asdict(analysis)
