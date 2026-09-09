# SchedFlow P0 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 P0 调度可靠性与性能优化：JobStore 到期索引、派发队列与优先级、协作式取消、一次性任务保留停用、错误可见化、锁拆分，并同步 REST/前端/文档。

**Architecture:** 保持单进程与现有 JobStore/Executor 接口兼容；新增 `core/dispatch.py` 作为主循环与 Executor 之间的有界优先级队列；`Workflow.run()` 通过可选 `cancel_event` 在拓扑层边界协作式停止；一次性触发器耗尽时把 Job 置为 `completed` 而非删除。

**Tech Stack:** Python 3.11+、pytest、ruff；SQLAlchemy/MongoDB/Redis 为可选 store；前端 Vue 3 + TypeScript。

---

## 任务总览

| # | 任务 | 产出 |
|---|------|------|
| 1 | MemoryJobStore 到期最小堆 | `core/jobstore.py` |
| 2 | SQLAlchemy 到期列与索引 | `core/stores/sqlalchemy.py` |
| 3 | MongoDB 到期字段与索引 | `core/stores/mongo.py` |
| 4 | Redis 等价测试 | `tests/core/test_stores.py` |
| 5 | Job `priority`/`completed` + 事件/状态扩展 | `core/job.py`、`core/events.py`、`core/log.py` |
| 6 | Workflow 协作式取消 | `core/workflow.py` |
| 7 | Executor/Job 取消传递 | `core/job.py`、`core/executor.py` |
| 8 | DispatchQueue | 新增 `core/dispatch.py` |
| 9 | Scheduler 派发/取消/事件接入 | `core/scheduler.py` |
| 10 | 一次性任务保留停用 | `core/scheduler.py` |
| 11 | 错误可见化 | `core/scheduler.py`、`core/events.py` |
| 12 | 锁拆分与并发测试 | `core/scheduler.py` |
| 13 | REST API 同步 | `api/rest/*`、契约测试 |
| 14 | 前端 P0 同步 | `frontend/src/*` |
| 15 | 文档/示例/变更记录 | `docs/*`、`CHANGELOG.md` |

每个任务都遵循 TDD：先加失败测试 → 运行确认失败 → 最小实现 → 全绿 → 提交。

---

### Task 1: MemoryJobStore 到期最小堆

**Files:**
- Modify: `src/schedflow/core/jobstore.py`
- Test: `tests/core/test_jobstore.py`

- [ ] **Step 1: 先写失败测试（追加到 `tests/core/test_jobstore.py`）**

```python
def test_get_due_ignores_stale_heap_entries_after_update():
    """Rescheduling a job must not let the old run time fire again."""
    store = make_store()
    now = datetime.now(UTC)
    job = make_job("j1")
    job.next_run_time = now - timedelta(seconds=1)
    store.add(job)

    job.next_run_time = now + timedelta(hours=1)
    store.update(job)

    assert store.get_due(now) == []
    assert store.get_next_run_time() == job.next_run_time


def test_get_due_removes_job_after_remove():
    store = make_store()
    now = datetime.now(UTC)
    job = make_job("j1")
    job.next_run_time = now - timedelta(seconds=1)
    store.add(job)
    store.remove("j1")

    assert store.get_due(now) == []
    assert store.get_next_run_time() is None


def test_get_due_fifo_for_same_run_time():
    """Jobs due at the same instant keep insertion order."""
    store = make_store()
    now = datetime.now(UTC)
    first = make_job("first")
    first.next_run_time = now
    second = make_job("second")
    second.next_run_time = now
    store.add(first)
    store.add(second)

    assert [job.job_id for job in store.get_due(now)] == ["first", "second"]
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_jobstore.py -q
```

预期：当前实现是线性扫描，三个新用例中前两个会失败（update/remove 后旧到期时间仍可见）。

- [ ] **Step 3: 实现最小堆（修改 `src/schedflow/core/jobstore.py`）**

顶部 import 增加：

```python
import heapq
import itertools
```

`MemoryJobStore.__init__` 与内部方法改为：

```python
class MemoryJobStore(JobStore):
    """In-memory job store (volatile) with an O(log n) due-time heap."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._logs: dict[str, list[ExecutionLog]] = {}
        self._heap: list[tuple] = []
        self._versions: dict[str, int] = {}
        self._counter = itertools.count()

    def _push_scheduled(self, job: Job) -> None:
        if job.next_run_time is None:
            return
        version = self._versions[job.job_id]
        heapq.heappush(
            self._heap,
            (
                job.next_run_time,
                next(self._counter),
                job.job_id,
                version,
            ),
        )

    def _clean_heap(self) -> None:
        while self._heap:
            _, _, job_id, version = self._heap[0]
            job = self._jobs.get(job_id)
            if (
                job is not None
                and job.next_run_time is not None
                and version == self._versions.get(job_id)
            ):
                return
            heapq.heappop(self._heap)

    def add(self, job: Job) -> None:
        if job.job_id in self._jobs:
            raise JobConflictError(job.job_id)
        self._jobs[job.job_id] = job
        self._versions[job.job_id] = self._versions.get(job.job_id, 0) + 1
        self._push_scheduled(job)

    def update(self, job: Job) -> None:
        if job.job_id not in self._jobs:
            raise JobNotFoundError(job.job_id)
        self._jobs[job.job_id] = job
        self._versions[job.job_id] = self._versions.get(job.job_id, 0) + 1
        self._push_scheduled(job)

    def remove(self, job_id: str) -> None:
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id)
        del self._jobs[job_id]
        self._versions[job_id] = self._versions.get(job_id, 0) + 1

    def get_due(self, now: datetime) -> list[Job]:
        self._clean_heap()
        due: list[Job] = []
        while self._heap:
            run_time, _, job_id, version = self._heap[0]
            if run_time > now:
                break
            job = self._jobs.get(job_id)
            if (
                job is None
                or version != self._versions.get(job_id)
                or job.next_run_time != run_time
            ):
                heapq.heappop(self._heap)
                continue
            heapq.heappop(self._heap)
            due.append(job)
        return due

    def get_next_run_time(self) -> datetime | None:
        self._clean_heap()
        if not self._heap:
            return None
        return self._heap[0][0]
```

`get_all()` 保持不变（它直接读 `_jobs`，顺序语义不变）。

- [ ] **Step 4: 运行确认通过**

```bash
python -m pytest tests/core/test_jobstore.py -q
```

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/jobstore.py tests/core/test_jobstore.py
git commit -m "feat(core): heap-based due lookup in MemoryJobStore"
```

---

### Task 2: SQLAlchemy 到期列与索引

**Files:**
- Modify: `src/schedflow/core/stores/sqlalchemy.py`
- Test: `tests/core/test_stores.py`

- [ ] **Step 1: 写失败测试（追加到 `tests/core/test_stores.py` 的 `TestSQLAlchemyJobStore`）**

```python
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
        assert sqlalchemy_store.get_next_run_time() == future.next_run_time
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_stores.py::TestSQLAlchemyJobStore::test_get_due_uses_utc_column_and_ignores_future -q
```

预期：当前实现只依赖 `job_json` 文本、无独立列；该用例仍会通过（因为行为本来正确）。要验证“不再全表扫描”需让实现先崩溃：暂时在 `get_due` 里断言列存在。

```python
    def test_get_due_requires_next_run_utc_column(self, sqlalchemy_store):
        import sqlalchemy as sa

        with sqlalchemy_store._engine.connect() as connection:
            rows = connection.execute(
                sa.text(
                    "SELECT name FROM pragma_table_info('jobs') WHERE name='next_run_utc'"
                )
            ).scalars().all()
        assert rows == ["next_run_utc"]
