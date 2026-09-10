"""RunSnapshot and workflow fingerprint tests."""

from schedflow.core.snapshot import DagChangedError, RunSnapshot, TaskRecordSnapshot
from schedflow.core.workflow import Workflow


def make_workflow() -> Workflow:
    wf = Workflow("wf")
    wf.add_task("a", func="os:getcwd")
    wf.add_task("b", func="os:getcwd")
    wf.add_edge("a", "b")
    return wf


def test_fingerprint_is_stable_and_sensitive():
    wf = make_workflow()
    same = make_workflow()
    assert wf.fingerprint() == same.fingerprint()

    same.add_task("c", func="os:getcwd")
    assert wf.fingerprint() != same.fingerprint()


def test_snapshot_roundtrip_and_node_updates():
    snapshot = RunSnapshot.start(
        job_id="j1",
        execution_id="run-1",
        workflow_fingerprint="abc",
        mode="full",
    )
    snapshot.set_node(
        TaskRecordSnapshot(node_id="a", status="succeeded", result={"v": 1})
    )

    restored = RunSnapshot.from_dict(snapshot.to_dict())

    assert restored.execution_id == "run-1"
    assert restored.records["a"].status == "succeeded"
    assert restored.records["a"].result == {"v": 1}
    assert restored.status == "running"


def test_dag_changed_error_is_a_value_error():
    assert issubclass(DagChangedError, ValueError)
