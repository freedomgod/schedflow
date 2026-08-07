"""Executor interface with thread, process and debug implementations."""

from __future__ import annotations

import concurrent.futures
import multiprocessing
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from schedflow.core.log import ExecutionLog
from schedflow.core.process_worker import run_job_in_process

if TYPE_CHECKING:
    from schedflow.core.job import Job


class Executor(ABC):
    """Executes a job for a single scheduled run time."""

    def start(self, scheduler) -> None:
        self._scheduler = scheduler

    def shutdown(self, *, wait: bool = True) -> None:
        pass

    @abstractmethod
    def submit(self, job: "Job", run_time: datetime) -> None: ...


class DebugExecutor(Executor):
    """Runs jobs synchronously in the calling thread (for tests/development)."""

    def submit(self, job: "Job", run_time: datetime) -> None:
        try:
            log = job.run()
        except Exception as exc:  # noqa: BLE001
            self._scheduler._on_job_finished(job, run_time, None, error=exc)
        else:
            self._scheduler._on_job_finished(job, run_time, log)


class ThreadPoolExecutor(Executor):
    """Runs jobs in a thread pool."""

    def __init__(self, max_workers: int = 10) -> None:
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, int(max_workers))
        )

    def submit(self, job: "Job", run_time: datetime) -> None:
        future = self._pool.submit(job.run)
        future.add_done_callback(
            lambda completed: self._handle(job, run_time, completed)
        )

    def _handle(self, job, run_time, future) -> None:
        try:
            log = future.result()
        except Exception as exc:  # noqa: BLE001
            self._scheduler._on_job_finished(job, run_time, None, error=exc)
        else:
            self._scheduler._on_job_finished(job, run_time, log)

    def shutdown(self, *, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)


class ProcessPoolExecutor(Executor):
    """Runs jobs in a process pool using a JSON worker protocol.

    Only the serialized job (``Job.to_dict()``) crosses the process boundary,
    so this works on Windows (spawn) as long as workflow references are
    importable from a fresh interpreter.
    """

    def __init__(self, max_workers: int = 10) -> None:
        context = multiprocessing.get_context("spawn")
        self._pool = concurrent.futures.ProcessPoolExecutor(
            max_workers=max(1, int(max_workers)),
            mp_context=context,
        )

    def submit(self, job: "Job", run_time: datetime) -> None:
        project_root = (
            str(job.workflow.project_root)
            if job.workflow.project_root is not None
            else None
        )
        future = self._pool.submit(
            run_job_in_process,
            job.to_dict(),
            run_time.isoformat(),
            project_root,
        )
        future.add_done_callback(
            lambda completed: self._handle(job, run_time, completed)
        )

    def _handle(self, job, run_time, future) -> None:
        try:
            data = future.result()
        except Exception as exc:  # noqa: BLE001
            self._scheduler._on_job_finished(job, run_time, None, error=exc)
        else:
            log = ExecutionLog.from_dict(data)
            self._scheduler._on_job_finished(job, run_time, log)

    def shutdown(self, *, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)
