"""Scheduler tests (explicit API, due processing, events)."""

import time
from datetime import UTC, datetime, timedelta

import pytest

from schedflow.core.executor import DebugExecutor
from schedflow.core.jobstore import (
    JobConflictError,
    JobNotFoundError,
    MemoryJobStore,
)
from schedflow.core.scheduler import Scheduler
from schedflow.core.workflow import Workflow
from schedflow.triggers import IntervalTrigger


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

    def submit(self, job, run_time, request=None, on_node_finished=None) -> None:
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
    run_time = datetime.now(UTC) - timedelta(seconds=1)
    job.next_run_time = run_time

    store = scheduler.get_jobstore("default")
    real_update = store.update

    def broken_update(_job):
        raise RuntimeError("simulated persistence failure")

    store.update = broken_update
    try:
        with pytest.raises(RuntimeError):
            scheduler._run_due_job(job, datetime.now(UTC))
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
    run_time = datetime.now(UTC) - timedelta(seconds=1)
    job.next_run_time = run_time
    now = datetime.now(UTC)

    scheduler.start()
    try:
        scheduler._run_due_job(job, now)
        deadline = time.time() + 5
        while not scheduler._executor.submitted and time.time() < deadline:
            time.sleep(0.05)
        assert scheduler._executor.submitted == [run_time]
        assert scheduler.get_job("j1").next_run_time > now
    finally:
        scheduler.shutdown()


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
    past = datetime.now(UTC) - timedelta(seconds=1)
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
    job.next_run_time = datetime.now(UTC) - timedelta(seconds=30)
    # The store keeps an indexed due-time snapshot; refresh it after mutating
    # the run time so the scheduler's due scan sees the stale run.
    scheduler.get_jobstore("default").update(job)
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
        datetime.now(UTC),
        None,
        error=RuntimeError("boom"),
    )
    logs = scheduler.get_job_logs("j1")
    assert logs and not logs[0].succeeded
    assert logs[0].records["a"].status == "failed"
    assert "boom" in logs[0].records["a"].error


def test_cancel_queued_job_does_not_run():
    scheduler = make_scheduler()
    seen = []
    scheduler.on("job.cancelled", seen.append)
    scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1"
    )
    job = scheduler.get_job("j1")
    scheduler._advance(job, job.next_run_time, datetime.now(UTC))
    scheduler._running["j1"] = 1
    assert (
        scheduler._dispatch_queue.put(
            scheduler.get_job("j1"), datetime.now(UTC)
        )
        is True
    )

    scheduler.cancel_job("j1")

    assert scheduler.get_job("j1") is not None
    assert "j1" not in scheduler._running
    assert seen and seen[0].kind == "job.cancelled"


def test_cancel_running_job_marks_cancel_event():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), job_id="j1")
    scheduler._running["j1"] = 1

    scheduler.cancel_job("j1")

    assert scheduler._cancel_events["j1"].is_set()


def test_one_shot_job_kept_as_completed_after_final_run():
    scheduler = make_scheduler()
    seen = []
    scheduler.on("job.completed", seen.append)
    scheduler.add_job(
        make_workflow(), trigger=StaticTrigger(datetime.now(UTC)), job_id="j1"
    )
    job = scheduler.get_job("j1")

    scheduler._advance(job, job.next_run_time, datetime.now(UTC))

    stored = scheduler.get_job("j1")
    assert stored is not None
    assert stored.status == "completed"
    assert stored.next_run_time is None
    assert seen and seen[0].kind == "job.completed"


def test_resume_job_keeps_completed_when_trigger_exhausted():
    scheduler = make_scheduler()
    scheduler.add_job(
        make_workflow(), trigger=StaticTrigger(datetime.now(UTC)), job_id="j1"
    )
    job = scheduler.get_job("j1")
    scheduler._advance(job, job.next_run_time, datetime.now(UTC))

    scheduler.resume_job("j1")

    assert scheduler.get_job("j1").status == "completed"
    assert scheduler.get_job("j1").next_run_time is None


def test_loop_error_publishes_scheduler_error_event():
    scheduler = make_scheduler()
    scheduler.state = 1  # STATE_RUNNING
    seen = []
    scheduler.on("scheduler.error", seen.append)

    def broken_process_due():
        raise RuntimeError("loop boom")

    original = scheduler._process_due
    scheduler._process_due = broken_process_due
    try:
        scheduler._main_loop_iteration_for_test()
    finally:
        scheduler._process_due = original

    assert seen
    assert "loop boom" in seen[0].detail["message"]


class _UnreachableJobStore(MemoryJobStore):
    """Memory store that behaves like a backend which is down."""

    def get_next_run_time(self):
        raise ConnectionError("backend down")

    def get_due(self, now):
        raise ConnectionError("backend down")


def test_unreachable_jobstore_does_not_kill_scheduler_loop():
    """A dead backend is skipped and reported, not fatal to the loop thread."""
    scheduler = make_scheduler()
    scheduler.state = 1  # STATE_RUNNING
    seen = []
    scheduler.on("scheduler.error", seen.append)
    dead = _UnreachableJobStore()
    scheduler._jobstores["dead"] = dead

    scheduler._main_loop_iteration_for_test()  # must not raise

    assert scheduler._guarded("dead", dead.get_next_run_time) is None
    assert seen, "the failure must be published as scheduler.error"
    assert "backend down" in seen[0].detail["message"]


