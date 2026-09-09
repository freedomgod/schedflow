"""DispatchQueue tests."""

import time
from datetime import UTC, datetime

from schedflow.core.dispatch import DispatchQueue
from schedflow.core.job import Job
from schedflow.core.workflow import Workflow


def make_job(job_id: str, priority: int = 0) -> Job:
    wf = Workflow(f"wf-{job_id}")
    wf.add_task("a", func="os:getcwd")
    return Job(wf, None, job_id=job_id, priority=priority)


def test_priority_order_and_fifo_tie():
    queue = DispatchQueue(capacity=10)
    now = datetime.now(UTC)
    assert queue.put(make_job("low", priority=10), now) is True
    assert queue.put(make_job("high", priority=1), now) is True
    assert queue.put(make_job("first-tie", priority=1), now) is True
    assert queue.put(make_job("second-tie", priority=1), now) is True

    popped = [queue.get(timeout=0.2) for _ in range(4)]
    assert [item[0].job_id for item in popped] == [
        "high",
        "first-tie",
        "second-tie",
        "low",
    ]


def test_cancel_removes_queued_job():
    queue = DispatchQueue(capacity=10)
    now = datetime.now(UTC)
    queue.put(make_job("j1"), now)
    assert queue.cancel("j1") is True
    assert queue.get(timeout=0.1) is None


def test_duplicate_and_full_queue():
    queue = DispatchQueue(capacity=1)
    now = datetime.now(UTC)
    assert queue.put(make_job("j1"), now) is True
    assert queue.put(make_job("j1"), now) is False
    assert queue.put(make_job("j2"), now) is False
    assert queue.size() == 1


def test_get_times_out():
    queue = DispatchQueue(capacity=1)
    started = time.monotonic()
    assert queue.get(timeout=0.05) is None
    assert time.monotonic() - started >= 0.04
