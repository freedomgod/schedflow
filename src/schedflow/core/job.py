"""Job: a workflow bound to a trigger and scheduling metadata."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from schedflow.core.log import ExecutionLog
from schedflow.core.workflow import Workflow
from schedflow.triggers.base import Trigger


class Job:
    """A scheduled workflow.

    Args:
        workflow: the :class:`Workflow` to execute (or its JSON dict).
        trigger: the trigger that determines when the job runs (optional;
            jobs without a trigger are run manually via ``run_job_now``).
        job_id: explicit identifier (a UUID hex string is generated if omitted).
        name: human-readable name.
        description: human-readable description.
        executor_alias: executor component alias.
        jobstore_alias: jobstore component alias.
        misfire_grace_time: seconds a late run is still allowed (None = never
            considered missed).
        coalesce: run once when multiple run times are due (kept for
            compatibility with the scheduler loop).
        max_instances: maximum number of concurrently running instances.
    """

    def __init__(
        self,
        workflow: Workflow | dict,
        trigger: Optional[Trigger] = None,
        *,
        job_id: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        executor_alias: str = "default",
        jobstore_alias: str = "default",
        misfire_grace_time: Optional[int] = None,
        coalesce: bool = True,
        max_instances: int = 1,
    ) -> None:
        if isinstance(workflow, dict):
            workflow = Workflow.from_dict(workflow)
        if not isinstance(workflow, Workflow):
            raise TypeError(
                "workflow must be a Workflow instance or its JSON dict"
            )
        if trigger is not None and not hasattr(trigger, "get_next_fire_time"):
            raise TypeError(
                "trigger must provide get_next_fire_time(previous, now) or be None"
            )
        self.workflow = workflow
        self.trigger = trigger
        self.job_id = job_id or uuid.uuid4().hex
        self.name = name
        self.description = description
        self.executor_alias = executor_alias
        self.jobstore_alias = jobstore_alias
        self.misfire_grace_time = misfire_grace_time
        self.coalesce = bool(coalesce)
        self.max_instances = max(1, int(max_instances))
        self.status: str = "running"
        self.next_run_time: Optional[datetime] = None
        if trigger is not None:
            self.next_run_time = trigger.get_next_fire_time(
                None, datetime.now().astimezone()
            )

    def run(self, *, max_workers: int = 3, executor: str = "thread") -> ExecutionLog:
        """Execute the workflow directly; the resulting log carries job_id."""
        log = self.workflow.run(max_workers=max_workers, executor=executor)
        log.job_id = self.job_id
        return log

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "workflow": self.workflow.to_dict(),
            "trigger": self.trigger.to_dict() if self.trigger is not None else None,
            "executor_alias": self.executor_alias,
            "jobstore_alias": self.jobstore_alias,
            "misfire_grace_time": self.misfire_grace_time,
            "coalesce": self.coalesce,
            "max_instances": self.max_instances,
            "next_run_time": (
                self.next_run_time.isoformat()
                if self.next_run_time is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict, *, project_root: Optional[Path | str] = None) -> "Job":
        workflow = Workflow.from_dict(data["workflow"])
        if project_root is not None:
            workflow.project_root = Path(project_root)
        trigger_data = data.get("trigger")
        trigger = Trigger.from_dict(trigger_data) if trigger_data else None
        job = cls(
            workflow,
            trigger,
            job_id=data.get("job_id"),
            name=data.get("name"),
            description=data.get("description"),
            executor_alias=data.get("executor_alias", "default"),
            jobstore_alias=data.get("jobstore_alias", "default"),
            misfire_grace_time=data.get("misfire_grace_time"),
            coalesce=data.get("coalesce", True),
            max_instances=data.get("max_instances", 1),
        )
        job.status = data.get("status", "running")
        next_run_time = data.get("next_run_time")
        if next_run_time:
            job.next_run_time = datetime.fromisoformat(next_run_time)
        return job

    def __repr__(self) -> str:
        return f"<Job job_id={self.job_id!r} name={self.name!r}>"
