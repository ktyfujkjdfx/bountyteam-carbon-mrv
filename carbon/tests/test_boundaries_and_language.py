"""The engine stays a pure library, and its wording stays within what the case supports."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from carbon import DEFAULT_PARAMETERS, notes, reasons
from carbon.claim import ClaimResult
from carbon.units import UnitsResult

ENGINE_MODULES = sorted(Path(__file__).resolve().parents[1].glob("*.py"))

FORBIDDEN_IMPORT_ROOTS = (
    "fastapi", "starlette", "uvicorn", "pydantic",
    "web3", "eth_account", "eth_typing", "eth_utils",
    "requests", "httpx", "aiohttp", "urllib3",
    "sqlalchemy", "psycopg", "sqlite3", "django", "flask",
    "backend", "frontend", "rs",
)

# Wording that would claim more than the case rules establish.
FORBIDDEN_WORDINGS = (
    "мошенн", "фальсифик", "доказанн", "гарантирован", "сертифицирован",
    "ущерб", "убыт", "одобрено к покупке", "инвестиционно привлекател",
    "fraud", "guaranteed", "certified", "investable", "value at risk",
)


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("module", ENGINE_MODULES, ids=lambda path: path.name)
def test_engine_modules_do_not_import_service_layers(module):
    assert not imported_roots(module) & set(FORBIDDEN_IMPORT_ROOTS)


def test_importing_the_engine_loads_no_service_layer():
    code = "import json, sys; import carbon; print(json.dumps(sorted(sys.modules)))"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = set(json.loads(completed.stdout))
    assert not loaded & set(FORBIDDEN_IMPORT_ROOTS)


@pytest.mark.parametrize("module", ENGINE_MODULES, ids=lambda path: path.name)
def test_engine_modules_avoid_unsupported_wordings(module):
    text = module.read_text(encoding="utf-8").lower()
    assert [phrase for phrase in FORBIDDEN_WORDINGS if phrase in text] == []


def test_note_catalogue_avoids_unsupported_wordings():
    for code, template in notes.CATALOGUE.items():
        lowered = template.lower()
        assert [phrase for phrase in FORBIDDEN_WORDINGS if phrase in lowered] == [], code


def test_note_catalogue_states_the_scenario_status():
    assert "сценарн" in notes.CATALOGUE[notes.SCENARIO_INTERVAL].lower()
    assert "условиям кейса" in notes.CATALOGUE[notes.CASE_UNITS]
    assert "не прогноз рынка" in notes.CATALOGUE[notes.SCENARIO_PRICES]
    assert "не влияет" in notes.CATALOGUE[notes.CLAIM_INPUT_LABEL]


def test_every_note_code_has_text():
    codes = {
        value for name, value in vars(notes).items()
        if name.isupper() and isinstance(value, str) and name != "CATALOGUE"
    }
    assert codes == set(notes.CATALOGUE)


def test_public_statuses_carry_no_verdict_wording():
    public = (
        reasons.CLAIM_STATUSES
        | reasons.UNAVAILABLE_REASONS
        | reasons.ZERO_UNIT_REASONS
        | reasons.CLAIM_MISMATCH_REASONS
        | {reasons.AVAILABLE, reasons.UNAVAILABLE}
    )
    for status in public:
        lowered = status.lower()
        assert [phrase for phrase in FORBIDDEN_WORDINGS if phrase in lowered] == []


def test_results_are_typed_and_serialisable_without_a_service_layer():
    assert UnitsResult.__annotations__["units"] == "int | None"
    assert ClaimResult.__annotations__["supported_share"] == "float | None"
    assert isinstance(DEFAULT_PARAMETERS.prices_rub, tuple)
