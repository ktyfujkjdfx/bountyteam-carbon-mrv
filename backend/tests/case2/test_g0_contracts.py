"""G0: the v2 contract documents, their fixtures and the boundary they must not cross.

These tests are about the contract itself, not about the running service. They fail if a
schema stops describing its own examples, if an enumeration loses a member consumers rely
on, if a fixture loses its label, or if anything v2 leaks into the frozen v1 application.
"""
from __future__ import annotations

import json
import math

import pytest
from jsonschema import Draft202012Validator

from backend.app import main as v1_main
from backend.app.contracts import openapi_document
from backend.app.v2 import contracts as v2

API_FIXTURES = {
    "analysis_result_available.json": "AnalysisResult",
    "analysis_result_zero_units.json": "AnalysisResult",
    "analysis_result_unavailable.json": "AnalysisResult",
}
INTERNAL_FIXTURES = {
    "raster_analysis.json": "RasterAnalysis",
    "cell_layer.geojson": "CellLayer",
    "carbon_assessment.json": "CarbonAssessment",
    "artifact_manifest.json": "ArtifactManifest",
}
LABELLED_FIXTURES = sorted(API_FIXTURES) + ["doc_example_units.json"]
KNOWN_LABELS = {"DOC_EXAMPLE", "UNIT_TEST_VECTOR", "CONTRACT_FIXTURE"}


# -- the documents themselves ------------------------------------------------------------
@pytest.mark.parametrize("document", [v2.API_MODELS, v2.INTERNAL_MODELS])
def test_schema_documents_are_valid_draft_2020_12(document):
    schema = v2._document(document)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["components"]["schemas"], "a contract document with no models is not a contract"


def test_every_ref_inside_the_schema_documents_resolves():
    for document in (v2.API_MODELS, v2.INTERNAL_MODELS):
        schema = v2._document(document)
        known = set(schema["components"]["schemas"])
        for ref in _collect_refs(schema):
            assert ref.startswith("#/components/schemas/"), f"{document} uses an external $ref: {ref}"
            assert ref.rsplit("/", 1)[1] in known, f"{document} references a missing model: {ref}"


def _collect_refs(node) -> list[str]:
    if isinstance(node, dict):
        found = [node["$ref"]] if isinstance(node.get("$ref"), str) else []
        for value in node.values():
            found.extend(_collect_refs(value))
        return found
    if isinstance(node, list):
        return [ref for item in node for ref in _collect_refs(item)]
    return []


def test_openapi_v2_describes_exactly_the_agreed_routes():
    document = v2.openapi_v2_document()
    assert document["openapi"].startswith("3.1")
    assert {(path, method) for path, item in document["paths"].items() for method in item} == {
        ("/auth/login", "post"),
        ("/auth/me", "get"),
        ("/auth/logout", "post"),
        ("/catalog", "get"),
        ("/areas/measure", "post"),
        ("/requests", "post"),
        ("/requests", "get"),
        ("/requests/{request_id}", "get"),
        ("/requests/{request_id}", "patch"),
        ("/requests/{request_id}/submit", "post"),
        ("/requests/{request_id}/analysis", "post"),
        ("/requests/{request_id}/finalize", "post"),
        ("/analyses", "post"),
        ("/analyses/{analysis_id}", "get"),
        ("/analyses/{analysis_id}/artifacts/{artifact_id}", "get"),
        ("/analyses/{analysis_id}/report", "get"),
        ("/analyses/{analysis_id}/value", "get"),
        ("/analyses/{analysis_id}/proof", "get"),
    }


def test_openapi_v2_documents_the_agreed_failure_codes():
    document = v2.openapi_v2_document()
    for path, item in document["paths"].items():
        for method, operation in item.items():
            codes = set(operation["responses"])
            assert "401" in codes, f"{method} {path} does not document 401"
            assert "503" in codes, f"{method} {path} does not document 503"
            # A route with a body or a path parameter can be sent a malformed one.
            if "{" in path or method == "post":
                if path not in ("/auth/logout",):
                    assert "422" in codes, f"{method} {path} does not document 422"
            # Anything that touches the work can be refused by role; signing in cannot.
            if not path.startswith("/auth/"):
                assert "403" in codes, f"{method} {path} does not document 403"
            if "{analysis_id}" in path:
                assert "404" in codes, f"{method} {path} does not document 404"
    assert "409" in document["paths"]["/analyses"]["post"]["responses"]


