"""Where the change is, what it is, and how much of the carbon change it carries.

Three separations run through this module and none of them is cosmetic.

**Fact and cause are different claims.** That cover was lost is something a
published loss-year product can establish. Why it was lost needs its own
evidence, and where there is none the answer stays `UNKNOWN` rather than
drifting to the most likely story.

**Detection resolution and carbon resolution are different.** Zones are drawn on
the 20 m Sentinel grid; the carbon they carry comes from CCI cells about 100 m
across. A zone's contribution therefore assumes the cell's change is spread
evenly inside the cell. That assumption is stated in the output, because a 20 m
outline invites the reader to believe in 20 m carbon accuracy that does not
exist.

**Contributions must reconcile.** Every zone's share of the stock change is
reported together with the remainder outside all zones, and the two add back to
the total on the same calculated area. A set of contributions that does not add
up is a set of numbers, not an explanation.
"""
import numpy
import rasterio.features
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform
from shapely.strtree import STRtree

from rs.case2.geometry import geodesic_area_ha
from rs.case2.grid import cell_polygon
from rs.case2.models import CARBON_FRACTION, CO2_PER_C

# One hectare on the 20 m grid. Smaller patches are dropped as a minimum
# mapping unit and the dropped count is reported rather than hidden.
PIXEL_AREA_HA = 0.04
MIN_ZONE_PIXELS = 25
CONNECTIVITY = 8
# A zone counts as cover loss when most of it is flagged by the loss-year
# product, and as fire-supported when most of it carries a trusted burn date.
MAJORITY = 0.5

FACT_TREE_COVER_LOSS = "TREE_COVER_LOSS"
FACT_SPECTRAL_CHANGE_ONLY = "SPECTRAL_CHANGE_ONLY"
FACT_RECOVERY_INDICATION = "RECOVERY_INDICATION"
CAUSE_FIRE_SUPPORTED = "FIRE_SUPPORTED"
CAUSE_UNKNOWN = "UNKNOWN"
# A regrowth signal has no disturbance to explain, so asking for its cause is
# the wrong question rather than an unanswered one.
CAUSE_NOT_APPLICABLE = "NOT_APPLICABLE"

METHOD_NOTE = (
    "zones are detected on the 20 m Sentinel grid; carbon is attributed from "
    "CCI cells about 100 m across, assuming the cell's change is distributed "
    "evenly within the cell"
)


def label_components(mask, connectivity=CONNECTIVITY):
    """Label connected True regions of `mask`, 1-based; 0 is background.

    Written out rather than taken from a library so the labelling has no
    optional dependency and no build-specific behaviour: the scan order is
    fixed, so labels are assigned identically on every platform.
    """
    height, width = mask.shape
    labels = numpy.zeros((height, width), dtype="int32")
    if not mask.any():
        return labels, {}
    if connectivity == 8:
        neighbours = [(-1, -1), (-1, 0), (-1, 1), (0, -1),
                      (0, 1), (1, -1), (1, 0), (1, 1)]
    else:
        neighbours = [(-1, 0), (0, -1), (0, 1), (1, 0)]

    counts = {}
    current = 0
    for row in range(height):
        for col in range(width):
            if not mask[row, col] or labels[row, col]:
                continue
            current += 1
            size = 0
            stack = [(row, col)]
            labels[row, col] = current
            while stack:
                r, c = stack.pop()
                size += 1
                for dr, dc in neighbours:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < height and 0 <= nc < width:
                        if mask[nr, nc] and not labels[nr, nc]:
                            labels[nr, nc] = current
                            stack.append((nr, nc))
            counts[current] = size
    return labels, counts


def polygonise(labels, transform, keep):
    """Polygon per kept label, in the grid's own CRS."""
    selected = numpy.where(numpy.isin(labels, list(keep)), labels, 0)
    polygons = {}
    for geometry, value in rasterio.features.shapes(
            selected.astype("int32"), mask=selected > 0,
            transform=transform, connectivity=CONNECTIVITY):
        label = int(value)
        polygon = shape(geometry)
        if label in polygons:
            polygons[label] = polygons[label].union(polygon)
        else:
            polygons[label] = polygon
    return polygons


