"""Execution records and workflow-level execution logs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from schedflow.utils import CustomTypeID

TaskStatus = ("pending", "running", "succeeded", "failed", "skipped")


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _from_iso(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value is not None else None


class TaskRecord:
    """Execution record for a single workflow node."""

    __slots__ = (
        "node_id",
        "task_id",
        "status",
        "result",
        "error",
        "skip_reason",
        "stdout",
        "stderr",
        "exit_code",
        "start_time",
        "end_time",
        "duration",
    )

    def __init__(
        self,
        node_id: str,
        task_id: Optional[str] = None,
        status: str = "pending",
        result: Any = None,
        error: Optional[str] = None,
        skip_reason: Optional[str] = None,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        exit_code: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        duration: Optional[float] = None,
    ) -> None:
        if status not in TaskStatus:
            raise ValueError(f"Unknown task status {status!r}")
        self.node_id = node_id
        self.task_id = task_id
        self.status = status
        self.result = result
        self.error = error
        self.skip_reason = skip_reason
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.start_time = start_time
        self.end_time = end_time
        self.duration = duration

    def mark_started(self) -> None:
        self.start_time = datetime.now()
        self.status = "running"

    def mark_succeeded(self, result: Any = None) -> None:
        self.end_time = datetime.now()
        self.status = "succeeded"
        self.result = result
        self._update_duration()

    def mark_failed(self, error: Any) -> None:
        self.end_time = datetime.now()
        self.status = "failed"
        self.error = str(error)
        self._update_duration()

    def mark_skipped(self, reason: str = "") -> None:
        self.status = "skipped"
        self.skip_reason = reason

    def _update_duration(self) -> None:
        if self.start_time is not None and self.end_time is not None:
            self.duration = (self.end_time - self.start_time).total_seconds()

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "task_id": self.task_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "skip_reason": self.skip_reason,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "start_time": _iso(self.start_time),
            "end_time": _iso(self.end_time),
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskRecord":
        return cls(
            node_id=data["node_id"],
            task_id=data.get("task_id"),
            status=data.get("status", "pending"),
            result=data.get("result"),
            error=data.get("error"),
            skip_reason=data.get("skip_reason"),
            stdout=data.get("stdout"),
            stderr=data.get("stderr"),
            exit_code=data.get("exit_code"),
            start_time=_from_iso(data.get("start_time")),
            end_time=_from_iso(data.get("end_time")),
            duration=data.get("duration"),
        )

    def __repr__(self) -> str:
        return f"<TaskRecord {self.node_id} status={self.status!r}>"


class ExecutionLog:
    """Record of one workflow execution (per run of a job or direct run)."""

    __slots__ = (
        "log_id",
        "job_id",
        "flow_id",
        "start_time",
        "end_time",
        "records",
        "dag_snapshot",
    )

    def __init__(
        self,
        flow_id: Optional[str] = None,
        *,
        job_id: Optional[str] = None,
        log_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
    ) -> None:
        self.log_id = log_id or CustomTypeID.full_str("flowlog")
        self.flow_id = flow_id
        self.job_id = job_id
        self.start_time = start_time or datetime.now()
        self.end_time: Optional[datetime] = None
        self.records: dict[str, TaskRecord] = {}
        self.dag_snapshot: Optional[dict] = None

    @property
    def succeeded(self) -> bool:
        """True when no node failed (skipped nodes are not failures)."""
        return all(record.status != "failed" for record in self.records.values())

    @property
    def duration(self) -> Optional[float]:
        if self.end_time is not None:
            return (self.end_time - self.start_time).total_seconds()
        return None

    def finalize(self) -> None:
        self.end_time = datetime.now()

    def failed_nodes(self) -> list[TaskRecord]:
        return [r for r in self.records.values() if r.status == "failed"]

    def skipped_nodes(self) -> list[TaskRecord]:
        return [r for r in self.records.values() if r.status == "skipped"]

    def to_dict(self) -> dict:
        return {
            "log_id": self.log_id,
            "job_id": self.job_id,
            "flow_id": self.flow_id,
            "start_time": _iso(self.start_time),
            "end_time": _iso(self.end_time),
            "duration": self.duration,
            "records": {
                node_id: record.to_dict()
                for node_id, record in self.records.items()
            },
            "dag_snapshot": self.dag_snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionLog":
        log = cls(
            flow_id=data.get("flow_id"),
            job_id=data.get("job_id"),
            log_id=data.get("log_id"),
            start_time=_from_iso(data.get("start_time")),
        )
        log.end_time = _from_iso(data.get("end_time"))
        log.records = {
            node_id: TaskRecord.from_dict(record)
            for node_id, record in (data.get("records") or {}).items()
        }
        log.dag_snapshot = data.get("dag_snapshot")
        return log

    def __repr__(self) -> str:
        return (
            f"<ExecutionLog log_id={self.log_id} flow_id={self.flow_id} "
            f"records={len(self.records)}>"
        )
