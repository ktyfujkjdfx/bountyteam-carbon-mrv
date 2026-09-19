"""python -m backend.serve -- run /api/v1 and /api/v2 on loopback (optionally with workers).

The two contracts are composed here and nowhere else: `create_app` still builds exactly the
frozen v1 application, `create_lens_app` builds the Carbon Lens application, and the
composition routes /api/v2 to the second one. Neither application imports the other.
"""
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
                        help="Do not start the embedded workers; run `python -m backend.worker` "
                             "and `python -m backend.lens_worker` separately")
    parser.add_argument("--no-lens", action="store_true",
                        help="Serve only the frozen /api/v1 contract")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    settings = load_settings()
    ctx = create_context(settings)
    app = create_app(ctx=ctx, embedded_worker=not args.no_worker)

    lens_stop = lens_thread = None
    if settings.lens_enabled and not args.no_lens:
        from .app.v2.adapters import EnginesUnavailable
        from .app.v2.api import compose, create_lens_app
        from .app.v2.service import create_lens_context
        from .app.v2.worker import start_worker_thread

        from .app.v2.auth import seed_demo_users

        if settings.lens_demo_accounts:
            seed_demo_users(ctx, {username: (role, password)
                                  for username, role, password in settings.lens_demo_accounts})
        try:
            lens = create_lens_context(ctx)
        except EnginesUnavailable as exc:
            # Fail closed. The alternative is a deployment that looks complete and
            # answers with numbers nobody measured, which is worse than being down.
            if settings.lens_require_real:
                logging.getLogger("backend.serve").error(
                    "refusing to start: %s (BACKEND_LENS_REQUIRE_REAL is set)", exc)
                return 2
            logging.getLogger("backend.serve").warning(
                "Carbon Lens disabled: %s. /api/v1 continues to serve; /api/v2 is not "
                "mounted and no stub answers in its place.", exc)
            lens = None
        if lens is not None:
            app = compose(app, create_lens_app(lens))
            if not args.no_worker:
                lens_thread, lens_stop = start_worker_thread(lens)

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        if lens_stop is not None:
            lens_stop.set()
            lens_thread.join(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
