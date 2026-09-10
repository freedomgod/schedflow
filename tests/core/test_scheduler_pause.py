"""暂停语义回归测试：paused 任务不得被重新武装或执行。"""

from datetime import UTC, datetime, timedelta

from schedflow.core.executor import DebugExecutor
from schedflow.core.jobstore import MemoryJobStore
from schedflow.core.scheduler import Scheduler
from schedflow.core.workflow import Workflow
from schedflow.triggers import IntervalTrigger


def module_fn(value: int = 1) -> int:
    return value


def make_workflow() -> Workflow:
    wf = Workflow("wf")
    wf.add_task("a", func=module_fn)
    return wf


def make_scheduler(store: MemoryJobStore | None = None) -> Scheduler:
    return Scheduler(jobstore=store or MemoryJobStore(), executor=DebugExecutor())


def test_update_job_with_trigger_does_not_wake_paused_job():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1")
    scheduler.pause_job("j1")

    updated = scheduler.update_job("j1", trigger=IntervalTrigger(seconds=30))

    assert updated.status == "paused"
    assert updated.next_run_time is None


def test_reschedule_does_not_wake_paused_job():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1")
    scheduler.pause_job("j1")

    updated = scheduler.reschedule_job("j1", IntervalTrigger(seconds=10))

    assert updated.status == "paused"
    assert updated.next_run_time is None
    assert scheduler.get_job("j1").next_run_time is None


def test_advance_disarms_job_that_is_not_running():
    scheduler = make_scheduler()
    job = scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1"
    )
    run_time = job.next_run_time
    scheduler.pause_job("j1")

    scheduler._advance(job, run_time, datetime.now(UTC))

    assert job.status == "paused"
    assert job.next_run_time is None


def test_resume_rearms_paused_job():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1")
    scheduler.pause_job("j1")

    resumed = scheduler.resume_job("j1")

    assert resumed.status == "running"
    assert resumed.next_run_time is not None
    assert resumed.next_run_time > datetime.now(UTC) - timedelta(seconds=1)
