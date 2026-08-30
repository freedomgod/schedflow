"""MemoryJobStore tests."""

from datetime import UTC, datetime, timedelta

import pytest

from schedflow.core.job import Job
from schedflow.core.jobstore import (
    JobConflictError,
    JobNotFoundError,
    MemoryJobStore,
)
from schedflow.core.log import ExecutionLog, TaskRecord
from schedflow.core.workflow import Workflow
from schedflow.triggers import IntervalTrigger


def module_fn(value: int = 1) -> int:
    return value


def make_job(job_id: str = "j1", name: str = "n") -> Job:
    wf = Workflow(f"wf-{job_id}")
    wf.add_task("a", func=module_fn)
    return Job(
        wf,
        IntervalTrigger(seconds=60),
        job_id=job_id,
        name=name,
    )


def make_store() -> MemoryJobStore:
    return MemoryJobStore()


def test_add_and_get():
    store = make_store()
    job = make_job()
    store.add(job)
    assert store.get("j1") is job


def test_duplicate_add_raises():
    store = make_store()
    store.add(make_job())
    with pytest.raises(JobConflictError):
        store.add(make_job())


def test_update_and_remove():
    store = make_store()
    job = make_job()
    store.add(job)
    job.name = "renamed"
    store.update(job)
    assert store.get("j1").name == "renamed"
    store.remove("j1")
    assert store.get("j1") is None


def test_remove_missing_raises():
    store = make_store()
    with pytest.raises(JobNotFoundError):
        store.remove("missing")


def test_get_due_sorted():
    store = make_store()
    now = datetime.now(UTC)
    job_a = make_job("a")
    job_a.next_run_time = now - timedelta(seconds=5)
    job_b = make_job("b")
    job_b.next_run_time = now - timedelta(seconds=1)
    job_c = make_job("c")
    job_c.next_run_time = now + timedelta(hours=1)
    store.add(job_c)
    store.add(job_a)
    store.add(job_b)

    due = store.get_due(now)

    assert [j.job_id for j in due] == ["a", "b"]


def test_get_all_paused_last():
    store = make_store()
    now = datetime.now(UTC)
    job_a = make_job("a")
    job_a.next_run_time = now + timedelta(hours=2)
    paused = make_job("paused")
    paused.next_run_time = None
    store.add(paused)
    store.add(job_a)

    jobs = store.get_all()

    assert [j.job_id for j in jobs] == ["a", "paused"]


def test_get_next_run_time():
    store = make_store()
    job = make_job()
    store.add(job)
    assert store.get_next_run_time() == job.next_run_time


def test_add_log_and_get_logs():
    store = make_store()
    job = make_job()
    store.add(job)

    log = ExecutionLog(flow_id="wf-j1", job_id="j1")
    log.records = {"a": TaskRecord(node_id="a", task_id="a", status="succeeded")}
    store.add_log("j1", log)

    logs = store.get_logs("j1")
    assert len(logs) == 1
    assert logs[0].log_id == log.log_id
    assert store.get_log("j1", log.log_id) is log
    assert store.get_log("j1", "missing") is None


def test_job_with_unresolvable_ref_is_kept():
    wf = Workflow("w")
    wf.add_task("a", func="missing_module_xyz:fn")
    job = Job(wf, None, job_id="j-ref")
    store = make_store()
    store.add(job)

    assert store.get("j-ref").workflow.to_dict()["nodes"][0]["task"]["ref"] == (
        "missing_module_xyz:fn"
    )
