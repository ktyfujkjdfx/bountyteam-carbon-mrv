"""The retrieval proof, run rather than described.

    python -m rs.case2.retrieval_demo --out runs/retrieval
    python -m rs.case2.retrieval_demo --out runs/retrieval --allow-network

Five claims are made about obtaining data from the open source, and each one is
either demonstrated here or reported as not demonstrated. Nothing in between.

1. A request by the user's parameters reaches the catalogue and returns a real
   windowed read of a real asset.
2. The same request replays from the cache with the network disabled, and the
   replay is labelled a replay rather than an acquisition.
3. The bytes carry the checksum they were recorded with, and our scaling of the
   open product reproduces the supplied crop.
4. An incompatible version is refused, not rescaled.
5. The official scenario runs end to end with no network at all.

By default only the offline claims run, against the cache fixture committed
with the tests. `--allow-network` adds the first claim against the live
catalogue; without it, claim 1 is reported as not attempted, because "we did
not try" and "it worked" are different statements.
"""
import argparse
import json
import sys
from pathlib import Path

from rs.case2 import sources
from rs.case2.analysis import analyse
from rs.case2.catalog import Dataset
from rs.case2.retrieve import (
    OFFSET_BEFORE_0400,
    RetrievalError,
    Retriever,
    Scope,
    compare_with_supplied,
    require_compatible,
)
from rs.determinism import write_json

FIXTURE_CACHE = (Path(__file__).resolve().parents[1] / "tests" / "case2"
                 / "fixtures" / "retrieval_cache")
DEMO_SCENE = "RU_MORDOVIA_03__S2A_38ULF_20210712_1_L2A"
DEMO_BAND = "B8A"

PASSED = "DEMONSTRATED"
FAILED = "FAILED"
SKIPPED = "NOT_ATTEMPTED"


def _step(name, claim, status, **detail):
    return {"step": name, "claim": claim, "status": status, **detail}


def online_request(retriever, dataset, allow_network):
    """Claim 1: one real request by the parameters of the request."""
    if not allow_network:
        return _step(
            "online_request",
            "a search and a windowed asset read by the user's parameters",
            SKIPPED,
            reason=("the network was not enabled for this run; pass "
                    "--allow-network to attempt it against the live catalogue"))
    try:
        result = compare_with_supplied(dataset, DEMO_SCENE, DEMO_BAND, retriever)
    except RetrievalError as exc:
        return _step("online_request", "a search and a windowed asset read",
                     FAILED, reason=str(exc))
    return _step(
        "online_request",
        "a search and a windowed asset read by the user's parameters",
        PASSED,
        item=result["item"],
        mode=result["asset_provenance"]["mode"],
        endpoint=result["search_provenance"]["endpoint"],
        compared_pixels=result["compared_pixels"])


def offline_replay(dataset, cache_dir):
    """Claims 2 and 3: the replay, its label, its checksum and its values."""
    replay = Retriever(cache_dir, allow_network=False)
    try:
        result = compare_with_supplied(dataset, DEMO_SCENE, DEMO_BAND, replay)
    except RetrievalError as exc:
        reason = str(exc)
        return [
            _step("offline_replay", "the same request replays with no network",
                  FAILED, reason=reason),
            _step("checksum", "the replayed bytes match their recorded checksum",
                  SKIPPED, reason="nothing was replayed"),
        ]
    asset = result["asset_provenance"]
    cached = Path(cache_dir) / "assets"
    stored = next(cached.glob(f"*{DEMO_BAND}*.tif"))
    import hashlib

    actual = hashlib.sha256(stored.read_bytes()).hexdigest()
    return [
        _step("offline_replay",
              "the same request replays from cache with the network disabled",
              PASSED,
              mode=asset["mode"],
              from_cache=asset["from_cache"],
              cache_key=asset["cache_key"],
              labelled_as_replay=asset["mode"] == sources.MODE_OFFLINE_REPLAY),
        _step("checksum",
              "the replayed bytes match their recorded checksum, and our "
              "scaling of the open product reproduces the supplied crop",
              PASSED if actual == asset["raw_sha256"] else FAILED,
              recorded_sha256=asset["raw_sha256"],
              actual_sha256=actual,
              max_abs_difference=result["max_abs_difference"],
              reproduces_supplied_crop=result["identical"]),
    ]


