"""Persistent JobStore tests (SQLAlchemy, Redis, MongoDB)."""

from datetime import UTC, datetime, timedelta

import pytest

from schedflow.core.job import Job
from schedflow.core.jobstore import JobConflictError, JobNotFoundError
from schedflow.core.log import ExecutionLog, TaskRecord
from schedflow.core.stores.mongo import MongoDBJobStore
from schedflow.core.stores.redis import RedisJobStore
from schedflow.core.stores.sqlalchemy import SQLAlchemyJobStore
from schedflow.core.workflow import Workflow
from schedflow.triggers import IntervalTrigger


def module_fn(value: int = 1) -> int:
    return value


def make_job(job_id: str = "j1", *, ref: str | None = None) -> Job:
    wf = Workflow(f"wf-{job_id}")
    wf.add_task("a", func=ref or module_fn)
    return Job(
        wf,
        IntervalTrigger(seconds=60),
        job_id=job_id,
        name=f"job-{job_id}",
    )


@pytest.fixture
def sqlalchemy_store():
    store = SQLAlchemyJobStore(url="sqlite:///:memory:")
    yield store
    store.close()


class TestSQLAlchemyJobStore:
    def test_add_and_get(self, sqlalchemy_store):
        sqlalchemy_store.add(make_job())
        job = sqlalchemy_store.get("j1")
        assert job.job_id == "j1"
        assert job.name == "job-j1"
        assert isinstance(job.workflow, Workflow)

    def test_duplicate_add_raises(self, sqlalchemy_store):
        sqlalchemy_store.add(make_job())
        with pytest.raises(JobConflictError):
            sqlalchemy_store.add(make_job())

    def test_update_and_remove(self, sqlalchemy_store):
        sqlalchemy_store.add(make_job())
        job = sqlalchemy_store.get("j1")
        job.name = "renamed"
        sqlalchemy_store.update(job)
        assert sqlalchemy_store.get("j1").name == "renamed"
        sqlalchemy_store.remove("j1")
        assert sqlalchemy_store.get("j1") is None

    def test_remove_missing_raises(self, sqlalchemy_store):
        with pytest.raises(JobNotFoundError):
            sqlalchemy_store.remove("missing")

    def test_get_due_filters_and_sorts(self, sqlalchemy_store):
        now = datetime.now(UTC)
        past_a = make_job("a")
        past_a.next_run_time = now - timedelta(seconds=5)
        past_b = make_job("b")
        past_b.next_run_time = now - timedelta(seconds=1)
        future = make_job("c")
        future.next_run_time = now + timedelta(hours=1)
        sqlalchemy_store.add(future)
        sqlalchemy_store.add(past_a)
        sqlalchemy_store.add(past_b)

        due = sqlalchemy_store.get_due(now)

        assert [job.job_id for job in due] == ["a", "b"]

    def test_get_due_uses_utc_column_and_ignores_future(self, sqlalchemy_store):
        from datetime import timedelta

        now = datetime.now(UTC)
        past = make_job("past")
        past.next_run_time = now - timedelta(seconds=2)
        future = make_job("future")
        future.next_run_time = now + timedelta(hours=1)
        paused = make_job("paused")
        paused.next_run_time = None
        sqlalchemy_store.add(future)
        sqlalchemy_store.add(past)
        sqlalchemy_store.add(paused)

        assert [job.job_id for job in sqlalchemy_store.get_due(now)] == ["past"]
        # 尚未执行的 past 仍是最早调度时间；get_next_run_time 返回它。
        assert sqlalchemy_store.get_next_run_time() == past.next_run_time

    def test_get_due_requires_next_run_utc_column(self, sqlalchemy_store):
        import sqlalchemy as sa

        sqlalchemy_store.get_due(datetime.now(UTC))
        with sqlalchemy_store._engine.connect() as connection:
            rows = connection.execute(
                sa.text(
                    "SELECT name FROM pragma_table_info('jobs') "
                    "WHERE name='next_run_utc'"
                )
            ).scalars().all()
        assert rows == ["next_run_utc"]

    def test_get_next_run_time(self, sqlalchemy_store):
        now = datetime.now(UTC)
        job = make_job("j1")
        job.next_run_time = now + timedelta(hours=3)
        sqlalchemy_store.add(job)
        assert sqlalchemy_store.get_next_run_time() == job.next_run_time

    def test_get_due_ignores_paused_job_with_armed_time(self, sqlalchemy_store):
        now = datetime.now(UTC)
        job = make_job("paused-armed")
        job.status = "paused"
        job.next_run_time = now - timedelta(seconds=5)
        sqlalchemy_store.add(job)

        assert sqlalchemy_store.get_due(now) == []
        assert sqlalchemy_store.get_next_run_time() is None

    def test_backfills_status_column(self, tmp_path):
        import sqlalchemy as sa

        url = f"sqlite:///{tmp_path / 'legacy.db'}"
        store = SQLAlchemyJobStore(url)
        store.add(make_job())
        with store._engine.begin() as connection:
            connection.execute(sa.text("DROP INDEX ix_jobs_status"))
            connection.execute(sa.text("ALTER TABLE jobs DROP COLUMN status"))
        store.close()

        reopened = SQLAlchemyJobStore(url)
        try:
            assert reopened.get_next_run_time() is not None
            with reopened._engine.connect() as connection:
                statuses = (
                    connection.execute(sa.text("SELECT status FROM jobs"))
                    .scalars()
                    .all()
                )
            assert statuses == ["running"]
        finally:
            reopened.close()

    def test_log_roundtrip(self, sqlalchemy_store):
        sqlalchemy_store.add(make_job())
        log = ExecutionLog(flow_id="wf-j1", job_id="j1")
        log.records = {"a": TaskRecord(node_id="a", task_id="a", status="succeeded")}
        log.dag_snapshot = {"nodes": []}

        sqlalchemy_store.add_log("j1", log)
        logs = sqlalchemy_store.get_logs("j1")

        assert len(logs) == 1
        assert logs[0].log_id == log.log_id
        assert logs[0].succeeded is True
        assert sqlalchemy_store.get_log("j1", log.log_id) is not None

    def test_unresolvable_ref_survives_roundtrip(self, sqlalchemy_store):
        """A job whose ref cannot be resolved must not be dropped on load."""
        sqlalchemy_store.add(make_job(ref="missing_module_xyz:fn"))

        job = sqlalchemy_store.get("j1")

        assert job is not None
        assert (
            job.workflow.to_dict()["nodes"][0]["task"]["ref"]
            == "missing_module_xyz:fn"
        )

    def test_snapshot_roundtrip(self, sqlalchemy_store):
        from schedflow.core.snapshot import RunSnapshot

        sqlalchemy_store.add(make_job())
        snapshot = RunSnapshot.start(
            job_id="j1", execution_id="run-1", workflow_fingerprint="f"
        )

        sqlalchemy_store.save_snapshot("j1", snapshot)
        restored = sqlalchemy_store.get_snapshot("j1", "run-1")

        assert restored.workflow_fingerprint == "f"
        assert [
            item.execution_id
            for item in sqlalchemy_store.list_snapshots("j1")
        ] == ["run-1"]
        sqlalchemy_store.delete_snapshot("j1", "run-1")
        assert sqlalchemy_store.get_snapshot("j1", "run-1") is None

    def test_ensure_tolerates_existing_column_and_index(
        self, sqlalchemy_store, monkeypatch
    ):
        sqlalchemy_store.add(make_job())
        sqlalchemy_store._schema_ready = False

        class StaleInspector:
            def get_table_names(self):
                return ["jobs", "job_run_snapshots"]

            def get_columns(self, table):
                return [{"name": "id"}, {"name": "job_json"}]

            def get_indexes(self, table):
                return []

        import schedflow.core.stores.sqlalchemy as store_module

        monkeypatch.setattr(
            store_module.sa, "inspect", lambda engine: StaleInspector()
        )

        sqlalchemy_store._ensure()

        assert sqlalchemy_store.get("j1").job_id == "j1"


