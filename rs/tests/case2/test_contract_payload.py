"""The payload as a consumer receives it: schema, strictness, coverage, warnings.

These tests guard the serialisation boundary rather than the science. What they
check is that a real result can be parsed, validated and acted on by somebody
who did not write it: strict JSON with no NaN, a coverage fraction that is both
honest and displayable, a warning every consumer can branch on, and a content
hash that a second implementation of the same ordering reproduces.
"""
import json
import math
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from rs.case2 import artifacts, notices
from rs.case2 import manifest as manifest_module
from rs.case2 import payload as payload_module
from rs.case2.analysis import analyse
from rs.case2.payload import PayloadError
from rs.contracts import digest

ROOT = Path(__file__).resolve().parents[3]
VENDORED_SCHEMA = (Path(__file__).parent / "fixtures" / "backend_g0"
                   / "internal-models.v2.schema.json")
LIVE_SCHEMA = ROOT / "contracts" / "v2" / "internal-models.v2.schema.json"


def _schema_document():
    """Backend's contract: the live one once it lands, the copy until then."""
    path = LIVE_SCHEMA if LIVE_SCHEMA.is_file() else VENDORED_SCHEMA
    with open(path, encoding="utf-8") as handle:
        return path, json.load(handle)


def _validator(model):
    """Validate one model out of a document that holds them all.

    The contract is an OpenAPI-style bundle: the models live under
    `components/schemas` and refer to each other with local pointers. Keeping
    the whole document as the schema and adding a `$ref` to the model under
    test resolves those pointers against the document's own base, so no
    reference has to be rewritten to run this.
    """
    _path, document = _schema_document()
    return Draft202012Validator(
        {**document, "$ref": f"#/components/schemas/{model}"})


def _errors(model, instance):
    return sorted(_validator(model).iter_errors(instance),
                  key=lambda error: list(error.absolute_path))


# -- the contract ---------------------------------------------------------

def test_a_real_payload_validates_against_the_consumer_schema(tver):
    """The document Backend receives, checked with Backend's own schema."""
    errors = _errors("RasterAnalysis", payload_module.analysis_payload(tver))
    assert not errors, [f"{list(e.absolute_path)}: {e.message}" for e in errors]


def test_a_real_payload_validates_without_optical_reading(analyses):
    """`change_evidence` and `paired` are null, not absent, and that is valid."""
    payload = payload_module.analysis_payload(analyses["RU_VOLOGDA_02"])
    assert payload["change_evidence"] is None
    assert payload["optical"]["paired"] is None
    assert not _errors("RasterAnalysis", payload)


def test_the_cell_layer_validates_against_the_consumer_schema(tver):
    assert not _errors("CellLayer", payload_module.cells_payload(tver))


def test_the_manifest_validates_against_the_consumer_schema(tver):
    payload = payload_module.analysis_payload(tver)
    manifest = manifest_module.build(tver, payload)
    assert not _errors("ArtifactManifest", manifest)


def test_the_schema_copy_is_the_one_backend_published():
    """The vendored copy must not drift; a difference is a finding, not a fix."""
    if not LIVE_SCHEMA.is_file():
        pytest.skip("contracts/v2 has not landed in this branch yet")
    assert json.loads(LIVE_SCHEMA.read_text(encoding="utf-8")) == \
        json.loads(VENDORED_SCHEMA.read_text(encoding="utf-8"))


# -- strict JSON ----------------------------------------------------------

