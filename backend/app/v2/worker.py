"""The Lens worker: durable, restartable, and single-flight per deployment.

It takes its own lease so that it can run beside the P0 worker without either of them
waiting on the other. A job interrupted by a restart goes back to QUEUED, because the
state that matters is in the database and a half-finished run has left nothing behind but
content-addressed bytes that the next run will simply write again.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid

from ..context import audit
from .service import LensContext, run_analysis

log = logging.getLogger("backend.lens.worker")
LEASE = "lens"


class LensWorker:
    def __init__(self, lens: LensContext, worker_id: str | None = None):
        self.lens = lens
        self.worker_id = worker_id or f"lens-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._recovered = False

    def acquire_lease(self) -> bool:
        now = time.time()
        limit = self.lens.app.settings.worker_lease_seconds
        with self.lens.app.db.transaction() as conn:
            row = conn.execute("SELECT worker_id, heartbeat_at FROM worker_leases WHERE lease=?",
                               (LEASE,)).fetchone()
            if row and row["worker_id"] != self.worker_id and now - row["heartbeat_at"] < limit:
                return False
            conn.execute("INSERT INTO worker_leases VALUES (?,?,?) ON CONFLICT(lease) DO UPDATE "
                         "SET worker_id=excluded.worker_id, heartbeat_at=excluded.heartbeat_at",
                         (LEASE, self.worker_id, now))
        return True

    def recover(self) -> None:
        count = self.lens.store.requeue_interrupted()
        if count:
            with self.lens.app.db.transaction() as conn:
                audit(conn, "LENS_JOBS_REQUEUED_AFTER_RESTART", None, count=count)
        self._recovered = True

    def tick(self) -> bool:
        """One full pass. False means another worker holds the lease."""
        if not self.acquire_lease():
            return False
        if not self._recovered:
            self.recover()
        for analysis_id in self.lens.store.pending():
            try:
                run_analysis(self.lens, analysis_id)
            except Exception:  # the loop outlives one bad job; the state is in the DB
                log.exception("lens job crashed outside its own error handling")
        return True

    def run_forever(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("lens worker tick failed")
            stop.wait(self.lens.app.settings.worker_poll_seconds)


def start_worker_thread(lens: LensContext) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()
    worker = LensWorker(lens)
    thread = threading.Thread(target=worker.run_forever, args=(stop,), name="lens-worker",
                              daemon=True)
    thread.start()
    return thread, stop
