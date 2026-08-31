"""Small background runner for persistent S1 parser/finalize work."""

from __future__ import annotations

import threading
import time

from document_parser.server.s1_services import S1Pipeline


class S1WorkerRunner:
    def __init__(self, pipeline: S1Pipeline, *, idle_seconds: float = 0.25) -> None:
        if idle_seconds <= 0:
            raise ValueError("idle_seconds must be positive")
        self.pipeline = pipeline
        self.idle_seconds = idle_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self.pipeline.recover_finalization_runs()
        self._thread = threading.Thread(target=self._run, name="server-s1-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            worked = False
            try:
                worked = self.pipeline.process_next_fragment() or worked
                worked = self.pipeline.process_next_finalization() or worked
            except Exception:
                # Persistent rows remain authoritative. A later loop/restart
                # retries recoverable work without killing the HTTP process.
                worked = False
            if not worked:
                self._stop.wait(self.idle_seconds)
