"""Job tests."""

from pathlib import Path

import pytest

from schedflow.core.job import Job
from schedflow.core.workflow import Workflow
from schedflow.triggers import IntervalTrigger


def module_fn(value: int = 1) -> int:
    return value


def make_workflow() -> Workflow:
    wf = Workflow("wf")
    wf.add_task("a", func=module_fn)
    return wf


def test_explicit_constructor_generates_job_id():
    job = Job(make_workflow(), IntervalTrigger(seconds=60))
    assert job.job_id


def test_accepts_workflow_dict():
    job = Job(make_workflow().to_dict(), IntervalTrigger(seconds=60))
    assert isinstance(job.workflow, Workflow)


def test_rejects_invalid_workflow():
    with pytest.raises(TypeError, match="workflow"):
        Job("not-a-workflow", None)


def test_next_run_time_computed_from_trigger():
    job = Job(make_workflow(), IntervalTrigger(seconds=60))
    assert job.next_run_time is not None


def test_run_sets_job_id_and_returns_log():
    job = Job(make_workflow(), None)
    log = job.run()
    assert log.job_id == job.job_id
    assert log.succeeded


def test_to_dict_roundtrip():
    wf = Workflow("w")
    wf.add_task("a", func="tests.core.test_job:module_fn", kwargs={"value": 5})
    job = Job(
        wf,
        IntervalTrigger(seconds=30),
        job_id="j1",
        name="n",
        description="d",
        max_instances=2,
    )

    restored = Job.from_dict(job.to_dict())

    assert restored.job_id == "j1"
    assert restored.name == "n"
    assert restored.description == "d"
    assert restored.max_instances == 2
    assert isinstance(restored.workflow, Workflow)
    assert restored.workflow.to_dict() == wf.to_dict()
    assert isinstance(restored.trigger, IntervalTrigger)


def test_from_dict_project_root():
    wf = Workflow("w")
    wf.add_task("a", func="some.module:fn")
    job = Job(wf, None, job_id="j1")
    data = job.to_dict()

    restored = Job.from_dict(data, project_root="D:/proj")

    assert restored.workflow.project_root == Path("D:/proj")


def test_to_dict_without_trigger():
    job = Job(make_workflow(), None, job_id="j2")
    data = job.to_dict()
    assert data["trigger"] is None
    restored = Job.from_dict(data)
    assert restored.trigger is None
