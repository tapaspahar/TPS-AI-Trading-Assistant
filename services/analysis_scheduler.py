"""Shared bounded background scheduler for live TPS analysis jobs."""
from __future__ import annotations

from queue import Queue
from threading import Lock, Thread
from time import monotonic
from zlib import crc32


class AnalysisScheduler:
    """Prevent duplicate work and cap simultaneous broker/CPU-heavy jobs."""

    _queue = Queue()
    _lock = Lock()
    _active = set()
    _metrics = {}
    _workers_started = False

    @classmethod
    def _ensure_workers(cls):
        with cls._lock:
            if cls._workers_started:
                return
            cls._workers_started = True
            for index in range(3):
                Thread(target=cls._worker_loop, name=f"tps-analysis-{index + 1}", daemon=True).start()

    @classmethod
    def _worker_loop(cls):
        while True:
            key, function = cls._queue.get()
            started = monotonic()
            try:
                function()
            finally:
                elapsed = monotonic() - started
                with cls._lock:
                    cls._active.discard(key)
                    metric = cls._metrics.setdefault(key, {"runs": 0, "skipped": 0, "last_seconds": 0.0})
                    metric["runs"] += 1
                    metric["last_seconds"] = round(elapsed, 3)
                cls._queue.task_done()

    @classmethod
    def submit_unique(cls, key, function):
        cls._ensure_workers()
        key = str(key)
        with cls._lock:
            if key in cls._active:
                metric = cls._metrics.setdefault(key, {"runs": 0, "skipped": 0, "last_seconds": 0.0})
                metric["skipped"] += 1
                return False
            cls._active.add(key)

        cls._queue.put((key, function))
        return True

    @staticmethod
    def stagger_ms(name, spread_ms=8_000):
        """Stable startup offset so page timers do not all fire together."""
        return 500 + crc32(str(name).encode("utf-8")) % max(1, int(spread_ms))

    @classmethod
    def metrics(cls):
        with cls._lock:
            return {key: dict(value, active=key in cls._active) for key, value in cls._metrics.items()}
