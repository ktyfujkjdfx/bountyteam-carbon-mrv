"""Risk flags that measure something and change nothing.

The panel exists for an investor, and the danger of such a panel is that a
level on a dashboard reads as a forecast. These tests hold the two lines that
keep it honest: every block carries the measurement it was banded from, and no
block touches a carbon number. The third line - that a count of past episodes
is not a probability of future fire - is asserted on the text, because that is
where it has to be said.
"""
import json

import pytest

from rs.case2 import payload as payload_module, risk
from rs.case2.analysis import analyse

BLOCKS = ("fire_risk_evidence", "forest_loss_evidence", "data_quality_risk")


@pytest.fixture(scope="module")
def risks(mordovia_03):
    return payload_module.analysis_payload(mordovia_03)["risks"]


# -- shape ----------------------------------------------------------------

def test_three_independent_blocks_are_returned(risks):
    assert set(risks) == {*BLOCKS, "affects_q", "note"}


def test_every_block_carries_level_basis_source_period_and_limitations(risks):
    for name in BLOCKS:
        block = risks[name]
        assert block["level"] in (risk.LOW, risk.MEDIUM, risk.HIGH, risk.UNKNOWN)
        assert isinstance(block["basis"], dict) and block["basis"]
        assert block["rule"]
        assert block["source"]
        assert block["period"] == {"year_start": 2020, "year_end": 2022}
        assert block["limitations"]


def test_no_block_affects_the_carbon_result(risks):
    assert risks["affects_q"] is False
    for name in BLOCKS:
        assert risks[name]["affects_q"] is False


def test_a_block_that_travels_alone_still_says_it_changes_nothing(risks):
    """The field is repeated per block because a block gets quoted on its own."""
    for name in BLOCKS:
        alone = json.dumps(risks[name])
        assert '"affects_q": false' in alone


def test_the_panel_refuses_to_become_a_probability_or_a_discount(risks):
    note = risks["note"]
    assert "none of them is a probability or a discount" in note
    fire = risks["fire_risk_evidence"]
    assert any("not a probability of future fire" in item
               for item in fire["limitations"])


def test_the_risks_never_reach_the_carbon_arithmetic(mordovia_03):
    """Removing the whole panel leaves every published number untouched."""
    payload = payload_module.analysis_payload(mordovia_03)
    without = {key: value for key, value in payload.items() if key != "risks"}
    assert "risk" not in json.dumps(without["stock_change"])
    assert "risk" not in json.dumps(without["coverage"])
    assert payload["stock_change"]["e_tco2e"] == pytest.approx(
        mordovia_03.change.e_tco2e, rel=1e-12)


# -- fire ------------------------------------------------------------------

def test_a_confirmed_episode_is_counted_and_dated(risks):
    fire = risks["fire_risk_evidence"]
    assert fire["basis"]["product_supplied"] is True
    assert fire["basis"]["episodes"] == 1
    assert fire["level"] == risk.MEDIUM
    dates = fire["basis"]["episode_dates"]
    assert [(item["date_min"], item["date_max"]) for item in dates] == \
        [("2021-08-05", "2021-08-22")]


def test_an_unsupplied_burn_product_is_unknown_and_never_low(tver):
    """An absent product is not an absence of fire, and LOW would say it was."""
    fire = payload_module.analysis_payload(tver)["risks"]["fire_risk_evidence"]
    assert fire["level"] == risk.UNKNOWN
    assert fire["basis"]["product_supplied"] is False
    assert fire["basis"]["episodes"] is None
    assert any("not evidence that nothing burned" in item
               for item in fire["limitations"])
    assert "not an absence of fire" in fire["rule"]


def test_the_fire_band_is_a_count_not_a_model():
    period = {"year_start": 2019, "year_end": 2024}
    for episodes, expected in ((0, risk.LOW), (1, risk.MEDIUM), (3, risk.HIGH)):
        evidence = {
            "available": True,
            "fire": {"available": True,
                     "detections": [{"granule": f"g{index}",
                                     "date_min": "2021-08-05",
                                     "date_max": "2021-08-22",
                                     "date_uncertainty_days_max": 7}
                                    for index in range(episodes)]},
            "zones": [],
        }
        block = risk.fire_risk(evidence, ("A",), period)
        assert block["level"] == expected
        assert block["basis"]["episodes"] == episodes


# -- forest loss ------------------------------------------------------------

