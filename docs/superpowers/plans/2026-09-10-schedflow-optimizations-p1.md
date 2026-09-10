# SchedFlow P1 优化实施计划（执行语义与断点续跑）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 P1：运行快照、full/resume 执行模式、增量可见执行状态、job 级自动恢复策略与工作流级总超时。

**Architecture:** `Workflow` 保持 DAG 执行引擎；新增 `RunSnapshot`（运行期可变状态）与不可变 `ExecutionLog` 分离；JobStore 增加快照存取；`RunRequest(mode, timeout, resume_execution_id)` 经 DispatchQueue 传到 Executor；resume 用快照中 succeeded 节点的结果跳过重跑并正常注入 `_pre_results`。

**Tech Stack:** Python 3.11+、pytest、ruff；SQLAlchemy / Redis / MongoDB 可选 store；Vue 3 + TypeScript。

---

## 任务总览

| # | 任务 | 主要产出 |
|---|------|----------|
| 1 | RunSnapshot 模型与 workflow fingerprint | `core/snapshot.py` |
| 2 | ExecutionLog / TaskRecord P1 字段 | `core/log.py` |
| 3 | Job `on_restart` / `workflow_timeout` | `core/job.py` |
| 4 | JobStore 快照接口 + Memory 实现 | `core/jobstore.py` |
| 5 | SQLAlchemy 快照表 | `core/stores/sqlalchemy.py` |
| 6 | MongoDB 快照集合 | `core/stores/mongo.py` |
| 7 | Redis 快照存储 | `core/stores/redis.py` |
| 8 | Workflow full/resume/timeout/回调 | `core/workflow.py` |
| 9 | RunRequest 贯通 Executor/DispatchQueue | `core/dispatch.py`、`core/executor.py`、`process_worker.py` |
| 10 | Scheduler 快照生命周期与恢复 | `core/scheduler.py` |
| 11 | REST API（run mode / runs / 409） | `api/rest/*` |
| 12 | 前端 P1 | `frontend/src/*` |
| 13 | 文档/示例/架构图/changelog | `docs/*`、`examples/*` |
| 14 | 最终验证 | pytest / ruff / 前端构建 |

每个任务遵循 TDD：先失败测试 → 最小实现 → 全量回归 → 提交。

---

### Task 1: RunSnapshot 模型与 workflow fingerprint

**Files:**
- Create: `src/schedflow/core/snapshot.py`
- Modify: `src/schedflow/core/workflow.py`（新增 `fingerprint()`）
- Test: `tests/core/test_snapshot.py`

- [ ] **Step 1: 写失败测试**

```python
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
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_snapshot.py -q
```

- [ ] **Step 3: 实现 `src/schedflow/core/snapshot.py`**

```python
"""Mutable per-execution run snapshots used for resume."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class DagChangedError(ValueError):
    """Raised when a snapshot was produced by a different workflow."""


def _iso(value: datetime) -> str:
    return value.isoformat()


@dataclass
class TaskRecordSnapshot:
    node_id: str
    status: str = "pending"
    result: Any = None
    error: str | None = None
    skip_reason: str | None = None
    resumed: bool = False

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "skip_reason": self.skip_reason,
            "resumed": self.resumed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TaskRecordSnapshot:
        return cls(
            node_id=data["node_id"],
            status=data.get("status", "pending"),
            result=data.get("result"),
            error=data.get("error"),
            skip_reason=data.get("skip_reason"),
            resumed=bool(data.get("resumed", False)),
        )


@dataclass
class RunSnapshot:
    execution_id: str
    job_id: str
    workflow_fingerprint: str
    mode: str = "full"
    resumes_from: str | None = None
    status: str = "running"
    started_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    records: dict[str, TaskRecordSnapshot] = field(default_factory=dict)

    @classmethod
    def start(
        cls,
        *,
        job_id: str,
        execution_id: str,
        workflow_fingerprint: str,
        mode: str = "full",
        resumes_from: str | None = None,
    ) -> RunSnapshot:
        return cls(
            execution_id=execution_id,
            job_id=job_id,
            workflow_fingerprint=workflow_fingerprint,
            mode=mode,
            resumes_from=resumes_from,
        )

    def set_node(self, record: TaskRecordSnapshot) -> None:
        self.records[record.node_id] = record
        self.updated_at = datetime.now()

    def mark_status(self, status: str) -> None:
        self.status = status
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "job_id": self.job_id,
            "workflow_fingerprint": self.workflow_fingerprint,
            "mode": self.mode,
            "resumes_from": self.resumes_from,
            "status": self.status,
            "started_at": _iso(self.started_at),
            "updated_at": _iso(self.updated_at),
            "records": {
                node_id: record.to_dict()
                for node_id, record in self.records.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> RunSnapshot:
        snapshot = cls(
            execution_id=data["execution_id"],
            job_id=data["job_id"],
            workflow_fingerprint=data["workflow_fingerprint"],
            mode=data.get("mode", "full"),
            resumes_from=data.get("resumes_from"),
            status=data.get("status", "running"),
            started_at=datetime.fromisoformat(data["started_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
        snapshot.records = {
            node_id: TaskRecordSnapshot.from_dict(record)
            for node_id, record in (data.get("records") or {}).items()
        }
        return snapshot
```

