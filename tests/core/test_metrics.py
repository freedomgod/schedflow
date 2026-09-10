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
