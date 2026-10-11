"""Local strict REST contract adaptation, with lazy callable references."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schedflow.api.rest.schemas import EdgeIn, NodeIn, TaskSpecIn, TriggerIn, WorkflowIn
from schedflow.api.timezone import with_default_timezone
from schedflow.api.trigger_validation import ensure_schedulable
from schedflow.core.job import Job
from schedflow.triggers.base import Trigger


class StrictTask(TaskSpecIn):
    model_config = ConfigDict(extra="forbid")
    timeout: float | None = Field(default=None, gt=0)


class StrictNode(NodeIn):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(min_length=1, max_length=128)
    task: str | StrictTask
    on_success: StrictTask | None = None
    on_failure: StrictTask | None = None
    retries: int = Field(default=1, ge=0, le=100)


class StrictEdge(EdgeIn):
    model_config = ConfigDict(extra="forbid")
    condition: StrictTask | None = None


class StrictWorkflow(WorkflowIn):
    model_config = ConfigDict(extra="forbid")
    nodes: list[StrictNode] = Field(min_length=1, max_length=100)
    edges: list[StrictEdge] = Field(default_factory=list, max_length=1000)


class StrictTrigger(TriggerIn):
    model_config = ConfigDict(extra="forbid")


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str | None = Field(default=None, min_length=1, max_length=128)
    name: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    workflow: StrictWorkflow
    trigger: StrictTrigger | None = None
    executor_alias: str = "default"
    jobstore_alias: str = "default"
    misfire_grace_time: int | None = Field(default=None, ge=0)
    coalesce: bool = True
    max_instances: int = Field(default=1, ge=1, le=100)
    priority: int = Field(default=0, ge=0)
    on_restart: Literal["none", "resume", "rerun"] = "none"
    workflow_timeout: float | None = Field(default=None, gt=0)
    status: Literal["running", "paused"] = "paused"
    next_run_time: str | None = None


def validate_candidate(payload, scheduler):
    data = Candidate.model_validate(payload)
    if data.executor_alias not in scheduler._executors:
        raise ValueError("Unknown executor alias")
    if data.jobstore_alias not in scheduler._jobstores:
        raise ValueError("Unknown jobstore alias")
    workflow = data.workflow.to_workflow()
    if scheduler._project_root is not None:
        workflow.project_root = scheduler._project_root
    if len({node.node_id for node in data.workflow.nodes}) != len(data.workflow.nodes):
        raise ValueError("Duplicate node_id")
    trigger = None
    if data.trigger:
        raw = data.trigger.model_dump()
        _check_nested_triggers(raw)
        raw = ensure_schedulable(with_default_timezone(raw))
        trigger = Trigger.from_dict(raw)
    kwargs = data.model_dump(exclude={"workflow", "trigger", "status", "next_run_time"})
    job = Job(workflow, trigger, **kwargs)
    job.status = data.status
    if job.status == "paused":
        job.next_run_time = None
    return job.to_dict()


def _check_nested_triggers(raw):
    StrictTrigger.model_validate(raw)
    if raw["type"] in {"and", "or"}:
        for nested in raw.get("args", {}).get("triggers", []):
            _check_nested_triggers(nested)


def inline_schema(model):
    """Detach a model schema for nesting in tool properties without broken root refs."""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def expand(value):
        if isinstance(value, dict):
            if "$ref" in value:
                name = value["$ref"].removeprefix("#/$defs/")
                return expand(
                    {
                        **definitions[name],
                        **{k: v for k, v in value.items() if k != "$ref"},
                    }
                )
            return {k: expand(v) for k, v in value.items()}
        if isinstance(value, list):
            return [expand(v) for v in value]
        return value

    return expand(schema)
