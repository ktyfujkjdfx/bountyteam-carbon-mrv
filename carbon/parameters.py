"""Case parameters from data/methodology/parameters.csv.

The defaults below repeat the official table so the engine works without file access;
test_parameters.py compares them with the CSV, so they cannot drift from the dataset.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PARAMETERS_CSV = REPO_ROOT / "data" / "methodology" / "parameters.csv"

METHOD_VERSION = "carbon-lens-trust-1.0.0"


@dataclass(frozen=True)
class CaseParameters:
    cf_agb: float
    co2_per_c: float
    unc_allowance: float
    unc_stop_ratio: float
    buffer_share: float
    leakage_tco2e: float
    prices_rub: tuple[float, ...]
    history_start_year: int
    history_end_year: int
    scenario_end_year: int


DEFAULT_PARAMETERS = CaseParameters(
    cf_agb=0.47,
    co2_per_c=44 / 12,
    unc_allowance=0.10,
    unc_stop_ratio=1.0,
    buffer_share=0.15,
    leakage_tco2e=0.0,
    prices_rub=(500.0, 1500.0, 4000.0),
    history_start_year=2015,
    history_end_year=2019,
    scenario_end_year=2029,
)


def parse_number(value: str) -> float:
    """Parse a CSV number; the official CO2_per_C is written as the ratio 44/12."""
    text = value.strip().replace(",", ".")
    return float(Fraction(text)) if "/" in text else float(text)


def load_parameters(path: Path = PARAMETERS_CSV) -> CaseParameters:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        table = {row["parameter"]: row["value"] for row in csv.DictReader(handle)}
    return CaseParameters(
        cf_agb=parse_number(table["CF_AGB"]),
        co2_per_c=parse_number(table["CO2_per_C"]),
        unc_allowance=parse_number(table["UNC_allowance"]),
        unc_stop_ratio=parse_number(table["UNC_stop_ratio"]),
        buffer_share=parse_number(table["BUF"]),
        leakage_tco2e=parse_number(table["LK"]),
        prices_rub=(
            parse_number(table["price_low"]),
            parse_number(table["price_base"]),
            parse_number(table["price_high"]),
        ),
        history_start_year=int(parse_number(table["history_start_year"])),
        history_end_year=int(parse_number(table["history_end_year"])),
        scenario_end_year=int(parse_number(table["scenario_end_year"])),
    )
