"""External evidence about cover loss and fire.

Two published products, read on their own terms:

* **Global Forest Change** records one loss year per pixel. A loss inside the
  analysed interval is a fact about cover; it says nothing about how much
  biomass went, and nothing about why.
* **MODIS MCD64A1** records an approximate burn date with a quality mask and a
  date uncertainty. A positive burn date is trusted only where the quality bits
  say the pixel is land and had enough observations.

MODIS was supplied for the two Mordovia plots only. Elsewhere the correct
statement is that the product was not provided, never that no fire occurred.
"""
from datetime import date, timedelta

import numpy

from rs.case2.catalog import DatasetError
from rs.case2.lookup import sample_on_grid

# Band order of the supplied three-band GFC crop.
GFC_TREECOVER_BAND = 1
GFC_LOSSYEAR_BAND = 2
GFC_DATAMASK_BAND = 3
GFC_LAND = 1

# QA bit 0 is land, bit 1 is "enough data for a reliable decision". The task
# materials say a positive burn date is checked against these two first.
MODIS_QA_LAND_BIT = 0
MODIS_QA_ENOUGH_DATA_BIT = 1
MODIS_NOT_BURNED = 0
MODIS_NODATA = -1


def loss_year_codes(year_start, year_end):
    """GFC codes for losses that happened inside `(year_start, year_end]`.

    Code 1 is the year 2001, so code = year - 2000. A stock difference between
    the 2019 and 2024 maps is affected by losses during 2020 to 2024, which is
    codes 20 to 24 - the range the data description names explicitly.
    """
    return tuple(range(year_start - 1999, year_end - 2000 + 1))


def gfc_on_grid(dataset, aoi_id, transform, width, height, crs, year_start, year_end):
    """Sample GFC onto a target grid and mark loss inside the interval."""
    path = dataset.path(f"{aoi_id}/GFC_2025_v1_13.tif")
    loss, loss_inside = sample_on_grid(
        path, transform, width, height, crs, band=GFC_LOSSYEAR_BAND)
    datamask, mask_inside = sample_on_grid(
        path, transform, width, height, crs, band=GFC_DATAMASK_BAND)
    treecover, _cover_inside = sample_on_grid(
        path, transform, width, height, crs, band=GFC_TREECOVER_BAND)
    codes = loss_year_codes(year_start, year_end)
    covered = loss_inside & mask_inside
    land = covered & (datamask == GFC_LAND)
    in_interval = land & numpy.isin(loss, codes)
    return {
        "loss_in_interval": in_interval,
        "loss_year_code": numpy.where(covered, loss, 0),
        "land": land,
        "treecover2000": treecover,
        "covered": covered,
        "codes": codes,
    }


def modis_available(dataset, aoi_id):
    return (dataset.root / aoi_id / "MODIS").is_dir()


def _burn_products(dataset, aoi_id):
    directory = dataset.root / aoi_id / "MODIS"
    return sorted(directory.glob("*_Burn_Date.tif"))


def doy_to_date(year, doy):
    return date(year, 1, 1) + timedelta(days=int(doy) - 1)


def fire_on_grid(dataset, aoi_id, transform, width, height, crs,
                 year_start, year_end):
    """Burn evidence sampled onto a target grid, or an explicit absence.

    Returns a dict with `available`; when False the caller must say the product
    was not supplied rather than reporting an absence of fire.
    """
    if not modis_available(dataset, aoi_id):
        return {
            "available": False,
            "reason": (f"MODIS MCD64A1 was not supplied for {aoi_id}; this is an "
                       f"absence of the product, not evidence that nothing burned"),
            "burned": numpy.zeros((height, width), dtype=bool),
        }

    burned = numpy.zeros((height, width), dtype=bool)
    detections = []
    for burn_path in _burn_products(dataset, aoi_id):
        stem = burn_path.name.replace("_Burn_Date.tif", "")
        qa_path = burn_path.with_name(f"{stem}_QA.tif")
        uncertainty_path = burn_path.with_name(f"{stem}_Burn_Date_Uncertainty.tif")
        if not qa_path.is_file():
            raise DatasetError(f"MODIS QA missing for {stem}")
        # The product year is encoded in the granule id as A<year><doy>.
        product_year = int(stem.split(".")[1][1:5])

        burn, burn_inside = sample_on_grid(burn_path, transform, width, height, crs,
                                           fill=MODIS_NODATA)
        qa, qa_inside = sample_on_grid(qa_path, transform, width, height, crs)
        uncertainty, _ = sample_on_grid(
            uncertainty_path, transform, width, height, crs)

        trusted = (burn_inside & qa_inside
                   & (((qa >> MODIS_QA_LAND_BIT) & 1) == 1)
                   & (((qa >> MODIS_QA_ENOUGH_DATA_BIT) & 1) == 1))
        positive = trusted & (burn > MODIS_NOT_BURNED)
        if not positive.any():
            continue
        days = burn[positive]
        first, last = int(days.min()), int(days.max())
        start_date = doy_to_date(product_year, first)
        end_date = doy_to_date(product_year, last)
        if not (year_start < start_date.year <= year_end
                or year_start < end_date.year <= year_end):
            continue
        burned |= positive
        detections.append({
            "granule": stem,
            "product_year": product_year,
            "pixels_on_target_grid": int(positive.sum()),
            "date_min": start_date.isoformat(),
            "date_max": end_date.isoformat(),
            "date_uncertainty_days_min": int(uncertainty[positive].min()),
            "date_uncertainty_days_max": int(uncertainty[positive].max()),
            # Kept out of the payload; it is what lets a zone name the event
            # that supports it instead of naming every event in the period.
            "mask": positive,
        })

    return {
        "available": True,
        "burned": burned,
        "detections": detections,
        "resolution_note": (
            "MODIS cells are about 463 m; a burn flag resampled onto the 20 m "
            "grid marks the cell that covers each pixel and is not a 20 m "
            "burn perimeter"),
        "qa_rule": "burn date trusted only where QA bits 0 (land) and 1 (enough data) are set",
    }
