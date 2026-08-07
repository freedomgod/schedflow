"""Async-flavored executor tests: end-to-end via the core Scheduler."""

import time

import pytest

from schedflow.core.jobstore import MemoryJobStore
from schedflow.core.scheduler import Scheduler
from schedflow.core.workflow import Workflow
from schedflow.triggers import IntervalTrigger


def module_fn(value: int = 1) -> int:
    """Module-level function so workflow references can resolve it."""
    return value * 2


def boom() -> int:
    """Module-level function that always fails."""
    raise RuntimeError("boom")


def ref_workflow() -> Workflow:
    wf = Workflow("wf")
    wf.add_task(
        "a", func="tests.core.test_async_executors:module_fn", kwargs={"value": 21}
    )
    return wf


def failing_workflow() -> Workflow:
    wf = Workflow("boom")
    wf.add_task("a", func="tests.core.test_async_executors:boom")
    return wf


def wait_for_logs(scheduler, job_id: str, timeout: float = 15.0):
    deadline = time.time() + timeout
    while not scheduler.get_job_logs(job_id) and time.time() < deadline:
        time.sleep(0.05)
    return scheduler.get_job_logs(job_id)


def run_with_executor(executor) -> None:
    scheduler = Scheduler(jobstore=MemoryJobStore(), executor=executor)
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


def test_asyncio_executor_runs_job() -> None:
    from schedflow.core.async_executors import AsyncIOExecutor

    run_with_executor(AsyncIOExecutor())


def test_asyncio_executor_records_failure() -> None:
    from schedflow.core.async_executors import AsyncIOExecutor

    scheduler = Scheduler(jobstore=MemoryJobStore(), executor=AsyncIOExecutor())
    scheduler.add_job(
        failing_workflow(), trigger=IntervalTrigger(seconds=1), job_id="j1"
    )
    scheduler.start()
    try:
        logs = wait_for_logs(scheduler, "j1")
        assert logs and not logs[0].succeeded
        assert logs[0].records["a"].status == "failed"
        assert "boom" in logs[0].records["a"].error
    finally:
        scheduler.shutdown()


def test_gevent_executor_runs_job() -> None:
    pytest.importorskip("gevent")
    from schedflow.core.async_executors import GeventExecutor

    run_with_executor(GeventExecutor())


def test_tornado_executor_runs_job() -> None:
    from schedflow.core.async_executors import TornadoExecutor

    run_with_executor(TornadoExecutor(max_workers=2))


def test_twisted_executor_runs_job() -> None:
    pytest.importorskip("twisted")
    from schedflow.core.async_executors import TwistedExecutor

    run_with_executor(TwistedExecutor())
