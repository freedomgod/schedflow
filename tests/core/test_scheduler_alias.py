"""Multi-executor/multi-jobstore alias routing on the core Scheduler."""

import time

import pytest

from schedflow.core.scheduler import Scheduler
from schedflow.core.workflow import Workflow
from schedflow.triggers import IntervalTrigger


def module_fn(value: int = 1) -> int:
    """Module-level function so workflow references can resolve it."""
    return value * 2


def ref_workflow() -> Workflow:
    wf = Workflow("wf")
    wf.add_task(
        "a", func="tests.core.test_scheduler_alias:module_fn", kwargs={"value": 21}
    )
    return wf


def wait_for_logs(scheduler, job_id: str, timeout: float = 15.0):
    deadline = time.time() + timeout
    while not scheduler.get_job_logs(job_id) and time.time() < deadline:
        time.sleep(0.05)
    return scheduler.get_job_logs(job_id)


def test_jobs_route_to_named_jobstore() -> None:
    scheduler = Scheduler()
    scheduler.add_jobstore("memory", "secondary")
    scheduler.add_job(ref_workflow(), job_id="j1", jobstore_alias="secondary")
    assert [j.job_id for j in scheduler.get_jobs(jobstore_alias="secondary")] == [
        "j1"
    ]
    assert scheduler.get_jobs(jobstore_alias="default") == []


def test_get_job_searches_all_stores() -> None:
    scheduler = Scheduler()
    scheduler.add_jobstore("memory", "secondary")
    scheduler.add_job(ref_workflow(), job_id="j1", jobstore_alias="secondary")
    assert scheduler.get_job("j1") is not None
    assert scheduler.get_job("j1").jobstore_alias == "secondary"


def test_executor_alias_is_recorded() -> None:
    scheduler = Scheduler()
    scheduler.add_executor("threadpool", "fast")
    scheduler.add_job(ref_workflow(), job_id="j1", executor_alias="fast")
    assert scheduler.get_job("j1").executor_alias == "fast"


def test_jobstore_migration_moves_jobs() -> None:
    scheduler = Scheduler()
    scheduler.add_jobstore("memory", "old")
    scheduler.add_jobstore("memory", "new")
    scheduler.add_job(ref_workflow(), job_id="j1", jobstore_alias="old")
    assert scheduler.migrate_jobstore("old", "new") == 1
    assert scheduler.count_jobs_by_jobstore("old") == 0
    assert scheduler.count_jobs_by_jobstore("new") == 1
    assert scheduler.get_job("j1").jobstore_alias == "new"


def test_job_runs_via_named_executor_and_jobstore() -> None:
    scheduler = Scheduler()
    scheduler.add_executor("threadpool", "fast")
    scheduler.add_jobstore("memory", "secondary")
    scheduler.add_job(
        ref_workflow(),
        trigger=IntervalTrigger(seconds=1),
        job_id="j1",
        executor_alias="fast",
        jobstore_alias="secondary",
    )
    scheduler.start()
    try:
        logs = wait_for_logs(scheduler, "j1")
        assert logs and logs[0].succeeded
        assert logs[0].records["a"].result == 42
    finally:
        scheduler.shutdown()


def test_remove_jobstore_refuses_when_jobs_present() -> None:
    scheduler = Scheduler()
    scheduler.add_jobstore("memory", "secondary")
    scheduler.add_job(ref_workflow(), job_id="j1", jobstore_alias="secondary")
    with pytest.raises(RuntimeError):
        scheduler.remove_jobstore("secondary")


def test_remove_executor_refuses_when_jobs_reference() -> None:
    scheduler = Scheduler()
    scheduler.add_executor("threadpool", "fast")
    scheduler.add_job(ref_workflow(), job_id="j1", executor_alias="fast")
    with pytest.raises(RuntimeError):
        scheduler.remove_executor("fast")


def test_add_duplicate_alias_raises() -> None:
    scheduler = Scheduler()
    with pytest.raises(ValueError):
        scheduler.add_jobstore("memory", "default")
    with pytest.raises(ValueError):
        scheduler.add_executor("threadpool", "default")


def test_cannot_remove_default_aliases() -> None:
    scheduler = Scheduler()
    with pytest.raises(RuntimeError):
        scheduler.remove_jobstore("default")
    with pytest.raises(RuntimeError):
        scheduler.remove_executor("default")
