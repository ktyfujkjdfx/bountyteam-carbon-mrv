"""Adapters, scope and the manifest that makes a retrieval checkable.

The retrieval itself is covered in `test_retrieval_and_research.py`. What these
tests guard is the record around it: that each product is described by its own
adapter rather than by a shared guess, that a retrieval cannot ask about more
than the user asked about, that an incompatible version is refused instead of
rescaled, and that the manifest carries everything a checker needs and nothing
a machine should keep to itself.
"""
import json

import pytest

from rs.case2 import sources
from rs.case2.retrieve import (
    OFFSET_BEFORE_0400,
    OFFSET_FROM_0400,
    RetrievalError,
    Retriever,
    Scope,
    offset_for_baseline,
    require_compatible,
)
from rs.case2 import retrieval_demo


# -- one adapter per source ----------------------------------------------

def test_every_product_has_its_own_adapter():
    assert set(sources.ADAPTERS) == {
        "sentinel2_l2a", "cci_biomass", "gfc_lossyear", "modis_burn_date"}
    for adapter in sources.ADAPTERS.values():
        assert adapter.product and adapter.version
        assert adapter.provider and adapter.license and adapter.attribution
        assert adapter.access


def test_only_sentinel_is_retrievable_and_the_rest_say_how_they_arrive():
    assert sources.SENTINEL2_L2A.retrievable is True
    for key in ("cci_biomass", "gfc_lossyear", "modis_burn_date"):
        adapter = sources.ADAPTERS[key]
        assert adapter.retrievable is False
        # An absent fetch must not read as a failed one.
        assert "supplied with the case" in adapter.access


def test_a_source_role_maps_to_the_adapter_behind_it():
    assert sources.adapter_for("cci_biomass") is sources.CCI_BIOMASS
    assert sources.adapter_for("sentinel2_scl") is sources.SENTINEL2_L2A
    assert sources.adapter_for("sentinel2_reflectance") is sources.SENTINEL2_L2A
    # A case table is not a published product and gets no product row.
    assert sources.adapter_for("case_table") is None


def test_the_official_set_is_named_as_the_only_source_of_numbers():
    assert "only source of analysis numbers" in sources.CCI_BIOMASS.note


# -- the scope of a retrieval --------------------------------------------

def test_a_retrieval_is_bounded_by_the_requested_area(dataset, tmp_path):
    request = dataset.geometries["RU_MORDOVIA_03"]
    scope = Scope.from_request(request, 2020, 2022)
    retriever = Retriever(tmp_path, allow_network=False, scope=scope)
    west, south, east, north = request.bounds
    with pytest.raises(RetrievalError, match="outside the request"):
        retriever.search((west - 1, south - 1, east + 1, north + 1),
                         "2021-07-29T00:00:00Z/2021-07-29T23:59:59Z")


def test_a_retrieval_is_bounded_by_the_requested_period(dataset, tmp_path):
    request = dataset.geometries["RU_MORDOVIA_03"]
    retriever = Retriever(tmp_path, allow_network=False,
                          scope=Scope.from_request(request, 2020, 2022))
    with pytest.raises(RetrievalError, match="outside the requested"):
        retriever.search(request.bounds,
                         "2015-07-29T00:00:00Z/2015-07-29T23:59:59Z")


def test_a_request_inside_the_scope_passes_the_bound_and_fails_on_the_cache(
        dataset, tmp_path):
    """The scope admits the user's own area; the empty cache is what stops it."""
    request = dataset.geometries["RU_MORDOVIA_03"]
    retriever = Retriever(tmp_path, allow_network=False,
                          scope=Scope.from_request(request, 2020, 2022))
    with pytest.raises(RetrievalError, match="no cached search"):
        retriever.search(request.bounds,
                         "2021-07-12T00:00:00Z/2021-07-12T23:59:59Z")


def test_the_scope_pads_by_one_pixel_so_an_edge_window_is_not_rejected(dataset):
    request = dataset.geometries["RU_MORDOVIA_03"]
    scope = Scope.from_request(request, 2020, 2022)
    west, south, east, north = request.bounds
    scope.check_bbox((west - scope.pad / 2, south, east, north))
    with pytest.raises(RetrievalError):
        scope.check_bbox((west - scope.pad * 10, south, east, north))


# -- version compatibility ------------------------------------------------

def test_the_offset_convention_follows_the_published_baseline_rule():
    assert offset_for_baseline("03.01") == OFFSET_BEFORE_0400
    assert offset_for_baseline("04.00") == OFFSET_FROM_0400
    assert offset_for_baseline("05.00") == OFFSET_FROM_0400
    assert offset_for_baseline(None) is None


def test_an_item_across_the_offset_change_is_refused_not_rescaled():
    item = {"id": "S2A_38ULF_20210712_1_L2A", "collection": "sentinel-2-l2a",
            "properties": {"s2:processing_baseline": "05.00"}}
    with pytest.raises(RetrievalError, match="not interchangeable"):
        require_compatible(item, processing_baseline="03.01")


def test_a_different_collection_is_a_different_product():
    item = {"id": "x", "collection": "sentinel-2-l1c",
            "properties": {"s2:processing_baseline": "03.01"}}
    with pytest.raises(RetrievalError, match="different collection"):
        require_compatible(item, processing_baseline="03.01")


