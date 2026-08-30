"""Event bus with string event kinds."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from schedflow.core.log import ExecutionLog, TaskRecord


EVENT_KINDS = frozenset(
    {
        "scheduler.started",
        "scheduler.paused",
        "scheduler.resumed",
        "scheduler.shutdown",
        "job.added",
        "job.updated",
        "job.removed",
        "job.paused",
        "job.resumed",
        "job.started",
        "job.succeeded",
        "job.failed",
        "job.missed",
        "job.max_instances",
        "task.executed",
        "task.error",
        "task.skipped",
    }
)


class SchedulerEvent:
    """A scheduler event with a string kind and optional payload."""

    __slots__ = ("job_id", "kind", "log", "record", "run_time")

    def __init__(
        self,
        kind: str,
        *,
        job_id: str | None = None,
        run_time: datetime | None = None,
        log: ExecutionLog | None = None,
        record: TaskRecord | None = None,
    ) -> None:
        if kind not in EVENT_KINDS:
            raise ValueError(
                f"Unknown event kind {kind!r}; expected one of "
                f"{sorted(EVENT_KINDS)}"
            )
        self.kind = kind
        self.job_id = job_id
        self.run_time = run_time
        self.log = log
        self.record = record

    def __repr__(self) -> str:
        return f"<SchedulerEvent kind={self.kind!r} job_id={self.job_id!r}>"


class EventBus:
    """Thread-safe event pub/sub keyed by event kind (``"*"`` = all)."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[SchedulerEvent], Any]]] = {}
        self._lock = threading.RLock()

    def subscribe(self, kind: str, callback: Callable[[SchedulerEvent], Any]) -> None:
        if kind not in EVENT_KINDS and kind != "*":
            raise ValueError(f"Unknown event kind {kind!r}")
        with self._lock:
            self._listeners.setdefault(kind, []).append(callback)

    def unsubscribe(self, kind: str, callback: Callable) -> bool:
        with self._lock:
            listeners = self._listeners.get(kind)
            if listeners and callback in listeners:
                listeners.remove(callback)
                return True
        return False

    def publish(self, event: SchedulerEvent) -> None:
        with self._lock:
            targets = list(self._listeners.get(event.kind, ())) + list(
                self._listeners.get("*", ())
            )
        for callback in targets:
            try:
                callback(event)
            except Exception:  # noqa: BLE001, S110 - listener errors are isolated
                pass
