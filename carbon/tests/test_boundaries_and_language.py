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
    # raster and projection work belongs to RS; the engine receives per-cell numbers
    "rasterio", "pyproj", "shapely", "gdal", "osgeo",
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


def test_the_engine_does_not_import_its_own_test_fixtures():
    """The fixture builder reads rasters; it must stay a test tool, outside the package."""
    for module in ENGINE_MODULES:
        roots = imported_roots(module)
        assert "carbon.tests" not in roots
        assert "build_cells" not in roots


def test_the_fixture_builder_lives_outside_the_engine():
    package = Path(__file__).resolve().parents[1]
    assert not (package / "build_cells.py").exists()
    assert (package / "tests" / "fixtures" / "build_cells.py").is_file()


@pytest.mark.parametrize("request_id", ["RU_TVER_01", "RU_MORDOVIA_03", "CHECK_TRANSFER_01"])
def test_the_published_passport_and_page_avoid_unsupported_wordings(request_id, case):
    """Everything a reader downloads is held to the same wording rule as the code."""
    from carbon import build_passport, build_report, render_html

    _, _, analysis, provenance = case(request_id)
    passport = build_passport(analysis, provenance=provenance)
    report = build_report(
        analysis, passport=passport, created_at="2026-09-19T00:00:00Z", run_id="lint",
    )
    page = render_html(report).lower()
    document = json.dumps(passport.content, ensure_ascii=False).lower()

    # the source catalogue is quoted verbatim, so only our own prose is checked here
    quoted = {
        source["limitations"].lower() for source in provenance["sources"]
    } | {source["required_attribution"].lower() for source in provenance["sources"]}
    for surface in (page, document):
        for phrase in FORBIDDEN_WORDINGS:
            if phrase in surface:
                assert any(phrase in text for text in quoted), phrase


# -- the enumerations of the method freeze --------------------------------------------------


def test_the_claim_statuses_are_exactly_the_seven_of_the_freeze():
    assert reasons.CLAIM_STATUSES == {
        "NOT_PROVIDED", "NOT_APPLICABLE", "NOT_COMPARABLE", "UNASSESSABLE",
        "SUPPORTED_BY_CASE", "PARTIALLY_SUPPORTED_BY_CASE", "NOT_SUPPORTED_BY_CASE",
    }


def test_the_spatial_scenarios_are_named_as_the_freeze_names_them():
    from carbon.interval import FULL_SPATIAL_CORRELATION, INDEPENDENT_NATIVE_CELLS, SPATIAL_MODES

    assert INDEPENDENT_NATIVE_CELLS == "INDEPENDENT_NATIVE_CELLS"
    assert FULL_SPATIAL_CORRELATION == "FULL_SPATIAL_CORRELATION"
    assert reasons.SPATIAL_SCENARIOS == set(SPATIAL_MODES)
    # the main scenario is the independent one; the correlated one is a stress scenario
    assert SPATIAL_MODES[0] == INDEPENDENT_NATIVE_CELLS


def test_the_availability_and_zero_vocabularies_never_overlap():
    """A reason for null must never be usable as a reason for zero, or the two blur."""
    assert reasons.UNAVAILABLE_REASONS & reasons.ZERO_UNIT_REASONS == frozenset()


def test_every_public_code_is_a_stable_upper_case_identifier():
    import re

    groups = (
        reasons.UNAVAILABLE_REASONS, reasons.ZERO_UNIT_REASONS, reasons.CLAIM_STATUSES,
        reasons.CLAIM_MISMATCH_REASONS, reasons.CLAIM_REASONS, reasons.CLAIM_SOURCES,
        reasons.SPATIAL_SCENARIOS,
    )
    for group in groups:
        for code in group:
            assert re.fullmatch(r"[A-Z][A-Z0-9_]*", code), code


def test_the_pool_and_the_unit_are_named_once():
    from carbon.analysis import DEFAULT_POOL, DEFAULT_UNIT

    assert DEFAULT_POOL == reasons.POOL_AGB_LIVE_WOODY == "AGB_LIVE_WOODY"
    assert DEFAULT_UNIT == reasons.UNIT_POTENTIAL_CASE == "POTENTIAL_UNIT_OF_THE_CASE"
