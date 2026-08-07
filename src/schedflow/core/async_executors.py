"""Async-flavored executors (feature parity with the legacy stack).

The core Scheduler is thread-based. These executors keep the legacy plugin
names and constructor schemas available by running the synchronous
``job.run()`` on their respective async infrastructure: a dedicated asyncio
event loop, gevent greenlets, a tornado-style thread pool, or the twisted
reactor thread pool.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor
from typing import TYPE_CHECKING

from schedflow.core.executor import Executor

if TYPE_CHECKING:
    from datetime import datetime

    from schedflow.core.job import Job


class AsyncIOExecutor(Executor):
    """Runs jobs on a dedicated asyncio event loop in a background thread."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self, scheduler) -> None:
        super().start(scheduler)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            name="schedflow-asyncio",
            daemon=True,
        )
        self._thread.start()

    def shutdown(self, *, wait: bool = True) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None and wait:
                self._thread.join(timeout=5)
        self._loop = None
        self._thread = None

    def submit(self, job: Job, run_time: datetime) -> None:
        async def _run():
            return job.run()

        future = asyncio.run_coroutine_threadsafe(_run(), self._loop)
        future.add_done_callback(
            lambda completed: self._handle(job, run_time, completed)
        )

    def _handle(self, job: Job, run_time: datetime, future) -> None:
        try:
            log = future.result()
        except Exception as exc:  # noqa: BLE001
            self._scheduler._on_job_finished(job, run_time, None, error=exc)
        else:
            self._scheduler._on_job_finished(job, run_time, log)


class GeventExecutor(Executor):
    """Runs jobs as gevent greenlets on a dedicated hub thread (requires gevent).

    The core scheduler loop is a plain ``threading`` thread, so greenlets
    spawned from it never run unless a hub is actively executing. This
    executor therefore runs its own hub on a background thread and schedules
    each job on that hub's loop.
    """

    def __init__(self) -> None:
        self._hub = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stop = threading.Event()

    def start(self, scheduler) -> None:
        super().start(scheduler)
        self._thread = threading.Thread(
            target=self._run_hub,
            name="schedflow-gevent",
            daemon=True,
        )
        self._thread.start()

    def _run_hub(self) -> None:
        from gevent import get_hub, sleep

        self._hub = get_hub()
        self._ready.set()
        # The hub greenlet becomes current only when this thread's root
        # greenlet yields to it. Keep yielding so the hub stays alive and
        # processes the greenlets scheduled by ``submit``.
        while not self._stop.is_set():
            sleep(0.5)

    def shutdown(self, *, wait: bool = True) -> None:
        self._stop.set()
        if self._thread is not None and wait:
            self._thread.join(timeout=5)
        self._hub = None
        self._thread = None

    def submit(self, job: Job, run_time: datetime) -> None:
        from gevent import Greenlet

        if self._hub is None:
            self._ready.wait(timeout=5)
        def _run() -> None:
            try:
                log = job.run()
            except Exception as exc:  # noqa: BLE001
                self._scheduler._on_job_finished(job, run_time, None, error=exc)
            else:
                self._scheduler._on_job_finished(job, run_time, log)

        greenlet = Greenlet(_run)
        greenlet.parent = self._hub
        self._hub.loop.run_callback(greenlet.start)


class TornadoExecutor(Executor):
    """Runs jobs in a thread pool (tornado's default executor semantics)."""

    def __init__(self, max_workers: int = 10) -> None:
        self._pool = _ThreadPoolExecutor(max_workers=max(1, int(max_workers)))

    def submit(self, job: Job, run_time: datetime) -> None:
        future = self._pool.submit(job.run)
        future.add_done_callback(
            lambda completed: self._handle(job, run_time, completed)
        )

    def _handle(self, job: Job, run_time: datetime, future) -> None:
        try:
            log = future.result()
        except Exception as exc:  # noqa: BLE001
            self._scheduler._on_job_finished(job, run_time, None, error=exc)
        else:
            self._scheduler._on_job_finished(job, run_time, log)

    def shutdown(self, *, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)


class TwistedExecutor(Executor):
    """Runs jobs in the twisted reactor's thread pool (requires twisted)."""

    def __init__(self) -> None:
        self._reactor = None

    def start(self, scheduler) -> None:
        super().start(scheduler)
        from twisted.internet import reactor

        self._reactor = reactor

    def submit(self, job: Job, run_time: datetime) -> None:
        def _run() -> None:
            try:
                log = job.run()
            except Exception as exc:  # noqa: BLE001
                self._scheduler._on_job_finished(job, run_time, None, error=exc)
            else:
                self._scheduler._on_job_finished(job, run_time, log)

        self._reactor.callInThread(_run)