`Workflow.fingerprint()`（`core/workflow.py`）：

```python
    def fingerprint(self) -> str:
        """Stable hash of the DAG definition used to validate resume snapshots."""
        import hashlib
        import json

        try:
            payload = self.to_dict()
        except (TypeError, ValueError):
            payload = self._snapshot()
        encoded = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, default=str
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]
```

- [ ] **Step 4: 运行确认通过**

```bash
python -m pytest tests/core/test_snapshot.py -q
ruff check src/schedflow/core/snapshot.py src/schedflow/core/workflow.py
```

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/snapshot.py src/schedflow/core/workflow.py tests/core/test_snapshot.py
git commit -m "feat(core): add run snapshots and workflow fingerprints"
```

---

### Task 2: ExecutionLog / TaskRecord P1 字段

**Files:**
- Modify: `src/schedflow/core/log.py`
- Test: `tests/core/test_log.py`

- [ ] **Step 1: 写失败测试**

```python
def test_log_mode_and_resume_fields_roundtrip():
    log = ExecutionLog(flow_id="wf", job_id="j1")
    log.mode = "resume"
    log.resumes_from = "run-0"
    record = TaskRecord(node_id="a", task_id="a", status="succeeded")
    record.resumed = True
    log.records["a"] = record
    log.finalize()

    restored = ExecutionLog.from_dict(log.to_dict())

    assert restored.mode == "resume"
    assert restored.resumes_from == "run-0"
    assert restored.records["a"].resumed is True


def test_log_timed_out_is_not_succeeded():
    log = ExecutionLog(flow_id="wf")
    log.records["a"] = TaskRecord(node_id="a", task_id="a", status="succeeded")
    log.records["b"] = TaskRecord(
        node_id="b",
        task_id="b",
        status="skipped",
        skip_reason="workflow_timeout",
    )
    log.finalize()

    assert log.timed_out is True
    assert log.succeeded is False
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_log.py -k "mode or timed_out" -q
```

- [ ] **Step 3: 实现**

- `TaskRecord.__slots__`、`__init__`、`to_dict/from_dict` 增加 `resumed: bool = False`；
- `ExecutionLog.__slots__`、`__init__`、`to_dict/from_dict` 增加
  `mode: str = "full"`、`resumes_from: str | None = None`；
- 新增属性：

```python
    @property
    def timed_out(self) -> bool:
        return any(
            record.skip_reason == "workflow_timeout"
            for record in self.records.values()
        )

    @property
    def succeeded(self) -> bool:
        return all(
            record.status not in ("failed", "cancelled")
            for record in self.records.values()
        ) and not self.timed_out
```

- [ ] **Step 4: 运行**

```bash
python -m pytest tests/core/test_log.py -q
ruff check src/schedflow/core/log.py
```

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/log.py tests/core/test_log.py
git commit -m "feat(core): add execution mode, resume and timeout fields to logs"
```

---

### Task 3: Job `on_restart` / `workflow_timeout`

**Files:**
- Modify: `src/schedflow/core/job.py`
- Modify: `src/schedflow/core/scheduler.py`（add_job/update_job 透传）
- Test: `tests/core/test_job.py`、`tests/core/test_scheduler.py`

