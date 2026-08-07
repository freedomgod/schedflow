"""Tests for execution records and logs."""

from datetime import datetime

from schedflow.core.log import ExecutionLog, TaskRecord


def make_record(node_id: str = "n1", task_id: str = "t1") -> TaskRecord:
    return TaskRecord(node_id=node_id, task_id=task_id)


class TestTaskRecord:
    def test_default_status_pending(self):
        record = make_record()
        assert record.status == "pending"

    def test_mark_started(self):
        record = make_record()
        record.mark_started()
        assert record.status == "running"
        assert record.start_time is not None

    def test_mark_succeeded(self):
        record = make_record()
        record.mark_started()
        record.mark_succeeded(result={"ok": True})
        assert record.status == "succeeded"
        assert record.result == {"ok": True}
        assert record.end_time is not None
        assert record.duration is not None

    def test_mark_failed(self):
        record = make_record()
        record.mark_started()
        record.mark_failed("ValueError: boom")
        assert record.status == "failed"
        assert record.error == "ValueError: boom"

    def test_mark_skipped(self):
        record = make_record()
        record.mark_skipped("dependency failed")
        assert record.status == "skipped"
        assert record.skip_reason == "dependency failed"

    def test_to_dict_roundtrip(self):
        record = make_record()
        record.mark_started()
        record.mark_succeeded(result=42)
        restored = TaskRecord.from_dict(record.to_dict())
        assert restored.node_id == "n1"
        assert restored.status == "succeeded"
        assert restored.result == 42


class TestExecutionLog:
    def test_init_sets_log_id_and_timestamps(self):
        log = ExecutionLog(flow_id="flow1")
        assert log.log_id
        assert log.flow_id == "flow1"
        assert log.start_time is not None
        assert log.end_time is None

    def test_succeeded_true_when_all_succeeded(self):
        log = ExecutionLog()
        log.records = {
            "n1": TaskRecord(node_id="n1", task_id="t1", status="succeeded"),
            "n2": TaskRecord(node_id="n2", task_id="t2", status="succeeded"),
        }
        log.end_time = datetime.now()
        assert log.succeeded is True
        assert log.failed_nodes() == []
        assert log.skipped_nodes() == []

    def test_succeeded_false_when_any_failed(self):
        log = ExecutionLog()
        log.records = {
            "n1": TaskRecord(node_id="n1", task_id="t1", status="succeeded"),
            "n2": TaskRecord(node_id="n2", task_id="t2", status="failed"),
            "n3": TaskRecord(node_id="n3", task_id="t3", status="skipped"),
        }
        log.end_time = datetime.now()
        assert log.succeeded is False
        assert [r.node_id for r in log.failed_nodes()] == ["n2"]
        assert [r.node_id for r in log.skipped_nodes()] == ["n3"]

    def test_duration(self):
        log = ExecutionLog()
        log.end_time = datetime.now()
        assert log.duration >= 0

    def test_to_dict_roundtrip(self):
        log = ExecutionLog(flow_id="flow1", job_id="job1")
        log.records = {
            "n1": TaskRecord(
                node_id="n1", task_id="t1", status="succeeded", result=42
            )
        }
        log.dag_snapshot = {"nodes": []}
        log.end_time = datetime.now()

        restored = ExecutionLog.from_dict(log.to_dict())
        assert restored.flow_id == "flow1"
        assert restored.job_id == "job1"
        assert restored.log_id == log.log_id
        assert restored.records["n1"].result == 42
        assert restored.succeeded is True