def test_the_loss_share_is_measured_on_the_product_that_covers_the_request(risks):
    loss = risks["forest_loss_evidence"]
    basis = loss["basis"]
    # The payload rounds to nine decimals, once, at the boundary.
    assert basis["loss_fraction"] == pytest.approx(
        basis["loss_pixels"] / basis["covered_pixels"], abs=1e-9)
    assert basis["loss_area_ha"] > 0
    assert basis["loss_year_codes"] == [21, 22]
    assert loss["level"] == risk.HIGH


def test_cover_loss_is_not_presented_as_biomass_removed(risks):
    loss = risks["forest_loss_evidence"]
    assert any("not a measure of biomass removed" in item
               for item in loss["limitations"])


def test_the_loss_bands_are_stated_and_applied():
    period = {"year_start": 2019, "year_end": 2024}
    for loss_pixels, expected in ((0, risk.LOW), (500, risk.MEDIUM),
                                  (5000, risk.HIGH)):
        evidence = {"available": True,
                    "gfc": {"covered_pixels": 10000,
                            "loss_pixels_in_request": loss_pixels,
                            "loss_year_codes": (20, 21)},
                    "zones": []}
        assert risk.forest_loss(evidence, ("A",), period)["level"] == expected


def test_an_unread_loss_product_is_unknown_rather_than_zero(analyses):
    """A run without optical never reads GFC; that is not zero loss."""
    loss = payload_module.analysis_payload(
        analyses["RU_TVER_01"])["risks"]["forest_loss_evidence"]
    assert loss["level"] == risk.UNKNOWN
    assert loss["basis"]["loss_fraction"] is None


# -- data quality -----------------------------------------------------------

def test_data_quality_is_measured_on_the_observations(risks):
    quality = risks["data_quality_risk"]
    basis = quality["basis"]
    assert 0.0 <= basis["paired_valid_fraction"] <= 1.0
    assert 0.0 <= basis["observation_gap_fraction"] <= 1.0
    assert basis["gap_reasons"]
    assert basis["scenes_read"] > 0
    assert basis["level_reasons"]


def test_a_mixed_offset_convention_makes_the_quality_risk_high(dataset):
    """The measured case: such a pair reads a control forest as regrowth."""
    period = {"year_start": 2019, "year_end": 2024}

    class Coverage:
        optical_paired_fraction = 1.0

    evidence = {
        "available": True,
        "scene_selection": {
            "rejected": [],
            "radiometric_note": {"same_offset_convention": False,
                                 "warning": "straddles 04.00"}},
        "observation_quality": {"paired_valid_fraction": 0.99},
        "observation_gaps": {"gap_fraction": 0.01, "by_reason": {}},
    }
    block = risk.data_quality(Coverage(), ["a"], evidence, period, True)
    assert block["level"] == risk.HIGH
    assert block["basis"]["radiometric_offset_mixed"] is True
    assert any("04.00" in reason for reason in block["basis"]["level_reasons"])


def test_optical_quality_never_reduces_the_biomass_coverage(risks, mordovia_03):
    quality = risks["data_quality_risk"]
    assert any("does not reduce the biomass coverage" in item
               for item in quality["limitations"])
    assert "unaffected" in quality["source"]["note"]
    assert mordovia_03.coverage.biomass_fraction > 0.99


def test_a_run_without_optical_reports_unknown_not_low(analyses):
    quality = payload_module.analysis_payload(
        analyses["RU_VOLOGDA_02"])["risks"]["data_quality_risk"]
    assert quality["level"] == risk.UNKNOWN
    assert quality["basis"]["paired_valid_fraction"] is None
    assert any("absent rather than zero" in item
               for item in quality["limitations"])


def test_a_cloudy_request_raises_the_quality_risk_and_nothing_else(
        dataset, mordovia_cloudy):
    """The window with the heavily clouded September scene."""
    risks = payload_module.analysis_payload(mordovia_cloudy)["risks"]
    quality = risks["data_quality_risk"]
    assert quality["basis"]["rejected_scenes"]
    assert quality["level"] in (risk.MEDIUM, risk.HIGH)
    # A cloudy request is not a risky forest: the other two blocks are
    # measured from their own products and do not move with the cloud.
    assert risks["fire_risk_evidence"]["basis"]["product_supplied"] is True
    assert risks["forest_loss_evidence"]["basis"]["loss_fraction"] is not None


def test_the_three_blocks_are_independent_of_one_another(risks):
    """No block reads another's level; each names its own product."""
    products = {risks[name]["source"].get("product") for name in BLOCKS}
    assert len(products) == 3
    for name in BLOCKS:
        assert "level" not in json.dumps(risks[name]["source"])
