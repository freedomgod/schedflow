"""Structured request/response schemas for the REST Web API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from schedflow.core.spec import TaskSpec
from schedflow.core.workflow import Workflow
from schedflow.triggers.base import Trigger


class TaskSpecIn(BaseModel):
    type: Literal["python_callable", "bash", "python", "python_script"] = (
        "python_callable"
    )
    ref: str | None = None
    command: str | None = None
    script_path: str | None = None
    script: str | None = None
    args: list = Field(default_factory=list)
    kwargs: dict = Field(default_factory=dict)
    timeout: float | None = None

    def to_spec(self) -> TaskSpec:
        return TaskSpec.from_dict(self.model_dump())


class NodeIn(BaseModel):
    node_id: str
    task: str | TaskSpecIn
    name: str | None = None
    description: str | None = None
    retries: int = 1
    on_success: TaskSpecIn | None = None
    on_failure: TaskSpecIn | None = None

    @model_validator(mode="after")
    def _normalize_task(self) -> NodeIn:
        if isinstance(self.task, str):
            self.task = TaskSpecIn(ref=self.task)
        return self


class EdgeIn(BaseModel):
    source: str
    target: str
    condition: TaskSpecIn | None = None
    name: str | None = None
    description: str | None = None


class WorkflowIn(BaseModel):
    flow_id: str | None = None
    project_root: str | None = None
    nodes: list[NodeIn] = Field(min_length=1)
    edges: list[EdgeIn] = Field(default_factory=list)

    def to_workflow(self) -> Workflow:
        workflow = Workflow(self.flow_id, project_root=self.project_root)
        for node in self.nodes:
            spec = node.task.to_spec()
            workflow.add_task(
                node.node_id,
                func=spec.ref if spec.type == "python_callable" else None,
                type=spec.type,
                command=spec.command,
                script_path=spec.script_path,
                script=spec.script,
                args=spec.args,
                kwargs=spec.kwargs,
                timeout=spec.timeout,
                name=node.name,
                description=node.description,
                retries=node.retries,
                on_success=node.on_success.to_spec() if node.on_success else None,
                on_failure=node.on_failure.to_spec() if node.on_failure else None,
            )
        for edge in self.edges:
            workflow.add_edge(
                edge.source,
                edge.target,
                condition=(
                    edge.condition.to_spec() if edge.condition is not None else None
                ),
                name=edge.name,
                description=edge.description,
            )
        return workflow


class TriggerIn(BaseModel):
    type: Literal["interval", "cron", "date", "calendarinterval", "and", "or"]
    args: dict = Field(default_factory=dict)

    def to_trigger(self) -> Trigger:
        return Trigger.from_dict({"type": self.type, "args": self.args})


class JobCreateRequest(BaseModel):
    workflow: WorkflowIn
    trigger: TriggerIn | None = None
    job_id: str | None = None
    name: str | None = None
    description: str | None = None
    executor_alias: str = "default"
    jobstore_alias: str = "default"
    misfire_grace_time: int | None = None
    coalesce: bool = True
    max_instances: int = 1
    replace: bool = False


class JobUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    workflow: WorkflowIn | None = None
    trigger: TriggerIn | None = None
    executor_alias: str | None = None
    jobstore_alias: str | None = None
    misfire_grace_time: int | None = None
    coalesce: bool | None = None
    max_instances: int | None = None


class RescheduleRequest(BaseModel):
    trigger: TriggerIn
