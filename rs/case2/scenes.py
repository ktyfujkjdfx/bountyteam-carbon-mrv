"""Choosing which two Sentinel-2 scenes a change is measured on.

The rule is written down and applied the same way to every request, because the
alternative - picking the pair that produces the nicest answer - is not a
method. In order:

1. Only scenes of the requested start year and end year are candidates.
2. A scene must see at least `USABLE_FLOOR` of the request on the usable
   classes. This is what removes the September 2021 scene over Mordovia, where
   roughly 2% of the crop is usable; it is removed for being unobservable, not
   for being inconvenient.
3. A pair whose two scenes share the radiometric offset convention beats one
   that does not. This rule is not a preference, it is a measurement: on the
   control plot, pairs mixing a pre-04.00 scene with a post-04.00 one give a
   median dNBR of about -0.86 and flag the entire forest as regrowth, while
   pairs on one convention give about -0.25 over the same ground and the same
   years. Mixing conventions is responsible for roughly three quarters of that
   apparent change. See `research.py`.
4. Among the survivors, the pair with the smallest difference in day of year
   wins. Two summer scenes a few days apart in the seasonal cycle are
   comparable; a July scene against a September one is not, and the difference
   in phenology would be read as a change in vegetation.
5. Ties break on the larger paired-valid area, then on scene key, so the same
   request always selects the same pair.

Every rejected scene is reported with the reason, so a reader can see what was
available and why it was not used.
"""
from datetime import datetime

USABLE_FLOOR = 0.5
# Above this the two dates sit in different parts of the season and the
# comparison carries a phenological difference that is not a disturbance.
SEASONAL_GAP_WARN_DAYS = 30

SELECTION_RULE = (
    "candidates limited to the requested years; scenes seeing less than "
    f"{USABLE_FLOOR:.0%} of the request on usable classes are rejected; a pair "
    "sharing the radiometric offset convention beats one that does not; among "
    "the rest the pair with the smallest day-of-year difference wins, ties "
    "broken by larger paired-valid area then by scene key"
)


def day_of_year(datetime_utc):
    stamp = datetime.strptime(datetime_utc[:19], "%Y-%m-%dT%H:%M:%S")
    return stamp.timetuple().tm_yday


def rejected_reason(scene, floor=USABLE_FLOOR):
    if scene.pixels_in_request == 0:
        return "the scene does not cover the request"
    if scene.usable_fraction < floor:
        return (f"only {scene.usable_fraction:.1%} of the request is usable, "
                f"below the {floor:.0%} floor")
    return None


def select(scenes, year_start, year_end, paired_area, floor=USABLE_FLOOR):
    """Return `(before, after, report)`; `before`/`after` are None if no pair.

    `paired_area(before_key, after_key)` gives the paired-valid pixel count of a
    candidate pair, so the tie-break does not have to guess.
    """
    report = {"rule": SELECTION_RULE, "considered": [], "rejected": []}
    eligible = {year_start: [], year_end: []}
    for scene in sorted(scenes, key=lambda item: item.scene_key):
        if scene.year not in eligible:
            continue
        report["considered"].append(scene.scene_key)
        reason = rejected_reason(scene, floor)
        if reason:
            report["rejected"].append({"scene_key": scene.scene_key, "reason": reason})
            continue
        eligible[scene.year].append(scene)

    if not eligible[year_start] or not eligible[year_end]:
        report["outcome"] = (
            "no usable pair: at least one of the two years has no scene above "
            "the usability floor")
        return None, None, report

    best = None
    for before in eligible[year_start]:
        for after in eligible[year_end]:
            gap = abs(day_of_year(before.datetime_utc)
                      - day_of_year(after.datetime_utc))
            paired = paired_area(before.scene_key, after.scene_key)
            mixed = (before.reflectance_offset_applied
                     != after.reflectance_offset_applied)
            key = (mixed, gap, -paired, before.scene_key, after.scene_key)
            if best is None or key < best[0]:
                best = (key, before, after)

    _key, before, after = best
    gap = abs(day_of_year(before.datetime_utc) - day_of_year(after.datetime_utc))
    report["outcome"] = "pair selected"
    report["seasonal_gap_days"] = gap
    if gap > SEASONAL_GAP_WARN_DAYS:
        report["seasonal_warning"] = (
            f"the two scenes are {gap} days apart in the season; part of any "
            f"index difference is phenology rather than disturbance")
    return before, after, report
