"""Tests for the Workflow DAG object."""

import time

import pytest

from schedflow.core.workflow import CycleError, Workflow
from schedflow.core.log import TaskRecord


def module_fn(value: int = 1) -> int:
    """Module-level function used for ref roundtrip tests."""
    return value * 10


def test_add_task_returns_node_id_and_accepts_callable():
    wf = Workflow("wf1")

    node_id = wf.add_task("n1", func=lambda: 1, name="task one")

    assert node_id == "n1"


def test_add_task_accepts_string_ref_without_resolving():
    wf = Workflow("wf1")

    wf.add_task("n1", func="nonexistent_module:fn")

    data = wf.to_dict()
    assert data["nodes"][0]["task"]["ref"] == "nonexistent_module:fn"


def test_add_task_duplicate_node_id_raises():
    wf = Workflow("wf1")
    wf.add_task("n1", func=lambda: 1)

    with pytest.raises(ValueError, match="exists"):
        wf.add_task("n1", func=lambda: 2)


def test_add_task_rejects_unknown_type():
    wf = Workflow("wf1")
    with pytest.raises(ValueError, match="type"):
        wf.add_task("n1", type="powershell", command="x")


def test_add_edge_missing_node_raises():
    wf = Workflow("wf1")
    wf.add_task("n1", func=lambda: 1)

    with pytest.raises(ValueError, match="n2"):
        wf.add_edge("n1", "n2")


def test_add_edge_cycle_raises_and_does_not_add_edge():
    wf = Workflow("wf1")
    wf.add_task("a", func=module_fn)
    wf.add_task("b", func=module_fn)
    wf.add_edge("a", "b")

    with pytest.raises(CycleError):
        wf.add_edge("b", "a")

    assert wf.to_dict()["edges"] == [{"source": "a", "target": "b", "condition": None, "name": None, "description": None}]


def test_run_sequential_with_pre_results_injected():
    wf = Workflow("seq")
    wf.add_task("a", func=lambda: "data")
    wf.add_task("b", func=lambda _pre_results: _pre_results["a"])
    wf.add_edge("a", "b")

    log = wf.run(max_workers=2)

    assert log.succeeded
    assert log.records["a"].result == "data"
    assert log.records["b"].result == "data"


def test_run_skipped_when_predecessor_failed():
    wf = Workflow("skip")

    def boom():
        raise ValueError("boom")

    wf.add_task("a", func=boom)
    wf.add_task("b", func=lambda: 1)
    wf.add_edge("a", "b")

    log = wf.run(max_workers=2)

    assert not log.succeeded
    assert log.records["a"].status == "failed"
    assert log.records["b"].status == "skipped"
    assert "boom" in log.records["a"].error


def test_run_condition_false_skips_target():
    wf = Workflow("cond")
    wf.add_task("a", func=lambda: {"value": 1})
    wf.add_task("b", func=lambda: "ran")
    wf.add_edge("a", "b", condition=lambda record: record.result["value"] > 10)

    log = wf.run(max_workers=2)

    assert log.records["a"].status == "succeeded"
    assert log.records["b"].status == "skipped"


def test_run_parallel_generation():
    wf = Workflow("par")
    wf.add_task("x", func=lambda: "x")
    wf.add_task("y", func=lambda: "y")
    wf.add_task("z", func=lambda _pre_results: sorted(_pre_results))
    wf.add_edge("x", "z")
    wf.add_edge("y", "z")

    log = wf.run(max_workers=2)

    assert log.succeeded
    assert log.records["z"].result == ["x", "y"]


def test_run_inputs_passed_to_tasks():
    wf = Workflow("inputs")
    wf.add_task("a", func=lambda x: x + 1)

    log = wf.run(inputs={"x": 41})

    assert log.records["a"].result == 42


def test_node_duration_reflects_actual_execution_time():
    """TaskRecord duration must cover the real node execution window, not
    be marked started after the node already finished."""
    wf = Workflow("wf")

    def slow(value: int = 1) -> int:
        time.sleep(0.05)
        return value

    wf.add_task("slow", func=slow)

    log = wf.run()
    record = log.records["slow"]

    assert record.status == "succeeded"
    assert record.start_time is not None
    assert record.end_time is not None
    assert record.duration is not None
    assert record.duration >= 0.03


def test_run_retries_then_succeeds():
    wf = Workflow("retry")
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError("not yet")
        return "ok"

    wf.add_task("a", func=flaky, retries=3)
    log = wf.run(max_workers=1)

    assert log.succeeded
    assert attempts["count"] == 3


def test_run_retries_exhausted_marks_failed():
    wf = Workflow("retry-fail")

    def always_fails():
        raise ValueError("always")

    wf.add_task("a", func=always_fails, retries=2)
    log = wf.run(max_workers=1)

    assert log.records["a"].status == "failed"
    assert "always" in log.records["a"].error


def test_run_timeout_marks_failed():
    wf = Workflow("timeout")

    def slow():
        time.sleep(1)
        return "late"

    wf.add_task("a", func=slow, timeout=0.05)
    log = wf.run(max_workers=1)

    assert log.records["a"].status == "failed"
    assert "timed out" in log.records["a"].error.lower()


def test_run_on_success_callback_called():
    wf = Workflow("cb-ok")
    seen = {}

    def on_success(retval):
        seen["retval"] = retval

    wf.add_task("a", func=lambda: 42, on_success=on_success)
    wf.run(max_workers=1)

    assert seen.get("retval") == 42


def test_run_on_failure_callback_called():
    wf = Workflow("cb-err")
    seen = {}

    def on_failure(error):
        seen["error"] = error

    def boom():
        raise ValueError("kaboom")

    wf.add_task("a", func=boom, on_failure=on_failure)
    wf.run(max_workers=1)

    assert "kaboom" in seen.get("error", "")


def test_run_python_script_node():
    wf = Workflow("script")
    wf.add_task("s", type="python_script", script="print('script-ok')")
    log = wf.run(max_workers=1)
    assert log.succeeded
    assert "script-ok" in log.records["s"].stdout


def test_to_dict_roundtrip_and_run():
    wf = Workflow("rt")
    wf.add_task(
        "n1",
        func="tests.core.test_workflow:module_fn",
        kwargs={"value": 3},
        retries=2,
    )
    wf.add_task(
        "n2",
        func="tests.core.test_workflow:module_fn",
        kwargs={"value": 1},
    )
    wf.add_edge("n1", "n2", name="dep")

    restored = Workflow.from_dict(wf.to_dict())
    data = restored.to_dict()
    assert data["flow_id"] == "rt"
    assert data["nodes"][0]["task"]["ref"].endswith(":module_fn")
    assert data["nodes"][0]["retries"] == 2
    assert data["edges"][0] == {
        "source": "n1",
        "target": "n2",
        "condition": None,
        "name": "dep",
        "description": None,
    }


def test_validate_passes_for_valid_workflow():
    wf = Workflow("valid")
    wf.add_task("a", func=lambda: 1)
    wf.add_task("b", func=lambda: 2)
    wf.add_edge("a", "b")
    wf.validate()
