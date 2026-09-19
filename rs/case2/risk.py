"""Three risk flags for an investor, measured and kept away from the arithmetic.

This is an extra panel, not a step in the method. Nothing here enters the stock
difference, the uncertainty interval or the potential units; every block says so
in its own `affects_q` field, which is always false. The official formula is
unchanged by anything on this page.

What the blocks are allowed to be is measurements with a stated banding. A count
of confirmed burn episodes is a fact about the past. The share of the request
the loss-year product flags is a fact about a published raster. The share of the
request two dates could actually be compared over is a fact about the
observations. Each is reported with the numbers it was banded from, so a reader
who disagrees with the bands can use the measurement instead.

What they are not allowed to become is a probability of fire or a financial
discount. Turning "one confirmed episode in this period" into "a 14% chance of
burning next year" needs a hazard model, a calibration set and a validation
that none of this package contains. The line is drawn here rather than left to
the reader, because a level on a dashboard is read as a forecast unless it says
otherwise.
"""
LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
UNKNOWN = "UNKNOWN"

# Risks never change a carbon number. The field is repeated on every block
# rather than stated once, because a block travels on its own.
AFFECTS_Q = False

PANEL_NOTE = (
    "an informational panel for an investor; no level here enters the stock "
    "difference, the uncertainty interval or the potential units, and none of "
    "them is a probability or a discount"
)

# Bands for the share of the request the loss-year product flags. They are
# reporting bands on a measured share, not a model, and the share travels with
# the level so a reader can band it differently.
LOSS_BANDS = ((0.01, LOW), (0.10, MEDIUM), (float("inf"), HIGH))
# Bands for the share of the request the two dates could be compared over.
PAIRED_BANDS = ((0.50, HIGH), (0.90, MEDIUM), (float("inf"), LOW))


def _band(value, bands):
    for boundary, level in bands:
        if value < boundary:
            return level
    raise AssertionError("unreachable: the last boundary is infinite")


def assess(coverage, scenes, change_evidence, parents, change_years,
           include_optical):
    """The three blocks, each independent of the other two."""
    period = {"year_start": change_years[0], "year_end": change_years[1]}
    return {
        "fire_risk_evidence": fire_risk(change_evidence, parents, period),
        "forest_loss_evidence": forest_loss(change_evidence, parents, period),
        "data_quality_risk": data_quality(
            coverage, scenes, change_evidence, period, include_optical),
        "affects_q": AFFECTS_Q,
        "note": PANEL_NOTE,
    }


def fire_risk(change_evidence, parents, period):
    """Confirmed burn episodes in the analysed period, and how many there were.

    An episode is a MODIS granule whose burn date is trusted by its own QA bits
    and falls inside the period. Where the product was not supplied the level is
    UNKNOWN, never LOW: an absent product is not an absence of fire, and that
    distinction is the whole reason this block exists rather than a boolean.
    """
    source = {
        "product": "MODIS MCD64A1 burned area",
        "version": "Collection 6.1",
        "resolution_m": 463,
        "qa_rule": "burn date trusted only where QA bits 0 and 1 are set",
    }
    limitations = [
        "a count of confirmed past episodes is not a probability of future "
        "fire; deriving one needs a hazard model this package does not contain",
        "the burn product is about 463 m and dates an event rather than "
        "delineating it",
    ]
    if change_evidence is None or not change_evidence.get("available"):
        return _block(UNKNOWN, {"episodes": None}, source, period,
                      [*limitations,
                       "no change evidence was produced for this request, so "
                       "the burn product was not read"],
                      "no evidence was read")

    fire = change_evidence["fire"]
    if not fire["available"]:
        return _block(
            UNKNOWN, {"episodes": None, "product_supplied": False}, source,
            period, [*limitations, fire["reason"]],
            "the product was not supplied for this area, which is not an "
            "absence of fire")

    detections = fire.get("detections", [])
    episodes = len(detections)
    level = LOW if episodes == 0 else (MEDIUM if episodes == 1 else HIGH)
    basis = {
        "episodes": episodes,
        "product_supplied": True,
        "analysed_area": parents[0],
        "episode_dates": [
            {"granule": detection["granule"],
             "date_min": detection["date_min"],
             "date_max": detection["date_max"],
             "date_uncertainty_days_max":
                 detection["date_uncertainty_days_max"]}
            for detection in detections],
        "zones_with_a_confirmed_cause": sum(
            1 for zone in change_evidence["zones"]
            if zone["cause"] == "FIRE_SUPPORTED"),
    }
    return _block(level, basis, source, period, limitations,
                  "no confirmed episode is LOW, one is MEDIUM, more than one "
                  "is HIGH, counted over the analysed period only")


