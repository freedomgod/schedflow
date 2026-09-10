"""Mutable per-execution run snapshots used for resume."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class DagChangedError(ValueError):
    """Raised when a snapshot was produced by a different workflow."""


def _iso(value: datetime) -> str:
    return value.isoformat()


@dataclass
class TaskRecordSnapshot:
    node_id: str
    status: str = "pending"
    result: Any = None
    error: str | None = None
    skip_reason: str | None = None
    resumed: bool = False

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "skip_reason": self.skip_reason,
            "resumed": self.resumed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TaskRecordSnapshot:
        return cls(
            node_id=data["node_id"],
            status=data.get("status", "pending"),
            result=data.get("result"),
            error=data.get("error"),
            skip_reason=data.get("skip_reason"),
            resumed=bool(data.get("resumed", False)),
        )


@dataclass
class RunSnapshot:
    execution_id: str
    job_id: str
    workflow_fingerprint: str
    mode: str = "full"
    resumes_from: str | None = None
    status: str = "running"
    started_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    records: dict[str, TaskRecordSnapshot] = field(default_factory=dict)

    @classmethod
    def start(
        cls,
        *,
        job_id: str,
        execution_id: str,
        workflow_fingerprint: str,
        mode: str = "full",
        resumes_from: str | None = None,
    ) -> RunSnapshot:
        return cls(
            execution_id=execution_id,
            job_id=job_id,
            workflow_fingerprint=workflow_fingerprint,
            mode=mode,
            resumes_from=resumes_from,
        )

    def set_node(self, record: TaskRecordSnapshot) -> None:
        self.records[record.node_id] = record
        self.updated_at = datetime.now()

    def mark_status(self, status: str) -> None:
        self.status = status
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "job_id": self.job_id,
            "workflow_fingerprint": self.workflow_fingerprint,
            "mode": self.mode,
            "resumes_from": self.resumes_from,
            "status": self.status,
            "started_at": _iso(self.started_at),
            "updated_at": _iso(self.updated_at),
            "records": {
                node_id: record.to_dict()
                for node_id, record in self.records.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> RunSnapshot:
        snapshot = cls(
            execution_id=data["execution_id"],
            job_id=data["job_id"],
            workflow_fingerprint=data["workflow_fingerprint"],
            mode=data.get("mode", "full"),
            resumes_from=data.get("resumes_from"),
            status=data.get("status", "running"),
            started_at=datetime.fromisoformat(data["started_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
        snapshot.records = {
            node_id: TaskRecordSnapshot.from_dict(record)
            for node_id, record in (data.get("records") or {}).items()
        }
        return snapshot
