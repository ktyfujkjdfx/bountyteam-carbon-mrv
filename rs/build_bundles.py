"""One-off driver that acquires real Sentinel-2 data for the Dadia AOI
(rs/configs/aoi_dadia.json) and produces both P0 evidence bundles.

Usage: python -m rs.build_bundles [no_change|fire|all]

This is the concrete, reproducible instantiation of `rs/acquire.py` +
`rs/verify.py` for the chosen real event; it is not itself part of the frozen
contract path (`python -m rs.verify --request ... --output ...` is).
"""
import json
import sys
import uuid
from pathlib import Path

from rs import acquire, stac, verify
from rs.contracts import digest

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "rs" / "configs" / "aoi_dadia.json"
# Not named "data"/"cache"/"runtime": those are gitignored repo-wide and this
# cache of AOI-windowed source rasters is committed for offline reproducibility.
DATA_ROOT = ROOT / "rs" / "sources"


def _scene_descriptor(config, scene_id, datetime_range):
    item = stac.get_item(config["stac_collection"], scene_id, config["stac_bbox_hint"], datetime_range)
    bbox = config["stac_bbox_hint"]
    local_paths = acquire.fetch_scene_bands(item, bbox, DATA_ROOT, config["plot_id"], scene_id)
    return acquire.build_scene_descriptor(item, local_paths)


def build_scenario(config, name):
    scenario = config["scenarios"][name]
    plot_id = config["plot_id"]
    geometry = config["geometry"]
    plot_geometry_hash = digest(geometry)

    before = _scene_descriptor(config, scenario["before_scene_id"], scenario["before_datetime_range"])
    after = _scene_descriptor(config, scenario["after_scene_id"], scenario["after_datetime_range"])

    forest_mask_path = DATA_ROOT / plot_id / "forest_mask_source.tif"
    if not forest_mask_path.exists():
        acquire.fetch_forest_mask_source(config["stac_bbox_hint"], DATA_ROOT, plot_id)

    request_path = ROOT / "rs" / "configs" / f"request_{name}.json"
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

    output_dir = ROOT / "rs" / "bundles" / name
    evidence = verify.run(request_path, output_dir)
    print(f"[{name}] outcome={evidence['outcome']} bundle={output_dir}")
    return evidence


def main(argv=None):
    argv = argv or sys.argv[1:]
    which = argv[0] if argv else "all"
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    names = list(config["scenarios"]) if which == "all" else [which]
    for name in names:
        build_scenario(config, name)


if __name__ == "__main__":
    main()
