"""Tests for open-source retrieval, offline replay and the research experiments.

Network tests are opt-in. Everything that matters for correctness - that a
cache miss without a network is an error, that a replay serves what was
genuinely fetched, that a signed URL is refused, that item selection is
explicit - runs against the committed fixture and needs no connection.

Set `RS_CASE2_NETWORK=1` to also run the tests that reach the open catalogue.
"""
import json
import os
import shutil
from pathlib import Path

import numpy
import pytest
import rasterio

from rs.case2 import research
from rs.case2.retrieve import (
    ASSET_BY_BAND,
    RetrievalError,
    Retriever,
    compare_with_supplied,
    strip_query,
)

FIXTURE_CACHE = Path(__file__).resolve().parent / "fixtures" / "retrieval_cache"
FIXTURE_SCENE = "RU_MORDOVIA_03__S2A_38ULF_20210712_1_L2A"
NETWORK = os.environ.get("RS_CASE2_NETWORK") == "1"
needs_network = pytest.mark.skipif(
    not NETWORK, reason="set RS_CASE2_NETWORK=1 to reach the open catalogue")


@pytest.fixture
def warm_cache(tmp_path):
    """A writable copy of the committed cache, so tests never mutate the fixture."""
    destination = tmp_path / "cache"
    shutil.copytree(FIXTURE_CACHE, destination)
    return destination


# --------------------------------------------------------------------------
# Offline replay and the refusal to fake it
# --------------------------------------------------------------------------

def test_a_cache_miss_without_a_network_is_an_error(tmp_path):
    retriever = Retriever(tmp_path / "empty", allow_network=False)
    with pytest.raises(RetrievalError, match="offline replay can only serve"):
        retriever.search((43.1, 54.8, 43.2, 54.9),
                         "2021-07-12T00:00:00Z/2021-07-12T23:59:59Z")


def test_an_asset_cache_miss_without_a_network_is_not_a_local_read(warm_cache):
    retriever = Retriever(warm_cache, allow_network=False)
    document, _provenance = retriever.search(
        *_fixture_query(warm_cache))
    item = retriever.select(document["features"],
                            item_id="S2A_38ULF_20210712_1_L2A")
    with pytest.raises(RetrievalError, match="not a local read standing in"):
        retriever.fetch_window(item, "B04", (0.0, 0.0, 1.0, 1.0))


def test_offline_replay_serves_what_was_actually_fetched(dataset, warm_cache):
    retriever = Retriever(warm_cache, allow_network=False)
    result = compare_with_supplied(dataset, FIXTURE_SCENE, "B8A", retriever)
    assert result["search_provenance"]["from_cache"] is True
    assert result["asset_provenance"]["from_cache"] is True
    assert result["compared_pixels"] > 0


def test_the_retrieved_window_reproduces_the_supplied_crop(dataset, warm_cache):
    """The compatibility check: same item, our scaling, their values."""
    retriever = Retriever(warm_cache, allow_network=False)
    result = compare_with_supplied(dataset, FIXTURE_SCENE, "B8A", retriever)
    assert result["identical"], result
    assert result["max_abs_difference"] < 1e-6, (
        "a systematic difference would mean a different item or baseline")
    assert result["item"]["processing_baseline"] == result[
        "supplied_processing_baseline"]
    assert result["asset_provenance"]["source_offset"] == -0.1
    assert result["asset_provenance"]["source_scale"] == 0.0001


def test_the_cached_window_matches_its_recorded_checksum(warm_cache):
    import hashlib

    for sidecar in (warm_cache / "assets").glob("*.provenance.json"):
        provenance = json.loads(sidecar.read_text(encoding="utf-8"))
        raster = sidecar.with_name(sidecar.name.replace(".provenance.json", ".tif"))
        assert raster.is_file()
        assert hashlib.sha256(raster.read_bytes()).hexdigest() == provenance[
            "raw_sha256"], (
            "the fixture raster was altered on checkout; see rs/.gitattributes")


def test_the_cache_stays_inside_its_own_directory(warm_cache):
    retriever = Retriever(warm_cache, allow_network=False)
    assert retriever.search_dir.is_relative_to(warm_cache)
    assert retriever.asset_dir.is_relative_to(warm_cache)
    for path in warm_cache.rglob("*"):
        assert path.is_relative_to(warm_cache)


# --------------------------------------------------------------------------
# Provenance hygiene
# --------------------------------------------------------------------------

def test_a_signed_url_is_refused_rather_than_recorded():
    signed = ("https://example.blob.core.windows.net/x/B04.tif"
              "?st=2026-09-19&se=2026-09-20&sig=abcdef")
    with pytest.raises(RetrievalError, match="signing parameters"):
        strip_query(signed)


