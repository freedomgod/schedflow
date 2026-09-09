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
from datetime import UTC, datetime

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
            sa.Column("next_run_utc", sa.String(64), nullable=True),
            sa.Index("ix_jobs_next_run_utc", "next_run_utc"),
        )
        self.logs = sa.Table(
            "job_logs",
            self._metadata,
            sa.Column("log_id", sa.String(76), primary_key=True),
            sa.Column("job_id", sa.String(191), nullable=False),
            sa.Column("log_json", sa.Text, nullable=False),
        )

    @staticmethod
    def _next_run_utc(job: Job) -> str | None:
        if job.next_run_time is None:
            return None
        return job.next_run_time.astimezone(UTC).isoformat()

    def _ensure(self) -> None:
        inspector = sa.inspect(self._engine)
        if "jobs" not in set(inspector.get_table_names()):
            self._metadata.create_all(self._engine, checkfirst=True)
            return
        columns = {
            column["name"] for column in inspector.get_columns("jobs")
        }
        if "next_run_utc" not in columns:
            with self._engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "ALTER TABLE jobs ADD COLUMN next_run_utc VARCHAR(64)"
                    )
                )
        index_names = {
            index["name"] for index in inspector.get_indexes("jobs")
        }
        if "ix_jobs_next_run_utc" not in index_names:
            with self._engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "CREATE INDEX ix_jobs_next_run_utc "
                        "ON jobs (next_run_utc)"
                    )
                )
        self._backfill_next_run_utc()

    def _backfill_next_run_utc(self) -> None:
        """Populate next_run_utc for rows written before the column existed."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                sa.select(self.jobs.c.id, self.jobs.c.job_json).where(
                    self.jobs.c.next_run_utc.is_(None)
                )
            ).all()
        for job_id, raw in rows:
            job = Job.from_dict(json.loads(raw))
            value = self._next_run_utc(job)
            if value is None:
                continue
            with self._engine.begin() as connection:
                connection.execute(
                    self.jobs.update()
                    .where(self.jobs.c.id == job_id)
                    .values(next_run_utc=value)
                )

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
                        next_run_utc=self._next_run_utc(job),
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
                .values(
                    job_json=json.dumps(job.to_dict(), ensure_ascii=False),
                    next_run_utc=self._next_run_utc(job),
                )
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

    def get(self, job_id: str) -> Job | None:
        self._ensure()
        with self._engine.connect() as connection:
            raw = connection.execute(
                sa.select(self.jobs.c.job_json).where(self.jobs.c.id == job_id)
            ).scalar_one_or_none()
        return Job.from_dict(json.loads(raw)) if raw is not None else None

    def get_due(self, now: datetime) -> list[Job]:
        self._ensure()
        now_utc = now.astimezone(UTC).isoformat()
        with self._engine.connect() as connection:
            raw_rows = connection.execute(
                sa.select(self.jobs.c.job_json)
                .where(
                    self.jobs.c.next_run_utc.is_not(None),
                    self.jobs.c.next_run_utc <= now_utc,
                )
                .order_by(self.jobs.c.next_run_utc)
            ).scalars().all()
        return [Job.from_dict(json.loads(raw)) for raw in raw_rows]

    def get_all(self) -> list[Job]:
        jobs = self._load_all()
        scheduled = sorted(
            (job for job in jobs if job.next_run_time is not None),
            key=lambda job: job.next_run_time,
        )
        paused = [job for job in jobs if job.next_run_time is None]
        return scheduled + paused

    def get_next_run_time(self) -> datetime | None:
        self._ensure()
        with self._engine.connect() as connection:
            raw = connection.execute(
                sa.select(self.jobs.c.next_run_utc)
                .where(self.jobs.c.next_run_utc.is_not(None))
                .order_by(self.jobs.c.next_run_utc)
                .limit(1)
            ).scalar_one_or_none()
        return datetime.fromisoformat(raw) if raw is not None else None

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

    def get_log(self, job_id: str, log_id: str) -> ExecutionLog | None:
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