def test_openapi_v2_only_references_models_that_exist():
    api = set(v2._document(v2.API_MODELS)["components"]["schemas"])
    for ref in _collect_refs(v2.openapi_v2_document()):
        if ref.startswith("#/components/"):
            continue
        file_part, _, model = ref.partition("#")
        assert file_part == v2.API_MODELS, f"OpenAPI references an unexpected document: {ref}"
        assert model.rsplit("/", 1)[1] in api, f"OpenAPI references a missing model: {ref}"


# -- fixtures ----------------------------------------------------------------------------
@pytest.mark.parametrize("name,model", sorted(API_FIXTURES.items()))
def test_api_fixtures_match_the_public_schema(name, model):
    v2.validate(v2.api_validator(model), v2.fixture(name), model)


@pytest.mark.parametrize("name,model", sorted(INTERNAL_FIXTURES.items()))
def test_internal_fixtures_match_the_adapter_schema(name, model):
    v2.validate(v2.internal_validator(model), v2.fixture(name), model)


@pytest.mark.parametrize("name", LABELLED_FIXTURES)
def test_every_fixture_says_what_it_is(name):
    label = v2.fixture(name)["fixture"]
    assert label["kind"] in KNOWN_LABELS
    assert label["label"] and label["note"], "a label without an explanation is not a label"


def test_internal_fixtures_are_marked_as_fixtures_too():
    """The internal payloads carry their provenance in the artifact records and the note."""
    raster = v2.fixture("raster_analysis.json")
    assert all(item["provenance"] == "CONTRACT_FIXTURE" for item in raster["artifacts"])
    assert "CONTRACT_FIXTURE" in v2.fixture("cell_layer.geojson")["note"]


def test_http_examples_reference_only_existing_fixtures():
    examples = v2.fixture("http_examples.v2.json")
    for name, example in examples.items():
        if name == "note":
            continue
        referenced = example["response"].get("result_fixture")
        if referenced:
            assert (v2.FIXTURES_V2 / referenced).is_file()


def test_http_error_examples_match_the_error_envelope():
    examples = v2.fixture("http_examples.v2.json")
    validator = v2.api_validator("Error")
    checked = 0
    for name, example in examples.items():
        if name == "note":
            continue
        body = example["response"].get("body")
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            v2.validate(validator, body, "Error")
            checked += 1
    assert checked >= 4, "the failure envelope needs more than one worked example"


def test_accepted_example_matches_the_accepted_model():
    examples = v2.fixture("http_examples.v2.json")
    v2.validate(v2.api_validator("AnalysisAccepted"),
                examples["createAnalysis"]["response"]["body"], "AnalysisAccepted")
    v2.validate(v2.api_validator("AnalysisRequest"),
                examples["createAnalysis"]["request"]["body"], "AnalysisRequest")


def test_running_analysis_example_carries_no_result_yet():
    body = v2.fixture("http_examples.v2.json")["getAnalysis_running"]["response"]["body"]
    v2.validate(v2.api_validator("Analysis"), body, "Analysis")
    assert body["job_state"] == "RUNNING" and body["result"] is None


# -- the independent status axes ---------------------------------------------------------
def _enum(model: str) -> set[str]:
    return set(v2._document(v2.API_MODELS)["components"]["schemas"][model]["enum"])


def test_the_six_status_axes_are_separate_enumerations():
    assert _enum("JobState") == {"QUEUED", "RUNNING", "SUCCEEDED", "FAILED"}
    assert _enum("CalculationStatus") == {"AVAILABLE", "UNAVAILABLE"}
    assert _enum("EvidenceStatus") == {"SUFFICIENT", "REVIEW_REQUIRED", "INSUFFICIENT"}
    assert _enum("AnchorStatus") == {"NOT_REQUESTED", "PENDING", "CONFIRMED", "FAILED"}
    assert _enum("PassportStatus") == {"DRAFT", "FINALIZED"}
    assert _enum("ClaimStatus") == {
        "NOT_PROVIDED", "NOT_APPLICABLE", "NOT_COMPARABLE", "UNASSESSABLE",
        "SUPPORTED_BY_CASE", "PARTIALLY_SUPPORTED_BY_CASE", "NOT_SUPPORTED_BY_CASE"}
    # The document status of a passport and the existence of a chain record are two
    # different questions, so the two vocabularies must not share a single word.
    assert not _enum("PassportStatus") & _enum("AnchorStatus")


def test_zero_reasons_and_unavailable_reasons_are_different_vocabularies():
    zero = _enum("ZeroUnitsReason")
    unavailable = _enum("UnavailableReason")
    assert zero == {"NON_POSITIVE_RELATIVE_RESULT", "UNCERTAINTY_TOO_HIGH", "ROUNDED_TO_ZERO"}
    assert not zero & unavailable, "a reason that means both null and zero would erase the difference"


