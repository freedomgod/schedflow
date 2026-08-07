"""Scheduler tests (explicit API, due processing, events)."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from schedflow.core.events import SchedulerEvent
from schedflow.core.executor import DebugExecutor
from schedflow.core.jobstore import JobConflictError, MemoryJobStore
from schedflow.core.scheduler import Scheduler
from schedflow.core.workflow import Workflow
from schedflow.triggers import DateTrigger, IntervalTrigger


def module_fn(value: int = 1) -> int:
    return value


def failing_fn() -> int:
    raise ValueError("boom")


def make_workflow() -> Workflow:
    wf = Workflow("wf")
    wf.add_task("a", func=module_fn)
    return wf


def make_mixed_workflow() -> Workflow:
    """a succeeds; bad fails; skip depends on bad and is skipped."""
    wf = Workflow("wf")
    wf.add_task("a", func=module_fn)
    wf.add_task("bad", func=failing_fn)
    wf.add_task("skip", func=module_fn)
    wf.add_edge("bad", "skip")
    return wf


def make_scheduler() -> Scheduler:
    return Scheduler(jobstore=MemoryJobStore(), executor=DebugExecutor())


class RecordingExecutor:
    """Executor stub that records submissions without running the job."""

    def __init__(self):
        self.submitted: list[datetime] = []

    def start(self, scheduler) -> None:
        pass

    def submit(self, job, run_time) -> None:
        self.submitted.append(run_time)

    def shutdown(self, *, wait: bool = True) -> None:
        pass


class StaticTrigger:
    """Test trigger that fires once at a fixed time."""

    def __init__(self, fire_at):
        self.fire_at = fire_at

    def get_next_fire_time(self, previous, now):
        if previous is not None:
            return None
        return self.fire_at

    def to_dict(self):
        return {"type": "static", "args": {"fire_at": self.fire_at.isoformat()}}


def test_due_job_not_dispatched_when_advance_persist_fails():
    """A failed next-run-time persist must not dispatch the run; otherwise
    the job stays due forever and executes back-to-back (the flood bug)."""
    scheduler = Scheduler(jobstore=MemoryJobStore(), executor=RecordingExecutor())
    job = scheduler.add_job(
        make_workflow(),
        trigger=IntervalTrigger(seconds=60),
        job_id="j1",
    )
    run_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    job.next_run_time = run_time

    store = scheduler.get_jobstore("default")
    real_update = store.update

    def broken_update(_job):
        raise RuntimeError("simulated persistence failure")

    store.update = broken_update
    try:
        with pytest.raises(RuntimeError):
            scheduler._run_due_job(job, datetime.now(timezone.utc))
        assert scheduler._executor.submitted == []
    finally:
        store.update = real_update


def test_due_job_dispatched_after_advance_persists():
    """The schedule must be persisted before the run is dispatched."""
    scheduler = Scheduler(jobstore=MemoryJobStore(), executor=RecordingExecutor())
    job = scheduler.add_job(
        make_workflow(),
        trigger=IntervalTrigger(seconds=60),
        job_id="j1",
    )
    run_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    job.next_run_time = run_time
    now = datetime.now(timezone.utc)

    scheduler._run_due_job(job, now)

    assert scheduler._executor.submitted == [run_time]
    assert scheduler.get_job("j1").next_run_time > now


def test_add_job_explicit_signature():
    scheduler = make_scheduler()
    job = scheduler.add_job(
        make_workflow(),
        trigger=IntervalTrigger(seconds=60),
        job_id="j1",
        name="n",
        max_instances=2,
    )
    assert job.job_id == "j1"
    assert scheduler.get_job("j1") is not None


def test_add_job_accepts_workflow_dict():
    scheduler = make_scheduler()
    job = scheduler.add_job(
        make_workflow().to_dict(), trigger=IntervalTrigger(seconds=60), job_id="j1"
    )
    assert isinstance(job.workflow, Workflow)


def test_add_job_rejects_positional_trigger():
    scheduler = make_scheduler()
    with pytest.raises(TypeError):
        scheduler.add_job(make_workflow(), IntervalTrigger(seconds=60))


def test_duplicate_job_id_raises():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), job_id="j1")
    with pytest.raises(JobConflictError):
        scheduler.add_job(make_workflow(), job_id="j1")


def test_replace_existing_job():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), job_id="j1", name="old")
    scheduler.add_job(make_workflow(), job_id="j1", name="new", replace=True)
    assert scheduler.get_job("j1").name == "new"


def test_remove_job():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), job_id="j1")
    scheduler.remove_job("j1")
    assert scheduler.get_job("j1") is None


def test_get_jobs():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), job_id="j1")
    scheduler.add_job(make_workflow(), job_id="j2")
    assert {job.job_id for job in scheduler.get_jobs()} == {"j1", "j2"}


def test_update_job():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), job_id="j1", name="old")
    scheduler.update_job("j1", name="new")
    assert scheduler.get_job("j1").name == "new"


def test_pause_and_resume():
    scheduler = make_scheduler()
    scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1"
    )
    scheduler.pause_job("j1")
    assert scheduler.get_job("j1").next_run_time is None
    scheduler.resume_job("j1")
    assert scheduler.get_job("j1").next_run_time is not None


def test_reschedule_job():
    scheduler = make_scheduler()
    scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1"
    )
    before = scheduler.get_job("j1").next_run_time
    scheduler.reschedule_job("j1", IntervalTrigger(seconds=3600))
    after = scheduler.get_job("j1").next_run_time
    assert after > before


def test_run_job_now_returns_log_and_persists():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), job_id="j1")
    log = scheduler.run_job_now("j1")
    assert log.succeeded
    assert scheduler.get_job_logs("j1")[0].log_id == log.log_id


def test_events_subscription():
    scheduler = make_scheduler()
    seen = []
    scheduler.on("job.added", seen.append)
    scheduler.add_job(make_workflow(), job_id="j1")
    assert seen and seen[0].job_id == "j1"


def test_off_unsubscribes():
    scheduler = make_scheduler()
    seen = []
    callback = seen.append
    scheduler.on("job.added", callback)
    scheduler.off("job.added", callback)
    scheduler.add_job(make_workflow(), job_id="j1")
    assert seen == []


def test_task_events_published_on_run_job_now():
    scheduler = make_scheduler()
    seen = []
    for kind in ("task.executed", "task.error", "task.skipped"):
        scheduler.on(kind, seen.append)
    scheduler.add_job(make_mixed_workflow(), job_id="j1")

    log = scheduler.run_job_now("j1")
    assert not log.succeeded

    kinds = [event.kind for event in seen]
    assert "task.executed" in kinds
    assert "task.error" in kinds
    assert "task.skipped" in kinds

    executed = next(e for e in seen if e.kind == "task.executed")
    assert executed.record.node_id == "a"
    assert executed.log is log

    failed = next(e for e in seen if e.kind == "task.error")
    assert failed.record.node_id == "bad"
    assert "boom" in failed.record.error

    skipped = next(e for e in seen if e.kind == "task.skipped")
    assert skipped.record.node_id == "skip"
    assert skipped.record.skip_reason


def test_task_events_published_when_started():
    scheduler = make_scheduler()
    seen = []
    scheduler.on("task.executed", seen.append)
    scheduler.on("*", lambda e: None)  # wildcard subscription stays valid
    scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=1), job_id="j1"
    )
    scheduler.start()
    try:
        deadline = time.time() + 5
        while not seen and time.time() < deadline:
            time.sleep(0.05)
        assert seen
        assert seen[0].kind == "task.executed"
        assert seen[0].record.node_id == "a"
    finally:
        scheduler.shutdown()


def test_start_processes_due_job():
    scheduler = make_scheduler()
    scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=1), job_id="j1"
    )
    scheduler.start()
    try:
        deadline = time.time() + 5
        while not scheduler.get_job_logs("j1") and time.time() < deadline:
            time.sleep(0.05)
        assert scheduler.get_job_logs("j1")[0].succeeded
    finally:
        scheduler.shutdown()


def test_due_job_in_the_past_fires_immediately():
    scheduler = make_scheduler()
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    scheduler.add_job(
        make_workflow(), trigger=StaticTrigger(past), job_id="j1"
    )
    scheduler.start()
    try:
        deadline = time.time() + 5
        while not scheduler.get_job_logs("j1") and time.time() < deadline:
            time.sleep(0.05)
        assert scheduler.get_job_logs("j1")[0].succeeded
    finally:
        scheduler.shutdown()


def test_missed_job_publishes_event():
    scheduler = make_scheduler()
    seen = []
    scheduler.on("job.missed", seen.append)
    job = scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1",
        misfire_grace_time=1,
    )
    job.next_run_time = datetime.now(timezone.utc) - timedelta(seconds=30)
    scheduler.start()
    try:
        deadline = time.time() + 5
        while not seen and time.time() < deadline:
            time.sleep(0.05)
        assert seen
    finally:
        scheduler.shutdown()


def test_run_error_persists_failed_log():
    """A job whose run() raises must still produce a failed ExecutionLog."""
    scheduler = make_scheduler()
    job = scheduler.add_job(make_workflow(), job_id="j1")
    scheduler._on_job_finished(
        job,
        datetime.now(timezone.utc),
        None,
        error=RuntimeError("boom"),
    )
    logs = scheduler.get_job_logs("j1")
    assert logs and not logs[0].succeeded
    assert logs[0].records["a"].status == "failed"
    assert "boom" in logs[0].records["a"].error
