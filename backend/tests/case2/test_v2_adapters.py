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

REFERENCE = REPO_ROOT / "backend" / "tests" / "case2" / "reference_engine.py"
METHOD_NUMBERS = (re.compile(r"0\.85"), re.compile(r"44\s*/\s*12"), re.compile(r"0\.47"),
                  re.compile(r"\bmath\.floor\b"), re.compile(r"0\.15\b"))


def _code_only(source: str) -> str:
    """The module with its comments and docstrings removed.

    A docstring that explains that CO2/C is written as the ratio 44/12 is documentation;
    a line that multiplies by it is the method. Only the second one matters here.
    """
    import ast

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and ast.get_docstring(node):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


# -- the boundary -------------------------------------------------------------------------
@pytest.mark.parametrize("module", [service, assemble, report_module, store, lens_api,
                                    geometry, raster_adapter])
def test_no_backend_module_contains_the_method(module):
    source = REPO_ROOT.joinpath(*module.__name__.split(".")).with_suffix(".py").read_text(
        encoding="utf-8")
    for pattern in METHOD_NUMBERS:
        assert not pattern.search(source), f"{module.__name__} contains {pattern.pattern}"


def test_no_scientific_stand_in_lives_under_the_application(harness):
    """The application ships no second implementation of the method.

    A stand-in that production code can import is a stand-in production can serve. The
    test double is in the test tree, and this walks the application to prove nothing
    there carries the arithmetic or reaches for it.
    """
    # The Lens application. The frozen P0 modules beside it are a different contract and
    # are not in scope here.
    application = REPO_ROOT / "backend" / "app" / "v2"
    for path in sorted(application.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for pattern in METHOD_NUMBERS:
            # Prose may name a coefficient; executable code may not carry one.
            assert not pattern.search(_code_only(source)), \
                f"{path} contains {pattern.pattern}"
        assert "reference_engine" not in source, path
        assert "reference_carbon" not in source, path


def test_the_duplicate_reference_engine_is_not_shipped():
    assert not REFERENCE.exists()


def test_the_carbon_adapter_calls_the_authoritative_workflow_and_adds_nothing():
    source = (REPO_ROOT / "backend" / "app" / "v2" / "adapters" / "carbon.py").read_text(
        encoding="utf-8")
    for pattern in METHOD_NUMBERS:
        assert not pattern.search(source), pattern.pattern
    assert "api.from_rs_payload(" in source
    assert "api.analyse(" in source
    for call in ("compute_interval", "compute_baseline", "compute_units", "compare_claim"):
        assert f"api.{call}(" not in source


def test_the_ports_are_satisfied_by_the_running_adapters(harness):
    assert isinstance(harness.lens.ports.raster, RasterAnalysisPort)
    assert isinstance(harness.lens.ports.carbon, CarbonAssessmentPort)
    assert harness.lens.ports.raster.name and harness.lens.ports.carbon.name


def test_the_registry_reports_what_is_actually_running():
    described = registry.describe()
    assert set(described) == {"engine_mode", "raster_core_available",
                              "carbon_engine_available", "missing_engines"}
    assert described["raster_core_available"] is raster_adapter.RS_AVAILABLE
    assert described["carbon_engine_available"] is carbon_adapter.CARBON_AVAILABLE


# -- fail closed --------------------------------------------------------------------------
def test_the_real_mode_refuses_to_build_without_the_real_engines(tmp_path):
    """No number is better than a plausible one, so a missing engine is an error."""
    if not registry.missing_engines():  # pragma: no cover - depends on the branch
        pytest.skip("both engines are merged into this branch")
    with pytest.raises(registry.EnginesUnavailable) as raised:
        registry.build_ports(tmp_path, engine_mode=registry.REAL)
    assert set(raised.value.missing) == set(registry.missing_engines())


def test_real_mode_without_rs_is_a_dependency_error(monkeypatch, tmp_path):
    monkeypatch.setattr(raster_adapter, "RS_AVAILABLE", False)
    monkeypatch.setattr(carbon_adapter, "CARBON_AVAILABLE", True)
    with pytest.raises(registry.EnginesUnavailable) as raised:
        registry.build_ports(tmp_path, engine_mode=registry.REAL)
    assert raised.value.missing == ("rs.case2",)


def test_real_mode_without_carbon_is_a_dependency_error(monkeypatch, tmp_path):
    monkeypatch.setattr(raster_adapter, "RS_AVAILABLE", True)
    monkeypatch.setattr(carbon_adapter, "CARBON_AVAILABLE", False)
    with pytest.raises(registry.EnginesUnavailable) as raised:
        registry.build_ports(tmp_path, engine_mode=registry.REAL)
    assert raised.value.missing == ("carbon",)


def test_an_import_error_inside_rs_is_not_a_fixture_fallback(monkeypatch, tmp_path):
    class BrokenRs:
        @staticmethod
        def analyse(*_args, **_kwargs):
            raise ImportError("nested raster dependency vanished")

    monkeypatch.setattr(raster_adapter, "_rs_analysis", BrokenRs())
    adapter = raster_adapter.RasterCoreAdapter(tmp_path)
    with pytest.raises(ImportError, match="nested raster dependency vanished"):
        adapter.analyse(_raster_request("RU_TVER_01", 2019, 2024))
    assert not isinstance(adapter, raster_adapter.ReplayRasterAdapter)


def test_an_import_error_inside_carbon_is_not_a_fixture_fallback(monkeypatch):
    api = carbon_adapter.engine()
    monkeypatch.setattr(api, "analyse", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        ImportError("nested carbon dependency vanished")))
    replay = raster_adapter.ReplayRasterAdapter().analyse(
        _raster_request("RU_TVER_01", 2019, 2024))
    with pytest.raises(ImportError, match="nested carbon dependency vanished"):
        _assess(replay.analysis, replay.cells, 2019, 2024)


