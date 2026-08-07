"""Structured request/response schemas for the REST Web API."""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

from schedflow.core.spec import TaskSpec
from schedflow.core.workflow import Workflow
from schedflow.triggers.base import Trigger


class TaskSpecIn(BaseModel):
    type: Literal["python_callable", "bash", "python", "python_script"] = (
        "python_callable"
    )
    ref: Optional[str] = None
    command: Optional[str] = None
    script_path: Optional[str] = None
    script: Optional[str] = None
    args: list = Field(default_factory=list)
    kwargs: dict = Field(default_factory=dict)
    timeout: Optional[float] = None

    def to_spec(self) -> TaskSpec:
        return TaskSpec.from_dict(self.model_dump())


class NodeIn(BaseModel):
    node_id: str
    task: Union[str, TaskSpecIn]
    name: Optional[str] = None
    description: Optional[str] = None
    retries: int = 1
    on_success: Optional[TaskSpecIn] = None
    on_failure: Optional[TaskSpecIn] = None

    @model_validator(mode="after")
    def _normalize_task(self) -> "NodeIn":
        if isinstance(self.task, str):
            self.task = TaskSpecIn(ref=self.task)
        return self


class EdgeIn(BaseModel):
    source: str
    target: str
    condition: Optional[TaskSpecIn] = None
    name: Optional[str] = None
    description: Optional[str] = None


class WorkflowIn(BaseModel):
    flow_id: Optional[str] = None
    project_root: Optional[str] = None
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
    trigger: Optional[TriggerIn] = None
    job_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    executor_alias: str = "default"
    jobstore_alias: str = "default"
    misfire_grace_time: Optional[int] = None
    coalesce: bool = True
    max_instances: int = 1
    replace: bool = False


class JobUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    workflow: Optional[WorkflowIn] = None
    trigger: Optional[TriggerIn] = None
    executor_alias: Optional[str] = None
    jobstore_alias: Optional[str] = None
    misfire_grace_time: Optional[int] = None
    coalesce: Optional[bool] = None
    max_instances: Optional[int] = None


class RescheduleRequest(BaseModel):
    trigger: TriggerIn
