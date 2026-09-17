"""python -m backend.tools.seed [--plot fixtures/plot.json] -- register the approved demo plot (idempotent)."""
import argparse
import json
import sys

from ..app.config import REPO_ROOT, load_settings
from ..app.context import create_context
from ..app.contracts import read_json
from ..app.evidence import EvidenceRejected
from ..app.ingest import register_plot


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plot", default=str(REPO_ROOT / "fixtures" / "plot.json"))
    args = parser.parse_args(argv)
    ctx = create_context(load_settings())
    plot = read_json(args.plot)
    try:
        inserted = register_plot(ctx, plot)
    except EvidenceRejected as exc:
        print(json.dumps({"ok": False, "error": exc.message}), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "plot_id": plot["plot_id"], "inserted": inserted,
                      "geometry_hash": plot["geometry_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
