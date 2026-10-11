import threading
from concurrent.futures import Future

import pytest

from schedflow.core import Scheduler, Workflow
from schedflow.core.run import RunRequest

STARTED = threading.Event()
RELEASE = threading.Event()
CALLS = []


def blocked(value=None):
    CALLS.append(value)
    STARTED.set()
    assert RELEASE.wait(5)
    return value


@pytest.fixture
def scheduler():
    STARTED.clear()
    RELEASE.clear()
    CALLS.clear()
    sched = Scheduler()
    flow = Workflow()
    flow.add_task("task", blocked, kwargs={"value": {"version": 1}})
    sched.add_job(flow, job_id="job", max_instances=2)
    yield sched
    RELEASE.set()
    sched.shutdown()


def accept(scheduler, execution_id="agentrun_first", job_id="job"):
    return scheduler.accept_manual_run(
        job_id,
        expected_hash=scheduler.job_config_hash(job_id),
        execution_id=execution_id,
    )


def test_accept_returns_without_waiting_and_persists_execution_id(scheduler):
    future = accept(scheduler)
    assert isinstance(future, Future)
    assert STARTED.wait(2)
    assert not future.done()
    assert scheduler.get_job_run("job", "agentrun_first")["status"] == "running"
    RELEASE.set()
    log = future.result(3)
    assert log.log_id == "agentrun_first"
    assert scheduler.get_job_log("job", log.log_id) is log


def test_duplicate_execution_id_executes_once(scheduler):
    first = accept(scheduler)
    assert accept(scheduler) is first
    RELEASE.set()
    first.result(3)
    assert accept(scheduler) is first
    assert len(CALLS) == 1


def test_accepted_workflow_freezes_mutable_configuration(scheduler):
    future = accept(scheduler)
    assert STARTED.wait(2)
    scheduler.get_job("job").workflow._nodes["task"].spec.kwargs["value"]["version"] = 2
    RELEASE.set()
    assert future.result(3).records["task"].result == {"version": 1}


def test_manual_accept_checks_full_hash_and_instance_limit(scheduler):
    stale = scheduler.job_config_hash("job")
    scheduler.update_job("job", name="changed")
    with pytest.raises(ValueError, match="configuration changed"):
        scheduler.accept_manual_run(
            "job", expected_hash=stale, execution_id="agentrun_stale"
        )
    accept(scheduler)
    accept(scheduler, "agentrun_second")
    with pytest.raises(ValueError, match="max_instances"):
        accept(scheduler, "agentrun_third")


def test_durable_prior_snapshot_is_not_executed_again(scheduler):
    scheduler._prepare_run(
        scheduler.get_job("job"), RunRequest(execution_id="agentrun_unknown")
    )
    with pytest.raises(ValueError, match="already exists"):
        accept(scheduler, "agentrun_unknown")
    assert CALLS == []


def test_shutdown_wait_false_does_not_cancel_actual_work_and_start_reopens_pool(
    scheduler,
):
    scheduler.start(paused=True)
    future = accept(scheduler)
    assert STARTED.wait(2)
    scheduler.shutdown(wait=False)
    assert not future.cancelled()
    RELEASE.set()
    assert future.result(3).succeeded
    scheduler.start(paused=True)
    assert accept(scheduler, "agentrun_restart").result(3).succeeded


def test_agent_unknown_snapshot_is_not_retried_on_start(scheduler):
    scheduler.update_job("job", on_restart="rerun")
    scheduler._prepare_run(
        scheduler.get_job("job"), RunRequest(execution_id="agentrun_unknown")
    )
    scheduler.start(paused=True)
    assert scheduler._dispatch_queue.size() == 0
    assert not STARTED.wait(0.1)


def test_manual_capacity_rejects_without_creating_snapshot(scheduler):
    scheduler.MANUAL_RUN_CAPACITY = 1
    accept(scheduler)
    with pytest.raises(ValueError, match="capacity"):
        accept(scheduler, "agentrun_capacity")
    assert scheduler.get_job_run("job", "agentrun_capacity") is None


def test_accepted_run_keeps_original_store_when_component_is_replaced(scheduler):
    from schedflow.core import MemoryJobStore

    scheduler.MANUAL_RUN_WORKERS = 1
    original_store = scheduler.get_jobstore("default")
    first = accept(scheduler)
    assert STARTED.wait(2)
    queued = accept(scheduler, "agentrun_queued")
    replacement = MemoryJobStore()
    replacement.add(scheduler.get_job("job"))
    scheduler.set_jobstore(replacement)
    RELEASE.set()
    first.result(3)
    log = queued.result(3)
    assert original_store.get_log("job", "agentrun_queued") is log
    assert original_store.get_snapshot("job", "agentrun_queued").status == "succeeded"
    assert replacement.get_log("job", "agentrun_queued") is None


def test_completed_receipt_history_is_bounded_and_durable_log_deduplicates(scheduler):
    RELEASE.set()
    for index in range(130):
        accept(scheduler, f"agentrun_history_{index}").result(3)
    assert len(scheduler._manual_futures) <= 128
    assert accept(scheduler, "agentrun_history_0").result(3).log_id == "agentrun_history_0"
    assert len(CALLS) == 130
