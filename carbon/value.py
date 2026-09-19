"""Scenario value of the potential units: V = Q × p, and nothing beyond it.

The case fixes three prices — 500, 1500 and 4000 roubles per unit — and the whole
financial layer is one multiplication by each of them. That is deliberate. A discounted
cash flow, a payback period or an expected revenue would each need a market assumption the
case does not give and this role cannot supply, so none of them is computed here.

Three rules keep the layer honest:

* a price scenario never changes Q. It reads the number of units and multiplies; the
  units, the interval and the baseline are already decided when this module is called;
* Q = 0 gives a value of 0 — a real answer. Q = null gives no value at all, because there
  is nothing to multiply, and a zero would read as "worth nothing" instead of "unknown";
* a price the user supplies is labelled `USER_SCENARIO` and is kept apart from the three
  official ones, so a chosen number can never be mistaken for a rule of the case.

Every result says in words that it is a scenario valuation and not a market price forecast.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import notes, reasons
from .parameters import DEFAULT_PARAMETERS, CaseParameters

CURRENCY = "RUB"
UNIT_LABEL = "POTENTIAL_UNIT_OF_THE_CASE"

OFFICIAL_CASE_PRICE = "OFFICIAL_CASE_PRICE"
USER_SCENARIO = "USER_SCENARIO"
PRICE_ORIGINS = frozenset({OFFICIAL_CASE_PRICE, USER_SCENARIO})

OFFICIAL_LABELS = ("LOW", "BASE", "HIGH")

DISCLAIMER = (
    "Сценарная оценка по ценам кейса. Это не прогноз рыночной цены, не ожидаемая выручка "
    "и не оценка стоимости актива."
)


@dataclass(frozen=True)
class PriceScenario:
    label: str
    price_rub: float
    origin: str = OFFICIAL_CASE_PRICE

    @property
    def is_official(self) -> bool:
        return self.origin == OFFICIAL_CASE_PRICE


@dataclass(frozen=True)
class ScenarioValuation:
    label: str
    origin: str
    price_rub: float
    value_rub: float
    currency: str = CURRENCY


@dataclass(frozen=True)
class ValueResult:
    status: str
    unavailable_reason: str | None = None
    units: int | None = None
    currency: str = CURRENCY
    unit_label: str = UNIT_LABEL
    formula: str = "V = Q × p"
    scenarios: tuple[ScenarioValuation, ...] = ()
    disclaimer: str = DISCLAIMER
    notes: tuple[notes.Note, ...] = ()

    @property
    def official(self) -> tuple[ScenarioValuation, ...]:
        return tuple(item for item in self.scenarios if item.origin == OFFICIAL_CASE_PRICE)

    @property
    def user_supplied(self) -> tuple[ScenarioValuation, ...]:
        return tuple(item for item in self.scenarios if item.origin == USER_SCENARIO)


def official_prices(parameters: CaseParameters = DEFAULT_PARAMETERS) -> tuple[PriceScenario, ...]:
    """The three prices of the case, in the order the table lists them."""
    return tuple(
        PriceScenario(label=label, price_rub=price, origin=OFFICIAL_CASE_PRICE)
        for label, price in zip(OFFICIAL_LABELS, parameters.prices_rub)
    )


def user_price(price_rub: float, *, label: str = "USER") -> PriceScenario:
    """A price the user chose. It is a scenario input, never a rule of the case."""
    if not isinstance(price_rub, (int, float)) or isinstance(price_rub, bool):
        raise ValueError("a user price must be a number")
    value = float(price_rub)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("a user price must be finite and not negative")
    return PriceScenario(label=label, price_rub=value, origin=USER_SCENARIO)


def scenario_values(
    *,
    units: int | None,
    status: str,
    unavailable_reason: str | None = None,
    extra_prices: tuple[PriceScenario, ...] = (),
    parameters: CaseParameters = DEFAULT_PARAMETERS,
) -> ValueResult:
    """Value the units under each price scenario. Reads Q; never changes it."""
    if status != reasons.AVAILABLE or units is None:
        # Nothing to multiply. A zero here would read as "worth nothing" rather than
        # "not known", and those are different answers.
        return ValueResult(
            status=reasons.UNAVAILABLE,
            unavailable_reason=unavailable_reason or reasons.MISSING_INPUT,
            units=None,
            notes=(notes.note(notes.VALUE_WITHOUT_UNITS), notes.note(notes.SCENARIO_PRICES)),
        )

    for scenario in extra_prices:
        if scenario.origin not in PRICE_ORIGINS:
            raise ValueError(f"price origin must be one of {sorted(PRICE_ORIGINS)}")

    valuations = tuple(
        ScenarioValuation(
            label=scenario.label,
            origin=scenario.origin,
            price_rub=scenario.price_rub,
            value_rub=units * scenario.price_rub,
        )
        for scenario in (*official_prices(parameters), *extra_prices)
    )
    attached = [notes.note(notes.SCENARIO_PRICES)]
    if any(scenario.origin == USER_SCENARIO for scenario in extra_prices):
        attached.append(notes.note(notes.USER_PRICE_SCENARIO))
    return ValueResult(
        status=reasons.AVAILABLE,
        units=units,
        scenarios=valuations,
        notes=tuple(attached),
    )
