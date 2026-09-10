"""Bounded priority dispatch queue between the scheduler loop and executors."""

from __future__ import annotations

import heapq
import itertools
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schedflow.core.job import Job
    from schedflow.core.run import RunRequest


class DispatchQueue:
    """Thread-safe bounded queue ordered by ``(priority, enqueue_seq)``."""

    def __init__(self, capacity: int = 10_000) -> None:
        self._capacity = max(1, int(capacity))
        self._heap: list[tuple] = []
        self._queued: dict[str, object] = {}
        self._cancelled: set[str] = set()
        self._cond = threading.Condition()
        self._counter = itertools.count()

    def put(
        self,
        job: Job,
        run_time: datetime,
        request: RunRequest | None = None,
    ) -> bool:
        with self._cond:
            if job.job_id in self._queued or len(self._queued) >= self._capacity:
                return False
            entry = (
                int(job.priority),
                next(self._counter),
                job.job_id,
                run_time,
                job,
                request,
            )
            heapq.heappush(self._heap, entry)
            self._queued[job.job_id] = entry
            self._cond.notify()
            return True

    def get(
        self, timeout: float | None = None
    ) -> tuple[Job, datetime, RunRequest | None] | None:
        with self._cond:
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                while self._heap:
                    _, _, job_id, run_time, job, request = heapq.heappop(
                        self._heap
                    )
                    if job_id in self._cancelled:
                        self._queued.pop(job_id, None)
                        self._cancelled.discard(job_id)
                        continue
                    self._queued.pop(job_id, None)
                    return job, run_time, request
                if deadline is None:
                    self._cond.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)

    def cancel(self, job_id: str) -> bool:
        with self._cond:
            if job_id not in self._queued:
                return False
            self._cancelled.add(job_id)
            self._cond.notify()
            return True

    def has(self, job_id: str) -> bool:
        with self._cond:
            return job_id in self._queued

    def size(self) -> int:
        with self._cond:
            return len(self._queued)

    def wakeup(self) -> None:
        with self._cond:
            self._cond.notify_all()
