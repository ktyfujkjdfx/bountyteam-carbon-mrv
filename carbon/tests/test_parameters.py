"""Engine defaults must stay identical to the official parameters table."""
from __future__ import annotations

import pytest

from carbon import DEFAULT_PARAMETERS, load_parameters
from carbon.parameters import PARAMETERS_CSV, parse_number


def test_defaults_match_the_official_csv():
    assert load_parameters(PARAMETERS_CSV) == DEFAULT_PARAMETERS


def test_official_csv_is_read_with_its_byte_order_mark():
    first_line = PARAMETERS_CSV.read_bytes().split(b"\n")[0]
    assert first_line.startswith(b"\xef\xbb\xbf")
    assert load_parameters(PARAMETERS_CSV).cf_agb == 0.47


def test_co2_per_carbon_is_the_exact_ratio():
    assert parse_number("44/12") == 44 / 12
    assert DEFAULT_PARAMETERS.co2_per_c == 44 / 12
    assert DEFAULT_PARAMETERS.co2_per_c != pytest.approx(3.67, abs=1e-6)


def test_case_scenario_constants():
    parameters = load_parameters(PARAMETERS_CSV)
    assert parameters.unc_allowance == 0.10
    assert parameters.unc_stop_ratio == 1.0
    assert parameters.buffer_share == 0.15
    assert parameters.leakage_tco2e == 0.0
    assert parameters.prices_rub == (500.0, 1500.0, 4000.0)
    assert (parameters.history_start_year, parameters.history_end_year) == (2015, 2019)
    assert parameters.scenario_end_year == 2029
