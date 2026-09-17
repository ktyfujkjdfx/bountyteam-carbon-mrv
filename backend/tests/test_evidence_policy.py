"""Validation, JCS/SHA-256 and policy v1: golden fixtures, negative cases, reference parity."""
from __future__ import annotations

import copy
import shutil
import sys

import pytest

from backend.app.config import REPO_ROOT
from backend.app.contracts import canonical, digest, hash_to_bytes32, read_json, sha256_hex
from backend.app.evidence import EvidenceRejected, Limits, safe_path, validate_evidence, validate_geometry
from backend.app.policy import Policy, action_flags

from .conftest import EXPECTED, FIXTURES, fixture_evidence

sys.path.insert(0, str(REPO_ROOT / "tools"))
import contract_helpers as reference  # noqa: E402  (frozen reference validator, read-only)

LABELS = ["no_change", "fire", "insufficient"]
POLICY = Policy.load(REPO_ROOT / "config" / "policy.v1.json")
GEOMETRY = read_json(FIXTURES / "plot.json")["geometry"]


@pytest.mark.parametrize("label", LABELS)
def test_golden_fixture_hash_quality_decision(label):
    evidence = fixture_evidence(label)
    result = validate_evidence(evidence, POLICY, bundle_root=FIXTURES, geometry=GEOMETRY)
    expected = EXPECTED[label]
    for key in ("evidence_quality", "evidence_quality_score", "decision", "reason"):
        assert result[key] == expected[key]
    assert canonical(evidence) == (FIXTURES / f"verification_{label}.canonical.json").read_bytes()
    evidence_hash = sha256_hex(canonical(evidence))
    assert evidence_hash == expected["evidence_hash"]
    record = POLICY.decision_record(evidence, evidence_hash, evidence["observation"]["after"]["acquired_at"])
    assert record == expected["decision_record"]
    assert digest(record) == expected["decision_hash"]


def test_hash_field_is_not_part_of_hashed_evidence_and_rs_cannot_supply_it():
    evidence = fixture_evidence("fire")
    assert "evidence_hash" not in canonical(evidence).decode()
    for field, value in [("evidence_hash", "0x" + "1" * 64), ("status", "FROZEN"), ("confidence", 0.99),
                         ("decision", "FREEZE_REQUESTED")]:
        tampered = copy.deepcopy(evidence)
        tampered[field] = value
        with pytest.raises(EvidenceRejected):
            validate_evidence(tampered, POLICY)
    tampered = copy.deepcopy(evidence)
    tampered["outcome"] = "FROZEN"
    with pytest.raises(EvidenceRejected):
        validate_evidence(tampered, POLICY)


def test_policy_parameters_hash_is_versioned_file_digest():
    assert POLICY.parameters_hash == EXPECTED["fire"]["decision_record"]["policy_parameters_hash"]
    assert POLICY.version == "1.0.0"