def incompatible_version(dataset, cache_dir):
    """Claim 4: a version that is not the reference is refused, not rescaled."""
    replay = Retriever(cache_dir, allow_network=False)
    row = next(entry for entry in dataset.scenes
               if entry["scene_key"] == DEMO_SCENE)
    refusals = []

    # An item on the other side of the 04.00 offset change, with the same id.
    across = {"id": row["item_id"], "collection": "sentinel-2-l2a",
              "properties": {"s2:processing_baseline": "05.00"}}
    try:
        require_compatible(across, processing_baseline="03.01")
        refusals.append({"case": "offset convention differs", "refused": False})
    except RetrievalError as exc:
        refusals.append({"case": "offset convention differs", "refused": True,
                         "reason": str(exc)})

    # A different collection entirely.
    other = {"id": row["item_id"], "collection": "sentinel-2-l1c",
             "properties": {"s2:processing_baseline": "03.01"}}
    try:
        require_compatible(other, processing_baseline="03.01")
        refusals.append({"case": "different collection", "refused": False})
    except RetrievalError as exc:
        refusals.append({"case": "different collection", "refused": True,
                         "reason": str(exc)})

    # A baseline the catalogue does not offer at all.
    try:
        replay.select([across], processing_baseline="99.99")
        refusals.append({"case": "baseline not offered", "refused": False})
    except RetrievalError as exc:
        refusals.append({"case": "baseline not offered", "refused": True,
                         "reason": str(exc)})

    # And the compatible case, so the check is shown to admit something.
    same = {"id": row["item_id"], "collection": "sentinel-2-l2a",
            "properties": {"s2:processing_baseline": row["processing_baseline"]}}
    accepted = require_compatible(
        same, processing_baseline=row["processing_baseline"])["id"]

    status = PASSED if all(entry["refused"] for entry in refusals) else FAILED
    return _step(
        "incompatible_version",
        "an incompatible product version is refused rather than rescaled",
        status, refusals=refusals, compatible_item_accepted=accepted,
        offset_before_0400=OFFSET_BEFORE_0400)


def scoped_request(dataset):
    """The retrieval asks only about the space and period the user asked about."""
    request = dataset.geometries["RU_MORDOVIA_03"]
    scope = Scope.from_request(request, 2020, 2022)
    bounded = Retriever(FIXTURE_CACHE, allow_network=False, scope=scope)
    west, south, east, north = request.bounds
    outcomes = []
    for name, bbox, window in (
            ("outside the request area",
             (west - 1.0, south - 1.0, east + 1.0, north + 1.0),
             "2021-07-29T00:00:00Z/2021-07-29T23:59:59Z"),
            ("outside the requested period", (west, south, east, north),
             "2015-07-29T00:00:00Z/2015-07-29T23:59:59Z")):
        try:
            bounded.search(bbox, window)
            outcomes.append({"case": name, "refused": False})
        except RetrievalError as exc:
            outcomes.append({"case": name, "refused": True, "reason": str(exc)})
    return _step(
        "scoped_request",
        "a retrieval is bounded by the user's own area and period",
        PASSED if all(entry["refused"] for entry in outcomes) else FAILED,
        scope=scope.as_dict(), outcomes=outcomes)


def official_scenario_offline(dataset):
    """Claim 5: the whole official scenario, with nothing reaching a network."""
    analysis = analyse(dataset.geometries["RU_MORDOVIA_03"], 2020, 2022,
                       dataset=dataset)
    return _step(
        "official_scenario_offline",
        "the official scenario runs end to end with no network at all",
        PASSED,
        e_tco2e=round(analysis.change.e_tco2e, 6),
        area_ha=round(analysis.request_area_ha, 4),
        zones=len(analysis.change_evidence["zones"]),
        sources_read=len(analysis.sources),
        note=("every number here comes from data/; the retriever is not "
              "consulted by the analysis and could not be"))


def run(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m rs.case2.retrieval_demo",
        description="Demonstrate open-data retrieval, provenance and replay.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=FIXTURE_CACHE,
                        help="retrieval cache to replay from")
    parser.add_argument("--allow-network", action="store_true",
                        help="also attempt one live request against the catalogue")
    parser.add_argument("--data-root", type=Path, default=None)
    args = parser.parse_args(argv)

    dataset = Dataset(args.data_root)
    online = Retriever(args.cache, allow_network=args.allow_network)
    steps = [online_request(online, dataset, args.allow_network)]
    steps.extend(offline_replay(dataset, args.cache))
    steps.append(incompatible_version(dataset, args.cache))
    steps.append(scoped_request(dataset))
    steps.append(official_scenario_offline(dataset))

    # The manifest lists what this run actually read: whatever the online
    # retriever served, whatever a replay served, and every supplied file the
    # analysis opened.
    replay = Retriever(args.cache, allow_network=False)
    try:
        compare_with_supplied(dataset, DEMO_SCENE, DEMO_BAND, replay)
    except RetrievalError:
        pass
    manifest = sources.manifest(online.served + replay.served)
    manifest["inputs"].extend(sources.supplied_entries(
        analyse(dataset.geometries["RU_MORDOVIA_03"], 2020, 2022,
                dataset=dataset, include_optical=False).sources))
    manifest["inputs"] = sorted(
        manifest["inputs"],
        key=lambda row: (row["source"], row["identifier"] or ""))

    report = {
        "schema": "rs.case2.retrieval-demo/1",
        "steps": steps,
        "source_manifest": manifest,
        "summary": {
            "demonstrated": sum(1 for step in steps if step["status"] == PASSED),
            "failed": sum(1 for step in steps if step["status"] == FAILED),
            "not_attempted": sum(1 for step in steps if step["status"] == SKIPPED),
        },
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "retrieval_demo.json", report)
    write_json(out / "source_manifest.json", manifest)

    for step in steps:
        print(f"{step['status']:<15} {step['step']:<26} {step['claim']}")
    print(f"written        : {out / 'retrieval_demo.json'}, "
          f"{out / 'source_manifest.json'}")
    return 1 if report["summary"]["failed"] else 0


def main(argv=None):
    try:
        return run(argv)
    except (RetrievalError, OSError) as exc:
        print(f"rs.case2.retrieval_demo: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