def test_zero_reasons_are_exactly_the_engine_vocabulary():
    """The carbon engine owns these strings; the contract must not invent a synonym."""
    pytest.importorskip("carbon", reason="carbon engine not merged into this branch yet")
    from carbon import reasons

    assert _enum("ZeroUnitsReason") == set(reasons.ZERO_UNIT_REASONS)
    assert _enum("ClaimStatus") == set(reasons.CLAIM_STATUSES)
    assert set(reasons.UNAVAILABLE_REASONS) <= _enum("UnavailableReason")


def test_no_public_investability_or_fraud_vocabulary():
    text = json.dumps(v2._document(v2.API_MODELS), ensure_ascii=False).upper()
    for forbidden in ("INVESTABLE", "PROVEN_FRAUD", "FRAUD_DETECTED", "APPROVED_FOR_PURCHASE"):
        assert forbidden not in text


def test_zone_fact_and_cause_are_separate_claims():
    assert _enum("ZoneFact") == {"TREE_COVER_LOSS", "SPECTRAL_CHANGE_ONLY", "RECOVERY_INDICATION"}
    assert "UNKNOWN" in _enum("ZoneCause"), "absent evidence must have somewhere honest to land"


def test_stub_origin_cannot_be_confused_with_real_computation():
    assert "STUB_FIXTURE" in _enum("DatasetOrigin")
    assert "COMPUTED_FROM_SUPPLIED_DATA" in _enum("DatasetOrigin")


# -- q = null and q = 0 are different answers ---------------------------------------------
def test_available_fixture_reproduces_the_official_example():
    units = v2.fixture("analysis_result_available.json")["units"]
    assert units["status"] == "AVAILABLE"
    assert units["q"] == 395
    assert units["zero_reason"] is None and units["unavailable_reason"] is None
    assert math.isclose(units["r_tco2e"], 517.0, rel_tol=1e-9)
    assert math.isclose(units["ratio"], 0.2, rel_tol=1e-9)
    assert math.isclose(units["radj_tco2e"], 465.3, rel_tol=1e-9)


def test_zero_fixture_is_zero_with_a_zero_reason():
    units = v2.fixture("analysis_result_zero_units.json")["units"]
    assert units["status"] == "AVAILABLE"
    assert units["q"] == 0
    assert units["zero_reason"] == "NON_POSITIVE_RELATIVE_RESULT"
    assert units["unavailable_reason"] is None


def test_unavailable_fixture_is_null_with_an_unavailable_reason():
    result = v2.fixture("analysis_result_unavailable.json")
    units = result["units"]
    assert units["status"] == "UNAVAILABLE"
    assert units["q"] is None
    assert units["unavailable_reason"] == "INCOMPLETE_COVERAGE"
    assert units["zero_reason"] is None
    assert result["calculation_status"] == "UNAVAILABLE"
    # Partial coverage is still a scientific outcome: the stock change survives.
    assert result["change"]["delta_carbon_tc"] is not None
    # And there is exactly one place the emission is published.
    assert result["change"]["eproj_ref"] == "units.eproj_tco2e"
    assert "eproj_tco2e" not in result["change"]


def test_unavailable_units_carry_no_scenario_money():
    values = v2.fixture("analysis_result_unavailable.json")["scenario_values"]
    assert values["low"] is None and values["base"] is None and values["high"] is None


def test_a_claim_against_a_null_q_is_unassessable_not_unsupported():
    claim = v2.fixture("analysis_result_unavailable.json")["claim"]
    assert claim["status"] == "UNASSESSABLE"
    assert claim["unsupported_gap"] is None and claim["scenario_gap_values"] is None


def test_a_claim_above_a_positive_q_is_partially_supported():
    claim = v2.fixture("analysis_result_available.json")["claim"]
    assert claim["status"] == "PARTIALLY_SUPPORTED_BY_CASE"
    assert claim["unsupported_gap"] == pytest.approx(600.0 - 395)
    assert claim["supported_share"] == pytest.approx(395 / 600)
    assert claim["scenario_gap_values"]["base"]["value_rub"] == pytest.approx(205 * 1500.0)


