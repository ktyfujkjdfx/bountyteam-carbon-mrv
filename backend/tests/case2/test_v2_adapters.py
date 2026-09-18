"""The adapter boundary: who owns the arithmetic, and what happens when they are absent."""
from __future__ import annotations

import math
import re

import pytest

from backend.app.config import REPO_ROOT
from backend.app.v2 import assemble, geometry, service, store
from backend.app.v2 import api as lens_api
from backend.app.v2 import report as report_module
from backend.app.v2.adapters import carbon as carbon_adapter
from backend.app.v2.adapters import raster as raster_adapter
from backend.app.v2.adapters import registry
from backend.app.v2.contracts import fixture, internal_validator, schema_errors
from backend.app.v2.ports import (CarbonAssessmentPort, CarbonRequest, RasterAnalysisPort,
                                  RasterRequest, RasterUnavailable)

# The one module allowed to contain the method, and only until carbon/ is merged.
REFERENCE = REPO_ROOT / "backend" / "app" / "v2" / "adapters" / "reference_carbon.py"
METHOD_NUMBERS = (re.compile(r"0\.85"), re.compile(r"44\s*/\s*12"), re.compile(r"0\.47"),
                  re.compile(r"\bmath\.floor\b"), re.compile(r"0\.15\b"))


# -- the boundary -------------------------------------------------------------------------
@pytest.mark.parametrize("module", [service, assemble, report_module, store, lens_api,
                                    geometry, raster_adapter])
def test_no_module_outside_the_reference_engine_contains_the_method(module):
    source = REPO_ROOT.joinpath(*module.__name__.split(".")).with_suffix(".py").read_text(
        encoding="utf-8")
    for pattern in METHOD_NUMBERS:
        assert not pattern.search(source), f"{module.__name__} contains {pattern.pattern}"


def test_the_reference_engine_is_the_only_stand_in_with_arithmetic():
    source = REFERENCE.read_text(encoding="utf-8")
    assert "floor(adjusted * UNIT_SHARE)" in source
    assert "temporary stand-in" in source.lower()
    assert "carbon/" in source


def test_the_carbon_adapter_composes_the_engine_and_adds_nothing():
    source = (REPO_ROOT / "backend" / "app" / "v2" / "adapters" / "carbon.py").read_text(
        encoding="utf-8")
    for pattern in METHOD_NUMBERS:
        assert not pattern.search(source), pattern.pattern
    for call in ("compute_interval", "compute_baseline", "compute_units", "compare_claim"):
        assert f"api.{call}(" in source


def test_the_ports_are_satisfied_by_the_running_adapters(harness):
    assert isinstance(harness.lens.ports.raster, RasterAnalysisPort)
    assert isinstance(harness.lens.ports.carbon, CarbonAssessmentPort)
    assert harness.lens.ports.raster.name and harness.lens.ports.carbon.name


def test_the_registry_reports_what_is_actually_running():
    described = registry.describe()
    assert set(described) == {"raster_core_available", "carbon_engine_available",
                              "raster_adapter", "carbon_adapter"}
    assert described["raster_core_available"] is raster_adapter.RS_AVAILABLE
    assert described["carbon_engine_available"] is not carbon_adapter.IS_REFERENCE_FALLBACK


def test_the_real_raster_core_wins_when_present():
    """Whenever rs.case2 is importable, the replay adapter must not be chosen."""
    port = registry.raster_port(REPO_ROOT / "backend" / "runtime" / "lens-runs")
    if raster_adapter.RS_AVAILABLE:  # pragma: no cover - depends on the branch
        assert isinstance(port, raster_adapter.RasterCoreAdapter)
    else:
        assert isinstance(port, raster_adapter.ReplayRasterAdapter)


def test_the_real_carbon_engine_wins_when_present():
    try:
        import carbon  # noqa: F401
    except ImportError:
        assert carbon_adapter.IS_REFERENCE_FALLBACK
        assert carbon_adapter.ENGINE_NAME.startswith("backend-reference/")
    else:  # pragma: no cover - depends on the branch
        assert not carbon_adapter.IS_REFERENCE_FALLBACK
        assert carbon_adapter.ENGINE_NAME.startswith("carbon/")


