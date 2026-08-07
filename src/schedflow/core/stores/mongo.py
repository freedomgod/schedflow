"""MongoDB job store (JSON documents, no pickle)."""

from __future__ import annotations

import json
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
    from pymongo import MongoClient
    from pymongo.errors import DuplicateKeyError
except ImportError as exc:  # pragma: no cover
    raise ImportError("MongoDBJobStore requires PyMongo installed") from exc


class MongoDBJobStore(JobStore):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 27017,
        database: str = "schedflow",
        collection: str = "jobs",
    ) -> None:
        self._client = MongoClient(
            host=host,
            port=int(port),
            serverSelectionTimeoutMS=3000,
        )
        self._collection = self._client[database][collection]
        self._logs_collection = self._client[database][f"{collection}_logs"]

    def add(self, job: Job) -> None:
        try:
            self._collection.insert_one(
                {
                    "_id": job.job_id,
                    "job_json": json.dumps(job.to_dict(), ensure_ascii=False),
                }
            )
        except DuplicateKeyError:
            raise JobConflictError(job.job_id)

    def update(self, job: Job) -> None:
        result = self._collection.update_one(
            {"_id": job.job_id},
            {"$set": {"job_json": json.dumps(job.to_dict(), ensure_ascii=False)}},
        )
        if result.matched_count == 0:
            raise JobNotFoundError(job.job_id)

    def remove(self, job_id: str) -> None:
        result = self._collection.delete_one({"_id": job_id})
        if result.deleted_count == 0:
            raise JobNotFoundError(job_id)

    def get(self, job_id: str) -> Optional[Job]:
        document = self._collection.find_one({"_id": job_id})
        if document is None:
            return None
        return Job.from_dict(json.loads(document["job_json"]))

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

    def get_log(self, job_id: str, log_id: str) -> Optional[ExecutionLog]:
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