def test_the_real_mode_never_returns_a_replay_adapter(tmp_path):
    if registry.missing_engines():
        with pytest.raises(registry.EnginesUnavailable):
            registry.build_ports(tmp_path, engine_mode=registry.REAL)
        return
    ports = registry.build_ports(tmp_path, engine_mode=registry.REAL)  # pragma: no cover
    assert not isinstance(ports.raster, raster_adapter.ReplayRasterAdapter)


def test_the_raster_port_does_not_fall_back_when_the_core_is_missing(tmp_path):
    if raster_adapter.RS_AVAILABLE:  # pragma: no cover - depends on the branch
        pytest.skip("rs.case2 is merged into this branch")
    with pytest.raises(raster_adapter.RasterCoreUnavailable):
        raster_adapter.build(tmp_path, fixture_mode=False)
    assert isinstance(raster_adapter.build(tmp_path, fixture_mode=True),
                      raster_adapter.ReplayRasterAdapter)


def test_the_carbon_port_does_not_fall_back_when_the_engine_is_missing():
    if carbon_adapter.CARBON_AVAILABLE:  # pragma: no cover - depends on the branch
        pytest.skip("carbon is merged into this branch")
    with pytest.raises(carbon_adapter.CarbonEngineUnavailable):
        carbon_adapter.engine()
    with pytest.raises(carbon_adapter.CarbonEngineUnavailable):
        carbon_adapter.CarbonAdapter()


def test_fixture_mode_still_needs_a_real_carbon_engine(tmp_path):
    """The vectors replay a raster payload, never a recorded Q."""
    if carbon_adapter.CARBON_AVAILABLE:  # pragma: no cover - depends on the branch
        pytest.skip("carbon is merged into this branch")
    with pytest.raises(registry.EnginesUnavailable) as raised:
        registry.build_ports(tmp_path, engine_mode=registry.FIXTURE)
    assert raised.value.missing == ("carbon",)


def test_an_unknown_engine_mode_is_refused(tmp_path):
    with pytest.raises(ValueError):
        registry.build_ports(tmp_path, engine_mode="ALMOST_REAL")


