"""Provenance: the official catalogue, recomputed checksums and what they do not prove."""
from __future__ import annotations

import pytest

from carbon import build_provenance, parameters_snapshot, verify_files
from carbon.parameters import DEFAULT_PARAMETERS, METHOD_VERSION
from carbon.provenance import (
    CHECKSUM_MISMATCH,
    CHECKSUM_MISSING,
    CHECKSUM_OK,
    CHECKSUM_UNREADABLE,
    METHODOLOGY_FILES,
    load_file_catalogue,
    load_sources,
)

CCI_2019 = "RU_TVER_01/CCI_Biomass_2019.tif"
CCI_2024 = "RU_TVER_01/CCI_Biomass_2024.tif"


@pytest.fixture(scope="module")
def catalogue():
    return load_file_catalogue()


def test_the_catalogue_covers_every_supplied_area(catalogue):
    per_area = {record.aoi_id for record in catalogue.values() if record.aoi_id}
    assert per_area == {
        "RU_TVER_01", "RU_VOLOGDA_02", "RU_MORDOVIA_03", "RU_MORDOVIA_04",
    }
    assert CCI_2019 in catalogue
    assert catalogue[CCI_2019].product_version == "7.0"
    assert catalogue[CCI_2019].crs == "EPSG:4326"
    # dataset-level files carry no aoi_id but are catalogued and checksummed too
    for relative in METHODOLOGY_FILES:
        assert relative in catalogue


def test_supplied_files_match_their_declared_checksums():
    checks = verify_files([CCI_2019, CCI_2024])
    assert [check.status for check in checks] == [CHECKSUM_OK, CHECKSUM_OK]
    assert all(check.computed_sha256 == check.declared_sha256 for check in checks)


def test_a_file_outside_the_catalogue_is_reported_not_ignored():
    checks = verify_files(["RU_TVER_01/NOT_SUPPLIED.tif"])
    assert checks[0].status == CHECKSUM_MISSING
    assert checks[0].ok is False


def test_a_missing_file_on_disk_is_reported(tmp_path, catalogue):
    checks = verify_files([CCI_2019], catalogue=catalogue, data_root=tmp_path)
    assert checks[0].status == CHECKSUM_UNREADABLE
    assert checks[0].computed_sha256 is None


def test_an_altered_file_is_caught(tmp_path, catalogue):
    target = tmp_path / "RU_TVER_01"
    target.mkdir()
    (target / "CCI_Biomass_2019.tif").write_bytes(b"not the supplied raster")
    checks = verify_files([CCI_2019], catalogue=catalogue, data_root=tmp_path)
    assert checks[0].status == CHECKSUM_MISMATCH
    assert checks[0].computed_sha256 != checks[0].declared_sha256


def test_provenance_records_the_licence_and_attribution_of_every_source_used():
    provenance = build_provenance(relative_paths=[CCI_2019, CCI_2024])
    assert provenance["all_checksums_match"] is True
    identifiers = [source["source_id"] for source in provenance["sources"]]
    assert identifiers[0] == "CCI_V7"
    assert "CASE_RULES_V1" in identifiers, "the case rules are an input, not a background fact"
    source = provenance["sources"][0]
    assert source["license_url"].startswith("https://")
    assert source["doi"]
    assert source["required_attribution"]
    assert source["limitations"]


def test_every_passport_checksums_the_methodology_tables():
    """Q depends on parameters.csv and baseline.csv whatever rasters were read."""
    provenance = build_provenance(relative_paths=[])
    recorded = {entry["relative_path"] for entry in provenance["files"]}
    assert set(METHODOLOGY_FILES) <= recorded
    assert provenance["all_checksums_match"] is True


def test_the_methodology_tables_are_not_listed_twice():
    provenance = build_provenance(relative_paths=[CCI_2019, *METHODOLOGY_FILES])
    listed = [entry["relative_path"] for entry in provenance["files"]]
    assert len(listed) == len(set(listed))


def test_provenance_names_only_the_official_roots():
    provenance = build_provenance(relative_paths=[CCI_2019])
    assert provenance["official_roots"] == ["data/", "doc/"]


def test_provenance_does_not_claim_the_estimate_is_correct():
    provenance = build_provenance(relative_paths=[CCI_2019])
    assert "не подтверждает правильность самой оценки" in provenance["note"]


def test_a_broken_checksum_makes_the_provenance_say_so(tmp_path, catalogue):
    target = tmp_path / "RU_TVER_01"
    target.mkdir()
    (target / "CCI_Biomass_2019.tif").write_bytes(b"tampered")
    provenance = build_provenance(
        relative_paths=[CCI_2019], catalogue=catalogue, data_root=tmp_path
    )
    assert provenance["all_checksums_match"] is False
    assert provenance["files"][0]["checksum_status"] == CHECKSUM_MISMATCH


def test_the_parameters_snapshot_is_the_official_table():
    snapshot = parameters_snapshot()
    assert snapshot["cf_agb"] == DEFAULT_PARAMETERS.cf_agb == 0.47
    assert snapshot["co2_per_c_exact"] == "44/12"
    assert snapshot["co2_per_c"] == 44 / 12
    assert snapshot["unc_allowance"] == 0.10
    assert snapshot["unc_stop_ratio"] == 1.0
    assert snapshot["buffer_share"] == 0.15
    assert snapshot["unit_share"] == 0.85
    assert snapshot["leakage_tco2e"] == 0.0
    assert snapshot["prices_rub"] == [500.0, 1500.0, 4000.0]
    assert snapshot["source"] == "data/methodology/parameters.csv"


def test_the_snapshot_records_the_method_version():
    assert build_provenance(relative_paths=[])["method_version"] == METHOD_VERSION


def test_the_source_registry_declares_the_dependence_limitation():
    """The publisher itself warns about dependent errors; the passport must carry that."""
    sources = load_sources()
    assert "CCI_V7" in sources
    assert "зависим" in sources["CCI_V7"].limitations.lower()
