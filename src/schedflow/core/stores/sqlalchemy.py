"""SQLAlchemy job store.

Jobs and execution logs are stored as JSON text (``Job.to_dict()`` /
``ExecutionLog.to_dict()``). References inside workflows are stored
verbatim and are never resolved during load, so jobs whose target module
is not importable in the current process are preserved instead of being
dropped.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Optional

from schedflow.core.job import Job
from schedflow.core.jobstore import (
    JobConflictError,
    JobNotFoundError,
    JobStore,
)
from schedflow.core.log import ExecutionLog

try:
    import sqlalchemy as sa
    from sqlalchemy.exc import IntegrityError, OperationalError
except ImportError:  # pragma: no cover - optional dependency
    # The dependency is checked at instantiation time so importing the package
    # works without optional extras installed.
    sa = None  # type: ignore[assignment]
    IntegrityError = None  # type: ignore[assignment,misc]
    OperationalError = None  # type: ignore[assignment,misc]


_LOCKED_MARKERS = (
    "database is locked",
    "database table is locked",
    "locking protocol",
    "is busy",
)


class SQLAlchemyJobStore(JobStore):
    """JobStore backed by any SQLAlchemy-supported database."""

    def __init__(self, url: str = "sqlite:///:memory:", *, engine=None) -> None:
        if sa is None:  # pragma: no cover
            raise ImportError(
                "SQLAlchemyJobStore requires the 'sqlalchemy' package. "
                "Install it with: pip install schedflow[sqlalchemy]"
            )
        self._engine = engine or sa.create_engine(url)
        self._metadata = sa.MetaData()
        self.jobs = sa.Table(
            "jobs",
            self._metadata,
            sa.Column("id", sa.String(191), primary_key=True),
            sa.Column("job_json", sa.Text, nullable=False),
        )
        self.logs = sa.Table(
            "job_logs",
            self._metadata,
            sa.Column("log_id", sa.String(76), primary_key=True),
            sa.Column("job_id", sa.String(191), nullable=False),
            sa.Column("log_json", sa.Text, nullable=False),
        )

    def _ensure(self) -> None:
        self._metadata.create_all(self._engine, checkfirst=True)

    def _with_write_retry(self, fn, *args):
        """Retry short-lived SQLite lock contention on write operations.

        The scheduler loop must not lose an ``update(job)`` (which advances
        next_run_time) to a transient ``database is locked`` error, otherwise
        the job stays due and executes back-to-back. When the lock persists
        past the retries the original exception propagates, and the scheduler
        simply retries the whole due-processing step on its next loop.
        """
        last_error = None
        for attempt in range(4):
            try:
                return fn(*args)
            except OperationalError as exc:
                message = str(exc).lower()
                if not any(marker in message for marker in _LOCKED_MARKERS):
                    raise
                last_error = exc
                time.sleep(0.05 * (2**attempt))
        raise last_error

    def add(self, job: Job) -> None:
        self._ensure()
        self._with_write_retry(self._add_once, job)

    def _add_once(self, job: Job) -> None:
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    self.jobs.insert().values(
                        id=job.job_id,
                        job_json=json.dumps(job.to_dict(), ensure_ascii=False),
                    )
                )
        except IntegrityError:
            raise JobConflictError(job.job_id)

    def update(self, job: Job) -> None:
        self._ensure()
        self._with_write_retry(self._update_once, job)

    def _update_once(self, job: Job) -> None:
        with self._engine.begin() as connection:
            result = connection.execute(
                self.jobs.update()
                .where(self.jobs.c.id == job.job_id)
                .values(job_json=json.dumps(job.to_dict(), ensure_ascii=False))
            )
            if result.rowcount == 0:
                raise JobNotFoundError(job.job_id)

    def remove(self, job_id: str) -> None:
        self._ensure()
        self._with_write_retry(self._remove_once, job_id)

    def _remove_once(self, job_id: str) -> None:
        with self._engine.begin() as connection:
            result = connection.execute(
                self.jobs.delete().where(self.jobs.c.id == job_id)
            )
            if result.rowcount == 0:
                raise JobNotFoundError(job_id)

    def get(self, job_id: str) -> Optional[Job]:
        self._ensure()
        with self._engine.connect() as connection:
            raw = connection.execute(
                sa.select(self.jobs.c.job_json).where(self.jobs.c.id == job_id)
            ).scalar_one_or_none()
        return Job.from_dict(json.loads(raw)) if raw is not None else None

    def get_due(self, now: datetime) -> list[Job]:
        jobs = self._load_all()
        return sorted(
            (
                job
                for job in jobs
                if job.next_run_time is not None and job.next_run_time <= now
            ),
            key=lambda job: job.next_run_time,
        )

    def get_all(self) -> list[Job]:
        jobs = self._load_all()
        scheduled = sorted(
            (job for job in jobs if job.next_run_time is not None),
            key=lambda job: job.next_run_time,
        )
        paused = [job for job in jobs if job.next_run_time is None]
        return scheduled + paused

    def get_next_run_time(self) -> Optional[datetime]:
        candidates = [
            job.next_run_time
            for job in self._load_all()
            if job.next_run_time is not None
        ]
        return min(candidates) if candidates else None

    def add_log(self, job_id: str, log: ExecutionLog) -> None:
        self._ensure()
        self._with_write_retry(self._add_log_once, job_id, log)

    def _add_log_once(self, job_id: str, log: ExecutionLog) -> None:
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    self.logs.insert().values(
                        log_id=log.log_id,
                        job_id=job_id,
                        log_json=json.dumps(log.to_dict(), ensure_ascii=False),
                    )
                )
        except IntegrityError:
            raise JobConflictError(log.log_id)

    def get_logs(self, job_id: str) -> list[ExecutionLog]:
        self._ensure()
        with self._engine.connect() as connection:
            raw_rows = connection.execute(
                sa.select(self.logs.c.log_json)
                .where(self.logs.c.job_id == job_id)
                .order_by(self.logs.c.log_id)
            ).scalars().all()
        return [ExecutionLog.from_dict(json.loads(raw)) for raw in raw_rows]

    def get_log(self, job_id: str, log_id: str) -> Optional[ExecutionLog]:
        for log in self.get_logs(job_id):
            if log.log_id == log_id:
                return log
        return None

    def close(self) -> None:
        self._engine.dispose()

    def _load_all(self) -> list[Job]:
        self._ensure()
        with self._engine.connect() as connection:
            raw_rows = connection.execute(
                sa.select(self.jobs.c.job_json)
            ).scalars().all()
        return [Job.from_dict(json.loads(raw)) for raw in raw_rows]