def test_an_ordinary_query_string_is_dropped_from_the_record():
    assert strip_query("https://example.com/a/B04.tif?bogus=1") == (
        "https://example.com/a/B04.tif")


def test_recorded_provenance_carries_no_query_string(warm_cache):
    for sidecar in (warm_cache / "assets").glob("*.provenance.json"):
        provenance = json.loads(sidecar.read_text(encoding="utf-8"))
        assert "?" not in provenance["asset_href"]
        assert provenance["license"].startswith("https://")
        assert "Copernicus" in provenance["required_attribution"]
        assert "supplied dataset in data/" in provenance["note"]


def test_the_provenance_records_what_a_replay_needs(warm_cache):
    sidecar = next((warm_cache / "assets").glob("*.provenance.json"))
    provenance = json.loads(sidecar.read_text(encoding="utf-8"))
    assert {"item_id", "collection", "band", "asset_key", "asset_href",
            "datetime", "processing_baseline", "source_scale", "source_offset",
            "window_bounds", "window_bounds_crs", "raw_sha256",
            "size_bytes"} <= set(provenance)


# --------------------------------------------------------------------------
# Item selection must be explicit
# --------------------------------------------------------------------------

def test_selection_refuses_to_guess():
    items = [{"id": "A", "properties": {"s2:processing_baseline": "03.01"}}]
    with pytest.raises(RetrievalError, match="must be explicit"):
        Retriever.select(items)


def test_selection_by_baseline_distinguishes_the_duplicate_items():
    """Earth Search serves one acquisition twice, at two baselines."""
    items = [
        {"id": "S2A_38ULF_20210729_0_L2A",
         "properties": {"s2:processing_baseline": "03.01"}},
        {"id": "S2A_38ULF_20210729_1_L2A",
         "properties": {"s2:processing_baseline": "05.00"}},
    ]
    assert Retriever.select(items, processing_baseline="05.00")["id"].endswith("_1_L2A")
    assert Retriever.select(items, processing_baseline="03.01")["id"].endswith("_0_L2A")


def test_an_absent_baseline_explains_why_the_choice_matters():
    items = [{"id": "A", "properties": {"s2:processing_baseline": "03.01"}}]
    with pytest.raises(RetrievalError, match=r"-0\.1 offset"):
        Retriever.select(items, processing_baseline="05.00")


def test_every_supplied_band_has_a_catalogue_asset(dataset):
    row = dataset.scenes_for("RU_TVER_01")[0]
    with rasterio.open(dataset.path(row["reflectance_path"])) as source:
        for band in source.descriptions:
            assert band in ASSET_BY_BAND, f"no STAC asset mapped for {band}"
    assert "SCL" in ASSET_BY_BAND


def test_an_unmapped_band_is_refused(warm_cache):
    retriever = Retriever(warm_cache, allow_network=False)
    item = {"id": "X", "properties": {}, "assets": {}}
    with pytest.raises(RetrievalError, match="no STAC asset is mapped"):
        retriever.fetch_window(item, "B99", (0, 0, 1, 1))


# --------------------------------------------------------------------------
# The research experiments
# --------------------------------------------------------------------------

def test_the_published_change_product_is_the_plain_annual_difference(dataset):
    """Experiment 1, first half: what kind of product the change layer is."""
    for aoi_id in sorted(dataset.geometries):
        result = research.uncertainty_transfer(dataset, aoi_id)
        assert result["difference"]["identical_to_annual_difference"], aoi_id
        assert result["difference"]["max_abs_deviation"] == 0.0


def test_the_publisher_transfers_the_two_years_as_independent(dataset):
    """Experiment 1, second half, and the reason it matters.

    If the published difference SD matched a correlated combination, a carbon
    result would inherit a much smaller uncertainty. It matches the independent
    combination instead, which settles the temporal axis - and only that axis.
    """
    for aoi_id in sorted(dataset.geometries):
        result = research.uncertainty_transfer(dataset, aoi_id)["sd_transfer"]
        assert result["ratio_to_independent_mean"] == pytest.approx(1.0, abs=0.02)
        assert result["published_mean"] > result["fully_correlated_mean"] * 1.5, (
            "a correlated transfer would be far tighter than what is published")