def detect(evidence, transform, min_pixels=MIN_ZONE_PIXELS):
    """Build loss and recovery zones from the stacked evidence masks.

    The two candidate masks are mutually exclusive by construction - a pixel
    cannot both lose and regain signal - so the resulting zones never overlap
    and their shares can be summed.
    """
    loss_candidate = evidence["loss_candidate"]
    recovery_candidate = evidence["recovery_candidate"] & ~loss_candidate

    result = {"zones": [], "dropped_below_mmu": 0,
              "dropped_below_mmu_ha": 0.0}
    next_id = 1
    for kind, candidate in (("loss", loss_candidate), ("recovery", recovery_candidate)):
        labels, counts = label_components(candidate)
        keep = {label for label, size in counts.items() if size >= min_pixels}
        dropped = {label: size for label, size in counts.items() if label not in keep}
        result["dropped_below_mmu"] += len(dropped)
        result["dropped_below_mmu_ha"] += sum(dropped.values()) * PIXEL_AREA_HA
        if not keep:
            continue
        for label, polygon in sorted(polygonise(labels, transform, keep).items()):
            pixels = labels == label
            result["zones"].append({
                "zone_id": f"Z{next_id:04d}",
                "kind": kind,
                "polygon": polygon,
                "pixel_count": counts[label],
                "pixel_mask": pixels,
            })
            next_id += 1
    return result


def classify(zone, evidence, fire):
    """Attach the fact, the cause, and the evidence each rests on."""
    pixels = zone["pixel_mask"]
    total = int(pixels.sum())
    gfc_loss = int((evidence["gfc_loss"] & pixels).sum())
    spectral = int((evidence["spectral_change"] & pixels).sum())
    paired = int((evidence["paired_valid"] & pixels).sum())
    burned = int((fire["burned"] & pixels).sum())

    if zone["kind"] == "recovery":
        fact = FACT_RECOVERY_INDICATION
    elif total and gfc_loss / total >= MAJORITY:
        fact = FACT_TREE_COVER_LOSS
    else:
        fact = FACT_SPECTRAL_CHANGE_ONLY

    cause = CAUSE_UNKNOWN
    cause_reason = "no evidence in the supplied products establishes a cause"
    if zone["kind"] == "recovery":
        cause = CAUSE_NOT_APPLICABLE
        cause_reason = (
            "a regrowth indication has no disturbance cause; it is also not "
            "evidence of recovered carbon")
    elif not fire["available"]:
        cause_reason = fire["reason"]
    elif zone["kind"] == "loss" and total and burned / total >= MAJORITY:
        cause = CAUSE_FIRE_SUPPORTED
        cause_reason = (
            "a trusted MODIS burn date covers most of the zone; the burn "
            "product is about 463 m and does not give a 20 m perimeter")

    return {
        "fact": fact,
        "cause": cause,
        "cause_reason": cause_reason,
        "evidence": {
            "pixels": total,
            "gfc_loss_fraction": (gfc_loss / total) if total else 0.0,
            "spectral_change_fraction": (spectral / total) if total else 0.0,
            "paired_valid_fraction": (paired / total) if total else 0.0,
            "fire_fraction": (burned / total) if total else 0.0,
        },
    }


