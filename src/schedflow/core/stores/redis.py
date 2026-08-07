"""Redis job store (JSON values, no pickle)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from schedflow.core.job import Job
from schedflow.core.jobstore import (
    JobConflictError,
    JobNotFoundError,
    JobStore,
)
from schedflow.core.log import ExecutionLog

try:
    from redis import Redis
except ImportError as exc:  # pragma: no cover
    raise ImportError("RedisJobStore requires redis installed") from exc


class RedisJobStore(JobStore):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        *,
        prefix: str = "schedflow",
    ) -> None:
        self._redis = Redis(
            host=host,
            port=int(port),
            db=int(db),
            socket_connect_timeout=5,
        )
        self._jobs_key = f"{prefix}:jobs"
        self._run_times_key = f"{prefix}:run_times"
        self._logs_key = f"{prefix}:logs"

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

    def get(self, job_id: str) -> Optional[Job]:
        raw = self._redis.hget(self._jobs_key, job_id)
        return Job.from_dict(json.loads(raw)) if raw else None

    def get_due(self, now: datetime) -> list[Job]:
        job_ids = self._redis.zrangebyscore(
            self._run_times_key, 0, now.timestamp()
        )
        return [job for job in (self.get(job_id) for job_id in job_ids) if job]

    def get_all(self) -> list[Job]:
        raw = self._redis.hgetall(self._jobs_key)
        jobs = [Job.from_dict(json.loads(value)) for value in raw.values()]
        scheduled = sorted(
            (job for job in jobs if job.next_run_time is not None),
            key=lambda job: job.next_run_time,
        )
        paused = [job for job in jobs if job.next_run_time is None]
        return scheduled + paused

    def get_next_run_time(self) -> Optional[datetime]:
        items = self._redis.zrange(
            self._run_times_key, 0, 0, withscores=True
        )
        if not items:
            return None
        return datetime.fromtimestamp(items[0][1], tz=timezone.utc)

    def add_log(self, job_id: str, log: ExecutionLog) -> None:
        self._redis.rpush(
            f"{self._logs_key}:{job_id}",
            json.dumps(log.to_dict(), ensure_ascii=False),
        )

    def get_logs(self, job_id: str) -> list[ExecutionLog]:
        raw_rows = self._redis.lrange(f"{self._logs_key}:{job_id}", 0, -1)
        return [ExecutionLog.from_dict(json.loads(raw)) for raw in raw_rows]

    def get_log(self, job_id: str, log_id: str) -> Optional[ExecutionLog]:
        for log in self.get_logs(job_id):
            if log.log_id == log_id:
                return log
        return None

    def close(self) -> None:
        self._redis.close()