- [ ] **Step 1: 写失败测试**

```python
def test_job_run_policy_fields_roundtrip():
    wf = Workflow("wf")
    wf.add_task("a", func="os:getcwd")
    job = Job(wf, None, job_id="p1", on_restart="resume", workflow_timeout=30)
    restored = Job.from_dict(job.to_dict())
    assert restored.on_restart == "resume"
    assert restored.workflow_timeout == 30


def test_job_rejects_unknown_on_restart():
    import pytest

    wf = Workflow("wf")
    wf.add_task("a", func="os:getcwd")
    with pytest.raises(ValueError):
        Job(wf, None, job_id="bad", on_restart="sometimes")
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_job.py -k "restart or workflow_timeout" -q
```

- [ ] **Step 3: 实现**

- `Job.__init__` 新增 `on_restart: str = "none"`、`workflow_timeout: float | None = None`；
  校验 `on_restart in {"none", "resume", "rerun"}`，非法值抛 `ValueError`；
- `to_dict/from_dict` 增加两个字段；
- `Scheduler.add_job/update_job` 增加同名参数并透传。

- [ ] **Step 4: 运行并提交**

```bash
python -m pytest tests/core/test_job.py tests/core/test_scheduler.py -q
ruff check src/schedflow/core
git add src/schedflow/core/job.py src/schedflow/core/scheduler.py tests/core/test_job.py tests/core/test_scheduler.py
git commit -m "feat(core): job restart policy and workflow timeout fields"
```

---

### Task 4: JobStore 快照接口 + Memory 实现

**Files:**
- Modify: `src/schedflow/core/jobstore.py`
- Test: `tests/core/test_jobstore.py`

- [ ] **Step 1: 写失败测试**

```python
def test_snapshot_crud_and_listing():
    from schedflow.core.snapshot import RunSnapshot, TaskRecordSnapshot

    store = make_store()
    store.add(make_job())
    first = RunSnapshot.start(
        job_id="j1", execution_id="run-1", workflow_fingerprint="f"
    )
    second = RunSnapshot.start(
        job_id="j1", execution_id="run-2", workflow_fingerprint="f"
    )
    first.set_node(
        TaskRecordSnapshot(node_id="a", status="succeeded", result=1)
    )

    store.save_snapshot("j1", first)
    store.save_snapshot("j1", second)

    assert store.get_snapshot("j1", "run-1").records["a"].result == 1
    assert [s.execution_id for s in store.list_snapshots("j1")] == [
        "run-2",
        "run-1",
    ]

    store.delete_snapshot("j1", "run-1")
    assert store.get_snapshot("j1", "run-1") is None
    assert store.list_snapshots("missing") == []
```

（用正常 import 替代 `__import__` 写法，保持测试可读。）

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_jobstore.py::test_snapshot_crud_and_listing -q
```

- [ ] **Step 3: 实现接口**

`JobStore` 新增抽象方法：

```python
    @abstractmethod
    def save_snapshot(self, job_id: str, snapshot) -> None: ...

    @abstractmethod
    def get_snapshot(self, job_id: str, execution_id: str): ...

    @abstractmethod
    def list_snapshots(self, job_id: str) -> list: ...

    @abstractmethod
    def delete_snapshot(self, job_id: str, execution_id: str) -> None: ...
```

`MemoryJobStore`：

```python
        self._snapshots: dict[str, dict[str, RunSnapshot]] = {}

    def save_snapshot(self, job_id: str, snapshot) -> None:
        self._snapshots.setdefault(job_id, {})[snapshot.execution_id] = snapshot

    def get_snapshot(self, job_id: str, execution_id: str):
        return self._snapshots.get(job_id, {}).get(execution_id)

    def list_snapshots(self, job_id: str) -> list:
        snapshots = self._snapshots.get(job_id, {}).values()
        return sorted(
            snapshots, key=lambda snapshot: snapshot.started_at, reverse=True
        )

    def delete_snapshot(self, job_id: str, execution_id: str) -> None:
        self._snapshots.get(job_id, {}).pop(execution_id, None)