def test_mixing_offset_conventions_dominates_the_apparent_change(dataset):
    """Experiment 2: the control plot separates the instrument from the forest."""
    effect = research.baseline_effect(dataset, research.CONTROL_AOI, 2019, 2024)
    matched = effect["matched_offset_convention"]
    mixed = effect["mixed_offset_convention"]
    assert matched and mixed, "the control plot offers both kinds of pair"
    assert mixed["dnbr_median_mean"] < matched["dnbr_median_mean"], (
        "mixing conventions pushes dNBR further negative")
    assert abs(mixed["dnbr_median_mean"]) > 2 * abs(matched["dnbr_median_mean"])
    assert mixed["share_below_recovery_mean"] > 0.99, (
        "a mixed pair flags essentially the whole control forest as regrowth")


def test_the_disturbance_signal_survives_every_scene_choice(dataset):
    """The artefact is not symmetric: a real fire shows up in every pair."""
    effect = research.baseline_effect(dataset, research.DISTURBED_AOI, 2019, 2024)
    assert effect["pairs"]
    assert all(pair["dnbr_median"] > 0 for pair in effect["pairs"]), (
        "every pair over the burned plot shows a loss of signal")
    assert all(pair["share_above_disturbance"] > 0.25 for pair in effect["pairs"])


def test_scene_selection_now_prefers_a_matched_offset_convention(dataset):
    from rs.case2.analysis import analyse

    analysis = analyse(dataset.geometries[research.CONTROL_AOI], 2019, 2024,
                       dataset=dataset)
    note = analysis.change_evidence["scene_selection"].get("radiometric_note")
    if note is not None:
        assert note["same_offset_convention"], (
            "a pair on one convention was available and should have been chosen")
    assert "radiometric offset convention" in (
        analysis.change_evidence["scene_selection"]["rule"])


@pytest.fixture(scope="module")
def pack(dataset):
    """The whole evidence pack, built once; the tests read it from many angles."""
    return research.build(dataset)


def test_the_evidence_pack_states_what_it_is_not(pack):
    assert "not an independent validation" in " ".join(pack["limitations"])
    assert "spatial dependence" in " ".join(pack["limitations"])
    assert "no baseline, uncertainty interval or unit count" in " ".join(
        pack["limitations"])
    assert pack["control_vs_disturbed"][research.CONTROL_AOI]["e_tco2e"] < 0
    assert pack["control_vs_disturbed"][research.DISTURBED_AOI]["e_tco2e"] > 0


def test_the_evidence_pack_renders_every_section(pack, tmp_path):
    out = research.write(tmp_path / "pack", pack)
    text = (out / "research.md").read_text(encoding="utf-8")
    assert "# RS research evidence pack" in text
    assert "published SD / independent SD" in text
    assert "offset convention" in text
    for heading in ("## 3.", "## Sites", "## Coverage and insufficient data",
                    "## Threshold sensitivity",
                    "## What dNBR can and cannot say",
                    "## Satellite support is not ground truth"):
        assert heading in text, heading
    assert json.loads((out / "research.json").read_text(encoding="utf-8"))


def test_the_pack_carries_a_control_a_loss_and_a_confirmed_fire(pack):
    roles = {site["role"]: site["aoi_id"] for site in pack["sites"]}
    assert set(roles) == {"control", "pronounced loss, cause not established",
                          "confirmed fire"}
    assert roles["control"] == research.CONTROL_AOI
    assert roles["confirmed fire"] == research.DISTURBED_AOI


def test_four_products_are_reported_side_by_side_and_unreconciled(pack):
    results = {row["aoi_id"]: row for row in pack["question_3"]["results"]}
    assert set(results) == {research.CONTROL_AOI, research.LOSS_AOI,
                            research.DISTURBED_AOI}
    for row in results.values():
        for product in ("cci_biomass", "gfc_lossyear", "sentinel2_spectral",
                        "modis_burn"):
            assert row[product]["claim"]
    # The finding is the disagreement: the control plot has no canopy loss at
    # all and yet most of it flags spectrally, which is the radiometric
    # artefact the second experiment measured.
    control = results[research.CONTROL_AOI]
    assert control["gfc_lossyear"]["loss_fraction"] == 0.0
    assert control["sentinel2_spectral"]["zone_fraction"] > 0.5
    assert control["cci_biomass"]["direction"] == "accumulation"


def test_the_loss_site_has_a_real_loss_and_no_established_cause(pack):
    row = next(entry for entry in pack["question_3"]["results"]
               if entry["aoi_id"] == research.LOSS_AOI)
    assert row["gfc_lossyear"]["loss_fraction"] > 0.1
    assert row["cci_biomass"]["direction"] == "loss"
    assert row["modis_burn"]["available"] is False
    assert row["modis_burn"]["zones_supported"] == 0
    assert all(key.endswith("UNKNOWN") or key.endswith("NOT_APPLICABLE")
               for key in row["zones_by_fact_and_cause"])