```

先运行上一条用例使其失败，再实现。

- [ ] **Step 3: 修改 `src/schedflow/core/stores/sqlalchemy.py`**

`from datetime import UTC, datetime`，并在 `jobs` 表中增加列与索引：

```python
        self.jobs = sa.Table(
            "jobs",
            self._metadata,
            sa.Column("id", sa.String(191), primary_key=True),
            sa.Column("job_json", sa.Text, nullable=False),
            sa.Column("next_run_utc", sa.String(64), nullable=True),
            sa.Index("ix_jobs_next_run_utc", "next_run_utc"),
        )
```

新增/替换方法：

```python
    @staticmethod
    def _next_run_utc(job: Job) -> str | None:
        if job.next_run_time is None:
            return None
        return job.next_run_time.astimezone(UTC).isoformat()

    def _ensure(self) -> None:
        self._metadata.create_all(self._engine, checkfirst=True)
        inspector = sa.inspect(self._engine)
        columns = {
            column["name"]
            for column in inspector.get_columns("jobs")
        }
        if "next_run_utc" not in columns:
            with self._engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "ALTER TABLE jobs ADD COLUMN next_run_utc VARCHAR(64)"
                    )
                )
        with self._engine.begin() as connection:
            connection.execute(
                sa.text(
                    "CREATE INDEX IF NOT EXISTS ix_jobs_next_run_utc "
                    "ON jobs (next_run_utc)"
                )
            )
        self._backfill_next_run_utc()

    def _backfill_next_run_utc(self) -> None:
        """Populate next_run_utc for rows written before the column existed."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                sa.select(self.jobs.c.id, self.jobs.c.job_json).where(
                    self.jobs.c.next_run_utc.is_(None)
                )
            ).all()
        for job_id, raw in rows:
            job = Job.from_dict(json.loads(raw))
            value = self._next_run_utc(job)
            with self._engine.begin() as connection:
                connection.execute(
                    self.jobs.update()
                    .where(self.jobs.c.id == job_id)
                    .values(next_run_utc=value)
                )
```

写入值（`_add_once`、`_update_once`）带上新列：

```python
            connection.execute(
                self.jobs.insert().values(
                    id=job.job_id,
                    job_json=json.dumps(job.to_dict(), ensure_ascii=False),
                    next_run_utc=self._next_run_utc(job),
                )
            )
```

```python
            connection.execute(
                self.jobs.update()
                .where(self.jobs.c.id == job.job_id)
                .values(
                    job_json=json.dumps(job.to_dict(), ensure_ascii=False),
                    next_run_utc=self._next_run_utc(job),
                )
            )
```

`get_due`/`get_next_run_time` 改为列查询：

```python
    def get_due(self, now: datetime) -> list[Job]:
        self._ensure()
        now_utc = now.astimezone(UTC).isoformat()
        with self._engine.connect() as connection:
            raw_rows = connection.execute(
                sa.select(self.jobs.c.job_json)
                .where(
                    self.jobs.c.next_run_utc.is_not(None),
                    self.jobs.c.next_run_utc <= now_utc,
                )
                .order_by(self.jobs.c.next_run_utc)
            ).scalars().all()
        return [Job.from_dict(json.loads(raw)) for raw in raw_rows]

    def get_next_run_time(self) -> datetime | None:
        self._ensure()
        with self._engine.connect() as connection:
            raw = connection.execute(
                sa.select(self.jobs.c.next_run_utc)
                .where(self.jobs.c.next_run_utc.is_not(None))
                .order_by(self.jobs.c.next_run_utc)
                .limit(1)
            ).scalar_one_or_none()
        return datetime.fromisoformat(raw) if raw is not None else None
```

`_ensure()` 现在会在 `add/update/get_*` 前执行；由于 `_load_all` 也调用 `_ensure`，注意 `_backfill_next_run_utc` 使用 `sa.select(self.jobs.c...)` 时不能再次触发 `_ensure`（不会递归，因为它直接用 engine）。

- [ ] **Step 4: 全量运行并修复**

```bash
python -m pytest tests/core/test_stores.py::TestSQLAlchemyJobStore -q
ruff check src/schedflow/core/stores/sqlalchemy.py
```

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/stores/sqlalchemy.py tests/core/test_stores.py
git commit -m "feat(stores): indexed next-run lookup for SQLAlchemyJobStore"
```

---

### Task 3: MongoDB 到期字段与索引

**Files:**
- Modify: `src/schedflow/core/stores/mongo.py`
- Test: `tests/core/test_stores.py`

- [ ] **Step 1: 写失败测试（追加到 `tests/core/test_stores.py`）**

```python
    def test_get_due_uses_indexed_utc_field(self):
        store = MongoDBJobStore(
            host="localhost", port=27017, database="schedflow_test"
        )
        try:
            now = datetime.now(UTC)
            past = make_job("mongo-past")
            past.next_run_time = now - timedelta(seconds=1)
            store.add(past)
            store.get_due(now)
            indexes = store._collection.index_information()
            assert any("next_run_utc" in key[0] for key in indexes.values())
        finally:
            store.close()
```

（Mongo 服务不可用时该测试自动跳过，与现有 skipif 相同；先运行确认失败：索引名断言失败。）

- [ ] **Step 2: 修改 `src/schedflow/core/stores/mongo.py`**

`from datetime import UTC, datetime`；`__init__` 末尾增加惰性索引标记：

```python
        self._indexes_ensured = False
```

类中新增索引确保方法：

```python
    def _ensure_indexes(self) -> None:
        if self._indexes_ensured:
            return
        self._collection.create_index("next_run_utc", background=True)
        self._indexes_ensured = True
```

新增静态方法与回填：

```python
    @staticmethod
    def _next_run_utc(job: Job) -> str | None:
        if job.next_run_time is None:
            return None
        return job.next_run_time.astimezone(UTC).isoformat()

    def _backfill_next_run_utc(self) -> None:
        missing = self._collection.find({"next_run_utc": {"$exists": False}})
        for document in missing:
            job = Job.from_dict(json.loads(document["job_json"]))
            self._collection.update_one(
                {"_id": job.job_id},
                {"$set": {"next_run_utc": self._next_run_utc(job)}},
            )
```

写入时带上字段：

```python
            self._collection.insert_one(
                {
                    "_id": job.job_id,
                    "job_json": json.dumps(job.to_dict(), ensure_ascii=False),
                    "next_run_utc": self._next_run_utc(job),
                }
            )
```

```python
        result = self._collection.update_one(
            {"_id": job.job_id},
            {
                "$set": {
                    "job_json": json.dumps(job.to_dict(), ensure_ascii=False),
                    "next_run_utc": self._next_run_utc(job),
                }
            },
        )
```

`get_due`/`get_next_run_time` 改为字段查询（查询前先 `_backfill_next_run_utc()` 兼容旧文档）：

```python
    def get_due(self, now: datetime) -> list[Job]:
        self._ensure_indexes()
        self._backfill_next_run_utc()
        now_utc = now.astimezone(UTC).isoformat()
        documents = (
            self._collection.find({"next_run_utc": {"$lte": now_utc}})
            .sort("next_run_utc", 1)
        )
        return [
            Job.from_dict(json.loads(document["job_json"]))
            for document in documents
        ]

    def get_next_run_time(self) -> datetime | None:
        self._ensure_indexes()
        self._backfill_next_run_utc()
        document = self._collection.find_one(
            {"next_run_utc": {"$exists": True, "$ne": None}},
            sort=[("next_run_utc", 1)],
        )
        if document is None:
            return None
        return datetime.fromisoformat(document["next_run_utc"])
```

- [ ] **Step 3: 运行（Mongo 可用时）**

```bash
python -m pytest tests/core/test_stores.py::TestMongoDBJobStore -q
```

Mongo 不可用时显示 skip，允许通过。

- [ ] **Step 4: 提交**

```bash
git add src/schedflow/core/stores/mongo.py tests/core/test_stores.py
git commit -m "feat(stores): indexed next-run lookup for MongoDBJobStore"
```

---

### Task 4: Redis 等价测试（实现已满足，无需改动）

**Files:**
- Test: `tests/core/test_stores.py`

- [ ] **Step 1: 追加测试（`TestRedisJobStore`）**

```python
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
            assert store.get_next_run_time() == future.next_run_time
        finally:
            store.close()
```

- [ ] **Step 2: 运行**

```bash
python -m pytest tests/core/test_stores.py::TestRedisJobStore -q
```

预期：无 redis-server 时 skip；有服务时全绿。

- [ ] **Step 3: 提交**

```bash
git add tests/core/test_stores.py
git commit -m "test(stores): cover Redis due lookup semantics"
```

---

### Task 5: Job `priority`/`completed` 与状态/事件扩展

**Files:**
- Modify: `src/schedflow/core/job.py`
- Modify: `src/schedflow/core/log.py`
- Modify: `src/schedflow/core/events.py`
- Test: `tests/core/test_job.py`、`tests/core/test_log.py`、`tests/core/test_events.py`

- [ ] **Step 1: 写失败测试**

`tests/core/test_job.py` 追加：

```python
def test_job_priority_default_and_roundtrip():
    from schedflow.core.job import Job
    from schedflow.core.workflow import Workflow

    wf = Workflow("wf")
    wf.add_task("a", func=lambda: 1)
    job = Job(wf, None, job_id="p1")
    assert job.priority == 0

    high = Job(wf, None, job_id="p2", priority=5)
    restored = Job.from_dict(high.to_dict())
    assert restored.priority == 5


def test_job_completed_status_roundtrip():
    from schedflow.core.job import Job
    from schedflow.core.workflow import Workflow

    wf = Workflow("wf")
    wf.add_task("a", func=lambda: 1)
    job = Job(wf, None, job_id="c1")
    job.status = "completed"
    restored = Job.from_dict(job.to_dict())
    assert restored.status == "completed"
```

`tests/core/test_log.py` 追加：

```python
def test_cancelled_record_and_log_flag():
    from schedflow.core.log import ExecutionLog, TaskRecord

    record = TaskRecord(node_id="a", task_id="a")
    record.mark_cancelled("job_cancelled")
    assert record.status == "cancelled"
    assert record.skip_reason == "job_cancelled"

    log = ExecutionLog(flow_id="wf")
    log.records["a"] = record
    log.records["b"] = TaskRecord(
        node_id="b", task_id="b", status="succeeded"
    )
    assert log.cancelled is True
    assert log.succeeded is False
```

`tests/core/test_events.py` 追加：

```python
def test_new_event_kinds_accepted():
    from schedflow.core.events import SchedulerEvent

    for kind in ("job.completed", "job.cancelled", "scheduler.error", "task.cancelled"):
        event = SchedulerEvent(kind, job_id="j1")
        assert event.kind == kind
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_job.py tests/core/test_log.py tests/core/test_events.py -q
```

- [ ] **Step 3: 实现**

`core/job.py`：

```python
        max_instances: int = 1,
        priority: int = 0,
    ) -> None:
        ...
        self.max_instances = max(1, int(max_instances))
        self.priority = max(0, int(priority))
```

`to_dict()` 增加 `"priority": self.priority`；`from_dict` 构造时传
`priority=data.get("priority", 0)`。

`core/log.py`：

```python
TaskStatus = (
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
    "cancelled",
)
```

`TaskRecord` 增加方法：

```python
    def mark_cancelled(self, reason: str = "") -> None:
        self.status = "cancelled"
        self.skip_reason = reason
```

`ExecutionLog.succeeded` 与新增属性：

```python
    @property
    def succeeded(self) -> bool:
        """True when no node failed or was cancelled."""
        return all(
            record.status not in ("failed", "cancelled")
            for record in self.records.values()
        )

    @property
    def cancelled(self) -> bool:
        return any(
            record.status == "cancelled"
            for record in self.records.values()
        )
```

`core/events.py`：`EVENT_KINDS` 增加四个 kind。

- [ ] **Step 4: 运行确认通过**

```bash
python -m pytest tests/core/test_job.py tests/core/test_log.py tests/core/test_events.py -q
ruff check src/schedflow/core
```

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/job.py src/schedflow/core/log.py src/schedflow/core/events.py tests/core/test_job.py tests/core/test_log.py tests/core/test_events.py
git commit -m "feat(core): job priority, completed status and cancelled records"
```

---

### Task 6: Workflow 协作式取消

**Files:**
- Modify: `src/schedflow/core/workflow.py`
- Test: `tests/core/test_workflow.py`

- [ ] **Step 1: 写失败测试**

```python
import threading


def test_run_cancel_stops_after_generation_boundary():
    wf = Workflow("cancel")
    entered = threading.Event()
    release = threading.Event()

    def blocker():
        entered.set()
        release.wait(2)
        return "ok"

    wf.add_task("slow", func=blocker)
    wf.add_task("later", func=lambda: 1)
    wf.add_edge("slow", "later")
    cancel_event = threading.Event()

    def cancel_soon():
        entered.wait(2)
        cancel_event.set()

    canceller = threading.Thread(target=cancel_soon)
    canceller.start()
    try:
        log = wf.run(max_workers=1, cancel_event=cancel_event)
    finally:
        release.set()
        canceller.join(2)

    assert log.records["slow"].status == "succeeded"
    assert log.records["later"].status == "cancelled"
    assert log.cancelled is True
    assert log.succeeded is False


def test_run_cancel_event_set_before_start_marks_all_cancelled():
    wf = Workflow("cancel-all")
    wf.add_task("a", func=lambda: 1)
    wf.add_task("b", func=lambda: 2)
    wf.add_edge("a", "b")

    event = threading.Event()
    event.set()
    log = wf.run(cancel_event=event)

    assert log.cancelled is True
    assert all(
        record.status == "cancelled"
        for record in log.records.values()
    )
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_workflow.py -k "cancel" -q
```

- [ ] **Step 3: 实现（`core/workflow.py`）**

`run()` 签名增加参数并把取消检查放在每层执行前后：

```python
    def run(
        self,
        *,
        max_workers: int = 3,
        executor: str = "thread",
        inputs: dict | None = None,
        cancel_event=None,
    ) -> ExecutionLog:
        ...
        for generation in self._generations():
            if cancel_event is not None and cancel_event.is_set():
                self._mark_pending_cancelled(log)
                break
            self._execute_generation(
                generation,
                log=log,
                max_workers=max_workers,
                inputs=inputs or {},
                cancel_event=cancel_event,
            )
            if cancel_event is not None and cancel_event.is_set():
                self._mark_pending_cancelled(log)
                break
        log.finalize()
        return log
```

新增辅助方法：

```python
    def _mark_pending_cancelled(self, log: ExecutionLog) -> None:
        for record in log.records.values():
            if record.status == "pending":
                record.mark_cancelled("job_cancelled")
```

`_execute_generation` 增加 `cancel_event` 参数，并在提交节点前检查：

```python
            for node_id in generation:
                if cancel_event is not None and cancel_event.is_set():
                    log.records[node_id].mark_cancelled("job_cancelled")
                    continue
                if not self._check_preconditions(node_id, log):
                    ...
```

- [ ] **Step 4: 运行确认通过**

```bash
python -m pytest tests/core/test_workflow.py -q
```

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/workflow.py tests/core/test_workflow.py
git commit -m "feat(core): cooperative cancellation in Workflow.run"
```

---

### Task 7: Executor/Job 取消传递

**Files:**
- Modify: `src/schedflow/core/job.py`
- Modify: `src/schedflow/core/executor.py`
- Test: `tests/core/test_executor.py`

- [ ] **Step 1: 写失败测试（`tests/core/test_executor.py`）**

```python
import threading


def test_threadpool_executor_passes_cancel_event_to_job_run():
    from schedflow.core.executor import ThreadPoolExecutor
    from schedflow.core.workflow import Workflow
    from schedflow.core.job import Job

    wf = Workflow("cancel-exec")
    wf.add_task("a", func=lambda: "ok")
    job = Job(wf, None, job_id="j-cancel")
    event = threading.Event()
    executor = ThreadPoolExecutor(max_workers=1)
    executor.start(_CancelSchedulerStub())
    try:
        # Job.run 会把 cancel_event 透传给 Workflow.run，此处验证可调用且不回归。
        log = job.run(cancel_event=event)
        assert log.succeeded
    finally:
        executor.shutdown()
```

- [ ] **Step 2: 修改 `src/schedflow/core/job.py`**

```python
    def run(
        self,
        *,
        max_workers: int = 3,
        executor: str = "thread",
        cancel_event=None,
    ) -> ExecutionLog:
        log = self.workflow.run(
            max_workers=max_workers,
            executor=executor,
            cancel_event=cancel_event,
        )
        log.job_id = self.job_id
        return log
```

- [ ] **Step 3: 修改 `src/schedflow/core/executor.py`**

`DebugExecutor.submit` 与 `ThreadPoolExecutor` 在调用 `job.run` 时从 scheduler 取取消事件：

```python
class DebugExecutor(Executor):
    def submit(self, job: Job, run_time: datetime) -> None:
        try:
            log = job.run(cancel_event=self._cancel_event(job))
        ...
```

`ThreadPoolExecutor`：

```python
    def submit(self, job: Job, run_time: datetime) -> None:
        future = self._pool.submit(
            job.run,
            cancel_event=self._cancel_event(job),
        )
```

两个执行器共享的 `_cancel_event` 辅助方法放在 `Executor` 基类（去掉上面的重复定义）：

```python
class Executor(ABC):
    ...
    def _cancel_event(self, job: Job):
        scheduler = getattr(self, "_scheduler", None)
        if scheduler is None:
            return None
        return scheduler._cancel_event_for(job.job_id)
```

`ProcessPoolExecutor` 与异步执行器不改（子进程/事件循环无法共享 `threading.Event`；文档注明取消仅对 Debug/ThreadPool 生效）。

- [ ] **Step 4: 运行**

```bash
python -m pytest tests/core/test_executor.py tests/core/test_scheduler.py -q
ruff check src/schedflow/core
```

预期：`Scheduler` 尚无 `_cancel_event_for`，直接运行会失败——先补一个占位实现会让本任务测试变假绿。正确顺序：本任务只改 Job/Executor，测试中使用的 scheduler stub 需要提供该方法。

在测试文件顶部加一个桩：

```python
class _CancelSchedulerStub:
    def _cancel_event_for(self, job_id):
        return None
```

并把 `executor.start(_CancelSchedulerStub())` 用于上述测试。

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/job.py src/schedflow/core/executor.py tests/core/test_executor.py
git commit -m "feat(core): plumb cancel event through Job and thread executors"
```

---

### Task 8: DispatchQueue（优先级/有界/取消）

**Files:**
- Create: `src/schedflow/core/dispatch.py`
- Test: `tests/core/test_dispatch.py`

- [ ] **Step 1: 写失败测试（新增 `tests/core/test_dispatch.py`）**

```python
"""DispatchQueue tests."""

import time
from datetime import UTC, datetime

from schedflow.core.dispatch import DispatchQueue
from schedflow.core.job import Job
from schedflow.core.workflow import Workflow


def make_job(job_id: str, priority: int = 0) -> Job:
    wf = Workflow(f"wf-{job_id}")
    wf.add_task("a", func=lambda: 1)
    return Job(wf, None, job_id=job_id, priority=priority)


def test_priority_order_and_fifo_tie():
    queue = DispatchQueue(capacity=10)
    now = datetime.now(UTC)
    assert queue.put(make_job("low", priority=10), now) is True
    assert queue.put(make_job("high", priority=1), now) is True
    assert queue.put(make_job("first-tie", priority=1), now) is True
    assert queue.put(make_job("second-tie", priority=1), now) is True

    popped = [queue.get(timeout=0.2) for _ in range(4)]
    assert [item[0].job_id for item in popped] == [
        "high",
        "first-tie",
        "second-tie",
        "low",
    ]


def test_cancel_removes_queued_job():
    queue = DispatchQueue(capacity=10)
    now = datetime.now(UTC)
    queue.put(make_job("j1"), now)
    assert queue.cancel("j1") is True
    assert queue.get(timeout=0.1) is None


def test_duplicate_and_full_queue():
    queue = DispatchQueue(capacity=1)
    now = datetime.now(UTC)
    assert queue.put(make_job("j1"), now) is True
    assert queue.put(make_job("j1"), now) is False
    assert queue.put(make_job("j2"), now) is False
    assert queue.size() == 1
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_dispatch.py -q
```

预期：`ModuleNotFoundError: schedflow.core.dispatch`。

- [ ] **Step 3: 新增 `src/schedflow/core/dispatch.py`**

```python
"""Bounded priority dispatch queue between the scheduler loop and executors."""

from __future__ import annotations

import heapq
import itertools
import threading
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schedflow.core.job import Job


class DispatchQueue:
    """Thread-safe bounded queue ordered by ``(priority, enqueue_seq)``."""

    def __init__(self, capacity: int = 10_000) -> None:
        self._capacity = max(1, int(capacity))
        self._heap: list[tuple] = []
        self._queued: dict[str, object] = {}
        self._cancelled: set[str] = set()
        self._cond = threading.Condition()
        self._counter = itertools.count()

    def put(self, job: Job, run_time: datetime) -> bool:
        with self._cond:
            if job.job_id in self._queued or len(self._queued) >= self._capacity:
                return False
            entry = (
                int(job.priority),
                next(self._counter),
                job.job_id,
                run_time,
                job,
            )
            heapq.heappush(self._heap, entry)
            self._queued[job.job_id] = entry
            self._cond.notify()
            return True

    def get(self, timeout: float | None = None) -> tuple[Job, datetime] | None:
        with self._cond:
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                while self._heap:
                    priority, seq, job_id, run_time, job = heapq.heappop(
                        self._heap
                    )
                    if job_id in self._cancelled:
                        self._queued.pop(job_id, None)
                        self._cancelled.discard(job_id)
                        continue
                    self._queued.pop(job_id, None)
                    return job, run_time
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                self._cond.wait(remaining)

    def cancel(self, job_id: str) -> bool:
        with self._cond:
            if job_id not in self._queued:
                return False
            self._cancelled.add(job_id)
            self._cond.notify()
            return True

    def has(self, job_id: str) -> bool:
        with self._cond:
            return job_id in self._queued

    def size(self) -> int:
        with self._cond:
            return len(self._queued)

    def wakeup(self) -> None:
        with self._cond:
            self._cond.notify_all()
```

- [ ] **Step 4: 运行确认通过**

```bash
python -m pytest tests/core/test_dispatch.py -q
ruff check src/schedflow/core/dispatch.py
```

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/dispatch.py tests/core/test_dispatch.py
git commit -m "feat(core): add bounded priority dispatch queue"
```

---

### Task 9: Scheduler 派发队列 / cancel_job / 事件接入

**Files:**
- Modify: `src/schedflow/core/scheduler.py`
- Test: `tests/core/test_scheduler.py`

- [ ] **Step 1: 写失败测试**

```python
def test_cancel_queued_job_does_not_run():
    scheduler = make_scheduler()
    seen = []
    scheduler.on("job.cancelled", seen.append)
    scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1"
    )
    scheduler._advance(scheduler.get_job("j1"), scheduler.get_job("j1").next_run_time, datetime.now(UTC))
    scheduler._running["j1"] = 1
    assert scheduler._dispatch_queue.put(scheduler.get_job("j1"), datetime.now(UTC)) is True

    scheduler.cancel_job("j1")

    assert scheduler.get_job("j1") is not None
    assert "j1" not in scheduler._running
    assert seen and seen[0].kind == "job.cancelled"


def test_cancel_running_job_marks_cancel_event():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), job_id="j1")
    scheduler._running["j1"] = 1

    scheduler.cancel_job("j1")

    assert scheduler._cancel_events["j1"].is_set()
```

同时把 `make_scheduler()` 的 executor 换成 `DebugExecutor` 的现有测试继续保留。

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_scheduler.py -k "cancel" -q
```

预期：`AttributeError: Scheduler has no _dispatch_queue`。

- [ ] **Step 3: 修改 `src/schedflow/core/scheduler.py`**

import 与 `Scheduler.__init__`（签名增加 `dispatch_capacity`，默认 10_000）：

```python
from schedflow.core.dispatch import DispatchQueue

        self._lock = threading.RLock()
        self._dispatch_lock = threading.RLock()
        self._running: dict[str, int] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._dispatch_queue = DispatchQueue(capacity=dispatch_capacity)
        self._dispatcher: threading.Thread | None = None
        self._error_event_logged_at: dict[str, float] = {}
```

公开方法（放在 `job management` 区域）：

```python
    def cancel_job(self, job_id: str) -> Job:
        with self._lock:
            job = self._find_job(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
        with self._dispatch_lock:
            if self._dispatch_queue.cancel(job_id):
                count = self._running.get(job_id, 1) - 1
                if count <= 0:
                    self._running.pop(job_id, None)
                else:
                    self._running[job_id] = count
                self._events.publish(
                    SchedulerEvent("job.cancelled", job_id=job_id)
                )
                return job
            if job_id in self._running:
                self._cancel_events.setdefault(
                    job_id, threading.Event()
                ).set()
                return job
        raise ValueError(f"Job {job_id!r} is not queued or running")

    def _cancel_event_for(self, job_id: str) -> threading.Event | None:
        with self._dispatch_lock:
            return self._cancel_events.get(job_id)
```

`start()` 启动派发线程：

```python
        self._dispatcher = threading.Thread(
            target=self._dispatch_loop,
            name="schedflow-dispatch",
            daemon=True,
        )
        self._dispatcher.start()
```

`shutdown()` 中唤醒并 join 派发线程：

```python
        self._dispatch_queue.wakeup()
        if self._dispatcher is not None:
            self._dispatcher.join(timeout=10 if wait else 0)
```

新增派发循环与内部方法：

```python
    def _dispatch_loop(self) -> None:
        while not self._stop_event.is_set():
            item = self._dispatch_queue.get(timeout=0.5)
            if item is None:
                continue
            job, run_time = item
            with self._dispatch_lock:
                cancel_event = self._cancel_events.get(job.job_id)
                if cancel_event is not None and cancel_event.is_set():
                    count = self._running.get(job.job_id, 1) - 1
                    if count <= 0:
                        self._running.pop(job.job_id, None)
                        self._cancel_events.pop(job.job_id, None)
                    else:
                        self._running[job.job_id] = count
                    self._events.publish(
                        SchedulerEvent("job.cancelled", job_id=job.job_id)
                    )
                    continue
            self._events.publish(
                SchedulerEvent(
                    "job.started", job_id=job.job_id, run_time=run_time
                )
            )
            executor = self._executors.get(
                job.executor_alias, self._executor
            )
            executor.submit(job, run_time)
```

`_run_due_job` 改为入队：

```python
    def _run_due_job(self, job: Job, now: datetime) -> None:
        run_time = job.next_run_time
        if (
            job.misfire_grace_time is not None
            and (now - run_time).total_seconds() > job.misfire_grace_time
        ):
            self._events.publish(
                SchedulerEvent("job.missed", job_id=job.job_id, run_time=run_time)
            )
            self._advance(job, run_time, now)
            return
        self._advance(job, run_time, now)
        with self._dispatch_lock:
            count = self._running.get(job.job_id, 0)
            if count >= job.max_instances:
                self._events.publish(
                    SchedulerEvent(
                        "job.max_instances",
                        job_id=job.job_id,
                        run_time=run_time,
                    )
                )
                return
            if not self._dispatch_queue.put(job, run_time):
                self._publish_error(
                    RuntimeError(
                        f"dispatch queue full for job {job.job_id!r}"
                    )
                )
                return
            self._running[job.job_id] = count + 1
```

注意 `_advance` 在原实现里位于 `job.started` 发布之前，顺序不变；`job.started` 现在由派发线程发布。

`_on_job_finished` 的收尾改为在 `_dispatch_lock` 内更新并清理取消事件，结果事件按状态分流：

```python
    def _on_job_finished(
        self,
        job: Job,
        run_time: datetime,
        log: ExecutionLog | None,
        error: Exception | None = None,
    ) -> None:
        with self._dispatch_lock:
            count = self._running.get(job.job_id, 1) - 1
            if count <= 0:
                self._running.pop(job.job_id, None)
                self._cancel_events.pop(job.job_id, None)
            else:
                self._running[job.job_id] = count
        if log is not None:
            ...  # 原 add_log 与 task events 逻辑不变
            if log.cancelled:
                kind = "job.cancelled"
            elif log.succeeded:
                kind = "job.succeeded"
            else:
                kind = "job.failed"
            self._events.publish(
                SchedulerEvent(kind, job_id=job.job_id, run_time=run_time, log=log)
            )
        elif error is not None:
            ...  # 原 failed log 逻辑不变
```

`_publish_task_events` 增加 cancelled 分支：

```python
            elif record.status == "cancelled":
                kind = "task.cancelled"
```

注意：`cancel_job` 测试直接操作 `_dispatch_queue.put` 时，需要先保证 scheduler 有该属性；按 Task 9 Step 3 实现后属性存在。

- [ ] **Step 4: 运行**

```bash
python -m pytest tests/core/test_scheduler.py tests/core/test_executor.py -q
```

若有既有测试依赖“job.started 在 `_run_due_job` 内发布”，同步调整断言到派发后。

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/scheduler.py tests/core/test_scheduler.py
git commit -m "feat(core): dispatch queue integration and cancel_job"
```

---

### Task 10: 一次性任务保留停用（completed）

**Files:**
- Modify: `src/schedflow/core/scheduler.py`
- Test: `tests/core/test_scheduler.py`

- [ ] **Step 1: 写失败测试**

```python
def test_one_shot_job_kept_as_completed_after_final_run():
    scheduler = make_scheduler()
    seen = []
    scheduler.on("job.completed", seen.append)
    scheduler.add_job(
        make_workflow(), trigger=StaticTrigger(datetime.now(UTC)), job_id="j1"
    )
    job = scheduler.get_job("j1")
    now = datetime.now(UTC)

    scheduler._advance(job, job.next_run_time, now)

    stored = scheduler.get_job("j1")
    assert stored is not None
    assert stored.status == "completed"
    assert stored.next_run_time is None
    assert seen and seen[0].kind == "job.completed"


def test_resume_job_keeps_completed_when_trigger_exhausted():
    scheduler = make_scheduler()
    scheduler.add_job(
        make_workflow(), trigger=StaticTrigger(datetime.now(UTC)), job_id="j1"
    )
    job = scheduler.get_job("j1")
    scheduler._advance(job, job.next_run_time, datetime.now(UTC))

    scheduler.resume_job("j1")

    assert scheduler.get_job("j1").status == "completed"
    assert scheduler.get_job("j1").next_run_time is None
```

`StaticTrigger` 已存在于测试文件顶部。

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/core/test_scheduler.py -k "one_shot or resume_job" -q
```

预期：第一个用例失败（job 被删除），第二个用例失败（状态被改回 running）。

- [ ] **Step 3: 修改 `_advance` 与 `resume_job`**

`_advance` 中 `next_run is None` 分支：

```python
            if next_run is None:
                job.status = "completed"
                job.next_run_time = None
                try:
                    store.update(job)
                except JobNotFoundError:
                    return
                self._events.publish(
                    SchedulerEvent("job.completed", job_id=job.job_id)
                )
                return
```

`resume_job`：

```python
            if job.status == "completed":
                next_run = (
                    job.trigger.get_next_fire_time(
                        None, datetime.now(self._timezone)
                    )
                    if job.trigger is not None
                    else None
                )
                if next_run is None:
                    store.update(job)
                    self._events.publish(
                        SchedulerEvent("job.resumed", job_id=job.job_id)
                    )
                    return job
                job.status = "running"
                job.next_run_time = next_run
            else:
                job.status = "running"
                job.next_run_time = (
                    job.trigger.get_next_fire_time(
                        None, datetime.now(self._timezone)
                    )
                    if job.trigger is not None
                    else None
                )
```

`update_job` 的 trigger 分支增加“completed 显式换触发器后恢复 running”：

```python
            if trigger is not None:
                ...
                job.trigger = trigger
                job.next_run_time = trigger.get_next_fire_time(
                    None, datetime.now(self._timezone)
                )
                if job.status == "completed":
                    job.status = "running"
```

- [ ] **Step 4: 运行**

```bash
python -m pytest tests/core/test_scheduler.py -q
ruff check src/schedflow/core/scheduler.py
```

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/scheduler.py tests/core/test_scheduler.py
git commit -m "feat(core): keep one-shot jobs as completed instead of removing"
```

---

### Task 11: 错误可见化（主循环与 listener）

**Files:**
- Modify: `src/schedflow/core/scheduler.py`
- Modify: `src/schedflow/core/events.py`
- Test: `tests/core/test_scheduler.py`、`tests/core/test_events.py`

- [ ] **Step 1: 写失败测试**

`tests/core/test_events.py`：

```python
def test_listener_exception_is_logged_not_silent(caplog):
    import logging

    bus = EventBus()

    def broken(event):
        raise RuntimeError("listener boom")

    bus.subscribe("job.added", broken)
    with caplog.at_level(logging.ERROR):
        bus.publish(SchedulerEvent("job.added", job_id="j1"))

    assert "listener boom" in caplog.text
    assert "listener" in caplog.text
```

`tests/core/test_scheduler.py`：

```python
def test_loop_error_publishes_scheduler_error_event():
    scheduler = make_scheduler()
    seen = []
    scheduler.on("scheduler.error", seen.append)

    def broken_store():
        raise RuntimeError("loop boom")

    original = scheduler._process_due
    scheduler._process_due = broken_store
    try:
        scheduler._main_loop_iteration_for_test()
    finally:
        scheduler._process_due = original

    assert seen
    assert "loop boom" in seen[0].detail["message"]
```

为便于测试，把主循环单轮抽成 `_main_loop_iteration_for_test()`：

```python
    def _main_loop_iteration_for_test(self) -> None:
        if self.state == STATE_RUNNING:
            try:
                self._process_due()
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("scheduler loop error")
                self._publish_error(exc)
```

`_main_loop` 调用该方法。

- [ ] **Step 2: 实现**

`events.py` 顶部：

```python
import logging

logger = logging.getLogger(__name__)
```

`SchedulerEvent.__slots__` 增加 `"detail"`，`__init__` 增加参数：

```python
    __slots__ = ("detail", "job_id", "kind", "log", "record", "run_time")

    def __init__(self, kind, *, job_id=None, run_time=None, log=None, record=None, detail=None):
        ...
        self.detail = detail
```

`EventBus.publish` 的 except 分支：

```python
            except Exception:  # noqa: BLE001 - listener errors are isolated
                listener = (
                    getattr(callback, "__qualname__", None)
                    or getattr(callback, "__name__", None)
                    or repr(callback)
                )
                logger.exception(
                    "event listener error kind=%s listener=%s",
                    event.kind,
                    listener,
                )
```

`scheduler.py` 顶部 `import logging` 与模块 logger：

```python
import logging

LOGGER = logging.getLogger(__name__)
```

`_publish_error` 与节流：

```python
    def _publish_error(self, error: Exception, key: str = "default") -> None:
        import time

        now = time.monotonic()
        last = self._error_event_logged_at.get(key, 0.0)
        if now - last < 60:
            return
        self._error_event_logged_at[key] = now
        self._events.publish(
            SchedulerEvent(
                "scheduler.error",
                detail={
                    "error_type": type(error).__name__,
                    "message": str(error),
                },
            )
        )
```

- [ ] **Step 3: 运行**

```bash
python -m pytest tests/core/test_events.py tests/core/test_scheduler.py -q
ruff check src/schedflow/core
```

预期：测试需配合 `scheduler.state = STATE_RUNNING`（`make_scheduler()` 默认 STOPPED，单轮方法测试时手动置 RUNNING 或在测试开头设置）。

- [ ] **Step 4: 提交**

```bash
git add src/schedflow/core/events.py src/schedflow/core/scheduler.py tests/core/test_events.py tests/core/test_scheduler.py
git commit -m "feat(core): surface scheduler and event listener errors"
```

---

### Task 12: 锁拆分与并发测试

**Files:**
- Modify: `src/schedflow/core/scheduler.py`
- Test: `tests/core/test_scheduler.py`

- [ ] **Step 1: 写并发测试**

```python
import threading


def test_concurrent_add_and_cancel_no_deadlock():
    scheduler = Scheduler(
        jobstore=MemoryJobStore(),
        executor=DebugExecutor(),
    )
    errors = []

    def add_jobs():
        try:
            for index in range(50):
                scheduler.add_job(
                    make_workflow(),
                    trigger=IntervalTrigger(seconds=3600),
                    job_id=f"j{index}",
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def cancel_missing():
        try:
            for _ in range(50):
                try:
                    scheduler.cancel_job("missing")
                except ValueError:
                    pass
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=add_jobs),
        threading.Thread(target=cancel_missing),
        threading.Thread(target=add_jobs),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert errors == []
    assert len(scheduler.get_jobs()) == 50
```

先补一个 `cancel_job` 未找到/未运行时的行为：未找到抛 `JobNotFoundError`，存在但未运行抛 `ValueError`。

- [ ] **Step 2: 实现锁拆分（合并进 Task 9/10 已引入的 `_dispatch_lock`）**

检查并确保以下顺序注释写进代码：

```python
# Lock ordering: always acquire self._lock (job registry) before
# self._dispatch_lock (queue/running/cancel). Never reverse this order.
```

对仍持有 `self._lock` 的 `_main_loop` 休眠计算，改为只在需要时持有：

```python
            with self._dispatch_lock:
                next_run = None
                for jobstore in self._jobstores.values():
                    candidate = jobstore.get_next_run_time()
                    if candidate is not None and (
                        next_run is None or candidate < next_run
                    ):
                        next_run = candidate
```

`_process_due` 不再持有 `_lock` 扫描（JobStore 本身线程安全；跨 store 列表拼接的竞态由 `_dispatch_lock` 内 put 时的去重兜底）：

```python
    def _process_due(self) -> None:
        now = datetime.now(self._timezone)
        due = []
        for jobstore in self._jobstores.values():
            due.extend(jobstore.get_due(now))
        for job in due:
            self._run_due_job(job, now)
```

- [ ] **Step 3: 运行**

```bash
python -m pytest tests/core/test_scheduler.py -q
python -m pytest tests/test_api_rest/test_api_rest.py -q
```

- [ ] **Step 4: 提交**

```bash
git add src/schedflow/core/scheduler.py tests/core/test_scheduler.py
git commit -m "refactor(core): split scheduler management and dispatch locks"
```

---

### Task 13: REST API 同步（priority/completed/cancel）

**Files:**
- Modify: `src/schedflow/api/rest/schemas.py`
- Modify: `src/schedflow/api/rest/routers.py`
- Modify: `src/schedflow/core/scheduler.py`（`update_job` 支持 priority）
- Test: `tests/test_api_rest/test_api_rest.py`、`tests/test_api_rest/test_frontend_parity.py`

- [ ] **Step 1: 写 API 失败测试（`tests/test_api_rest/test_api_rest.py`）**

```python
def test_create_job_with_priority_and_cancel_queued():
    from fastapi.testclient import TestClient
    from schedflow.api import create_app
    from schedflow.core import Scheduler

    app = create_app(Scheduler(), include_auth=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        payload = {
            "workflow": {
                "flow_id": "api-cancel",
                "nodes": [
                    {
                        "node_id": "a",
                        "task": {"type": "python_callable", "ref": "os:getcwd"},
                    }
                ],
                "edges": [],
            },
            "trigger": {"type": "interval", "args": {"seconds": 3600}},
            "job_id": "cancel-me",
            "priority": 3,
        }
        created = client.post("/api/jobs", json=payload)
        assert created.status_code == 200, created.text
        assert created.json()["data"]["priority"] == 3

        cancelled = client.post("/api/jobs/cancel-me/cancel")
        assert cancelled.status_code in (200, 409)


def test_completed_status_visible_via_api():
    from fastapi.testclient import TestClient
    from schedflow.api import create_app
    from schedflow.core import Scheduler

    app = create_app(Scheduler(), include_auth=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        scheduler = client.app.state.scheduler
        wf = Workflow("wf")
        wf.add_task("a", func=lambda: 1)
        scheduler.add_job(wf, job_id="done")
        scheduler.get_job("done").status = "completed"
        scheduler.get_job("done").next_run_time = None

        job = client.get("/api/jobs/done").json()["data"]
        assert job["status"] == "completed"
```

需要 `from schedflow.core.workflow import Workflow`。

- [ ] **Step 2: 实现**

`schemas.py`：

```python
class JobCreateRequest(BaseModel):
    ...
    priority: int = Field(default=0, ge=0)


class JobUpdateRequest(BaseModel):
    ...
    priority: int | None = Field(default=None, ge=0)
```

`scheduler.update_job` 增加：

```python
            if priority is not None:
                job.priority = max(0, int(priority))
```

`routers.py`：

```python
from schedflow.core.log import ExecutionLog  # noqa: F401 仅在类型提示需要时
```

`create_job` 传 `priority=request.priority`；`update_job` 的 `changes` 已含 priority 直接传 `scheduler.update_job(..., **changes)`（update_job 签名需加 `priority=None`）。

新增端点：

```python
@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, scheduler=Depends(_get_scheduler)):
    try:
        job = scheduler.cancel_job(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return APIResponse(data=job.to_dict())
```

`api/rest/routers.py` 里 `run_job_now`、`get_job` 等无需改动。

- [ ] **Step 3: 更新前端契约测试**

在 `tests/test_api_rest/test_frontend_parity.py` 的 `_workflow_payload()` 相关 job 创建后断言：

```python
        assert created.json()["data"]["priority"] == 0
```

并为状态白名单加断言：

```python
def test_job_status_values_match_frontend_contract():
    with _client() as client:
        scheduler = client.app.state.scheduler
        wf = Workflow("wf")
        wf.add_task("a", func=lambda: 1)
        scheduler.add_job(wf, job_id="status-job")
        scheduler.get_job("status-job").status = "completed"

        data = client.get("/api/jobs/status-job").json()["data"]
        assert data["status"] in {"running", "paused", "completed"}
```

- [ ] **Step 4: 运行**

```bash
python -m pytest tests/test_api_rest/test_api_rest.py tests/test_api_rest/test_frontend_parity.py -q
ruff check src/schedflow/api
```

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/api/rest/schemas.py src/schedflow/api/rest/routers.py src/schedflow/core/scheduler.py tests/test_api_rest/test_api_rest.py tests/test_api_rest/test_frontend_parity.py
git commit -m "feat(api): priority, completed status and cancel endpoint"
```

---

### Task 14: 前端 P0 同步

**Files:**
- Modify: `frontend/src/types/job.ts`
- Modify: `frontend/src/api/mappers.ts`
- Modify: `frontend/src/api/jobs.ts`
- Modify: `frontend/src/views/jobs/JobForm.vue`
- Modify: `frontend/src/views/jobs/JobList.vue`
- Modify: `frontend/src/views/jobs/JobDetail.vue`
- Modify: `frontend/src/views/logs/ExecutionOutput.vue`（若含状态样式）

- [ ] **Step 1: 类型与 API（先写可被 type-check 捕获的改动）**

`frontend/src/types/job.ts`：

```ts
export type JobStatus = 'RUNNING' | 'PAUSED' | 'COMPLETED'

export interface Job {
  ...
  job_status: JobStatus
  priority?: number
}

export interface JobCreateParams {
  ...
  priority?: number
}

export interface JobUpdateParams {
  ...
  priority?: number
}
```

`frontend/src/api/mappers.ts`：

```ts
export function jobFromApi(job: any): Job {
  ...
  priority: job.priority ?? 0,
  ...
}

export function jobCreatePayload(params: JobCreateParams): any {
  return {
    ...
    priority: params.priority,
  }
}

export function jobUpdatePayload(params: JobUpdateParams): any {
  const result: Record<string, unknown> = {
    ...
    priority: params.priority,
  }
  ...
}
```

`frontend/src/api/jobs.ts`：

```ts
export function cancelJob(id: string): Promise<Job> {
  return (schedulerClient.post(`/jobs/${id}/cancel`) as Promise<any>).then(
    jobFromApi,
  )
}
```

- [ ] **Step 2: 视图改动**

`JobList.vue`：
- 状态 chip 增加 `COMPLETED` 映射（颜色灰/蓝、文案“已完成”）；
- 增加“取消”按钮，仅对未开始/运行中的 job 可用；点击后调用 `cancelJob(id)` 并刷新列表。

`JobForm.vue`：
- 增加“优先级”数字输入（`el-input-number`），绑定 `form.priority`，提交时放入 `JobCreateParams`。

`JobDetail.vue`：
- 展示 `job.priority`；
- 增加取消按钮与错误提示（409 时提示“任务未在运行”）。

`ExecutionOutput.vue`：
- 节点状态样式加入 `CANCELLED`（红色/斜体或与失败区分）。

具体模板代码以仓库现有 Element Plus 写法为准，保证 `npm run type-check` 通过。

- [ ] **Step 3: 验证**

```bash
cd frontend
npm run type-check
npm run build
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src
git commit -m "feat(frontend): priority, completed status and cancel action"
```

---

### Task 15: 文档与变更记录（P0）

**Files:**
- Modify: `docs/user-guide/core-features.zh.md` / `.en.md`
- Modify: `docs/user-guide/dag-workflow.zh.md` / `.en.md`
- Modify: `docs/api-reference/index.zh.md` / `.en.md`
- Modify: `docs/index.zh.md` / `.en.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/changelog.zh.md` / `.en.md`
- Modify: `README.md` / `README_EN.md`（特性清单如有涉及）

- [ ] **Step 1: 补充文档内容（中英一致，示例为中文）**

`core-features.zh.md` 的 Job 管理小节加入：

```markdown
### 优先级与取消

- `Job.priority`（默认 0，越小越先执行）控制到期任务的派发顺序；
- `POST /api/jobs/{id}/cancel` 取消尚未开始的任务；运行中任务在节点边界协作式停止。

### 一次性任务

date 等单次触发器执行后任务不会被删除，而是保持为 `completed` 状态并停止参与调度；
可随时在任务列表中查看历史，或用 `POST /api/jobs/{id}/run` 手动重跑。
```

`dag-workflow.zh.md` 的执行控制小节加入协作式取消与 `cancelled` 节点状态说明。

`api-reference/index.zh.md` 增加 cancel 端点、`priority` 字段、`completed` 状态值。

`index.zh.md` 核心特性表更新：Job 管理行补充“优先级 / 取消 / 单次任务保留”。

`CHANGELOG.md` 与站点 changelog 增加 P0 条目，格式沿用现有版本条目。

- [ ] **Step 2: 全量验证**

```bash
python -m pytest
ruff check .
cd frontend && npm run type-check && npm run build
```

（外部 Redis/Mongo 服务不可用时相关用例自动 skip，属于预期。）

- [ ] **Step 3: 提交**

```bash
git add docs README.md README_EN.md CHANGELOG.md
git commit -m "docs: P0 priority, cancellation and completed job behavior"
```

---

## 完成标准（DoD）

- [ ] `python -m pytest` 全绿（外部服务缺失时仅 skip）
- [ ] `ruff check .` 无告警
- [ ] `frontend` type-check/build 通过
- [ ] `tests/test_api_rest/test_frontend_parity.py` 覆盖新契约
- [ ] P0 文档 zh/en 同步完成，CHANGELOG 更新
- [ ] 每任务独立提交，无混合提交