def forest_loss(change_evidence, parents, period):
    """How much of the request the loss-year product flags inside the period."""
    source = {
        "product": "Global Forest Change tree cover loss year",
        "version": "2025 v1.13",
        "resolution_m": 30,
        "sampled_onto": "the 20 m analysis grid by pixel centre",
    }
    limitations = [
        "cover loss is a fact about canopy, not a measure of biomass removed; "
        "the carbon comes from the stock difference, not from this share",
        "the loss year is annual, so a loss inside the period is dated to a "
        "year and not to a day",
    ]
    if change_evidence is None or not change_evidence.get("available"):
        return _block(UNKNOWN, {"loss_fraction": None}, source, period,
                      [*limitations,
                       "no change evidence was produced for this request, so "
                       "the loss-year product was not read"],
                      "no evidence was read")

    gfc = change_evidence["gfc"]
    covered = gfc["covered_pixels"]
    loss = gfc["loss_pixels_in_request"]
    if not covered:
        return _block(UNKNOWN, {"loss_fraction": None, "covered_pixels": 0},
                      source, period,
                      [*limitations,
                       "the loss-year product does not cover this request"],
                      "the product does not reach the request")

    fraction = loss / covered
    basis = {
        "loss_fraction": fraction,
        "loss_pixels": loss,
        "covered_pixels": covered,
        # On the 20 m grid the analysis samples the product onto.
        "loss_area_ha": round(loss * 0.04, 6),
        "loss_year_codes": list(gfc["loss_year_codes"]),
        "analysed_area": parents[0],
        "zones_with_established_cover_loss": sum(
            1 for zone in change_evidence["zones"]
            if zone["fact"] == "TREE_COVER_LOSS"),
    }
    return _block(_band(fraction, LOSS_BANDS), basis, source, period,
                  limitations,
                  "below 1% of the covered request is LOW, below 10% is "
                  "MEDIUM, at or above 10% is HIGH")


def data_quality(coverage, scenes, change_evidence, period, include_optical):
    """Whether the observations were good enough to read a change from.

    Deliberately separate from the two above. A cloudy request is not a risky
    forest, and a clear one is not a safe investment; merging observation
    quality into a hazard flag is how a dashboard ends up telling an investor
    something the data never said.
    """
    source = {
        "product": "Sentinel-2 L2A scene classification and the paired-valid mask",
        "usable_classes": [4, 5],
        "note": "biomass coverage is unaffected by any of this",
    }
    limitations = [
        "optical quality constrains what can be read from imagery; it does not "
        "reduce the biomass coverage the carbon result rests on",
    ]
    if not include_optical:
        return _block(UNKNOWN, {"paired_valid_fraction": None}, source, period,
                      [*limitations,
                       "optical reading was switched off for this run; the "
                       "coverage is absent rather than zero"],
                      "optical reading was switched off")

    basis = {
        "optical_paired_coverage_fraction": coverage.optical_paired_fraction,
        "scenes_read": len(scenes),
        "rejected_scenes": [],
        "paired_valid_fraction": None,
        "observation_gap_fraction": None,
        "gap_reasons": {},
        "radiometric_offset_mixed": None,
        "seasonal_gap_days": None,
    }
    reasons = []
    level = _band(coverage.optical_paired_fraction, PAIRED_BANDS)

    if change_evidence is not None and change_evidence.get("available"):
        selection = change_evidence["scene_selection"]
        quality = change_evidence["observation_quality"]
        gaps = change_evidence["observation_gaps"]
        note = selection.get("radiometric_note")
        mixed = bool(note) and not note["same_offset_convention"]
        basis.update({
            "paired_valid_fraction": quality["paired_valid_fraction"],
            "observation_gap_fraction": gaps["gap_fraction"],
            "gap_reasons": {reason: block["area_ha"]
                            for reason, block in gaps["by_reason"].items()},
            "rejected_scenes": [row["scene_key"]
                                for row in selection.get("rejected", ())],
            "radiometric_offset_mixed": mixed,
            "seasonal_gap_days": selection.get("seasonal_gap_days"),
        })
        level = _highest(level, _band(quality["paired_valid_fraction"],
                                      PAIRED_BANDS))
        if mixed:
            # The measured case: a pair across the 04.00 change reads a control
            # forest as regrowth. Nothing else about the request can redeem it.
            level = HIGH
            reasons.append("the two scenes straddle the 04.00 radiometric "
                           "offset change, so the comparison is not safe to "
                           "read as change")
        elif note:
            level = _highest(level, MEDIUM)
            reasons.append("the two scenes come from different processing "
                           "baselines on one offset convention")
        if basis["rejected_scenes"]:
            level = _highest(level, MEDIUM)
            reasons.append(f"{len(basis['rejected_scenes'])} scene(s) were "
                           f"below the usability floor and not used")
        if gaps["gap_fraction"] > 0.05:
            level = _highest(level, MEDIUM)
            reasons.append(f"{gaps['gap_fraction']:.1%} of the request could "
                           f"not be compared between the two dates")
    elif change_evidence is not None:
        level = _highest(level, MEDIUM)
        reasons.append(f"no change evidence was produced: "
                       f"{change_evidence.get('reason')}")

    basis["level_reasons"] = reasons
    return _block(level, basis, source, period, limitations,
                  "banded on the paired-valid share of the request, raised to "
                  "MEDIUM by a rejected scene, a differing processing baseline "
                  "or gaps above 5%, and to HIGH by a mixed offset convention")


def _highest(left, right):
    order = (UNKNOWN, LOW, MEDIUM, HIGH)
    return max((left, right), key=order.index)


def _block(level, basis, source, period, limitations, rule):
    return {
        "level": level,
        "basis": basis,
        "rule": rule,
        "source": source,
        "period": period,
        "limitations": list(limitations),
        "affects_q": AFFECTS_Q,
    }
