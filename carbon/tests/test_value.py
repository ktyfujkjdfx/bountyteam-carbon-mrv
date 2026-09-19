"""Financial scenarios: V = Q × p, the three official prices, and nothing implied."""
from __future__ import annotations

import math

import pytest

from carbon import official_prices, reasons, scenario_values, user_price
from carbon.parameters import DEFAULT_PARAMETERS
from carbon.value import (
    CURRENCY,
    DISCLAIMER,
    OFFICIAL_CASE_PRICE,
    USER_SCENARIO,
    PriceScenario,
)
from carbon.tests.conftest import ALL_REQUESTS, build_case


def test_the_official_prices_are_the_three_of_the_case():
    prices = official_prices()
    assert [scenario.price_rub for scenario in prices] == [500.0, 1500.0, 4000.0]
    assert [scenario.label for scenario in prices] == ["LOW", "BASE", "HIGH"]
    assert all(scenario.is_official for scenario in prices)
    assert tuple(scenario.price_rub for scenario in prices) == DEFAULT_PARAMETERS.prices_rub


def test_the_value_is_the_product_and_nothing_else():
    result = scenario_values(units=395, status=reasons.AVAILABLE)
    assert result.formula == "V = Q × p"
    assert [item.value_rub for item in result.scenarios] == [197_500.0, 592_500.0, 1_580_000.0]
    assert {item.currency for item in result.scenarios} == {CURRENCY}
    assert result.unit_label == "POTENTIAL_UNIT_OF_THE_CASE"


def test_zero_units_are_worth_zero_which_is_an_answer():
    result = scenario_values(units=0, status=reasons.AVAILABLE)
    assert result.status == reasons.AVAILABLE
    assert result.units == 0
    assert [item.value_rub for item in result.scenarios] == [0.0, 0.0, 0.0]


def test_unknown_units_have_no_value_rather_than_a_zero_one():
    """Q = null and Q = 0 must not collapse into the same money on the screen."""
    result = scenario_values(
        units=None, status=reasons.UNAVAILABLE, unavailable_reason=reasons.INCOMPLETE_COVERAGE
    )
    assert result.status == reasons.UNAVAILABLE
    assert result.unavailable_reason == reasons.INCOMPLETE_COVERAGE
    assert result.units is None
    assert result.scenarios == ()
    assert "VALUE_WITHOUT_UNITS" in {item.code for item in result.notes}
    assert "не нулевая стоимость" in next(
        item.text for item in result.notes if item.code == "VALUE_WITHOUT_UNITS"
    )


def test_an_unavailable_status_is_respected_even_if_a_number_is_passed():
    result = scenario_values(units=10, status=reasons.UNAVAILABLE)
    assert result.status == reasons.UNAVAILABLE
    assert result.scenarios == ()


# -- the user scenario ---------------------------------------------------------------------


def test_a_user_price_is_kept_apart_from_the_official_ones():
    result = scenario_values(
        units=100, status=reasons.AVAILABLE, extra_prices=(user_price(2500.0),)
    )
    assert len(result.official) == 3
    assert len(result.user_supplied) == 1
    chosen = result.user_supplied[0]
    assert chosen.origin == USER_SCENARIO
    assert chosen.value_rub == 250_000.0
    assert all(item.origin == OFFICIAL_CASE_PRICE for item in result.official)
    assert "USER_PRICE_SCENARIO" in {item.code for item in result.notes}


def test_a_user_price_is_not_present_unless_it_was_supplied():
    result = scenario_values(units=100, status=reasons.AVAILABLE)
    assert result.user_supplied == ()
    assert "USER_PRICE_SCENARIO" not in {item.code for item in result.notes}


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), "500", None, True])
def test_an_unusable_user_price_is_refused(bad):
    with pytest.raises(ValueError):
        user_price(bad)


def test_a_zero_user_price_is_allowed_and_gives_zero():
    result = scenario_values(
        units=100, status=reasons.AVAILABLE, extra_prices=(user_price(0.0),)
    )
    assert result.user_supplied[0].value_rub == 0.0


def test_an_unknown_price_origin_is_refused():
    with pytest.raises(ValueError, match="price origin"):
        scenario_values(
            units=10, status=reasons.AVAILABLE,
            extra_prices=(PriceScenario(label="X", price_rub=1.0, origin="MARKET_FORECAST"),),
        )


# -- the boundaries ------------------------------------------------------------------------


def test_a_price_scenario_never_changes_the_units():
    plain = scenario_values(units=42, status=reasons.AVAILABLE)
    with_user = scenario_values(
        units=42, status=reasons.AVAILABLE, extra_prices=(user_price(999_999.0),)
    )
    assert plain.units == with_user.units == 42
    assert [item.value_rub for item in plain.official] == [
        item.value_rub for item in with_user.official
    ]


def test_the_result_says_it_is_a_scenario_and_not_a_market_forecast():
    result = scenario_values(units=1, status=reasons.AVAILABLE)
    assert result.disclaimer == DISCLAIMER
    assert "не прогноз рыночной цены" in result.disclaimer
    assert "не ожидаемая выручка" in result.disclaimer


def test_the_module_computes_no_discounted_cash_flow():
    """NPV, payback and future cash flows are out of scope and must stay out.

    The prose says so; this checks the executable code, where saying so is not enough.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(
        (Path(__file__).resolve().parents[1] / "value.py").read_text(encoding="utf-8")
    )
    identifiers = {
        node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr.lower() for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        target.lower()
        for node in ast.walk(tree) if isinstance(node, ast.arg)
        for target in (node.arg,)
    }
    for forbidden in ("npv", "discount_rate", "discount", "payback", "irr", "cash_flow"):
        assert forbidden not in identifiers, forbidden
    # the only arithmetic here is a product; no exponentiation, which is what
    # compounding and discounting would need
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Pow)]


@pytest.mark.parametrize("request_id", ALL_REQUESTS)
def test_the_official_areas_are_worth_zero_because_they_earn_zero(request_id, areas, sample_requests):
    _, _, analysis, _ = build_case(request_id, areas, sample_requests)
    result = scenario_values(units=analysis.units.units, status=analysis.units.status)
    assert analysis.units.units == 0
    assert result.status == reasons.AVAILABLE
    assert all(item.value_rub == 0.0 for item in result.scenarios)
    assert all(math.isfinite(item.value_rub) for item in result.scenarios)