def test_a_stand_in_can_never_be_reported_as_a_measurement(harness):
    job = harness.analyse({"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024},
                          key="origin-key-000001")
    run = job["result"]["run"]
    assert run["dataset_origin"] == "STUB_FIXTURE"
    assert run["raster_adapter"] == "backend-replay"
    assert job["result"]["fixture"] is not None


# -- the raster port ----------------------------------------------------------------------
def _raster_request(aoi_id: str, year_start: int, year_end: int) -> RasterRequest:
    from backend.app.v2 import catalog

    geom, area_ha = geometry.validate(catalog.area(aoi_id).geometry)
    return RasterRequest(geometry=geom, canonical_geometry=geometry.canonical_geometry(geom),
                         geometry_hash=geometry.geometry_hash(geom), area_ha=area_ha,
                         year_start=year_start, year_end=year_end)


def test_the_replay_adapter_answers_only_the_keys_it_was_given():
    adapter = raster_adapter.ReplayRasterAdapter()
    known = adapter.analyse(_raster_request("RU_TVER_01", 2019, 2024))
    assert known.dataset_origin == "STUB_FIXTURE"
    assert known.fixture["kind"] == "UNIT_TEST_VECTOR"

    with pytest.raises(RasterUnavailable) as raised:
        adapter.analyse(_raster_request("RU_TVER_01", 2020, 2023))
    assert raised.value.reason == "RASTER_ANALYSIS_UNAVAILABLE"


def test_an_unavailable_raster_becomes_a_result_not_a_failed_job(harness):
    job = harness.analyse({"aoi_id": "RU_TVER_01", "year_start": 2020, "year_end": 2023},
                          key="unavail-key-00001")
    assert job["job_state"] == "SUCCEEDED"
    assert job["result"]["units"]["unavailable_reason"] == "RASTER_ANALYSIS_UNAVAILABLE"


def test_every_replay_payload_matches_the_internal_contract():
    adapter = raster_adapter.ReplayRasterAdapter()
    entries = adapter.entries()
    assert len(entries) >= 4
    for entry in entries:
        for key, model in (("analysis", "RasterAnalysis"), ("cells", "CellLayer"),
                           ("manifest", "ArtifactManifest")):
            from backend.app.contracts import read_json

            value = read_json(adapter.root / entry[key])
            assert not schema_errors(internal_validator(model), value), (entry["name"], model)


def test_the_replay_vectors_cover_every_decision_branch():
    outcomes = {(entry["outcome"]["status"], entry["outcome"]["zero_reason"],
                 entry["outcome"]["unavailable_reason"])
                for entry in raster_adapter.ReplayRasterAdapter().entries()}
    assert ("AVAILABLE", None, None) in outcomes
    assert ("AVAILABLE", "NON_POSITIVE_RELATIVE_RESULT", None) in outcomes
    assert ("AVAILABLE", "UNCERTAINTY_TOO_HIGH", None) in outcomes
    assert ("UNAVAILABLE", None, "INCOMPLETE_COVERAGE") in outcomes


def test_a_payload_that_breaks_the_internal_contract_is_refused(harness, monkeypatch):
    """A drifting producer fails the job; it never reaches a passport."""
    from backend.app.v2.contracts import ContractViolation

    adapter = raster_adapter.ReplayRasterAdapter()
    good = adapter.analyse(_raster_request("RU_TVER_01", 2019, 2024))
    broken = {key: value for key, value in good.analysis.items() if key != "stock_change"}

    with pytest.raises(ContractViolation):
        raster_adapter._result(broken, good.cells, good.manifest, "test", "STUB_FIXTURE",
                               None, {})


# -- the carbon port ----------------------------------------------------------------------
def _assess(raster: dict, cells: dict, year_start: int, year_end: int, **claim):
    return carbon_adapter.CarbonAdapter().assess(CarbonRequest(
        raster=raster, cells=cells, geometry_hash="0x" + "0" * 64, year_start=year_start,
        year_end=year_end, claimed_units=claim.get("claimed_units"),
        claim_origin=claim.get("claim_origin"), claim_scope=claim.get("claim_scope")))


def test_the_carbon_adapter_output_matches_the_internal_contract():
    adapter = raster_adapter.ReplayRasterAdapter()
    raster = adapter.analyse(_raster_request("RU_TVER_01", 2019, 2024))
    assessment = _assess(raster.analysis, raster.cells, 2019, 2024).assessment
    assert not schema_errors(internal_validator("CarbonAssessment"), assessment)
    assert assessment["units"]["units"] > 0


def test_the_engine_reproduces_the_official_worked_example():
    """The number the statement itself prints: 100 ha, one year, 100 -> 104 t/ha, Q = 395."""
    api = carbon_adapter.engine()
    vector = fixture("doc_example_units.json")
    given, expected = vector["input"], vector["expected"]
    parameters = api.load_parameters()

    cells = api.CellObservations.from_sequences(
        area_ha=[given["area_ha"]], agb_start=[given["mean_agb_start_tdm_ha"]],
        agb_end=[given["mean_agb_end_tdm_ha"]], sd_start=[0.0], sd_end=[0.0])
    interval = api.compute_interval(cells, year_start=given["year_start"],
                                    year_end=given["year_end"], parameters=parameters)
    assert interval.e_proj_tco2e == pytest.approx(expected["eproj_tco2e"], abs=1e-9)
    assert interval.mean_start_tc_ha == pytest.approx(expected["mean_carbon_start_tc_ha"],
                                                      abs=1e-9)
    assert interval.mean_end_tc_ha == pytest.approx(expected["mean_carbon_end_tc_ha"], abs=1e-9)

    half = given["half_width_tco2e"]
    units = api.compute_units(
        e_proj_tco2e=interval.e_proj_tco2e, e_base_tco2e=expected["ebase_tco2e"],
        lower_tco2e=interval.e_proj_tco2e - half, upper_tco2e=interval.e_proj_tco2e + half,
        area_ha=given["area_ha"], year_start=given["year_start"],
        year_end=given["year_end"], parameters=parameters)
    assert units.r_tco2e == pytest.approx(expected["r_tco2e"], abs=1e-6)
    assert units.ratio == pytest.approx(expected["ratio"], abs=1e-9)
    assert units.uncertainty_share == pytest.approx(expected["unc"], abs=1e-9)
    assert units.r_adj_tco2e == pytest.approx(expected["radj_tco2e"], abs=1e-6)
    assert units.units == expected["q"] == 395
    assert units.buffer_tco2e == pytest.approx(expected["buffer_tco2e"], abs=1e-6)
    for value, price in zip(units.scenario_values, (500.0, 1500.0, 4000.0)):
        assert value.value_rub == pytest.approx(expected["scenario_values_rub"][
            {500.0: "low", 1500.0: "base", 4000.0: "high"}[price]])


def test_the_literal_share_and_the_subtraction_are_not_interchangeable():
    """floor(Radj x 0.85) and floor(Radj - Radj x 0.15) differ next to a whole number."""
    disagreements = 0
    for step in range(1, 20001):
        adjusted = step / 17.0
        if math.floor(adjusted * 0.85) != math.floor(adjusted - adjusted * 0.15):
            disagreements += 1
    assert disagreements > 0, "if these agreed everywhere the statement's wording would not matter"


def test_missing_uncertainty_is_not_silently_treated_as_certainty():
    """Absent per-cell deviations must not become H = 0 and a free positive answer."""
    adapter = raster_adapter.ReplayRasterAdapter()
    raster = adapter.analyse(_raster_request("RU_TVER_01", 2019, 2024))
    stripped = {**raster.cells, "features": [
        {**feature, "properties": {**feature["properties"], "valid": False}}
        for feature in raster.cells["features"]]}
    assessment = _assess(raster.analysis, stripped, 2019, 2024).assessment
    assert assessment["units"]["status"] == "UNAVAILABLE"
    assert assessment["units"]["units"] is None


def test_cell_weights_decide_the_parent_parts_without_double_counting():
    adapter = raster_adapter.ReplayRasterAdapter()
    raster = adapter.analyse(_raster_request("RU_TVER_01", 2019, 2024))
    parts = carbon_adapter.baseline_parts(raster.cells, ["RU_TVER_01"], 0.0)
    assert [aoi for aoi, _ in parts] == ["RU_TVER_01"]
    assert sum(area for _, area in parts) == pytest.approx(
        raster.analysis["coverage"]["calculated_ha"], rel=1e-9)


def test_the_claim_comparison_runs_through_the_engine():
    adapter = raster_adapter.ReplayRasterAdapter()
    raster = adapter.analyse(_raster_request("RU_TVER_01", 2019, 2024))
    assessment = _assess(raster.analysis, raster.cells, 2019, 2024,
                         claimed_units=100000.0, claim_origin="USER_INPUT").assessment
    claim = assessment["claim"]
    assert claim["status"] == "PARTIALLY_SUPPORTED_BY_CASE"
    assert claim["source"] == "USER_INPUT"
    assert claim["gap_units"] == pytest.approx(100000.0 - assessment["units"]["units"])


def test_the_engine_never_imports_a_web_or_chain_library():
    source = REFERENCE.read_text(encoding="utf-8")
    for forbidden in ("fastapi", "web3", "sqlite3", "requests", "httpx"):
        assert forbidden not in source


# -- service-level wiring -----------------------------------------------------------------
def test_the_service_snapshots_the_request_before_running(harness):
    resolved = service.resolve({"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024,
                                "claimed_units": 10})
    assert resolved.snapshot["geometry"]["type"] == "Polygon"
    assert resolved.snapshot["claimed_units"] == 10.0
    assert resolved.snapshot["claim_origin"] == "USER_INPUT"
    assert resolved.input_hash.startswith("0x")


def test_the_scope_key_separates_contour_period_pool_and_method():
    first = store.scope_key(geometry_hash="0xa", year_start=2019, year_end=2024,
                            pool="AGB_LIVE_WOODY", method_version="m1")
    for changed in (
        store.scope_key(geometry_hash="0xb", year_start=2019, year_end=2024,
                        pool="AGB_LIVE_WOODY", method_version="m1"),
        store.scope_key(geometry_hash="0xa", year_start=2020, year_end=2024,
                        pool="AGB_LIVE_WOODY", method_version="m1"),
        store.scope_key(geometry_hash="0xa", year_start=2019, year_end=2024,
                        pool="WHOLE_ECOSYSTEM", method_version="m1"),
        store.scope_key(geometry_hash="0xa", year_start=2019, year_end=2024,
                        pool="AGB_LIVE_WOODY", method_version="m2"),
    ):
        assert changed != first


def test_the_method_version_names_all_three_owners(harness):
    job = harness.analyse({"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024},
                          key="version-key-00001")
    method = job["result"]["identity"]["method_version"]
    assert method.count("+") == 2
    assert method.startswith("carbon-lens-backend/")