```

`close()` 增加 `self._snapshots.clear()`；顶部 TYPE_CHECKING import RunSnapshot。

- [ ] **Step 4: 运行并提交**

```bash
python -m pytest tests/core/test_jobstore.py -q
ruff check src/schedflow/core/jobstore.py
git add src/schedflow/core/jobstore.py tests/core/test_jobstore.py
git commit -m "feat(core): snapshot storage API with memory implementation"
```

---

### Task 5: SQLAlchemy 快照表

**Files:**
- Modify: `src/schedflow/core/stores/sqlalchemy.py`
- Test: `tests/core/test_stores.py`

- [ ] **Step 1: 写失败测试（`TestSQLAlchemyJobStore`）**

```python
    def test_snapshot_roundtrip(self, sqlalchemy_store):
        from schedflow.core.snapshot import RunSnapshot

        sqlalchemy_store.add(make_job())
        snapshot = RunSnapshot.start(
            job_id="j1", execution_id="run-1", workflow_fingerprint="f"
        )
        sqlalchemy_store.save_snapshot("j1", snapshot)

        restored = sqlalchemy_store.get_snapshot("j1", "run-1")
        assert restored.workflow_fingerprint == "f"
        assert [s.execution_id for s in sqlalchemy_store.list_snapshots("j1")] == [
            "run-1"
        ]
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_stores.py::TestSQLAlchemyJobStore::test_snapshot_roundtrip -q
```

- [ ] **Step 3: 实现**

新增表：

```python
        self.snapshots = sa.Table(
            "job_run_snapshots",
            self._metadata,
            sa.Column("execution_id", sa.String(76), primary_key=True),
            sa.Column("job_id", sa.String(191), nullable=False),
            sa.Column("snapshot_json", sa.Text, nullable=False),
            sa.Column("started_at", sa.String(64), nullable=False),
        )
        sa.Index("ix_snapshots_job_started", "job_id", "started_at")
```

实现 `save_snapshot`（存在则 update，否则 insert）、`get_snapshot`、
`list_snapshots`（按 `started_at DESC`）、`delete_snapshot`；均走
`_with_write_retry` 与 `_ensure`。

- [ ] **Step 4: 运行并提交**

```bash
python -m pytest tests/core/test_stores.py::TestSQLAlchemyJobStore -q
ruff check src/schedflow/core/stores/sqlalchemy.py
git add src/schedflow/core/stores/sqlalchemy.py tests/core/test_stores.py
git commit -m "feat(stores): SQLAlchemy snapshot persistence"
```

---

### Task 6: MongoDB 快照集合

**Files:**
- Modify: `src/schedflow/core/stores/mongo.py`
- Test: `tests/core/test_stores.py`

- [ ] **Step 1: 写失败测试（Mongo 可用时运行，否则 skip）**

```python
    def test_snapshot_roundtrip(self):
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
        finally:
            store.close()
```

- [ ] **Step 2: 实现**

`__init__` 增加 `self._snapshots_collection = self._client[database][f"{collection}_snapshots"]`；
`_ensure_indexes()` 同步创建 `(job_id, started_at)` 索引；
实现四个方法（`update_one(..., upsert=True)`）。

- [ ] **Step 3: 运行并提交**

```bash
python -m pytest tests/core/test_stores.py::TestMongoDBJobStore -q
ruff check src/schedflow/core/stores/mongo.py
git add src/schedflow/core/stores/mongo.py tests/core/test_stores.py
git commit -m "feat(stores): MongoDB snapshot persistence"
```

---

### Task 7: Redis 快照存储

**Files:**
- Modify: `src/schedflow/core/stores/redis.py`
- Test: `tests/core/test_stores.py`

- [ ] **Step 1: 写失败测试（`TestRedisJobStore`）**

```python
    def test_snapshot_roundtrip(self):
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
        finally:
            store.close()