def test_a_demo_deployment_may_not_run_the_lens_on_fixtures():
    """Replayed vectors and measurements are indistinguishable once they are on a screen."""
    from backend.app.config import ConfigError, Settings

    with pytest.raises(ConfigError):
        Settings(demo_session="x" * 16, mode="LOCAL_DEMO", chain_adapter="web3",
                 lens_engine_mode="FIXTURE").validate()
    with pytest.raises(ConfigError):
        Settings(demo_session="x" * 16, lens_engine_mode="FIXTURE",
                 lens_require_real=True).validate()


def test_a_stand_in_can_never_be_reported_as_a_measurement(harness):
    job = harness.analyse({"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024},
                          key="origin-key-000001")
    run = job["result"]["run"]
    assert run["dataset_origin"] == "STUB_FIXTURE"
    assert run["raster_adapter"] == "backend-replay"
    assert job["result"]["fixture"] is not None


def test_an_artifact_integrity_error_does_not_change_scientific_numbers(harness):
    job = harness.analyse({"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024},
                          key="artifact-fail-key")
    analysis_id = job["analysis_id"]
    before = job["result"]["units"]
    row = harness.lens.store.artifact_rows(analysis_id)[0]
    path = harness.lens.store.artifact_root / row["storage_name"]
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"corrupt")
        response = harness.client.get(
            f"/api/v2/analyses/{analysis_id}/artifacts/{row['artifact_id']}",
            headers=harness.api.headers())
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "ARTIFACT_INTEGRITY_FAILED"
        after = harness.api.get(f"/analyses/{analysis_id}", "Analysis")["result"]["units"]
        assert after == before
    finally:
        path.write_bytes(original)


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
def _engine_under_test():
    """The only engine this branch runs."""
    return carbon_adapter.engine()


def _assess(raster: dict, cells: dict, year_start: int, year_end: int, **claim):
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    return carbon_adapter.CarbonAdapter().assess(CarbonRequest(
        raster=raster, cells=cells, geometry=polygon,
        geometry_hash=carbon_adapter.engine().geometry_hash(polygon), year_start=year_start,
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
    api = _engine_under_test()
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
    with pytest.raises(ValueError, match="excluded as invalid"):
        _assess(raster.analysis, stripped, 2019, 2024)


def test_a_missing_sd_value_is_an_explicit_adapter_error():
    adapter = raster_adapter.ReplayRasterAdapter()
    raster = adapter.analyse(_raster_request("RU_TVER_01", 2019, 2024))
    cells = {**raster.cells, "features": [dict(feature) for feature in raster.cells["features"]]}
    first = cells["features"][0]
    first["properties"] = {**first["properties"], "agb_sd_t_ha": {"2019": 1.0}}
    with pytest.raises(ValueError, match="agb_sd_t_ha has no value for 2024"):
        _assess(raster.analysis, cells, 2019, 2024)


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
    assert claim["unsupported_gap"] == pytest.approx(
        100000.0 - assessment["units"]["units"])


def test_the_engine_never_imports_a_web_or_chain_library():
    import ast

    imported = set()
    for path in sorted((REPO_ROOT / "carbon").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert imported.isdisjoint({"fastapi", "web3", "sqlite3", "requests", "httpx"})


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


def test_the_catalog_says_which_engine_mode_answered(harness):
    catalog_body = harness.api.get("/catalog", "Catalog")
    assert catalog_body["engine_mode"] in ("REAL", "FIXTURE")
    assert catalog_body["engine_mode"] == harness.settings.lens_engine_mode


def test_an_engine_that_vanishes_mid_flight_fails_the_job_without_a_number(harness):
    """A dependency that disappears ends the job. It never ends in a plausible value."""
    analysis_id = harness.submit({"aoi_id": "RU_TVER_01", "year_start": 2019,
                                  "year_end": 2024}, key="vanish-key-000001")

    class Gone:
        name = "gone"

        def assess(self, request):
            raise carbon_adapter.CarbonEngineUnavailable("engine removed")

    harness.lens.ports.__dict__["carbon"] = Gone()
    harness.run()

    view = harness.api.get(f"/analyses/{analysis_id}", "Analysis")
    assert view["job_state"] == "FAILED"
    assert view["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert view["result"] is None