def test_the_payload_is_strict_json_with_no_nan_or_infinity(tver):
    payload = payload_module.analysis_payload(tver)
    text = json.dumps(payload, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text
    # A strict reader must be able to take it back.
    assert json.loads(text, parse_constant=_reject_constant) == payload


def _reject_constant(name):
    raise AssertionError(f"strict JSON must not contain {name}")


def test_a_non_finite_number_stops_the_run_instead_of_being_serialised():
    with pytest.raises(PayloadError):
        payload_module._round(float("nan"))
    with pytest.raises(PayloadError):
        payload_module._round({"rate": float("inf")})


def test_ensure_strict_rejects_what_round_never_sees(tver):
    payload = payload_module.analysis_payload(tver)
    assert payload_module.ensure_strict(payload) is payload
    with pytest.raises(PayloadError):
        payload_module.ensure_strict({"artifacts": [{"size_bytes": float("nan")}]})
    with pytest.raises(PayloadError):
        payload_module.ensure_strict({"grids": {1: "not a string key"}})


def test_an_unreachable_cell_carries_null_rather_than_nan(tver):
    """A NaN value becomes null with valid=false; zero AGB stays a number."""
    cell = tver.cells[0]
    broken = type(cell)(
        **{**cell.__dict__,
           "agb": {year: float("nan") for year in cell.agb},
           "agb_sd": {year: float("nan") for year in cell.agb_sd},
           "valid": False})
    zeroed = type(cell)(
        **{**cell.__dict__,
           "agb": {year: 0.0 for year in cell.agb},
           "valid": True})
    layer = payload_module.cells_payload(
        type(tver)(**{**tver.__dict__, "cells": (broken, zeroed)}))

    missing, zero = layer["features"]
    assert missing["properties"]["valid"] is False
    assert set(missing["properties"]["agb_t_ha"].values()) == {None}
    assert set(missing["properties"]["agb_sd_t_ha"].values()) == {None}
    # The geometry and the weight survive: the cell exists, its values do not.
    assert missing["properties"]["weight_ha"] > 0
    assert missing["geometry"]["type"] == "Polygon"

    assert zero["properties"]["valid"] is True
    assert set(zero["properties"]["agb_t_ha"].values()) == {0.0}
    json.dumps(layer, allow_nan=False)


def test_a_null_cell_value_is_not_yet_expressible_in_the_consumer_schema(tver):
    """A known divergence, asserted so it stays visible until Backend fixes it.

    `CellFeature.properties.agb_t_ha` is declared `{"type": "number"}`. RS has to
    emit null for a cell the map does not reach, because NaN is not JSON and
    zero is a published biomass value. The supplied rasters contain no such
    cell, so every real payload validates; this records what would happen if one
    appeared.
    """
    cell = tver.cells[0]
    broken = type(cell)(
        **{**cell.__dict__, "agb": {year: float("nan") for year in cell.agb},
           "agb_sd": {year: float("nan") for year in cell.agb_sd}, "valid": False})
    layer = payload_module.cells_payload(
        type(tver)(**{**tver.__dict__, "cells": (broken,)}))
    errors = _errors("CellLayer", layer)
    assert errors, "the schema now accepts a null cell value; drop this test"
    assert all("None is not of type 'number'" in error.message for error in errors)


# -- coverage -------------------------------------------------------------

def test_raw_coverage_may_exceed_one_and_the_published_one_never_does(tver):
    """Geodesic area is not additive; the arithmetic is published, not hidden."""
    biomass = payload_module.analysis_payload(tver)["coverage"]["biomass"]
    assert biomass["fraction_raw"] > 1.0
    assert biomass["fraction_raw"] < 1.000001
    assert biomass["fraction"] == 1.0


def test_every_coverage_axis_publishes_both_fractions(analyses, tver):
    for analysis in (*analyses.values(), tver):
        coverage = payload_module.analysis_payload(analysis)["coverage"]
        for axis in ("biomass", "biomass_sd", "optical_paired"):
            block = coverage[axis]
            assert set(block) == {"area_ha", "fraction", "fraction_raw"}
            assert 0.0 <= block["fraction"] <= 1.0
            assert block["fraction"] == min(1.0, max(0.0, block["fraction_raw"]))


def test_the_area_difference_is_signed_and_missing_area_is_not(tver):
    coverage = payload_module.analysis_payload(tver)["coverage"]
    assert coverage["area_difference_ha"] == pytest.approx(
        coverage["calculated_ha"] - coverage["requested_ha"], abs=1e-9)
    # On a fully covered request the summed weights exceed the polygon area, so
    # the signed difference is positive while the shortfall is exactly zero.
    assert coverage["area_difference_ha"] > 0
    assert coverage["missing_ha"] == 0.0
    assert coverage["complete"] is True


def test_the_cell_weight_sum_is_published_where_the_areas_are(tver):
    payload = payload_module.analysis_payload(tver)
    assert payload["coverage"]["cell_weight_sum_ha"] == \
        payload["cells"]["weight_sum_ha"]
    assert payload["cells"]["count"] == (payload["cells"]["valid_count"]
                                         + payload["cells"]["invalid_count"])


def test_a_partial_request_reports_a_negative_area_difference(dataset, sample_request):
    """The contour that hangs outside its parent area: real shortfall, real sign."""
    from shapely.geometry import box, mapping, shape

    inside = shape(sample_request["geometry"])
    lon_min, lat_min, lon_max, lat_max = inside.bounds
    half_outside = box(lon_min, lat_min, lon_max, lat_max + (lat_max - lat_min))
    analysis = analyse(mapping(half_outside), 2020, 2024, dataset=dataset,
                       include_optical=False)
    coverage = payload_module.analysis_payload(analysis)["coverage"]
    assert coverage["complete"] is False
    assert coverage["missing_ha"] > 0
    assert coverage["area_difference_ha"] < 0
    assert coverage["missing_ha"] == pytest.approx(
        -coverage["area_difference_ha"], rel=1e-9)
    assert coverage["biomass"]["fraction"] < 1.0


# -- warnings -------------------------------------------------------------

def test_every_warning_carries_a_registered_code_and_its_fixed_severity(
        tver, mordovia_03, analyses):
    seen = set()
    for analysis in (tver, mordovia_03, *analyses.values()):
        for item in payload_module.analysis_payload(analysis)["warnings"]:
            assert set(item) == {"code", "severity", "message", "details"}
            assert item["code"] in notices.SEVERITIES
            assert item["severity"] == notices.SEVERITIES[item["code"]]
            assert item["message"]
            assert isinstance(item["details"], dict)
            seen.add(item["code"])
    # The cautions these five requests genuinely raise.
    assert {notices.MODEL_YEARS_NOT_OBSERVATIONS,
            notices.CELL_WEIGHT_SUM_DIFFERS,
            notices.OPTICAL_DISABLED,
            notices.ZONE_CAUSE_UNKNOWN} <= seen


def test_a_severity_belongs_to_the_code_not_to_the_call_site():
    assert notices.SEVERITIES[notices.RADIOMETRIC_OFFSET_MIXED] == notices.CRITICAL
    assert notices.SEVERITIES[notices.RADIOMETRIC_BASELINE_DIFFERS] == notices.WARNING
    with pytest.raises(notices.NoticeError):
        notices.warning("RS_NOT_A_REAL_CODE", "anything")
    with pytest.raises(notices.NoticeError):
        notices.warning(notices.SEASONAL_GAP, "")


def test_the_radiometric_caution_is_never_lost_between_the_core_and_the_wire(tver):
    """The strongest thing RS can say about a pair has to survive the boundary."""
    note = tver.change_evidence["scene_selection"].get("radiometric_note")
    assert note, "Tver 2019-2024 selects a pair across two processing baselines"
    codes = {item["code"]: item
             for item in payload_module.analysis_payload(tver)["warnings"]}
    raised = codes.get(notices.RADIOMETRIC_OFFSET_MIXED) or \
        codes[notices.RADIOMETRIC_BASELINE_DIFFERS]
    assert raised["message"] == note["warning"]
    assert raised["details"]["same_offset_convention"] == note["same_offset_convention"]
    assert raised["details"]["before_baseline"] == note["before_baseline"]


def test_a_rejected_scene_keeps_its_own_warning(mordovia_cloudy):
    """The clouded September scene is reported as rejected, with the reason."""
    rejected = [item for item in
                payload_module.analysis_payload(mordovia_cloudy)["warnings"]
                if item["code"] == notices.SCENE_REJECTED]
    assert rejected
    for item in rejected:
        assert item["details"]["scene_key"]
        assert "usable" in item["details"]["reason"]


def test_an_absent_burn_product_is_a_warning_not_an_absence_of_fire(tver):
    absent = [item for item in payload_module.analysis_payload(tver)["warnings"]
              if item["code"] == notices.FIRE_PRODUCT_ABSENT]
    assert len(absent) == 1
    assert "not an absence of fire" not in absent[0]["message"]
    assert "absence of the product" in absent[0]["message"]


def test_warnings_and_limitations_are_separate_lists(tver):
    payload = payload_module.analysis_payload(tver)
    assert isinstance(payload["limitations"], list)
    assert all(isinstance(item, str) for item in payload["limitations"])
    assert all(isinstance(item, dict) for item in payload["warnings"])
    assert payload["limitations"] and payload["warnings"]


def test_the_worst_severity_is_reportable_without_collapsing_the_list():
    items = [notices.warning(notices.SCENE_REJECTED, "a", scene_key="x", reason="y"),
             notices.warning(notices.INCOMPLETE_COVERAGE, "b")]
    assert notices.highest_severity(items) == notices.WARNING
    assert notices.highest_severity([]) is None


# -- artifacts and the content hash ---------------------------------------

def test_every_artifact_role_is_in_the_agreed_vocabulary(tmp_path, tver):
    records = _write_artifacts(tmp_path, tver)
    roles = {item["role"] for item in records}
    assert roles <= set(artifacts.ARTIFACT_ROLES)
    assert "cci_cell_layer" in roles


def test_every_source_role_is_in_the_agreed_vocabulary(tver):
    roles = {source.role for source in tver.sources}
    assert roles <= set(artifacts.SOURCE_ROLES)
    assert "cci_biomass" in roles


def test_an_unknown_role_is_refused_rather_than_published():
    with pytest.raises(artifacts.ArtifactError):
        artifacts.record("x", role="whatever", media_type="application/json",
                         data=b"{}", relative_path="x.json")


def test_artifacts_are_matchable_by_role_and_sha256(tmp_path, tver):
    records = _write_artifacts(tmp_path, tver)
    index = artifacts.index_by_role_and_sha256(records)
    assert len(index) == len(records)
    for item in records:
        assert index[(item["role"], item["sha256"])] is item
    duplicate = dict(records[0], id="a second id for the same bytes")
    with pytest.raises(artifacts.ArtifactError):
        artifacts.index_by_role_and_sha256([*records, duplicate])


def test_the_manifest_repeats_the_artifact_rows_without_moving_the_hash(
        tmp_path, tver):
    payload = payload_module.analysis_payload(tver)
    payload["artifacts"] = _write_artifacts(tmp_path, tver)
    manifest = manifest_module.build(tver, payload)
    assert manifest["artifacts"] == payload["artifacts"]
    assert manifest["content_sha256"] == digest(payload)


def test_a_second_implementation_of_the_documented_order_gets_the_same_hash(
        tmp_path, tver):
    """The ordering Backend's adapter replicates: artifacts, then payload, then hash.

    Backend writes the artifacts, assigns them to `payload["artifacts"]` and only
    then builds the manifest. If the two implementations disagree on that order
    the hashes diverge silently, so the order is asserted rather than described.
    """
    first = payload_module.analysis_payload(tver)
    first["artifacts"] = _write_artifacts(tmp_path / "one", tver)
    mine = manifest_module.build(tver, first)["content_sha256"]

    second = payload_module.analysis_payload(tver)
    second["artifacts"] = _write_artifacts(tmp_path / "two", tver)
    theirs = manifest_module.build(tver, second)["content_sha256"]

    assert mine == theirs
    # Hashing before the artifacts are attached gives a different answer, which
    # is exactly the drift this test exists to catch.
    without = payload_module.analysis_payload(tver)
    assert digest(without) != mine


def _write_artifacts(out_dir, analysis):
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = "test"
    records = artifacts.write_cell_artifacts(
        out_dir, prefix, payload_module.cells_payload(analysis),
        analysis.grids[f"cci_biomass:{analysis.parents[0]}"])
    if analysis.raw_change is not None:
        records.extend(artifacts.write_change_artifacts(
            out_dir, prefix, analysis.raw_change, analysis.raw_change["grid"],
            out_dir))
    return records


def test_no_artifact_record_leaks_a_path_from_this_machine(tmp_path, tver):
    for item in _write_artifacts(tmp_path, tver):
        assert not Path(item["path"]).is_absolute()
        assert str(tmp_path) not in json.dumps(item)
        assert item["api_url"].startswith("artifacts/")
        assert math.isfinite(item["size_bytes"])
