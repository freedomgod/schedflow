"""JobStore interface and in-memory implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schedflow.core.job import Job
    from schedflow.core.log import ExecutionLog


class JobConflictError(Exception):
    """Raised when adding a job whose id already exists."""


class JobNotFoundError(Exception):
    """Raised when a job id cannot be found."""


class JobStore(ABC):
    """Persistence interface for jobs and execution logs.

    Implementations must be safe to call from the scheduler loop thread and
    from API request threads.
    """

    @abstractmethod
    def add(self, job: Job) -> None: ...

    @abstractmethod
    def update(self, job: Job) -> None: ...

    @abstractmethod
    def remove(self, job_id: str) -> None: ...

    @abstractmethod
    def get(self, job_id: str) -> Job | None: ...

    @abstractmethod
    def get_due(self, now: datetime) -> list[Job]: ...

    @abstractmethod
    def get_all(self) -> list[Job]: ...

    @abstractmethod
    def get_next_run_time(self) -> datetime | None: ...

    @abstractmethod
    def add_log(self, job_id: str, log: ExecutionLog) -> None: ...

    @abstractmethod
    def get_logs(self, job_id: str) -> list[ExecutionLog]: ...

    @abstractmethod
    def get_log(self, job_id: str, log_id: str) -> ExecutionLog | None: ...

    @abstractmethod
    def close(self) -> None: ...


class MemoryJobStore(JobStore):
    """In-memory job store (volatile)."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._logs: dict[str, list[ExecutionLog]] = {}

    def add(self, job: Job) -> None:
        if job.job_id in self._jobs:
            raise JobConflictError(job.job_id)
        self._jobs[job.job_id] = job

    def update(self, job: Job) -> None:
        if job.job_id not in self._jobs:
            raise JobNotFoundError(job.job_id)
        self._jobs[job.job_id] = job

    def remove(self, job_id: str) -> None:
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id)
        del self._jobs[job_id]

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def get_due(self, now: datetime) -> list[Job]:
        due = [
            job
            for job in self._jobs.values()
            if job.next_run_time is not None and job.next_run_time <= now
        ]
        return sorted(due, key=lambda job: job.next_run_time)

    def get_all(self) -> list[Job]:
        scheduled = sorted(
            (job for job in self._jobs.values() if job.next_run_time is not None),
            key=lambda job: job.next_run_time,
        )
        paused = [job for job in self._jobs.values() if job.next_run_time is None]
        return scheduled + paused

    def get_next_run_time(self) -> datetime | None:
        candidates = [
            job.next_run_time
            for job in self._jobs.values()
            if job.next_run_time is not None
        ]
        return min(candidates) if candidates else None

    def add_log(self, job_id: str, log: ExecutionLog) -> None:
        self._logs.setdefault(job_id, []).append(log)

    def get_logs(self, job_id: str) -> list[ExecutionLog]:
        return list(self._logs.get(job_id, []))

    def get_log(self, job_id: str, log_id: str) -> ExecutionLog | None:
        for log in self.get_logs(job_id):
            if log.log_id == log_id:
                return log
        return None

    def close(self) -> None:
        self._jobs.clear()
        self._logs.clear()