def contributions(zones, cells, request, grid_crs, year_start, year_end):
    """Share of the stock change carried by each zone, plus the remainder.

    Shares come from the geodesic overlap between a zone and the part of each
    CCI cell that lies inside the request. Because zones do not overlap, the
    shares of one cell sum to at most one and the remainder is whatever is left
    of that cell.
    """
    to_wgs84 = Transformer.from_crs(grid_crs, "EPSG:4326", always_xy=True)
    shapes_wgs84 = [
        shapely_transform(lambda x, y: to_wgs84.transform(x, y), zone["polygon"])
        for zone in zones
    ]
    totals = {zone["zone_id"]: 0.0 for zone in zones}
    areas = {zone["zone_id"]: 0.0 for zone in zones}
    remainder_tc = 0.0
    if shapes_wgs84:
        tree = STRtree(shapes_wgs84)
    else:
        tree = None

    for cell in cells:
        if not cell.valid:
            continue
        delta_tc_per_ha = (cell.agb[year_end] - cell.agb[year_start]) * CARBON_FRACTION
        piece = _cell_piece(cell, request)
        piece_area = geodesic_area_ha(piece) if not piece.is_empty else 0.0
        if piece_area <= 0:
            continue
        covered = 0.0
        if tree is not None:
            for index in tree.query(piece):
                overlap = piece.intersection(shapes_wgs84[int(index)])
                if overlap.is_empty:
                    continue
                overlap_ha = geodesic_area_ha(overlap)
                if overlap_ha <= 0:
                    continue
                zone_id = zones[int(index)]["zone_id"]
                totals[zone_id] += delta_tc_per_ha * overlap_ha
                areas[zone_id] += overlap_ha
                covered += overlap_ha
        leftover = max(0.0, piece_area - covered)
        remainder_tc += delta_tc_per_ha * leftover

    return {
        "per_zone_delta_tc": totals,
        "per_zone_overlap_ha": areas,
        "remainder_delta_tc": remainder_tc,
    }


def _cell_piece(cell, request):
    """The part of one CCI cell that lies inside the request."""
    from shapely.geometry import box

    lon_min, lat_min, lon_max, lat_max = cell.bounds
    return box(lon_min, lat_min, lon_max, lat_max).intersection(request)


def reconcile(contribution, total_delta_tc, tolerance_tc=1e-3):
    """Check that zone shares plus the remainder equal the whole change."""
    zone_sum = sum(contribution["per_zone_delta_tc"].values())
    accounted = zone_sum + contribution["remainder_delta_tc"]
    residual = total_delta_tc - accounted
    return {
        "zone_delta_tc": zone_sum,
        "remainder_delta_tc": contribution["remainder_delta_tc"],
        "accounted_delta_tc": accounted,
        "total_delta_tc": total_delta_tc,
        "residual_tc": residual,
        # The residual is float64 accumulation over tens of thousands of
        # geodesic areas. One gram of carbon per thousand tonnes is noise; the
        # check still fails loudly if an overlap is double counted or dropped.
        "balanced": abs(residual) <= max(tolerance_tc, abs(total_delta_tc) * 1e-7),
        "tolerance_tc": max(tolerance_tc, abs(total_delta_tc) * 1e-7),
        "note": (
            "zone contributions and the remainder are parts of one stock "
            "difference; they are never added to a separately computed fire "
            "emission, which would count the same loss twice"),
    }


def to_geojson(zones, classifications, contribution, grid_crs):
    """Zones as WGS84 GeoJSON, with the fact, the cause and the contribution."""
    from rs.determinism import round_geojson

    to_wgs84 = Transformer.from_crs(grid_crs, "EPSG:4326", always_xy=True)
    features = []
    for zone, classification in zip(zones, classifications):
        polygon = shapely_transform(
            lambda x, y: to_wgs84.transform(x, y), zone["polygon"])
        zone_id = zone["zone_id"]
        delta_tc = contribution["per_zone_delta_tc"].get(zone_id, 0.0)
        features.append({
            "type": "Feature",
            "properties": {
                "zone_id": zone_id,
                "fact": classification["fact"],
                "cause": classification["cause"],
                "cause_reason": classification["cause_reason"],
                "pixel_count": zone["pixel_count"],
                "detected_area_ha": round(zone["pixel_count"] * PIXEL_AREA_HA, 6),
                "cci_overlap_ha": round(
                    contribution["per_zone_overlap_ha"].get(zone_id, 0.0), 6),
                "delta_tc": round(delta_tc, 9),
                "contribution_tco2e": round(-delta_tc * CO2_PER_C, 9),
                "evidence": classification["evidence"],
            },
            "geometry": mapping(polygon),
        })
    return round_geojson({
        "type": "FeatureCollection",
        "name": "change_zones",
        "note": METHOD_NOTE,
        "features": features,
    })