# -- the doc example as pure arithmetic ---------------------------------------------------
def test_doc_example_vector_is_internally_consistent():
    vector = v2.fixture("doc_example_units.json")
    given, expected, tol = vector["input"], vector["expected"], vector["tolerance"]
    area, cf, co2 = given["area_ha"], given["cf_agb"], given["co2_per_c"]

    start = given["mean_agb_start_tdm_ha"] * cf
    end = given["mean_agb_end_tdm_ha"] * cf
    delta = (end - start) * area
    eproj = -delta * co2
    ebase = -(given["baseline_stock_end_tc_ha"] - given["baseline_stock_start_tc_ha"]) * area * co2
    r = ebase - eproj - given["leakage_tco2e"]
    h = given["half_width_tco2e"]
    ratio = h / r
    unc = min(1.0, max(0.0, ratio - given["unc_allowance"]))
    radj = r * (1.0 - unc)

    assert delta == pytest.approx(expected["delta_carbon_tc"], abs=tol)
    assert eproj == pytest.approx(expected["eproj_tco2e"], abs=tol)
    assert ebase == pytest.approx(expected["ebase_tco2e"], abs=tol)
    assert r == pytest.approx(expected["r_tco2e"], abs=1e-6)
    assert ratio == pytest.approx(expected["ratio"], abs=1e-9)
    assert radj == pytest.approx(expected["radj_tco2e"], abs=1e-6)
    assert math.floor(radj * 0.85) == expected["q"] == 395


def test_q_uses_the_literal_factor_of_the_statement():
    """floor(Radj x 0.85) and floor(Radj - Radj x 0.15) are not the same integer."""
    vector = v2.fixture("doc_example_units.json")
    radj = vector["expected"]["radj_tco2e"]
    assert math.floor(radj * 0.85) == vector["expected"]["q"]
    residual = radj - vector["expected"]["buffer_tco2e"] - vector["expected"]["q"]
    assert 0.0 <= residual <= 1.0
    assert residual == pytest.approx(vector["expected"]["rounding_residual_tco2e"], abs=1e-9)


# -- the frozen v1 boundary ---------------------------------------------------------------
def test_v1_openapi_still_knows_nothing_about_v2():
    document = openapi_document()
    assert all(not path.startswith("/api/v2") for path in document["paths"])
    assert document["servers"][0]["url"].endswith("/api/v1")


def test_the_v1_application_exposes_no_v2_route(tmp_path):
    from backend.tests.conftest import make_settings

    app = v1_main.create_app(settings=make_settings(tmp_path))
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any("/api/v2" in path for path in paths)
    assert not any(path.startswith("/api/v2") for path in
                   (getattr(route, "path", "") for route in v1_main.router.routes))


def test_v2_documents_live_beside_v1_and_do_not_replace_it():
    assert (v2.CONTRACTS_V2 / v2.API_MODELS).is_file()
    assert (v2.CONTRACTS_V2.parent / "openapi.yaml").is_file()
    assert (v2.CONTRACTS_V2.parent / "api-models.schema.json").is_file()
    assert v2.CONTRACTS_V2.name == "v2"


# -- forward compatibility of the enumerations --------------------------------------------
def test_every_public_enumeration_is_closed():
    """A value that is not in the contract never reaches a consumer.

    The other half of this bargain lives in `docs/case2/G0_CONTRACT.md`: consumers must
    treat an unrecognised value as unknown rather than crash, so that adding one is a
    contract change and not an outage.
    """
    schemas = v2._document(v2.API_MODELS)["components"]["schemas"]
    enums = {name: body for name, body in schemas.items() if "enum" in body}
    assert len(enums) >= 15
    for name, body in enums.items():
        assert body["type"] == "string", name
        assert len(set(body["enum"])) == len(body["enum"]), name
        assert all(value == value.upper() for value in body["enum"]), name


def test_an_undeclared_enum_value_is_refused_rather_than_served():
    result = v2.fixture("analysis_result_available.json")
    result["units"]["zero_reason"] = "SOME_FUTURE_REASON"
    with pytest.raises(v2.ContractViolation):
        v2.validate(v2.api_validator("AnalysisResult"), result, "AnalysisResult")


def test_a_zero_claim_has_its_own_status_and_its_own_reason():
    statuses, reasons = _enum("ClaimStatus"), _enum("ClaimMismatchReason")
    assert "NOT_APPLICABLE" in statuses
    assert "NO_POSITIVE_CLAIM" in reasons
    # It is a reason for not comparing, not a reason the claim disagreed.
    assert "NO_POSITIVE_CLAIM" not in statuses


def test_the_spatial_scenarios_are_named_as_the_method_freeze_names_them():
    assert _enum("SpatialDependence") == {"INDEPENDENT_NATIVE_CELLS",
                                          "FULL_SPATIAL_CORRELATION"}