```

- [ ] **Step 2: 实现**

- 新增 key：`self._snapshots_key = f"{prefix}:snapshots"`（hash：field=`{job_id}:{execution_id}`）；
- 新增 zset：`f"{prefix}:snapshot_order"`（score=started_at.timestamp，member 同上）；
- `list_snapshots` 用 zrevrange 取成员后 hget 并过滤 job_id；
- `delete_snapshot` 同步 hdel/zrem。

- [ ] **Step 3: 运行并提交**

```bash
python -m pytest tests/core/test_stores.py::TestRedisJobStore -q
ruff check src/schedflow/core/stores/redis.py
git add src/schedflow/core/stores/redis.py tests/core/test_stores.py
git commit -m "feat(stores): Redis snapshot persistence"
```

---

### Task 8: Workflow full/resume/timeout/节点回调

**Files:**
- Modify: `src/schedflow/core/workflow.py`
- Test: `tests/core/test_workflow.py`

- [ ] **Step 1: 写失败测试**

```python
def test_run_resume_skips_succeeded_nodes_and_keeps_results():
    from schedflow.core.snapshot import RunSnapshot, TaskRecordSnapshot

    attempts = {"a": 0, "b": 0}

    def bump_a():
        attempts["a"] += 1
        return "A"

    def read_a(_pre_results):
        attempts["b"] += 1
        return _pre_results["a"] + "B"

    wf = Workflow("resume")
    wf.add_task("a", func=bump_a)
    wf.add_task("b", func=read_a)
    wf.add_edge("a", "b")

    snapshot = RunSnapshot.start(
        job_id="j1",
        execution_id="run-0",
        workflow_fingerprint=wf.fingerprint(),
        status="failed",
    )
    snapshot.set_node(
        TaskRecordSnapshot(node_id="a", status="succeeded", result="A")
    )

    log = wf.run(mode="resume", resume_from_snapshot=snapshot)

    assert attempts == {"a": 0, "b": 1}
    assert log.records["a"].status == "succeeded"
    assert log.records["a"].resumed is True
    assert log.records["a"].result == "A"
    assert log.records["b"].result == "AB"
    assert log.mode == "resume"
    assert log.resumes_from == "run-0"


def test_run_resume_rejects_changed_dag():
    import pytest

    from schedflow.core.snapshot import DagChangedError, RunSnapshot

    wf = Workflow("resume")
    wf.add_task("a", func="os:getcwd")
    snapshot = RunSnapshot.start(
        job_id="j1",
        execution_id="run-0",
        workflow_fingerprint="different",
    )

    with pytest.raises(DagChangedError):
        wf.run(mode="resume", resume_from_snapshot=snapshot)


def test_run_workflow_timeout_marks_pending_skipped():
    import time

    wf = Workflow("timeout")
    wf.add_task("slow", func=lambda: time.sleep(0.2))
    wf.add_task("later", func=lambda: 1)
    wf.add_edge("slow", "later")

    log = wf.run(timeout=0.05)

    assert log.records["later"].status == "skipped"
    assert log.records["later"].skip_reason == "workflow_timeout"
    assert log.timed_out is True
    assert log.succeeded is False


def test_run_node_callback_sees_each_completed_node():
    wf = Workflow("cb")
    wf.add_task("a", func=lambda: 1)
    seen = []

    wf.run(on_node_finished=lambda node_id, record: seen.append((node_id, record.status)))

    assert seen == [("a", "succeeded")]
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_workflow.py -k "resume or timeout or node_callback" -q
```

- [ ] **Step 3: 实现**

`Workflow.run` 新签名：

```python
    def run(
        self,
        *,
        max_workers: int = 3,
        executor: str = "thread",
        inputs: dict | None = None,
        cancel_event=None,
        mode: str = "full",
        resume_from_snapshot=None,
        timeout: float | None = None,
        on_node_finished=None,
    ) -> ExecutionLog:
```

关键逻辑：

- `mode not in {"full", "resume"}` → `ValueError`；
- `resume` 且无快照 → `ValueError("mode='resume' requires a snapshot")`；
- fingerprint 不一致 → `DagChangedError`；
- `log.mode = mode`、`log.resumes_from = snapshot.execution_id if resume`；
- records 初始化：resume 时对快照中 `succeeded` 节点创建
  `TaskRecord(status="succeeded", result=..., resumed=True)`；
- `_execute_generation` 跳过已经是 `succeeded` 的节点；
- deadline：`deadline = time.monotonic() + timeout`；每层开始与每个节点开始前检查，
  超时把 pending 节点 `mark_skipped("workflow_timeout")` 并停止；
- 每个节点结果落盘后调用 `on_node_finished(node_id, record)`（succeeded/failed/skipped/cancelled 都调用；
  resume 跳过的节点不调用）。

- [ ] **Step 4: 运行并提交**

```bash
python -m pytest tests/core/test_workflow.py -q
ruff check src/schedflow/core/workflow.py
git add src/schedflow/core/workflow.py tests/core/test_workflow.py
git commit -m "feat(core): resume, timeout and node callbacks in Workflow.run"
```

---

### Task 9: RunRequest 贯通 Executor / DispatchQueue

**Files:**
- Create: `src/schedflow/core/run.py`
- Modify: `src/schedflow/core/dispatch.py`
- Modify: `src/schedflow/core/executor.py`
- Modify: `src/schedflow/core/process_worker.py`
- Test: `tests/core/test_dispatch.py`、`tests/core/test_executor.py`

- [ ] **Step 1: 写失败测试**

```python
def test_dispatch_queue_carries_run_request():
    from schedflow.core.run import RunRequest

    queue = DispatchQueue(capacity=1)
    request = RunRequest(mode="resume", timeout=10, resume_execution_id="run-0")
    queue.put(make_job("j1"), datetime.now(UTC), request)

    job, run_time, carried = queue.get(timeout=0.1)
    assert carried == request
    assert carried.mode == "resume"
