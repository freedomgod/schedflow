"""MongoDB job store (JSON documents, no pickle)."""

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

try:
    from pymongo import MongoClient
    from pymongo.errors import DuplicateKeyError
except ImportError:  # pragma: no cover - optional dependency
    # The dependency is checked at instantiation time so importing the package
    # works without optional extras installed.
    MongoClient = None  # type: ignore[assignment,misc]
    DuplicateKeyError = None  # type: ignore[assignment,misc]


class MongoDBJobStore(JobStore):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 27017,
        database: str = "schedflow",
        collection: str = "jobs",
    ) -> None:
        if MongoClient is None:  # pragma: no cover
            raise ImportError(
                "MongoDBJobStore requires the 'pymongo' package. "
                "Install it with: pip install schedflow[mongodb]"
            )
        self._client = MongoClient(
            host=host,
            port=int(port),
            serverSelectionTimeoutMS=3000,
        )
        self._collection = self._client[database][collection]
        self._logs_collection = self._client[database][f"{collection}_logs"]
        self._indexes_ensured = False

    def _ensure_indexes(self) -> None:
        if self._indexes_ensured:
            return
        self._collection.create_index("next_run_utc", background=True)
        self._indexes_ensured = True

    @staticmethod
    def _next_run_utc(job: Job) -> str | None:
        if job.next_run_time is None:
            return None
        return job.next_run_time.astimezone(UTC).isoformat()

    def _backfill_next_run_utc(self) -> None:
        missing = self._collection.find({"next_run_utc": {"$exists": False}})
        for document in missing:
            job = Job.from_dict(json.loads(document["job_json"]))
            value = self._next_run_utc(job)
            if value is None:
                continue
            self._collection.update_one(
                {"_id": job.job_id},
                {"$set": {"next_run_utc": value}},
            )

    def add(self, job: Job) -> None:
        try:
            self._collection.insert_one(
                {
                    "_id": job.job_id,
                    "job_json": json.dumps(job.to_dict(), ensure_ascii=False),
                    "next_run_utc": self._next_run_utc(job),
                }
            )
        except DuplicateKeyError:
            raise JobConflictError(job.job_id)

    def update(self, job: Job) -> None:
        result = self._collection.update_one(
            {"_id": job.job_id},
            {
                "$set": {
                    "job_json": json.dumps(job.to_dict(), ensure_ascii=False),
                    "next_run_utc": self._next_run_utc(job),
                }
            },
        )
        if result.matched_count == 0:
            raise JobNotFoundError(job.job_id)

    def remove(self, job_id: str) -> None:
        result = self._collection.delete_one({"_id": job_id})
        if result.deleted_count == 0:
            raise JobNotFoundError(job_id)

    def get(self, job_id: str) -> Job | None:
        document = self._collection.find_one({"_id": job_id})
        if document is None:
            return None
        return Job.from_dict(json.loads(document["job_json"]))

    def get_due(self, now: datetime) -> list[Job]:
        self._ensure_indexes()
        self._backfill_next_run_utc()
        now_utc = now.astimezone(UTC).isoformat()
        documents = self._collection.find(
            {"next_run_utc": {"$type": "string", "$lte": now_utc}}
        ).sort("next_run_utc", 1)
        return [
            Job.from_dict(json.loads(document["job_json"]))
            for document in documents
        ]

    def get_all(self) -> list[Job]:
        jobs = self._load_all()
        scheduled = sorted(
            (job for job in jobs if job.next_run_time is not None),
            key=lambda job: job.next_run_time,
        )
        paused = [job for job in jobs if job.next_run_time is None]
        return scheduled + paused

    def get_next_run_time(self) -> datetime | None:
        self._ensure_indexes()
        self._backfill_next_run_utc()
        document = self._collection.find_one(
            {"next_run_utc": {"$exists": True, "$ne": None}},
            sort=[("next_run_utc", 1)],
        )
        if document is None:
            return None
        return datetime.fromisoformat(document["next_run_utc"])

    def add_log(self, job_id: str, log: ExecutionLog) -> None:
        self._logs_collection.insert_one(
            {
                "_id": log.log_id,
                "job_id": job_id,
                "log_json": json.dumps(log.to_dict(), ensure_ascii=False),
            }
        )

    def get_logs(self, job_id: str) -> list[ExecutionLog]:
        documents = self._logs_collection.find({"job_id": job_id})
        return [
            ExecutionLog.from_dict(json.loads(document["log_json"]))
            for document in documents
        ]

    def get_log(self, job_id: str, log_id: str) -> ExecutionLog | None:
        for log in self.get_logs(job_id):
            if log.log_id == log_id:
                return log
        return None

    def close(self) -> None:
        self._client.close()

    def _load_all(self) -> list[Job]:
        return [
            Job.from_dict(json.loads(document["job_json"]))
            for document in self._collection.find()
        ]