def test_unreachable_jobstore_does_not_block_other_stores():
    """Jobs in healthy stores keep running while another store is down."""
    scheduler = make_scheduler()
    scheduler._jobstores["dead"] = _UnreachableJobStore()
    scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=1), job_id="j1"
    )
    scheduler.start()
    try:
        deadline = time.time() + 5
        while not scheduler.get_job_logs("j1") and time.time() < deadline:
            time.sleep(0.05)
        logs = scheduler.get_job_logs("j1")
        assert logs and logs[0].succeeded
        assert scheduler._thread is not None
        assert scheduler._thread.is_alive()
    finally:
        scheduler.shutdown()


def test_start_survives_unreachable_jobstore():
    """A dead store must not abort startup (previously it exited the app)."""
    scheduler = make_scheduler()
    scheduler._jobstores["dead"] = _UnreachableJobStore()

    scheduler.start()
    try:
        assert scheduler.state == 1  # STATE_RUNNING
        assert scheduler._thread is not None
        assert scheduler._thread.is_alive()
    finally:
        scheduler.shutdown()


def test_get_jobs_skips_unreachable_jobstore():
    """Listing jobs degrades to the stores that answer."""
    scheduler = make_scheduler()
    scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1"
    )
    scheduler._jobstores["dead"] = _UnreachableJobStore()

    assert [job.job_id for job in scheduler.get_jobs()] == ["j1"]
    assert scheduler.get_job("j1").job_id == "j1"


def test_jobstore_probe_reports_and_caches_failure():
    """Probing a dead store reports the error and backs off between tries."""
    scheduler = make_scheduler()
    attempts: list[int] = []

    class DeadStore(MemoryJobStore):
        def get_all(self):
            attempts.append(1)
            raise ConnectionError("backend down")

    scheduler._jobstores["dead"] = DeadStore()
    scheduler.JOBSTORE_RETRY_AFTER_SECONDS = 30.0

    first = scheduler.jobstore_probe("dead")
    second = scheduler.jobstore_probe("dead")

    assert first["reachable"] is False
    assert first["job_count"] == 0
    assert "backend down" in first["error"]
    assert second == first, "the cached failure must be reported again"
    assert len(attempts) == 1, "the cooldown must skip the second round trip"

    # A store that is not registered at all is reported as not loaded.
    missing = scheduler.jobstore_probe("ghost")
    assert missing["reachable"] is False
    assert missing["error"]

    # Healthy stores report a count.
    scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1"
    )
    healthy = scheduler.jobstore_probe("default")
    assert healthy == {"job_count": 1, "reachable": True, "error": None}


def test_count_jobs_by_jobstore_tolerates_unreachable_store():
    """A dead store counts as empty so it can still be removed."""
    scheduler = make_scheduler()
    scheduler._jobstores["dead"] = _UnreachableJobStore()
    assert scheduler.count_jobs_by_jobstore("dead") == 0


def test_concurrent_add_and_cancel_no_deadlock():
    import threading

    scheduler = Scheduler(
        jobstore=MemoryJobStore(),
        executor=DebugExecutor(),
    )
    errors = []

    def add_jobs(offset: int):
        try:
            for index in range(50):
                scheduler.add_job(
                    make_workflow(),
                    trigger=IntervalTrigger(seconds=3600),
                    job_id=f"j{offset + index}",
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def cancel_missing():
        try:
            for _ in range(50):
                try:
                    scheduler.cancel_job("missing")
                except JobNotFoundError:
                    pass
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=add_jobs, args=(0,)),
        threading.Thread(target=cancel_missing),
        threading.Thread(target=add_jobs, args=(50,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert errors == []
    assert len(scheduler.get_jobs()) == 100


def test_run_job_now_resume_uses_snapshot():
    from schedflow.core.snapshot import RunSnapshot, TaskRecordSnapshot

    scheduler = make_scheduler()
    calls = {"a": 0}

    def bump():
        calls["a"] += 1
        return "A"

    wf = Workflow("wf")
    wf.add_task("a", func=bump)
    wf.add_task("b", func=lambda: "B")
    wf.add_edge("a", "b")
    scheduler.add_job(wf, job_id="j1")
    snapshot = RunSnapshot.start(
        job_id="j1",
        execution_id="run-0",
        workflow_fingerprint=wf.fingerprint(),
        status="failed",
    )
    snapshot.set_node(
        TaskRecordSnapshot(node_id="a", status="succeeded", result="A")
    )
    scheduler.get_jobstore("default").save_snapshot("j1", snapshot)

    log = scheduler.run_job_now("j1", mode="resume")

    assert calls["a"] == 0
    assert log.records["a"].resumed is True
    assert log.records["b"].status == "succeeded"


def test_start_applies_on_restart_rerun_policy():
    from schedflow.core.snapshot import RunSnapshot

    scheduler = make_scheduler()
    scheduler.add_job(
        make_workflow(),
        trigger=IntervalTrigger(seconds=3600),
        job_id="j1",
        on_restart="rerun",
    )
    job = scheduler.get_job("j1")
    snapshot = RunSnapshot.start(
        job_id="j1",
        execution_id="run-stale",
        workflow_fingerprint=job.workflow.fingerprint(),
    )
    scheduler.get_jobstore("default").save_snapshot("j1", snapshot)

    scheduler.start()
    try:
        deadline = time.time() + 5
        while not scheduler.get_job_logs("j1") and time.time() < deadline:
            time.sleep(0.05)
        assert scheduler.get_job_logs("j1")
        stale = scheduler.get_jobstore("default").get_snapshot(
            "j1", "run-stale"
        )
        assert stale.status in {"failed", "cancelled", "succeeded"}
    finally:
        scheduler.shutdown()
