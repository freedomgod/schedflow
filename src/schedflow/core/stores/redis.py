"""Redis job store (JSON values, no pickle)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from schedflow.core.job import Job
from schedflow.core.jobstore import (
    JobConflictError,
    JobNotFoundError,
    JobStore,
)
from schedflow.core.log import ExecutionLog
from schedflow.core.snapshot import RunSnapshot

try:
    from redis import Redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
except ImportError:  # pragma: no cover - optional dependency
    # The dependency is checked at instantiation time so importing the package
    # works without optional extras installed.
    Redis = None  # type: ignore[assignment,misc]
    NoBackoff = None  # type: ignore[assignment,misc]
    Retry = None  # type: ignore[assignment,misc]


class RedisJobStore(JobStore):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        *,
        username: str | None = None,
        password: str | None = None,
        prefix: str = "schedflow",
    ) -> None:
        if Redis is None:  # pragma: no cover
            raise ImportError(
                "RedisJobStore requires the 'redis' package. "
                "Install it with: pip install schedflow[redis]"
            )
        self._redis = Redis(
            host=host,
            port=int(port),
            db=int(db),
            # redis-py treats None as "no AUTH"; empty strings are also
            # normalised away so an untouched UI field never sends "".
            username=username or None,
            password=password or None,
            socket_connect_timeout=5,
            # redis-py's default exponential retry turns one refused
            # connection into ~15s of blocking. The jobstore is polled
            # continuously, so fail fast and let the caller decide how soon
            # to try again.
            retry=Retry(NoBackoff(), 0) if Retry is not None else None,
        )
        self._jobs_key = f"{prefix}:jobs"
        self._run_times_key = f"{prefix}:run_times"
        self._logs_key = f"{prefix}:logs"
        self._snapshots_key = f"{prefix}:snapshots"

    def add(self, job: Job) -> None:
        if self._redis.hexists(self._jobs_key, job.job_id):
            raise JobConflictError(job.job_id)
        pipeline = self._redis.pipeline()
        pipeline.hset(
            self._jobs_key,
            job.job_id,
            json.dumps(job.to_dict(), ensure_ascii=False),
        )
        if job.next_run_time is not None:
            pipeline.zadd(
                self._run_times_key,
                {job.job_id: job.next_run_time.timestamp()},
            )
        pipeline.execute()

    def update(self, job: Job) -> None:
        if not self._redis.hexists(self._jobs_key, job.job_id):
            raise JobNotFoundError(job.job_id)
        pipeline = self._redis.pipeline()
        pipeline.hset(
            self._jobs_key,
            job.job_id,
            json.dumps(job.to_dict(), ensure_ascii=False),
        )
        if job.next_run_time is not None:
            pipeline.zadd(
                self._run_times_key,
                {job.job_id: job.next_run_time.timestamp()},
            )
        else:
            pipeline.zrem(self._run_times_key, job.job_id)
        pipeline.execute()

    def remove(self, job_id: str) -> None:
        if not self._redis.hexists(self._jobs_key, job_id):
            raise JobNotFoundError(job_id)
        pipeline = self._redis.pipeline()
        pipeline.hdel(self._jobs_key, job_id)
        pipeline.zrem(self._run_times_key, job_id)
        pipeline.execute()

    def get(self, job_id: str) -> Job | None:
        raw = self._redis.hget(self._jobs_key, job_id)
        return Job.from_dict(json.loads(raw)) if raw else None

    def get_due(self, now: datetime) -> list[Job]:
        job_ids = self._redis.zrangebyscore(
            self._run_times_key, 0, now.timestamp()
        )
        jobs = (self.get(job_id) for job_id in job_ids)
        return [job for job in jobs if job is not None and job.status == "running"]

    def get_all(self) -> list[Job]:
        raw = self._redis.hgetall(self._jobs_key)
        jobs = [Job.from_dict(json.loads(value)) for value in raw.values()]
        scheduled = sorted(
            (job for job in jobs if job.next_run_time is not None),
            key=lambda job: job.next_run_time,
        )
        paused = [job for job in jobs if job.next_run_time is None]
        return scheduled + paused

    def get_next_run_time(self) -> datetime | None:
        for job_id, score in self._redis.zrange(
            self._run_times_key, 0, -1, withscores=True
        ):
            job = self.get(job_id)
            if job is not None and job.status == "running":
                return datetime.fromtimestamp(score, tz=UTC)
        return None

    def add_log(self, job_id: str, log: ExecutionLog) -> None:
        self._redis.rpush(
            f"{self._logs_key}:{job_id}",
            json.dumps(log.to_dict(), ensure_ascii=False),
        )

    def get_logs(self, job_id: str) -> list[ExecutionLog]:
        raw_rows = self._redis.lrange(f"{self._logs_key}:{job_id}", 0, -1)
        return [ExecutionLog.from_dict(json.loads(raw)) for raw in raw_rows]

    def get_log(self, job_id: str, log_id: str) -> ExecutionLog | None:
        for log in self.get_logs(job_id):
            if log.log_id == log_id:
                return log
        return None

    @staticmethod
    def _snapshot_member(job_id: str, execution_id: str) -> str:
        return f"{job_id}:{execution_id}"

    def _snapshot_order_key(self, job_id: str) -> str:
        return f"{self._snapshots_key}:order:{job_id}"

    def save_snapshot(self, job_id: str, snapshot: RunSnapshot) -> None:
        member = self._snapshot_member(job_id, snapshot.execution_id)
        pipeline = self._redis.pipeline()
        pipeline.hset(
            self._snapshots_key,
            member,
            json.dumps(snapshot.to_dict(), ensure_ascii=False),
        )
        pipeline.zadd(
            self._snapshot_order_key(job_id),
            {member: snapshot.started_at.timestamp()},
        )
        pipeline.execute()

    def get_snapshot(
        self, job_id: str, execution_id: str
    ) -> RunSnapshot | None:
        raw = self._redis.hget(
            self._snapshots_key,
            self._snapshot_member(job_id, execution_id),
        )
        return RunSnapshot.from_dict(json.loads(raw)) if raw else None

    def list_snapshots(self, job_id: str) -> list[RunSnapshot]:
        members = self._redis.zrevrange(
            self._snapshot_order_key(job_id), 0, -1
        )
        snapshots = []
        for member in members:
            raw = self._redis.hget(self._snapshots_key, member)
            if raw:
                snapshots.append(RunSnapshot.from_dict(json.loads(raw)))
        return snapshots

    def delete_snapshot(self, job_id: str, execution_id: str) -> None:
        member = self._snapshot_member(job_id, execution_id)
        pipeline = self._redis.pipeline()
        pipeline.hdel(self._snapshots_key, member)
        pipeline.zrem(self._snapshot_order_key(job_id), member)
        pipeline.execute()

    def close(self) -> None:
        self._redis.close()