def test_jcs_known_vector_and_raw_bytes32():
    sample = {"numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27], "literals": [None, True, False]}
    assert canonical(sample) == b'{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}'
    digest_hex = EXPECTED["fire"]["evidence_hash"]
    raw = hash_to_bytes32(digest_hex)
    assert len(raw) == 32 and "0x" + raw.hex() == digest_hex  # raw digest, not keccak(text=hex)


def _mutations():
    def m(fn):
        e = fixture_evidence("fire")
        fn(e)
        return e
    return {
        "bad_timestamp": m(lambda e: e["observation"]["after"].__setitem__("acquired_at", "2024-08-01")),
        "unknown_field": m(lambda e: e["metrics"].__setitem__("forest_loss_pct", 90)),
        "reversed_dates": m(lambda e: e["observation"].update(before=e["observation"]["after"],
                                                               after=e["observation"]["before"])),
        "wrong_crs": m(lambda e: e["method"]["grid"].__setitem__("epsg", 4326)),
        "wrong_resolution": m(lambda e: e["method"]["grid"]["transform"].__setitem__(0, 10)),
        "bad_area_units": m(lambda e: e["metrics"].__setitem__("affected_area_ha", 1000)),
        "bad_counts": m(lambda e: e["metrics"].__setitem__("affected_pixel_count", 2600)),
        "tiny_component": m(lambda e: e["metrics"].__setitem__("affected_pixel_count", 1)),
        "config_hash": m(lambda e: e["method"].__setitem__("config_sha256", "0x" + "2" * 64)),
        "firms_window": m(lambda e: e["firms"].__setitem__("window_start", "2024-07-11T05:00:00Z")),
        "real_relabel": m(lambda e: e.__setitem__("dataset_kind", "REAL")),
        "nan": m(lambda e: e["metrics"].__setitem__("dnbr_mean", float("nan"))),
        "outcome_disagrees": m(lambda e: e.__setitem__("outcome", "NO_CHANGE")),
        "seasonal_mismatch": m(lambda e: e["quality"].__setitem__("temporal_comparability", "NO")),
        "unattributed": m(lambda e: e["firms"].update(support="NOT_FOUND", hotspot_count=0,
                                                      matched_points_artifact_id=None)),
    }


@pytest.mark.parametrize("name,evidence", list(_mutations().items()), ids=list(_mutations()))
def test_backend_validator_agrees_with_frozen_reference(name, evidence):
    try:
        expected = reference.validate_evidence(copy.deepcopy(evidence))
    except Exception:
        expected = None
    if expected is None:
        with pytest.raises(EvidenceRejected):
            validate_evidence(evidence, POLICY)
    else:
        assert validate_evidence(evidence, POLICY) == expected


def test_geometry_hash_unclosed_ring_and_invalid_polygon_rejected():
    evidence = fixture_evidence("fire")
    evidence["plot_geometry_hash"] = "0x" + "1" * 64
    with pytest.raises(EvidenceRejected, match="geometry hash"):
        validate_evidence(evidence, POLICY, geometry=GEOMETRY)
    open_ring = copy.deepcopy(GEOMETRY)
    open_ring["coordinates"][0][-1][0] += 0.01
    with pytest.raises(EvidenceRejected):
        validate_geometry(open_ring)
    bow_tie = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    with pytest.raises(EvidenceRejected):
        validate_geometry(bow_tie)
    with pytest.raises(EvidenceRejected):
        validate_geometry({"type": "Polygon", "coordinates": [[[200, 0], [201, 1], [201, 0], [200, 0]]]})


def test_tampered_artifact_and_source_rejected(tmp_path):
    shutil.copytree(FIXTURES, tmp_path / "bundle")
    evidence = fixture_evidence("fire")
    with (tmp_path / "bundle" / evidence["artifacts"][0]["relative_path"]).open("ab") as handle:
        handle.write(b"TAMPERED")
    with pytest.raises(EvidenceRejected, match="checksum"):
        validate_evidence(evidence, POLICY, bundle_root=tmp_path / "bundle")
    shutil.rmtree(tmp_path / "bundle")
    shutil.copytree(FIXTURES, tmp_path / "bundle")
    with (tmp_path / "bundle" / "assets" / "source_forest_mask.tif").open("ab") as handle:
        handle.write(b"X")
    with pytest.raises(EvidenceRejected, match="Source checksum"):
        validate_evidence(evidence, POLICY, bundle_root=tmp_path / "bundle")


def test_oversized_artifact_rejected_before_read():
    evidence = fixture_evidence("fire")
    with pytest.raises(EvidenceRejected, match="Oversized"):
        validate_evidence(evidence, POLICY, bundle_root=FIXTURES, limits=Limits(max_artifact_bytes=16))


@pytest.mark.parametrize("value", ["../private.key", "/etc/passwd", "assets/../../private.key", "assets\\bad.tif"])
def test_path_traversal_rejected(value):
    with pytest.raises(EvidenceRejected):
        safe_path(FIXTURES, value)


def test_symlink_escape_rejected(tmp_path):
    (tmp_path / "bundle").mkdir()
    (tmp_path / "secret.txt").write_text("secret")
    (tmp_path / "bundle" / "link.txt").symlink_to(tmp_path / "secret.txt")
    with pytest.raises(EvidenceRejected):
        safe_path(tmp_path / "bundle", "link.txt")


def _counts(evidence, n, v, k):
    evidence["metrics"].update(baseline_forest_pixel_count=n, paired_valid_forest_pixel_count=v,
                               affected_pixel_count=k, baseline_forest_area_ha=n * 0.04,
                               analysed_forest_area_ha=v * 0.04, affected_area_ha=k * 0.04,
                               affected_fraction_of_baseline_forest=round(k / n, 6))
    evidence["quality"]["paired_valid_forest_ratio"] = round(v / n, 6)
    return evidence


@pytest.mark.parametrize("v,quality", [(1749, "INSUFFICIENT"), (1750, "REVIEW_REQUIRED"), (2124, "REVIEW_REQUIRED"),
                                        (2125, "SUFFICIENT")])
def test_quality_boundaries_use_integer_pixel_counts(v, quality):
    assert POLICY.evaluate(_counts(fixture_evidence("fire"), 2500, v, 400))["evidence_quality"] == quality


@pytest.mark.parametrize("pixels,decision", [(124, "REVIEW_REQUIRED"), (125, "FREEZE_REQUESTED")])
def test_five_hectare_boundary(pixels, decision):
    assert POLICY.evaluate(_counts(fixture_evidence("fire"), 2500, 2500, pixels))["decision"] == decision


def test_one_percent_threshold_in_addition_to_area():
    result = POLICY.evaluate(_counts(fixture_evidence("fire"), 20000, 20000, 125))
    assert (result["decision"], result["reason"]) == ("REVIEW_REQUIRED", "BELOW_POLICY_THRESHOLD")


def test_policy_thresholds_come_from_versioned_file(tmp_path):
    document = read_json(REPO_ROOT / "config" / "policy.v1.json")
    document["freeze_min_area_ha"] = 100
    (tmp_path / "policy.json").write_text(__import__("json").dumps(document))
    stricter = Policy.load(tmp_path / "policy.json")
    assert stricter.evaluate(fixture_evidence("fire"))["reason"] == "BELOW_POLICY_THRESHOLD"
    assert stricter.parameters_hash != POLICY.parameters_hash


def test_future_replay_rejected_and_frozen_never_auto_reactivates():
    evidence = fixture_evidence("fire")
    with pytest.raises(ValueError):
        POLICY.decision_record(evidence, EXPECTED["fire"]["evidence_hash"], "2024-07-01T00:00:00Z")
    assert not any(action_flags("FROZEN", "NO_RESTRICTION", is_latest=True, demo_authorized=True).values())
    assert not any(action_flags("ACTIVE", "NO_RESTRICTION", is_latest=True, demo_authorized=True,
                                pending_freeze=True).values())
    assert not any(action_flags("ACTIVE", "REVIEW_REQUIRED", is_latest=True, demo_authorized=True).values())
