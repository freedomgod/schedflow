"""Metrics registry tests."""

import pytest

from schedflow.core.metrics import (
    counter_inc,
    gauge_set,
    histogram_observe,
    render_prometheus,
    reset_metrics,
)


@pytest.fixture(autouse=True)
def _reset_metrics():
    reset_metrics()


def test_metrics_render_prometheus_text():
    counter_inc("schedflow_job_runs_total", labels={"outcome": "succeeded"})
    gauge_set("schedflow_dispatch_queue_depth", 3)
    histogram_observe("schedflow_job_run_duration_seconds", 1.5)

    text = render_prometheus()

    assert 'schedflow_job_runs_total{outcome="succeeded"} 1' in text
    assert "schedflow_dispatch_queue_depth 3" in text
    assert "schedflow_job_run_duration_seconds_count 1" in text
    assert "schedflow_job_run_duration_seconds_sum 1.5" in text


def test_metrics_are_monotonic_and_labels_are_separate():
    counter_inc("schedflow_job_runs_total", labels={"outcome": "failed"})
    counter_inc("schedflow_job_runs_total", labels={"outcome": "failed"})
    counter_inc("schedflow_job_runs_total", labels={"outcome": "succeeded"})

    text = render_prometheus()

    assert 'schedflow_job_runs_total{outcome="failed"} 2' in text
    assert 'schedflow_job_runs_total{outcome="succeeded"} 1' in text


def test_listener_errors_are_counted():
    from schedflow.core.events import EventBus, SchedulerEvent

    bus = EventBus()

    def broken(event):
        raise RuntimeError("boom")

    bus.subscribe("job.added", broken)
    bus.publish(SchedulerEvent("job.added", job_id="j1"))

    assert "schedflow_event_listener_errors_total 1" in render_prometheus()


def test_scheduler_state_runs_and_run_outcome_metrics():
    from schedflow.core.executor import DebugExecutor
    from schedflow.core.jobstore import MemoryJobStore
    from schedflow.core.scheduler import Scheduler
    from schedflow.core.workflow import Workflow

    workflow = Workflow("metrics")
    workflow.add_task("a", func="os:getcwd")
    scheduler = Scheduler(
        jobstore=MemoryJobStore(), executor=DebugExecutor()
    )
    scheduler.add_job(workflow, job_id="metrics-job")
    scheduler.run_job_now("metrics-job")

    text = render_prometheus()
    assert 'schedflow_job_runs_total{outcome="succeeded"} 1' in text
    assert "schedflow_job_run_duration_seconds_count 1" in text
    assert "schedflow_jobs_total" in text

    scheduler.start()
    try:
        assert "schedflow_scheduler_state 1" in render_prometheus()
        scheduler.pause()
        assert "schedflow_scheduler_state 2" in render_prometheus()
        scheduler.resume()
        assert "schedflow_scheduler_state 1" in render_prometheus()
    finally:
        scheduler.shutdown()
    assert "schedflow_scheduler_state 0" in render_prometheus()