def test_a_matching_convention_is_accepted_even_on_a_different_baseline():
    """04.00 and 05.00 carry the same offset; the check is on the convention."""
    item = {"id": "x", "collection": "sentinel-2-l2a",
            "properties": {"s2:processing_baseline": "05.00"}}
    assert require_compatible(item, processing_baseline="04.00") is item


# -- the manifest ---------------------------------------------------------

def test_the_manifest_records_what_a_checker_needs(dataset, tver):
    entries = sources.supplied_entries(tver.sources)
    manifest = sources.manifest(entries, generated_at="2026-01-01T00:00:00+00:00")
    assert manifest["schema"] == sources.MANIFEST_SCHEMA
    assert manifest["generated_at"] == "2026-01-01T00:00:00+00:00"
    assert len(manifest["adapters"]) == 4
    assert manifest["inputs"]
    for row in manifest["inputs"]:
        assert row["source"] in sources.ADAPTERS
        assert row["product"] and row["version"]
        assert row["license"] and row["attribution"]
        assert row["identifier"]
        assert len(row["checksum_sha256"]) == 64
        assert row["mode"] in manifest["modes"]


def test_a_supplied_file_is_labelled_a_read_not_an_acquisition(tver):
    entries = sources.supplied_entries(tver.sources)
    assert {row["mode"] for row in entries} == {sources.MODE_SUPPLIED_DATASET}
    assert all(row["url"] is None for row in entries)


def test_the_case_tables_are_not_listed_as_published_products(tver):
    """areas.csv is not a product; the artifact manifest covers it instead."""
    listed = {row["identifier"] for row in sources.supplied_entries(tver.sources)}
    assert not any(name in listed for name in
                   ("data/areas.csv", "data/scenes.csv", "data/areas.geojson"))
    assert any(path.endswith(".tif") for path in listed)


def test_a_replay_that_cannot_date_itself_says_so_rather_than_guessing():
    row = sources.SENTINEL2_L2A.entry(
        identifier="x", mode=sources.MODE_OFFLINE_REPLAY, access_date=None)
    assert "unknown, not assumed" in row["access_date_note"]
    dated = sources.SENTINEL2_L2A.entry(
        identifier="x", mode=sources.MODE_OFFLINE_REPLAY,
        access_date="2026-01-01T00:00:00+00:00")
    assert "access_date_note" not in dated


def test_the_manifest_is_ordered_so_two_identical_runs_agree(tver):
    entries = sources.supplied_entries(tver.sources)
    first = sources.manifest(entries, generated_at="t")
    second = sources.manifest(list(reversed(entries)), generated_at="t")
    assert first == second


# -- the demo proof -------------------------------------------------------

@pytest.fixture(scope="module")
def demo_report(tmp_path_factory):
    out = tmp_path_factory.mktemp("retrieval_demo")
    assert retrieval_demo.main(["--out", str(out)]) == 0
    return json.loads((out / "retrieval_demo.json").read_text(encoding="utf-8"))


def test_the_demo_runs_every_offline_claim(demo_report):
    by_step = {step["step"]: step for step in demo_report["steps"]}
    for name in ("offline_replay", "checksum", "incompatible_version",
                 "scoped_request", "official_scenario_offline"):
        assert by_step[name]["status"] == retrieval_demo.PASSED, name
    assert demo_report["summary"]["failed"] == 0


def test_an_unattempted_network_claim_is_not_reported_as_a_success(demo_report):
    """"We did not try" and "it worked" are different statements."""
    online = next(step for step in demo_report["steps"]
                  if step["step"] == "online_request")
    assert online["status"] == retrieval_demo.SKIPPED
    assert "--allow-network" in online["reason"]


def test_the_replay_is_labelled_a_replay(demo_report):
    replay = next(step for step in demo_report["steps"]
                  if step["step"] == "offline_replay")
    assert replay["mode"] == sources.MODE_OFFLINE_REPLAY
    assert replay["labelled_as_replay"] is True
    assert replay["cache_key"]


def test_the_checksum_step_compares_the_bytes_on_disk(demo_report):
    checksum = next(step for step in demo_report["steps"]
                    if step["step"] == "checksum")
    assert checksum["actual_sha256"] == checksum["recorded_sha256"]
    assert checksum["reproduces_supplied_crop"] is True
    assert checksum["max_abs_difference"] < 1e-6


def test_the_official_scenario_step_reports_real_numbers(demo_report):
    official = next(step for step in demo_report["steps"]
                    if step["step"] == "official_scenario_offline")
    assert official["area_ha"] == pytest.approx(1829.5984, abs=1e-4)
    assert official["zones"] > 0
    assert "the retriever is not consulted" in official["note"]


def test_the_demo_manifest_holds_no_secret_and_no_local_path(demo_report):
    text = json.dumps(demo_report["source_manifest"])
    for marker in ("X-Amz", "Signature", "token=", "AWSAccessKeyId",
                   "C:\\", "/home/", "/Users/"):
        assert marker not in text, marker
    assert "earth-search.aws.element84.com" in text


def test_the_demo_manifest_separates_what_was_replayed_from_what_was_read(
        demo_report):
    modes = {row["mode"] for row in demo_report["source_manifest"]["inputs"]}
    assert sources.MODE_SUPPLIED_DATASET in modes
    assert sources.MODE_OFFLINE_REPLAY in modes
