"""One-off driver that acquires real Sentinel-2 data for a configured AOI
(default: rs/configs/aoi_dadia.json) and produces its evidence bundle(s).

Usage: python -m rs.build_bundles [scenario|all] [--config path/to/aoi.json]

This is the concrete, reproducible instantiation of `rs/acquire.py` +
`rs/verify.py` for a chosen real event; it is not itself part of the frozen
contract path (`python -m rs.verify --request ... --output ...` is).
"""
import json
import sys
import uuid
from pathlib import Path

from rs import acquire, stac, verify
from rs.contracts import digest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "rs" / "configs" / "aoi_dadia.json"
# Not named "data"/"cache"/"runtime": those are gitignored repo-wide and this
# cache of AOI-windowed source rasters is committed for offline reproducibility.
DATA_ROOT = ROOT / "rs" / "sources"


def _scene_descriptor(config, scene_id, datetime_range):
    item = stac.get_item(config["stac_collection"], scene_id, config["stac_bbox_hint"], datetime_range)
    bbox = config["stac_bbox_hint"]
    local_paths = acquire.fetch_scene_bands(item, bbox, DATA_ROOT, config["plot_id"], scene_id)
    return acquire.build_scene_descriptor(item, local_paths)


def build_scenario(config, name, *, site_tag):
    scenario = config["scenarios"][name]
    plot_id = config["plot_id"]
    geometry = config["geometry"]
    plot_geometry_hash = digest(geometry)

    before = _scene_descriptor(config, scenario["before_scene_id"], scenario["before_datetime_range"])
    after = _scene_descriptor(config, scenario["after_scene_id"], scenario["after_datetime_range"])

    forest_mask_path = DATA_ROOT / plot_id / "forest_mask_source.tif"
    if not forest_mask_path.exists():
        acquire.fetch_forest_mask_source(config["stac_bbox_hint"], DATA_ROOT, plot_id)

    request_name = f"request_{name}" if not site_tag else f"request_{site_tag}_{name}"
    request_path = ROOT / "rs" / "configs" / f"{request_name}.json"
    acquire.write_request(
        request_path,
        request_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{plot_id}:{name}")),
        plot_id=plot_id,
        geometry=geometry,
        plot_geometry_hash=plot_geometry_hash,
        before=before,
        after=after,
        data_root=str(DATA_ROOT.relative_to(ROOT)).replace("\\", "/"),
        dataset_kind="REAL",
    )

    bundle_name = name if not site_tag else f"{site_tag}_{name}"
    output_dir = ROOT / "rs" / "bundles" / bundle_name
    evidence = verify.run(request_path, output_dir)
    print(f"[{site_tag}/{name}] outcome={evidence['outcome']} bundle={output_dir}")
    return evidence


def main(argv=None):
    argv = argv or sys.argv[1:]
    config_path = DEFAULT_CONFIG_PATH
    positional = []
    i = 0
    while i < len(argv):
        if argv[i] == "--config":
            config_path = Path(argv[i + 1])
            i += 2
        else:
            positional.append(argv[i])
            i += 1
    which = positional[0] if positional else "all"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    # The original primary-AOI run kept unprefixed request_<scenario>.json /
    # bundles/<scenario> paths; only additional (e.g. reserve) configs get a
    # site tag, so re-running the default config never orphans those files.
    site_tag = "" if config_path == DEFAULT_CONFIG_PATH else config_path.stem.replace("aoi_", "")
    names = list(config["scenarios"]) if which == "all" else [which]
    for name in names:
        build_scenario(config, name, site_tag=site_tag)


if __name__ == "__main__":
    main()
