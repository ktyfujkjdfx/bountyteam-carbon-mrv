"""The serialisation boundary.

This is the only module that knows what the fields are called on the wire. When
G0 fixes the shared v2 contract, this file changes and the raster core does not.
Floats are rounded here, once, so the same request produces the same bytes on
every platform and the content hash means something.
"""
from dataclasses import asdict

from rs.determinism import COORDINATE_DECIMALS

VALUE_DECIMALS = 9


def _round(value, decimals=VALUE_DECIMALS):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        rounded = round(value, decimals)
        # Keep zero unsigned so -0.0 and 0.0 cannot hash differently.
        return rounded + 0.0
    if isinstance(value, dict):
        return {key: _round(item, decimals) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round(item, decimals) for item in value]
    return value


def _years(mapping):
    """Year-keyed mapping with string keys, as JSON requires."""
    return {str(year): _round(value) for year, value in sorted(mapping.items())}


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
            "complete": coverage.complete,
            "biomass": {
                "area_ha": _round(coverage.biomass_ha),
                "fraction": _round(coverage.biomass_fraction),
            },
            "biomass_sd": {
                "area_ha": _round(coverage.biomass_sd_ha),
                "fraction": _round(coverage.biomass_sd_fraction),
            },
            "optical_paired": {
                "area_ha": _round(coverage.optical_paired_ha),
                "fraction": _round(coverage.optical_paired_fraction),
            },
            "note": (
                "the three coverages answer different questions and are never "
                "combined; cloud in an optical scene does not reduce biomass coverage"
            ),
        },
        "cells": {
            "count": len(analysis.cells),
            "valid_count": sum(1 for cell in analysis.cells if cell.valid),
            "weight_sum_ha": _round(analysis.cell_weight_sum_ha),
            "artifact": "cells.geojson",
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
        "grids": {name: grid_payload(grid)
                  for name, grid in sorted(analysis.grids.items())},
        "parameters": _round(dict(sorted(analysis.parameters.items()))),
        "limitations": list(analysis.limitations),
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


def as_dict(analysis):
    """Raw dataclass view, for callers that want the internal shape."""
    return asdict(analysis)
