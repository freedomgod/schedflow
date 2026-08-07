"""Persistent JobStore tests (SQLAlchemy, Redis, MongoDB)."""

from datetime import datetime, timedelta, timezone

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
        now = datetime.now(timezone.utc)
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

    def test_get_next_run_time(self, sqlalchemy_store):
        now = datetime.now(timezone.utc)
        job = make_job("j1")
        job.next_run_time = now + timedelta(hours=3)
        sqlalchemy_store.add(job)
        assert sqlalchemy_store.get_next_run_time() == job.next_run_time

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