```

- [ ] **Step 2: 实现 `src/schedflow/core/run.py`**

```python
"""Per-run options passed from the scheduler through executors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunRequest:
    mode: str = "full"
    timeout: float | None = None
    resume_execution_id: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"full", "resume"}:
            raise ValueError(f"Unknown run mode {self.mode!r}")

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "timeout": self.timeout,
            "resume_execution_id": self.resume_execution_id,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> RunRequest:
        data = data or {}
        return cls(
            mode=data.get("mode", "full"),
            timeout=data.get("timeout"),
            resume_execution_id=data.get("resume_execution_id"),
        )
```

- [ ] **Step 3: 贯通接口**

- `DispatchQueue.put(job, run_time, request=None)`；堆条目与 `get()` 返回
  `(job, run_time, request)`；
- `Executor.submit(self, job, run_time, request: RunRequest | None = None)`；
  Debug/ThreadPool 调用 `job.run(..., request=...)`；
- ProcessPool 把 `request.to_dict()` 传给 `run_job_in_process`，worker 用
  `RunRequest.from_dict` 重建后调用 `job.run(...)`；
- 异步执行器（asyncio/gevent/tornado/twisted）的 `submit` 接受并透传 request，
  在各自线程/事件循环内以 `job.run(mode=..., timeout=...)` 执行；
- 所有测试里的 executor stub 签名同步补 `request=None`。

- [ ] **Step 4: 运行并提交**

```bash
python -m pytest tests/core/test_dispatch.py tests/core/test_executor.py -q
ruff check src/schedflow/core
git add src/schedflow/core/run.py src/schedflow/core/dispatch.py src/schedflow/core/executor.py src/schedflow/core/process_worker.py tests/core/test_dispatch.py tests/core/test_executor.py
git commit -m "feat(core): carry RunRequest through dispatch and executors"
```

---

### Task 10: Scheduler 快照生命周期与自动恢复

**Files:**
- Modify: `src/schedflow/core/scheduler.py`
- Test: `tests/core/test_scheduler.py`

- [ ] **Step 1: 写失败测试**

```python
def test_run_job_now_resume_uses_snapshot(monkeypatch):
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
        make_workflow(), trigger=IntervalTrigger(seconds=3600), job_id="j1",
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
        assert (
            scheduler.get_jobstore("default")
            .get_snapshot("j1", "run-stale")
            .status
            in {"failed", "cancelled", "succeeded"}
        )
    finally:
        scheduler.shutdown()
```

- [ ] **Step 2: 实现**

- 新增 `_latest_resumable_snapshot(job_id)`：取 `list_snapshots` 中首个
  `status in {"running", "failed"}` 的快照；
- `_execute_run(job, run_time, request, executor)`：创建 `RunSnapshot`
  （resume 时沿用 `resume_execution_id` 的 `resumes_from`）、定义
  `on_node_finished(node_id, record)` 更新快照并 `save_snapshot`；
  调 `job.run(request=...)`，结束后快照 `mark_status(succeeded/failed/cancelled)`、
  保存，并清理超出 20 份的旧快照；
- 调度派发：`_run_due_job` 构造
  `RunRequest(mode="full", timeout=job.workflow_timeout)`；`_dispatch_loop` 把
  request 交给 executor；
- `run_job_now(job_id, *, max_workers=3, mode="full", timeout=None)`：
  resume 时读取 `_latest_resumable_snapshot`，无快照 → `ValueError`，
  fingerprint 不兼容 → `DagChangedError`；否则走 `_execute_run`；
- `start()` 在启动线程后调用 `_recover_interrupted_runs()`：
  对每个 job 的最新 running 快照按 `job.on_restart` 分派
  `none`（跳过）/`resume`（提交 resume；不兼容时快照置 failed 并发
  `job.failed`）/`rerun`（提交 full）；
- 取消语义：`_on_job_finished` 末尾把快照置 `cancelled`（若 log.cancelled）。

- [ ] **Step 3: 运行并提交**

```bash
python -m pytest tests/core/test_scheduler.py -q
ruff check src/schedflow/core/scheduler.py
git add src/schedflow/core/scheduler.py tests/core/test_scheduler.py
git commit -m "feat(core): snapshot lifecycle and on_restart recovery in Scheduler"
```

---

### Task 11: REST API（run mode / runs / 409）

**Files:**
- Modify: `src/schedflow/api/rest/schemas.py`
- Modify: `src/schedflow/api/rest/routers.py`
- Modify: `src/schedflow/api/exceptions.py`
- Test: `tests/test_api_rest/test_api_rest.py`、`test_frontend_parity.py`

- [ ] **Step 1: 写失败测试**

```python
def test_run_resume_returns_409_without_snapshot():
    client = make_client()
    client.post(
        "/api/jobs",
        json={"workflow": workflow_payload("r"), "job_id": "r1"},
    )

    resp = client.post("/api/jobs/r1/run", json={"mode": "resume"})

    assert resp.status_code == 409
    assert "snapshot" in resp.text.lower()


def test_runs_overview_lists_executions():
    client = make_client()
    scheduler = client.app.state.scheduler_api
    client.post(
        "/api/jobs",
        json={"workflow": workflow_payload("runs"), "job_id": "runs-job"},
    )
    scheduler.run_job_now("runs-job")

    runs = client.get("/api/jobs/runs-job/runs").json()["data"]

    assert runs and runs[0]["execution_id"]
```

- [ ] **Step 2: 实现**

- schemas：`RunJobRequest { mode: Literal["full","resume"]="full"; timeout: float|None }`；
- `POST /api/jobs/{id}/run` 接收 body（可选，默认 full），resume 无快照 / DAG 变更
  → 409；其他 ValueError → 422；
- 新增 `GET /api/jobs/{id}/runs`：返回
  `[{execution_id, mode, resumes_from, status, started_at, ended_at}]`；
- 新增 `GET /api/jobs/{id}/runs/{execution_id}`：snapshot 为 running 时返回
  snapshot JSON；否则优先返回 ExecutionLog；
- `api/exceptions.py` 增加 `DagChangedError → 409`。

- [ ] **Step 3: 运行并提交**

```bash
python -m pytest tests/test_api_rest -q
ruff check src/schedflow/api
git add src/schedflow/api/rest src/schedflow/api/exceptions.py tests/test_api_rest
git commit -m "feat(api): full/resume run modes and run overview endpoints"
```

---

### Task 12: 前端 P1

**Files:**
- Modify: `frontend/src/types/job.ts`
- Modify: `frontend/src/api/jobs.ts`
- Modify: `frontend/src/api/logs.ts`
- Modify: `frontend/src/api/mappers.ts`
- Modify: `frontend/src/views/jobs/JobForm.vue`
- Modify: `frontend/src/views/jobs/JobDetail.vue`
- Modify: `frontend/src/views/logs/ExecutionList.vue`、`JobLogs.vue`、`JobLogViewer.vue`
- Modify: `frontend/src/views/jobs/ExecutionOutput.vue`（resumed/cancelled 标记）

- [ ] **Step 1: 类型与 API**

- `Job` 增加 `on_restart?: 'none'|'resume'|'rerun'`、`workflow_timeout?: number`；
- `ExecutionLog` 增加 `mode?: string`、`resumes_from?: string | null`；
  `NodeExecutionRecord` 增加 `resumed?: boolean`；
- `RunSummary` 类型；
- `api/jobs.ts` 增加 `runJob(id, { mode, timeout })`；
- `api/logs.ts` 增加 `getRuns(jobId)`、`getRunDetail(jobId, executionId)`。

- [ ] **Step 2: 视图**

- `JobForm.vue`：高级选项增加 `on_restart` 下拉与 `workflow_timeout` 数字输入；
- `JobDetail.vue`：运行按钮支持 full / resume 选择；resume 无快照/DAG 变更时展示
  后端 409 文案；展示运行历史（execution_id、mode、resumes_from、status）；
- `ExecutionList.vue` / `JobLogs.vue` / `JobLogViewer.vue`：显示 mode 与恢复链；
- `ExecutionOutput.vue`：`record.resumed` 显示“已恢复”标记；cancelled 节点沿用状态样式。

- [ ] **Step 3: 验证并提交**

```bash
cd frontend
npm run type-check
npm run build
cd ..
git add frontend/src
git commit -m "feat(frontend): resume runs, run history and restart policy"
```

---

### Task 13: 文档 / 示例 / 架构图 / changelog

**Files:**
- Modify: `docs/introduction.zh.md` / `.en.md`
- Modify: `docs/user-guide/core-features.*`、`dag-workflow.*`、`advanced-usage.*`
- Modify: `docs/api-reference/index.*`
- Modify: `docs/index.zh.md` / `.en.md`
- Modify: `docs/images/schedflow-architecture.json` + 重新 deliver HTML
- Create: `examples/resume_execution_example.py`
- Modify: `examples/README.md`
- Modify: `CHANGELOG.md`、`docs/changelog.zh.md` / `.en.md`

- [ ] **Step 1: 文档内容**

- `introduction`：架构总览/数据流补充“运行快照、full/resume、on_restart”；
- `core-features`：Job 字段 `on_restart`/`workflow_timeout`、runs 概览；
- `dag-workflow`：`run(mode/resume/timeout)`、resume 限制与 `resumed` 记录；
- `advanced-usage`：断点续跑与自动恢复策略完整示例；
- `api-reference`：run body、runs 端点、409 错误；
- 架构图：更新 ExecutionLog/JobStore 卡片文案说明运行快照与恢复，用 archify
  `validate` + `deliver` 重新产出 HTML（不新增组件，保持 10 节点）。

- [ ] **Step 2: 示例**

`examples/resume_execution_example.py`：构造 3 节点 DAG，第一次运行到失败，
保存快照后调用 `run_job_now(job_id, mode="resume")`，打印跳过节点与恢复节点。
在 `examples/README.md` 登记该示例。

- [ ] **Step 3: 验证并提交**

```bash
python -m pytest -q
ruff check .
cd frontend && npm run type-check && npm run build && cd ..
node "C:\Users\WWH\.agents\skills\archify\bin\archify.mjs" validate architecture docs/images/schedflow-architecture.json --quality showcase --json
node "C:\Users\WWH\.agents\skills\archify\bin\archify.mjs" deliver architecture docs/images/schedflow-architecture.json docs/images/schedflow-architecture.html --quality showcase --json
git add docs examples CHANGELOG.md README.md README_EN.md
git commit -m "docs: P1 run snapshots, resume and workflow timeout"
```

---

### Task 14: 最终验证（P1 DoD）

- [ ] `python -m pytest` 全绿（外部服务缺失仅 skip）
- [ ] `ruff check .` 无告警
- [ ] `frontend` type-check/build 通过
- [ ] `tests/test_api_rest/test_frontend_parity.py` 覆盖 mode/resumes_from/runs
- [ ] 示例 `examples/resume_execution_example.py` 可运行
- [ ] 架构图重新交付且可视化校验通过
- [ ] 文档 zh/en 与 changelog 更新完成
