"""Register an approved demo plot (idempotent; refuses to silently change a geometry version).

  python -m backend.tools.seed                                   # fixtures/plot.json
  python -m backend.tools.seed --plot path/to/plot.json          # {plot_id, name, geometry, geometry_hash, area_ha, dataset_kind}
  python -m backend.tools.seed --rs-request rs/configs/request_fire.json [--name NAME] [--area-ha HA]

With --rs-request the plot id, approved geometry, its JCS SHA-256 hash and dataset kind come
from the RS request; area_ha defaults to the WGS84 geodesic area of that geometry.
"""
import argparse
import json
import sys

from pyproj import Geod
from shapely.geometry import shape

from ..app.config import REPO_ROOT, load_settings
from ..app.context import create_context
from ..app.contracts import read_json
from ..app.evidence import EvidenceRejected
from ..app.ingest import register_plot


def geodesic_area_ha(geometry: dict) -> float:
    area_m2, _ = Geod(ellps="WGS84").geometry_area_perimeter(shape(geometry))
    return round(abs(area_m2) / 10_000, 6)


def plot_from_rs_request(request: dict, name: str | None = None, area_ha: float | None = None) -> dict:
    return {"plot_id": request["plot_id"], "name": name or request["plot_id"], "geometry": request["geometry"],
            "geometry_hash": request["plot_geometry_hash"],
            "area_ha": area_ha if area_ha is not None else geodesic_area_ha(request["geometry"]),
            "dataset_kind": request["dataset_kind"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--plot", default=str(REPO_ROOT / "fixtures" / "plot.json"))
    source.add_argument("--rs-request", help="rs-request.schema.json file whose approved geometry defines the plot")
    parser.add_argument("--name", help="Display name (with --rs-request)")
    parser.add_argument("--area-ha", type=float, help="Registered area in ha (with --rs-request)")
    args = parser.parse_args(argv)
    ctx = create_context(load_settings())
    plot = (plot_from_rs_request(read_json(args.rs_request), args.name, args.area_ha) if args.rs_request
            else read_json(args.plot))
    try:
        inserted = register_plot(ctx, plot)
    except EvidenceRejected as exc:
        print(json.dumps({"ok": False, "error": exc.message}), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "plot_id": plot["plot_id"], "inserted": inserted,
                      "geometry_hash": plot["geometry_hash"], "area_ha": plot["area_ha"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