@pytest.mark.skipif(
    not __import__("shutil").which("redis-server"),
    reason="Redis server not available",
)
class TestRedisJobStore:
    def test_add_get_roundtrip(self):
        store = RedisJobStore(host="localhost", port=6379, db=15)
        try:
            store.add(make_job())
            job = store.get("j1")
            assert job is not None and job.job_id == "j1"
        finally:
            store.close()


@pytest.mark.skipif(
    not __import__("shutil").which("mongod"),
    reason="MongoDB server not available",
)
class TestMongoDBJobStore:
    def test_add_get_roundtrip(self):
        store = MongoDBJobStore(
            host="localhost", port=27017, database="schedflow_test"
        )
        try:
            store.add(make_job())
            job = store.get("j1")
            assert job is not None and job.job_id == "j1"
        finally:
            store.close()

    def test_get_due_and_next_run_time_use_run_times_index(self):
        store = RedisJobStore(host="localhost", port=6379, db=15)
        try:
            now = datetime.now(UTC)
            past = make_job("redis-past")
            past.next_run_time = now - timedelta(seconds=1)
            future = make_job("redis-future")
            future.next_run_time = now + timedelta(hours=1)
            store.add(future)
            store.add(past)

            assert [job.job_id for job in store.get_due(now)] == ["redis-past"]
            assert store.get_next_run_time() == past.next_run_time
        finally:
            store.close()

    def test_snapshot_roundtrip_redis(self):
        from schedflow.core.snapshot import RunSnapshot

        store = RedisJobStore(host="localhost", port=6379, db=15)
        try:
            snapshot = RunSnapshot.start(
                job_id="redis-snap",
                execution_id="run-1",
                workflow_fingerprint="f",
            )
            store.save_snapshot("redis-snap", snapshot)

            assert (
                store.get_snapshot("redis-snap", "run-1").workflow_fingerprint
                == "f"
            )
            assert [
                item.execution_id
                for item in store.list_snapshots("redis-snap")
            ] == ["run-1"]
            store.delete_snapshot("redis-snap", "run-1")
            assert store.get_snapshot("redis-snap", "run-1") is None
        finally:
            store.close()

    def test_get_due_uses_indexed_utc_field(self):
        store = MongoDBJobStore(
            host="localhost", port=27017, database="schedflow_test"
        )
        try:
            now = datetime.now(UTC)
            past = make_job("mongo-past")
            past.next_run_time = now - timedelta(seconds=1)
            future = make_job("mongo-future")
            future.next_run_time = now + timedelta(hours=1)
            store.add(future)
            store.add(past)

            due = store.get_due(now)
            assert [job.job_id for job in due] == ["mongo-past"]
            assert store.get_next_run_time() == past.next_run_time
            indexes = store._collection.index_information()
            assert any("next_run_utc" in key[0] for key in indexes.values())
        finally:
            store.close()

    def test_snapshot_roundtrip_mongodb(self):
        from schedflow.core.snapshot import RunSnapshot

        store = MongoDBJobStore(
            host="localhost", port=27017, database="schedflow_test"
        )
        try:
            snapshot = RunSnapshot.start(
                job_id="mongo-snap",
                execution_id="run-1",
                workflow_fingerprint="f",
            )
            store.save_snapshot("mongo-snap", snapshot)

            assert (
                store.get_snapshot("mongo-snap", "run-1").workflow_fingerprint
                == "f"
            )
            assert [
                item.execution_id
                for item in store.list_snapshots("mongo-snap")
            ] == ["run-1"]
            store.delete_snapshot("mongo-snap", "run-1")
            assert store.get_snapshot("mongo-snap", "run-1") is None
        finally:
            store.close()
