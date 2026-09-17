"""python -m backend.serve -- run /api/v1 on loopback (optionally with the embedded worker)."""
import argparse
import logging

import uvicorn

from .app.config import load_settings
from .app.context import create_context
from .app.main import create_app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default loopback)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-worker", action="store_true",
                        help="Do not start the embedded worker; run `python -m backend.worker` separately")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = create_app(ctx=create_context(load_settings()), embedded_worker=not args.no_worker)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
