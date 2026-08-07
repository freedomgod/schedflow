"""executor tests: thread pool and process pool end-to-end via Scheduler."""

import time

import pytest

from schedflow.core.executor import DebugExecutor, ProcessPoolExecutor
from schedflow.core.jobstore import MemoryJobStore
from schedflow.core.scheduler import Scheduler
from schedflow.core.workflow import Workflow
from schedflow.triggers import IntervalTrigger


def module_fn(value: int = 1) -> int:
    """Module-level function so the process pool worker can resolve it."""
    return value * 2


def ref_workflow() -> Workflow:
    wf = Workflow("wf")
    wf.add_task("a", func="tests.core.test_executor:module_fn", kwargs={"value": 21})
    return wf


def wait_for_logs(scheduler, job_id: str, timeout: float = 15.0):
    deadline = time.time() + timeout
    while not scheduler.get_job_logs(job_id) and time.time() < deadline:
        time.sleep(0.05)
    return scheduler.get_job_logs(job_id)


def test_debug_executor_runs_job():
    scheduler = Scheduler(jobstore=MemoryJobStore(), executor=DebugExecutor())
    scheduler.add_job(
        ref_workflow(), trigger=IntervalTrigger(seconds=1), job_id="j1"
    )
    scheduler.start()
    try:
        logs = wait_for_logs(scheduler, "j1")
        assert logs and logs[0].succeeded
        assert logs[0].records["a"].result == 42
    finally:
        scheduler.shutdown()


def test_thread_pool_executor_runs_job():
    from schedflow.core.executor import ThreadPoolExecutor

    scheduler = Scheduler(
        jobstore=MemoryJobStore(), executor=ThreadPoolExecutor(max_workers=2)
    )
    scheduler.add_job(
        ref_workflow(), trigger=IntervalTrigger(seconds=1), job_id="j1"
    )
    scheduler.start()
    try:
        logs = wait_for_logs(scheduler, "j1")
        assert logs and logs[0].succeeded
        assert logs[0].records["a"].result == 42
    finally:
        scheduler.shutdown()


def test_process_pool_executor_runs_job():
    scheduler = Scheduler(
        jobstore=MemoryJobStore(), executor=ProcessPoolExecutor(max_workers=2)
    )
    scheduler.add_job(
        ref_workflow(), trigger=IntervalTrigger(seconds=1), job_id="j1"
    )
    scheduler.start()
    try:
        logs = wait_for_logs(scheduler, "j1")
        assert logs and logs[0].succeeded
        assert logs[0].records["a"].result == 42
    finally:
        scheduler.shutdown()


def test_process_pool_unresolvable_ref_records_failure():
    scheduler = Scheduler(
        jobstore=MemoryJobStore(), executor=ProcessPoolExecutor(max_workers=2)
    )
    wf = Workflow("bad")
    wf.add_task("a", func="missing_module_xyz:fn")
    scheduler.add_job(wf, trigger=IntervalTrigger(seconds=1), job_id="j1")
    scheduler.start()
    try:
        logs = wait_for_logs(scheduler, "j1")
        assert logs
        assert logs[0].records["a"].status == "failed"
        assert "missing_module_xyz" in logs[0].records["a"].error
    finally:
        scheduler.shutdown()
