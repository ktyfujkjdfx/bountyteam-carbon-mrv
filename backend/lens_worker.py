"""python -m backend.lens_worker -- the durable Carbon Lens worker.

Separate from `python -m backend.worker` on purpose: the P0 worker is the single runtime
chain sender and serializes nonces under its own lease, and the Lens worker touches no
chain at all. Running one must never block the other.
"""
import argparse
import logging
import signal
import threading

from .app.config import load_settings
from .app.context import create_context
from .app.v2.service import create_lens_context
from .app.v2.worker import LensWorker


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    worker = LensWorker(create_lens_context(create_context(load_settings())))
    if args.once:
        return 0 if worker.tick() else 3
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    worker.run_forever(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