def test_the_fire_site_is_the_only_one_with_an_established_cause(pack):
    row = next(entry for entry in pack["question_3"]["results"]
               if entry["aoi_id"] == research.DISTURBED_AOI)
    assert row["modis_burn"]["available"] is True
    assert row["modis_burn"]["episodes"] == 1
    assert row["modis_burn"]["zones_supported"] > 0


def test_the_pack_shows_what_incomplete_coverage_does(pack):
    coverage = pack["coverage_and_insufficient_data"]
    complete, partial = coverage["cases"]
    assert complete["complete"] is True
    assert complete["units_may_be_computed"] is True
    assert complete["area_difference_ha"] > 0

    assert partial["complete"] is False
    assert partial["units_may_be_computed"] is False
    assert partial["missing_ha"] > 0
    assert partial["area_difference_ha"] < 0
    assert "null rather than computed" in coverage["rule"]


def test_a_contour_no_product_covers_is_a_refusal_not_a_zero(pack):
    refusal = pack["coverage_and_insufficient_data"]["outside_every_product"]
    assert refusal["outcome"] == "INSUFFICIENT_DATA"
    assert refusal["code"] == "RS_NO_SOURCE_COVERAGE"
    assert "never a statement that nothing changed" in refusal["note"]


def test_the_sensitivity_grid_marks_the_published_choice_and_changes_nothing(pack):
    for block in pack["threshold_sensitivity"]:
        published = [row for row in block["grid"] if row["is_published_choice"]]
        assert len(published) == 1
        assert published[0]["dnbr_threshold"] == 0.27
        assert published[0]["mask"] == "strict"
        assert len(block["grid"]) > 1
        assert "none" in block["effect_on_the_official_result"]


def test_the_pack_separates_satellite_support_from_ground_truth(pack):
    statement = pack["satellite_support_is_not_ground_truth"]
    assert "does not establish one in the way a field visit would" in statement
    assert "no number here has been validated against the ground" in statement


def test_the_pack_states_what_a_multi_year_dnbr_cannot_measure(pack):
    dnbr = pack["dnbr_limitations"]
    assert "not a reliable absolute measure" in dnbr["finding"]
    assert "Detection" in dnbr["what_survives"] or \
        "detection" in dnbr["what_survives"]
    assert "never as recovered carbon" in dnbr["consequence"]


# --------------------------------------------------------------------------
# Benchmark
# --------------------------------------------------------------------------

def test_the_benchmark_names_the_machine_it_measured(dataset):
    from rs.case2 import bench

    result = bench.run(dataset, include_optical=False)
    cases = {row["case"] for row in result["measurements"]}
    assert {"RU_TVER_01", "RU_VOLOGDA_02", "RU_MORDOVIA_03", "RU_MORDOVIA_04",
            "CHECK_TRANSFER_01", "hand-drawn contour"} <= cases
    assert result["environment"]["platform"]
    assert "not a service level" in result["note"]
    for row in result["measurements"]:
        assert row["seconds"] > 0
        assert row["peak_python_memory_mb"] > 0


# --------------------------------------------------------------------------
# Network-dependent, opt-in
# --------------------------------------------------------------------------

@needs_network
def test_the_open_catalogue_answers_a_search_by_geometry_and_date(tmp_path, dataset):
    retriever = Retriever(tmp_path / "cache")
    bounds = dataset.geometries["RU_MORDOVIA_03"].bounds
    document, provenance = retriever.search(
        bounds, "2021-07-01T00:00:00Z/2021-07-31T23:59:59Z", limit=5)
    assert document["features"]
    assert provenance["from_cache"] is False
    assert provenance["response_sha256"]


@needs_network
def test_a_real_asset_window_is_fetched_and_matches_the_supplied_crop(
        tmp_path, dataset):
    retriever = Retriever(tmp_path / "cache")
    result = compare_with_supplied(dataset, FIXTURE_SCENE, "B8A", retriever)
    assert result["identical"]
    assert result["asset_provenance"]["from_cache"] is False
    replay = Retriever(tmp_path / "cache", allow_network=False)
    again = compare_with_supplied(dataset, FIXTURE_SCENE, "B8A", replay)
    assert again["asset_provenance"]["raw_sha256"] == result[
        "asset_provenance"]["raw_sha256"]


def _fixture_query(cache_dir):
    """The bbox and datetime the committed search response was fetched with."""
    document = json.loads(
        next((cache_dir / "search").glob("*.json")).read_text(encoding="utf-8"))
    query = document["provenance"]["query"]
    return query["bbox"], query["datetime"]
