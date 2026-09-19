"""The HTTP surface of /api/v2: shape, headers, failures and the untouched v1 boundary."""
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from backend.app.contracts import openapi_document
from backend.app.v2 import api as lens_api
from backend.app.v2.contracts import openapi_v2_document

from .conftest import ACTOR, SESSION, assert_model

GOOD = {"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024}


# -- the published document is the implemented one ----------------------------------------
def test_routes_exactly_match_the_v2_document():
    served = {(route.path, method.lower()) for route in lens_api.router.routes
              if isinstance(route, APIRoute) for method in route.methods}
    specified = {(path, method) for path, item in openapi_v2_document()["paths"].items()
                 for method in item}
    assert served == specified


def test_v2_document_is_served_as_the_contract(harness):
    response = harness.client.get("/api/v2/openapi.json", headers=harness.api.headers())
    assert response.status_code == 200
    assert response.json() == openapi_v2_document()


def test_v2_document_validates_as_openapi():
    from openapi_spec_validator import validate
    from openapi_spec_validator.readers import read_from_filename

    from backend.app.v2.contracts import CONTRACTS_V2, OPENAPI

    document, base_uri = read_from_filename(str(CONTRACTS_V2 / OPENAPI))
    validate(document, base_uri=base_uri)


def test_v1_document_is_untouched_by_the_composition(harness):
    response = harness.client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json() == openapi_document()
    assert all(not path.startswith("/api/v2") for path in response.json()["paths"])


def test_v1_routes_still_answer_beside_v2(harness):
    health = harness.client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "CONTRACT_FIXTURE"


def test_the_pydantic_body_and_the_json_schema_agree(harness):
    """A request the schema rejects must not be accepted by the model, and the reverse."""
    from backend.app.v2.contracts import api_validator, schema_errors

    cases = [
        ({"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024}, True),
        ({"aoi_id": "RU_TVER_01", "year_start": 2018, "year_end": 2024}, False),
        ({"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2025}, False),
        ({"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024, "surprise": 1}, False),
        ({"aoi_id": "RU_TVER_01", "year_start": 2019, "year_end": 2024,
          "claimed_units": -5}, False),
    ]
    for body, expected in cases:
        accepted = not schema_errors(api_validator("AnalysisRequest"), body)
        assert accepted is expected, body
        response = harness.client.post(
            "/api/v2/analyses", json=body,
            headers=harness.api.headers(actor=ACTOR, key="agreement-key-01"))
        assert (response.status_code == 202) is expected, (body, response.text)


# -- headers ------------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/catalog", "/analyses/00000000-0000-4000-8000-000000000001"])
def test_reads_require_the_demo_session(harness, path):
    response = harness.client.get("/api/v2" + path)
    assert response.status_code == 401
    assert_model(response.json(), "Error")
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_a_wrong_session_is_not_a_hint(harness):
    response = harness.client.get("/api/v2/catalog", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401
    assert "wrong-token" not in response.text


def test_the_mutation_needs_a_key_and_takes_its_caller_from_the_session(harness):
    """A role a client can set is not an authorization, so no such header is read."""
    accepted = harness.client.post("/api/v2/analyses", json=GOOD,
                                   headers={**harness.api.headers(),
                                            "Idempotency-Key": "no-actor-key-1"})
    assert accepted.status_code == 202

    without_key = harness.client.post("/api/v2/analyses", json=GOOD,
                                      headers=harness.api.headers())
    assert without_key.status_code == 422
    assert without_key.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_short_key_is_refused(harness):
    response = harness.client.post("/api/v2/analyses", json=GOOD,
                                   headers=harness.api.headers(actor=ACTOR, key="short"))
    assert response.status_code == 422


def test_every_response_carries_the_hardening_headers(harness):
    response = harness.client.get("/api/v2/catalog", headers=harness.api.headers())
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"]


# -- the catalog --------------------------------------------------------------------------
def test_catalog_describes_the_supplied_dataset(harness):
    catalog = harness.api.get("/catalog", "Catalog")
    assert [area["aoi_id"] for area in catalog["areas"]] == [
        "RU_TVER_01", "RU_VOLOGDA_02", "RU_MORDOVIA_03", "RU_MORDOVIA_04"]
    assert [item["request_id"] for item in catalog["sample_requests"]] == ["CHECK_TRANSFER_01"]
    assert [price["rub_per_unit"] for price in catalog["prices"]] == [500.0, 1500.0, 4000.0]
    assert catalog["year_min"] == 2019 and catalog["year_max"] == 2024
    assert catalog["max_area_ha"] == 2000.0


def test_catalog_names_the_adapters_actually_running(harness):
    catalog = harness.api.get("/catalog", "Catalog")
    assert catalog["raster_adapter"] == harness.lens.ports.raster.name
    assert catalog["carbon_adapter"] == harness.lens.ports.carbon.name


def test_catalog_years_come_from_the_files_on_disk(harness):
    catalog = harness.api.get("/catalog", "Catalog")
    for area in catalog["areas"]:
        assert 2019 in area["available_years"] and 2024 in area["available_years"]


# -- request validation -------------------------------------------------------------------
def _post(harness, body, key="validate-key-001"):
    return harness.client.post("/api/v2/analyses", json=body,
                               headers=harness.api.headers(actor=ACTOR, key=key))


def test_a_reversed_period_is_rejected(harness):
    response = _post(harness, {"aoi_id": "RU_TVER_01", "year_start": 2024, "year_end": 2019})
    assert response.status_code == 422
    assert_model(response.json(), "Error")


def test_a_period_outside_the_data_is_rejected(harness):
    response = _post(harness, {"aoi_id": "RU_TVER_01", "year_start": 2015, "year_end": 2024})
    assert response.status_code == 422


def test_an_unknown_area_is_not_found(harness):
    response = _post(harness, {"aoi_id": "RU_NOWHERE_99", "year_start": 2019, "year_end": 2024})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_request_without_a_contour_is_rejected(harness):
    response = _post(harness, {"year_start": 2019, "year_end": 2024})
    assert response.status_code == 422


def test_a_self_intersecting_polygon_is_not_repaired(harness):
    bowtie = {"type": "Polygon", "coordinates": [[[32.91, 56.59], [32.93, 56.60],
                                                  [32.91, 56.60], [32.93, 56.59],
                                                  [32.91, 56.59]]]}
    response = _post(harness, {"geometry": bowtie, "year_start": 2019, "year_end": 2024})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_GEOMETRY"


def test_a_contour_larger_than_the_limit_is_rejected(harness):
    huge = {"type": "Polygon", "coordinates": [[[32.0, 56.0], [33.0, 56.0], [33.0, 57.0],
                                                [32.0, 57.0], [32.0, 56.0]]]}
    response = _post(harness, {"geometry": huge, "year_start": 2019, "year_end": 2024})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "AREA_TOO_LARGE"
    assert body["error"]["details"]["max_area_ha"] == 2000.0


def test_swapped_coordinates_produce_no_data_rather_than_a_number(harness):
    """lat/lon swapped is a valid polygon somewhere else on Earth, so it is accepted.

    What must not happen is a plausible answer for a place the dataset never covered.
    """
    swapped = {"type": "Polygon", "coordinates": [[[56.59, 32.91], [56.60, 32.91],
                                                   [56.60, 32.93], [56.59, 32.93],
                                                   [56.59, 32.91]]]}
    job = harness.analyse({"geometry": swapped, "year_start": 2019, "year_end": 2024},
                          key="swapped-key-0001")
    assert job["job_state"] == "SUCCEEDED"
    units = job["result"]["units"]
    assert units["q"] is None
    assert units["unavailable_reason"] == "RASTER_ANALYSIS_UNAVAILABLE"


def test_a_negative_claim_is_rejected(harness):
    response = _post(harness, {**GOOD, "claimed_units": -1})
    assert response.status_code == 422


def test_a_claim_origin_without_a_claim_is_rejected(harness):
    response = _post(harness, {**GOOD, "claim_origin": "DEMO_INPUT"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CLAIM"


def test_an_unknown_field_is_refused_rather_than_ignored(harness):
    response = _post(harness, {**GOOD, "temporal_correlation": 0.5})
    assert response.status_code == 422


# -- failures -----------------------------------------------------------------------------
def test_an_unknown_analysis_is_404(harness):
    harness.api.get("/analyses/00000000-0000-4000-8000-0000000000aa", "Error", status=404)


def test_a_malformed_analysis_id_is_422_not_a_lookup(harness):
    harness.api.get("/analyses/not-a-uuid", "Error", status=422)


def test_an_unknown_route_under_v2_is_404_in_the_envelope(harness):
    response = harness.client.get("/api/v2/nothing-here", headers=harness.api.headers())
    assert response.status_code == 404
    assert_model(response.json(), "Error")


def test_errors_carry_no_stack_trace_or_local_path(harness):
    response = _post(harness, {"aoi_id": "RU_NOWHERE_99", "year_start": 2019, "year_end": 2024})
    text = response.text
    for leak in ("Traceback", "/Users/", "site-packages", ".py\", line"):
        assert leak not in text


def test_cors_is_off_unless_an_origin_is_configured(harness, tmp_path):
    response = harness.client.get("/api/v2/catalog",
                                  headers={**harness.api.headers(),
                                           "Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_cors_allows_only_the_configured_origin(tmp_path):
    from .conftest import Harness

    harness = Harness(tmp_path, cors_origins=("http://127.0.0.1:4173",))
    allowed = harness.client.get("/api/v2/catalog",
                                 headers={**harness.api.headers(),
                                          "Origin": "http://127.0.0.1:4173"})
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:4173"
    refused = harness.client.get("/api/v2/catalog",
                                 headers={**harness.api.headers(),
                                          "Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in refused.headers}


def test_cors_preflight_allows_the_bearer_authorization_header(tmp_path):
    from .conftest import Harness

    origin = "http://127.0.0.1:4173"
    harness = Harness(tmp_path, cors_origins=(origin,))
    for method in ("GET", "POST", "PATCH"):
        response = harness.client.options(
            "/api/v2/catalog",
            headers={"Origin": origin, "Access-Control-Request-Method": method,
                     "Access-Control-Request-Headers": "authorization"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert "authorization" in response.headers["access-control-allow-headers"].lower()


# -- measuring a contour before anything is queued ----------------------------------------
def _measure(harness, geometry, *, status: int = 200):
    response = harness.client.post("/api/v2/areas/measure", json={"geometry": geometry},
                                   headers=harness.api.headers())
    assert response.status_code == status, response.text
    body = response.json()
    assert_model(body, "AreaMeasurement" if status == 200 else "Error")
    return body


def _square(side_degrees: float, west: float = 32.92, south: float = 56.60) -> dict:
    return {"type": "Polygon", "coordinates": [[[west, south], [west + side_degrees, south],
                                                [west + side_degrees, south + side_degrees],
                                                [west, south + side_degrees], [west, south]]]}


def test_measuring_a_contour_creates_no_analysis(harness):
    body = _measure(harness, _square(0.01))
    assert body["valid"] is True and body["within_limit"] is True
    assert body["area_ha"] > 0.0
    assert body["geometry_hash"].startswith("0x")
    assert harness.counted("lens_analyses") == 0


def test_the_measured_area_is_the_area_the_analysis_reports(harness):
    """One algorithm, so a number shown before submitting cannot change afterwards."""
    from backend.app.v2 import catalog

    geometry = catalog.area("RU_TVER_01").geometry
    measured = _measure(harness, geometry)
    job = harness.analyse({"geometry": geometry, "year_start": 2019, "year_end": 2024},
                          key="measure-key-00001")
    assert job["result"]["areas"]["requested_ha"] == pytest.approx(measured["area_ha"])
    assert job["result"]["identity"]["geometry_hash"] == measured["geometry_hash"]


def test_a_contour_over_the_limit_is_reported_with_its_size_not_thrown(harness):
    from backend.app.v2.geometry import MAX_AREA_HA

    body = _measure(harness, _square(0.5))
    assert body["area_ha"] > MAX_AREA_HA
    assert body["within_limit"] is False and body["valid"] is False
    assert "AREA_LIMIT_EXCEEDED" in [item["code"] for item in body["errors"]]
    limit_error = next(item for item in body["errors"]
                       if item["code"] == "AREA_LIMIT_EXCEEDED")
    assert limit_error["details"]["max_area_ha"] == MAX_AREA_HA


def test_the_limit_the_measurement_states_is_the_limit_the_analysis_enforces(harness):
    from backend.app.v2.geometry import MAX_AREA_HA

    too_big = _square(0.5)
    assert _measure(harness, too_big)["max_area_ha"] == MAX_AREA_HA
    refused = harness.client.post(
        "/api/v2/analyses", json={"geometry": too_big, "year_start": 2019, "year_end": 2024},
        headers=harness.api.headers(key="toobig-key-000001"))
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "AREA_TOO_LARGE"


def test_an_unusable_contour_is_a_measurement_with_named_errors(harness):
    # A bow tie: never repaired silently, because a repaired ring is a different contour
    # with a different area and a different hash.
    body = _measure(harness, {"type": "Polygon",
                              "coordinates": [[[35.0, 57.0], [35.1, 57.1], [35.1, 57.0],
                                               [35.0, 57.1], [35.0, 57.0]]]})
    assert body["valid"] is False
    assert body["area_ha"] is None and body["geometry_hash"] is None
    assert [item["code"] for item in body["errors"]] == ["INVALID_GEOMETRY"]
    assert body["errors"][0]["severity"] == "BLOCKING"


@pytest.mark.parametrize("geometry", [
    {"type": "Polygon", "coordinates": []},
    {"type": "Point", "coordinates": [32.93, 56.61]},
    {"type": "Polygon", "coordinates": [[[3300000, 6200000], [3300100, 6200000],
                                             [3300100, 6200100], [3300000, 6200100],
                                             [3300000, 6200000]]]},
])
def test_empty_unsupported_and_wrong_crs_geometries_are_named(harness, geometry):
    body = _measure(harness, geometry)
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "INVALID_GEOMETRY"


def test_a_contour_outside_the_supplied_aoi_coverage_is_blocked(harness):
    outside = _square(0.01, west=35.0, south=57.0)
    body = _measure(harness, outside)
    assert body["valid"] is False
    assert body["within_limit"] is True
    assert body["geometry_hash"] is not None
    assert [item["code"] for item in body["errors"]] == ["OUTSIDE_DATA_COVERAGE"]



def test_measuring_still_needs_a_session(harness):
    response = harness.client.post("/api/v2/areas/measure",
                                   json={"geometry": _square(0.01)})
    assert response.status_code == 401
