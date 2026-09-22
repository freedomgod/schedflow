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
from schedflow.core.snapshot import RunSnapshot

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
        *,
        username: str | None = None,
        password: str | None = None,
        # ``authSource`` keeps pymongo's spelling so the storage form key and
        # the driver keyword stay identical.
        authSource: str | None = None,
    ) -> None:
        if MongoClient is None:  # pragma: no cover
            raise ImportError(
                "MongoDBJobStore requires the 'pymongo' package. "
                "Install it with: pip install schedflow[mongodb]"
            )
        credentials: dict[str, str] = {}
        if username:
            credentials["username"] = username
        if password:
            credentials["password"] = password
        if authSource:
            credentials["authSource"] = authSource
        self._client = MongoClient(
            host=host,
            port=int(port),
            serverSelectionTimeoutMS=3000,
            **credentials,
        )
        self._collection = self._client[database][collection]
        self._logs_collection = self._client[database][f"{collection}_logs"]
        self._snapshots_collection = self._client[database][
            f"{collection}_snapshots"
        ]
        self._indexes_ensured = False

    def _ensure_indexes(self) -> None:
        if self._indexes_ensured:
            return
        self._collection.create_index("next_run_utc", background=True)
        self._collection.create_index("status", background=True)
        self._snapshots_collection.create_index(
            [("job_id", 1), ("started_at", -1)], background=True
        )
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

    def _backfill_status(self) -> None:
        """Populate status for documents written before the field existed."""
        missing = self._collection.find({"status": {"$exists": False}})
        for document in missing:
            job = Job.from_dict(json.loads(document["job_json"]))
            self._collection.update_one(
                {"_id": job.job_id},
                {"$set": {"status": job.status}},
            )

    def add(self, job: Job) -> None:
        try:
            self._collection.insert_one(
                {
                    "_id": job.job_id,
                    "job_json": json.dumps(job.to_dict(), ensure_ascii=False),
                    "next_run_utc": self._next_run_utc(job),
                    "status": job.status,
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
                    "status": job.status,
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
        self._backfill_status()
        now_utc = now.astimezone(UTC).isoformat()
        documents = self._collection.find(
            {
                "next_run_utc": {"$type": "string", "$lte": now_utc},
                "status": "running",
            }
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
        self._backfill_status()
        document = self._collection.find_one(
            {
                "next_run_utc": {"$exists": True, "$ne": None},
                "status": "running",
            },
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

    @staticmethod
    def _snapshot_id(job_id: str, execution_id: str) -> str:
        return f"{job_id}:{execution_id}"

    def save_snapshot(self, job_id: str, snapshot: RunSnapshot) -> None:
        self._ensure_indexes()
        self._snapshots_collection.update_one(
            {"_id": self._snapshot_id(job_id, snapshot.execution_id)},
            {
                "$set": {
                    "job_id": job_id,
                    "execution_id": snapshot.execution_id,
                    "started_at": snapshot.started_at.isoformat(),
                    "snapshot_json": json.dumps(
                        snapshot.to_dict(), ensure_ascii=False
                    ),
                }
            },
            upsert=True,
        )

    def get_snapshot(
        self, job_id: str, execution_id: str
    ) -> RunSnapshot | None:
        self._ensure_indexes()
        document = self._snapshots_collection.find_one(
            {"_id": self._snapshot_id(job_id, execution_id)}
        )
        if document is None:
            return None
        return RunSnapshot.from_dict(json.loads(document["snapshot_json"]))

    def list_snapshots(self, job_id: str) -> list[RunSnapshot]:
        self._ensure_indexes()
        documents = self._snapshots_collection.find(
            {"job_id": job_id}
        ).sort([("started_at", -1), ("_id", -1)])
        return [
            RunSnapshot.from_dict(json.loads(document["snapshot_json"]))
            for document in documents
        ]

    def delete_snapshot(self, job_id: str, execution_id: str) -> None:
        self._ensure_indexes()
        self._snapshots_collection.delete_one(
            {"_id": self._snapshot_id(job_id, execution_id)}
        )

    def close(self) -> None:
        self._client.close()

    def _load_all(self) -> list[Job]:
        return [
            Job.from_dict(json.loads(document["job_json"]))
            for document in self._collection.find()
        ]
