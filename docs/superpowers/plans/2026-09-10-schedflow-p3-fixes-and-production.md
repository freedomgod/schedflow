# SchedFlow P3 修复与生产化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复“暂停任务仍被执行”“编辑任务保存 500”“DAG 画布空白”三个缺陷，统一前端组件样式与设置页信息架构，并把生产前端改为 nginx 容器托管。

**Architecture:** 后端把 `Job.status` 提升为唯一可调度真值（写入点收敛为 `_arm`/`_disarm`，四个 JobStore 的到期查询同步过滤，启动时自愈存量数据）；前端把重复的页面级组件样式上移为全局组件层，DAG 布局改用 dagre 0.8.5 的正确入口；生产前端由 `nginx:alpine` 托管构建产物并反代 `/api`。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy/pymongo/redis；Vue 3 + TypeScript + Vite + Element Plus + LogicFlow + dagre；Docker + nginx:alpine。

**设计依据:** `docs/superpowers/specs/2026-09-10-schedflow-p3-fixes-and-production-design.md`

---

## 文件结构

| 文件 | 职责 | 动作 |
|------|------|------|
| `src/schedflow/core/scheduler.py` | 调度状态机与启动自愈 | 修改 |
| `src/schedflow/core/jobstore.py` | Memory store 到期过滤 | 修改 |
| `src/schedflow/core/stores/sqlalchemy.py` | 关系型 store 的 `status` 列与过滤 | 修改 |
| `src/schedflow/core/stores/redis.py` | Redis store 过滤 | 修改 |
| `src/schedflow/core/stores/mongo.py` | MongoDB store 的 `status` 字段与过滤 | 修改 |
| `src/schedflow/api/rest/routers.py` | `PUT /api/jobs/{id}` 修复 | 修改 |
| `src/schedflow/core/webhook.py` | 抽出可复用的单次投递 `deliver_once()` | 修改 |
| `src/schedflow/api/routers/settings.py` | Webhook 测试端点 | 修改 |
| `frontend/src/views/jobs/dagreLayout.ts` | 独立可测的 DAG 布局计算 | 新增 |
| `frontend/src/styles/components.css` | 全局组件层样式 | 新增 |
| `frontend/src/views/settings/ObservabilitySettings.vue` | 集成页（Webhook 可用化） | 重写 |
| `frontend/src/views/settings/SystemSettings.vue` | 新增「API 写限流」标签页 | 修改 |
| `frontend/scripts/clean-dist.mjs` | 构建前清理产物 | 新增 |
| `frontend/nginx.conf.template` | 生产静态托管与 `/api` 反代 | 新增 |
| `Dockerfile`、`docker-compose.yml` | nginx web 服务 | 修改 |
| `tests/core/test_scheduler_pause.py` | 暂停语义回归测试 | 新增 |
| `tests/core/test_jobstore.py`、`tests/core/test_stores.py` | 存储层过滤测试 | 修改 |
| `tests/core/test_webhook.py`、`tests/test_api/test_settings_ops.py` | 投递与测试端点 | 修改 |
| `tests/test_api_rest/test_api_rest.py` | PUT 修复测试 | 修改 |

---

### Task 1: Scheduler 侧 `status` 不变式

**Files:**
- Modify: `src/schedflow/core/scheduler.py`（`update_job` 触发器分支、`pause_job`、`resume_job`、`_advance`）
- Test: `tests/core/test_scheduler_pause.py`

- [ ] **Step 1: 写失败测试**

```python
"""暂停语义回归测试：paused 任务不得被重新武装或执行。"""

from datetime import UTC, datetime, timedelta

from schedflow.core.executor import DebugExecutor
from schedflow.core.jobstore import MemoryJobStore
from schedflow.core.scheduler import Scheduler
from schedflow.core.workflow import Workflow
from schedflow.triggers import IntervalTrigger


def module_fn(value: int = 1) -> int:
    return value


def make_workflow() -> Workflow:
    wf = Workflow("wf")
    wf.add_task("a", func=module_fn)
    return wf


def make_scheduler(store: MemoryJobStore | None = None) -> Scheduler:
    return Scheduler(jobstore=store or MemoryJobStore(), executor=DebugExecutor())


def test_update_job_with_trigger_does_not_wake_paused_job():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1")
    scheduler.pause_job("j1")

    updated = scheduler.update_job("j1", trigger=IntervalTrigger(seconds=30))

    assert updated.status == "paused"
    assert updated.next_run_time is None


def test_reschedule_does_not_wake_paused_job():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1")
    scheduler.pause_job("j1")

    updated = scheduler.reschedule_job("j1", IntervalTrigger(seconds=10))

    assert updated.status == "paused"
    assert updated.next_run_time is None
    assert scheduler.get_job("j1").next_run_time is None


def test_advance_disarms_job_that_is_not_running():
    scheduler = make_scheduler()
    job = scheduler.add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1"
    )
    run_time = job.next_run_time
    scheduler.pause_job("j1")

    scheduler._advance(job, run_time, datetime.now(UTC))

    assert job.status == "paused"
    assert job.next_run_time is None


def test_resume_rearms_paused_job():
    scheduler = make_scheduler()
    scheduler.add_job(make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1")
    scheduler.pause_job("j1")

    resumed = scheduler.resume_job("j1")

    assert resumed.status == "running"
    assert resumed.next_run_time is not None
    assert resumed.next_run_time > datetime.now(UTC) - timedelta(seconds=1)
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_scheduler_pause.py -q`
Expected: `update_job` 与 `reschedule` 两个用例 FAIL（`next_run_time` 非空）。

- [ ] **Step 3: 实现助手并接入写入点**

在 `Scheduler` 内 `pause_job` 之前新增：

```python
    def _disarm(self, job: Job) -> None:
        """Clear the armed schedule; a job without next_run_time is not schedulable."""
        job.next_run_time = None

    def _arm(
        self,
        job: Job,
        now: datetime,
        *,
        previous: datetime | None = None,
    ) -> bool:
        """Arm the job only when it is schedulable.

        Returns True when a next run time was produced. Non-running jobs are
        always disarmed so ``status`` stays the single source of truth.
        """
        if job.status != "running" or job.trigger is None:
            self._disarm(job)
            return False
        job.next_run_time = job.trigger.get_next_fire_time(previous, now)
        return job.next_run_time is not None
```

`update_job` 的触发器分支改为：

```python
            if trigger is not None:
                if not hasattr(trigger, "get_next_fire_time"):
                    raise TypeError(
                        "trigger must provide get_next_fire_time(previous, now)"
                    )
                job.trigger = trigger
                if job.status == "completed":
                    job.status = "running"
                self._arm(job, datetime.now(self._timezone))
```

`pause_job` 中原有的 `job.next_run_time = None` 改为 `self._disarm(job)`；
`resume_job` 中计算 `job.next_run_time` 的表达式改为
`self._arm(job, datetime.now(self._timezone))`。

`_advance` 整体替换为：

```python
    def _advance(self, job: Job, run_time: datetime, now: datetime) -> None:
        store = self._jobstores.get(job.jobstore_alias, self._jobstore)
        if job.status != "running":
            if job.next_run_time is not None:
                self._disarm(job)
                try:
                    store.update(job)
                except JobNotFoundError:
                    return
            return
        if job.trigger is None:
            self._disarm(job)
        else:
            next_run = job.trigger.get_next_fire_time(run_time, now)
            if next_run is None:
                job.status = "completed"
                self._disarm(job)
                try:
                    store.update(job)
                except JobNotFoundError:
                    return
                self._events.publish(
                    SchedulerEvent("job.completed", job_id=job.job_id)
                )
                self._refresh_job_metrics()
                return
            job.next_run_time = next_run
        try:
            store.update(job)
        except JobNotFoundError:
            pass
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_scheduler_pause.py tests/core/test_scheduler.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/scheduler.py tests/core/test_scheduler_pause.py
git commit -m "fix(core): keep paused jobs disarmed in scheduler updates"
```

---

### Task 2: MemoryJobStore 到期过滤

**Files:**
- Modify: `src/schedflow/core/jobstore.py`（`_push_scheduled`、`_clean_heap`）
- Test: `tests/core/test_jobstore.py`

- [ ] **Step 1: 写失败测试**

```python
def test_get_due_ignores_paused_job_with_armed_time():
    store = make_store()
    job = make_job()
    store.add(job)
    job.status = "paused"
    job.next_run_time = datetime.now(UTC) - timedelta(seconds=5)

    assert store.get_due(datetime.now(UTC)) == []
    assert store.get_next_run_time() is None


def test_push_scheduled_skips_non_running_job():
    store = make_store()
    job = make_job()
    job.status = "paused"
    store.add(job)

    assert store.get_next_run_time() is None
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_jobstore.py -q -k "paused or non_running"`
Expected: FAIL（`get_due` 仍返回该任务）。

- [ ] **Step 3: 实现过滤**

`_push_scheduled` 开头增加：

```python
        if job.next_run_time is None or job.status != "running":
            return
```

`_clean_heap` 的有效性判定增加 `and job.status == "running"`：

```python
            if (
                job is not None
                and job.next_run_time is not None
                and job.status == "running"
                and version == self._versions.get(job_id)
            ):
                return
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_jobstore.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/jobstore.py tests/core/test_jobstore.py
git commit -m "fix(core): skip non-running jobs in memory jobstore lookups"
```

---

### Task 3: SQLAlchemyJobStore 的 `status` 列与过滤

**Files:**
- Modify: `src/schedflow/core/stores/sqlalchemy.py`（表定义、`_ensure_schema`、回填、`_add_once`/`_update_once`、`get_due`、`get_next_run_time`）
- Test: `tests/core/test_stores.py`

- [ ] **Step 1: 写失败测试**

```python
def test_sqlalchemy_get_due_ignores_paused_job(tmp_path):
    from schedflow.core.stores.sqlalchemy import SQLAlchemyJobStore

    store = SQLAlchemyJobStore(f"sqlite:///{tmp_path / 'jobs.db'}")
    job = make_job()
    store.add(job)
    job.status = "paused"
    job.next_run_time = datetime.now(UTC) - timedelta(seconds=5)
    store.update(job)

    assert store.get_due(datetime.now(UTC)) == []
    assert store.get_next_run_time() is None


def test_sqlalchemy_backfills_status_column(tmp_path):
    import sqlalchemy as sa

    from schedflow.core.stores.sqlalchemy import SQLAlchemyJobStore

    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    store = SQLAlchemyJobStore(url)
    store.add(make_job())
    with store._engine.begin() as connection:
        connection.execute(sa.text("ALTER TABLE jobs DROP COLUMN status"))
    store._engine.dispose()

    reopened = SQLAlchemyJobStore(url)

    assert reopened.get_next_run_time() is not None
    with reopened._engine.connect() as connection:
        statuses = connection.execute(
            sa.text("SELECT status FROM jobs")
        ).scalars().all()
    assert statuses == ["running"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_stores.py -q -k sqlalchemy`
Expected: FAIL（没有 `status` 列，`get_due` 仍返回 paused 任务）。

- [ ] **Step 3: 实现列、回填与过滤**

`self.jobs` 表定义追加：

```python
            sa.Column("status", sa.String(16), nullable=True),
            sa.Index("ix_jobs_status", "status"),
```

`_ensure_schema` 在 `next_run_utc` 的处理之后追加：

```python
        if "status" not in columns:
            try:
                with self._engine.begin() as connection:
                    connection.execute(
                        sa.text("ALTER TABLE jobs ADD COLUMN status VARCHAR(16)")
                    )
            except OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        if "ix_jobs_status" not in index_names:
            try:
                with self._engine.begin() as connection:
                    connection.execute(
                        sa.text("CREATE INDEX ix_jobs_status ON jobs (status)")
                    )
            except OperationalError as exc:
                if "already exists" not in str(exc).lower():
                    raise
        self._backfill_status()
```

新增回填方法：

```python
    def _backfill_status(self) -> None:
        """Populate status for rows written before the column existed."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                sa.select(self.jobs.c.id, self.jobs.c.job_json).where(
                    self.jobs.c.status.is_(None)
                )
            ).all()
        for job_id, raw in rows:
            job = Job.from_dict(json.loads(raw))
            with self._engine.begin() as connection:
                connection.execute(
                    self.jobs.update()
                    .where(self.jobs.c.id == job_id)
                    .values(status=job.status)
                )
```

`_add_once`/`_update_once` 的 `values(...)` 增加 `status=job.status`；
`get_due` 与 `get_next_run_time` 的 `where(...)` 增加
`self.jobs.c.status == "running"`。

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_stores.py tests/core/test_scheduler_alias.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/stores/sqlalchemy.py tests/core/test_stores.py
git commit -m "fix(stores): filter non-running jobs in sqlalchemy lookups"
```

---

### Task 4: Redis / MongoDB 存储过滤

**Files:**
- Modify: `src/schedflow/core/stores/redis.py`、`src/schedflow/core/stores/mongo.py`
- Test: `tests/core/test_stores.py`

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.redis
def test_redis_get_due_ignores_paused_job(redis_store):
    job = make_job()
    redis_store.add(job)
    job.status = "paused"
    job.next_run_time = datetime.now(UTC) - timedelta(seconds=5)
    redis_store.update(job)

    assert redis_store.get_due(datetime.now(UTC)) == []
    assert redis_store.get_next_run_time() is None
```

（若测试文件尚无 `redis_store` fixture，则复用文件中既有的 Redis store 构造方式；
MongoDB 用例按仓库现有约定在服务不可用时跳过。）

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_stores.py -q -k redis_get_due_ignores_paused`
Expected: FAIL 或 SKIP（本机无 Redis 时由 `conftest.py` 自动跳过）。

- [ ] **Step 3: 实现过滤**

Redis `get_due`：

```python
    def get_due(self, now: datetime) -> list[Job]:
        job_ids = self._redis.zrangebyscore(
            self._run_times_key, 0, now.timestamp()
        )
        jobs = (self.get(job_id) for job_id in job_ids)
        return [job for job in jobs if job and job.status == "running"]
```

Redis `get_next_run_time`：

```python
    def get_next_run_time(self) -> datetime | None:
        for job_id, score in self._redis.zrange(
            self._run_times_key, 0, -1, withscores=True
        ):
            job = self.get(job_id)
            if job is not None and job.status == "running":
                return datetime.fromtimestamp(score, tz=UTC)
        return None
```

MongoDB：`_ensure_indexes` 增加 `create_index("status", background=True)`；
`add`/`update` 写入的文档增加 `"status": job.status`；新增 `_backfill_status()`
（与 `_backfill_next_run_utc` 同风格，为缺少 `status` 的文档补写）；`get_due` 与
`get_next_run_time` 的查询条件增加 `"status": "running"`。

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_stores.py -q`
Expected: PASS（Redis/Mongo 不可用时相应用例 SKIP）。

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/stores/redis.py src/schedflow/core/stores/mongo.py tests/core/test_stores.py
git commit -m "fix(stores): filter non-running jobs in redis and mongodb lookups"
```

---

### Task 5: 启动自愈存量数据

**Files:**
- Modify: `src/schedflow/core/scheduler.py`（`start`）
- Test: `tests/core/test_scheduler_pause.py`

- [ ] **Step 1: 写失败测试**

```python
def test_start_repairs_legacy_armed_paused_job():
    store = MemoryJobStore()
    job = make_scheduler(store).add_job(
        make_workflow(), trigger=IntervalTrigger(seconds=60), job_id="j1"
    )
    job.status = "paused"  # 历史坏数据：paused 但仍带 next_run_time

    scheduler = make_scheduler(store)
    scheduler.start()
    try:
        assert store.get("j1").next_run_time is None
        assert store.get_next_run_time() is None
    finally:
        scheduler.shutdown(wait=False)
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_scheduler_pause.py -q -k repair`
Expected: FAIL（`next_run_time` 仍非空）。

- [ ] **Step 3: 实现自愈**

```python
    def _repair_armed_paused_jobs(self) -> list[str]:
        """Disarm jobs that are not running but still carry a next run time."""
        repaired: list[str] = []
        with self._lock:
            stores = list(self._jobstores.values()) or [self._jobstore]
            for store in stores:
                for job in store.get_all():
                    if job.status == "running" or job.next_run_time is None:
                        continue
                    self._disarm(job)
                    try:
                        store.update(job)
                    except JobNotFoundError:
                        continue
                    repaired.append(job.job_id)
        if repaired:
            LOGGER.warning(
                "disarmed %d non-running job(s) with stale next_run_time: %s",
                len(repaired),
                repaired,
            )
        return repaired
```

在 `start()` 中 `self._dispatcher.start()` 之前调用 `self._repair_armed_paused_jobs()`。

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_scheduler_pause.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/core/scheduler.py tests/core/test_scheduler_pause.py
git commit -m "fix(core): disarm stale armed jobs on scheduler start"
```

---

### Task 6: 修复 `PUT /api/jobs/{id}`

**Files:**
- Modify: `src/schedflow/api/rest/routers.py`（`update_job`）
- Test: `tests/test_api_rest/test_api_rest.py`

- [ ] **Step 1: 写失败测试**

```python
def test_update_job_with_trigger_and_workflow():
    client = _client()
    created = client.post(
        "/api/jobs",
        json={
            "name": "update-me",
            "workflow": _workflow_payload(),
            "trigger": {"type": "interval", "args": {"seconds": 60}},
        },
    ).json()["data"]

    response = client.put(
        f"/api/jobs/{created['job_id']}",
        json={
            "name": "renamed",
            "trigger": {"type": "interval", "args": {"seconds": 120}},
            "workflow": _workflow_payload(),
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "renamed"
    assert data["trigger"]["type"] == "IntervalTrigger"
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_api_rest/test_api_rest.py -q -k update_job_with_trigger`
Expected: FAIL，500 `'dict' object has no attribute 'to_trigger'`。

- [ ] **Step 3: 实现修复**

`update_job` 端点开头替换为：

```python
    workflow = (
        request.workflow.to_workflow() if request.workflow is not None else None
    )
    trigger = (
        request.trigger.to_trigger() if request.trigger is not None else None
    )
    changes = request.model_dump(
        exclude_none=True, exclude={"workflow", "trigger"}
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_api_rest -q`
Expected: PASS（含 `test_frontend_parity.py`）。

- [ ] **Step 5: 提交**

```bash
git add src/schedflow/api/rest/routers.py tests/test_api_rest/test_api_rest.py
git commit -m "fix(api): accept workflow and trigger in job update"
```

---

### Task 7: Webhook 单次投递抽取与测试端点

**Files:**
- Modify: `src/schedflow/core/webhook.py`、`src/schedflow/api/routers/settings.py`、`src/schedflow/api/schemas.py`
- Test: `tests/core/test_webhook.py`、`tests/test_api/test_settings_ops.py`

- [ ] **Step 1: 写失败测试**

```python
def _stub_server(received: dict) -> str:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            received["body"] = json.loads(self.rfile.read(length))
            received["secret"] = self.headers.get("X-SchedFlow-Secret")
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/hook"


def test_deliver_once_posts_payload_with_secret():
    received: dict = {}
    url = _stub_server(received)

    result = deliver_once(
        WebhookConfig(url=url, events=("*",), secret="s3cret", timeout=2.0),
        {"kind": "job.succeeded", "job_id": "j1"},
    )

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert received["body"]["kind"] == "job.succeeded"
    assert received["secret"] == "s3cret"


def test_deliver_once_reports_failure():
    result = deliver_once(
        WebhookConfig(url="http://127.0.0.1:1/nope", timeout=0.2),
        {"kind": "job.succeeded"},
    )

    assert result["ok"] is False
    assert result["error"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_webhook.py -q -k deliver_once`
Expected: FAIL，`ImportError: cannot import name 'deliver_once'`。

- [ ] **Step 3: 实现 `deliver_once` 并让 sink 复用**

`core/webhook.py` 新增模块级函数：

```python
def deliver_once(config: WebhookConfig, payload: dict) -> dict:
    """POST one payload with the sink's retry policy.

    Returns ``{"ok", "status_code", "error", "duration_ms"}`` and never raises
    for transport errors, so callers can surface the outcome to users.
    """
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config.secret:
        headers["X-SchedFlow-Secret"] = config.secret
    started = time.monotonic()
    last_error: Exception | None = None
    status_code: int | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            config.url, data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=config.timeout) as response:
                status_code = response.status
                if 200 <= status_code < 300:
                    return {
                        "ok": True,
                        "status_code": status_code,
                        "error": None,
                        "duration_ms": (time.monotonic() - started) * 1000,
                    }
        except Exception as exc:  # noqa: BLE001 - retry on any failure
            last_error = exc
        time.sleep(0.5 * (2**attempt))
    return {
        "ok": False,
        "status_code": status_code,
        "error": str(last_error) if last_error else "delivery failed",
        "duration_ms": (time.monotonic() - started) * 1000,
    }
```

`WebhookEventSink._deliver` 改为：

```python
    def _deliver(self, config: WebhookConfig, payload: dict) -> None:
        result = deliver_once(config, payload)
        if result["ok"]:
            counter_inc("schedflow_webhook_delivered_total")
            return
        counter_inc("schedflow_webhook_failures_total")
        LOGGER.warning(
            "webhook delivery failed url=%s error=%s",
            config.url,
            result["error"],
        )
```

- [ ] **Step 4: 增加 API 端点与 schema**

`api/schemas.py`：

```python
class WebhookTestRequest(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    secret: str | None = None
    timeout: float | None = None
```

`api/routers/settings.py`：

```python
@router.post("/webhooks/test")
def webhooks_test(request_body: WebhookTestRequest):
    from schedflow.core.webhook import WebhookConfig, deliver_once

    candidate = request_body.model_dump(exclude_none=True)
    if not candidate.get("url"):
        configs = get_webhooks_config()
        if not configs:
            raise HTTPException(status_code=422, detail="No webhook configured")
        candidate = {**configs[0], **candidate}
    config = WebhookConfig.from_dict(candidate)
    event = (config.events or ("job.succeeded",))[0]
    if event == "*" or event.endswith(".*"):
        event = "job.succeeded"
    payload = {
        "kind": event,
        "job_id": "test",
        "run_time": None,
        "detail": {"source": "webhook-test"},
    }
    return APIResponse(data=deliver_once(config, payload))
```

`tests/test_api/test_settings_ops.py` 增加两个用例：未配置任何 Webhook 且未传 `url` 时返回 422；
monkeypatch `schedflow.core.webhook.deliver_once` 返回
`{"ok": True, "status_code": 200, "error": None, "duration_ms": 1.0}` 时响应 `data["ok"] is True`。

- [ ] **Step 5: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_webhook.py tests/test_api/test_settings_ops.py -q`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add src/schedflow/core/webhook.py src/schedflow/api/routers/settings.py src/schedflow/api/schemas.py tests/core/test_webhook.py tests/test_api/test_settings_ops.py
git commit -m "feat(api): add webhook delivery test endpoint"
```

---

### Task 8: DAG 布局修复与前端测试基线

**Files:**
- Create: `frontend/src/views/jobs/dagreLayout.ts`、`frontend/src/views/jobs/__tests__/dagreLayout.spec.ts`
- Modify: `frontend/src/views/jobs/WorkflowEditor.vue`、`frontend/src/types/workflow.ts`、`frontend/package.json`

- [ ] **Step 1: 安装依赖与测试脚本**

```bash
cd frontend
npm install --save dagre@^0.8.5
npm install --save-dev vitest@^3 @types/dagre
```

`package.json` 的 `scripts` 增加 `"test": "vitest run"`。

- [ ] **Step 2: 写失败测试**

```ts
import { describe, expect, it } from 'vitest'
import { computeDagreLayout } from '../dagreLayout'

const nodes = [
  { node_id: 'a', task_node: { name: 'a', func: { type: 'bash' } } },
  { node_id: 'b', task_node: { name: 'b', func: { type: 'python_script' } } },
] as any
const edges = [{ source: 'a', target: 'b' }] as any

describe('computeDagreLayout', () => {
  it('places every node for a two-node workflow', () => {
    const positions = computeDagreLayout(nodes, edges)

    expect(positions.size).toBe(2)
    for (const id of ['a', 'b']) {
      const pos = positions.get(id)!
      expect(Number.isFinite(pos.x)).toBe(true)
      expect(Number.isFinite(pos.y)).toBe(true)
    }
    expect(positions.get('b')!.y).toBeGreaterThan(positions.get('a')!.y)
  })

  it('returns an empty layout when there are no nodes', () => {
    expect(computeDagreLayout([], []).size).toBe(0)
  })
})
```

- [ ] **Step 3: 运行确认失败**

Run: `cd frontend && npm test`
Expected: FAIL，`Failed to resolve import "../dagreLayout"`。

- [ ] **Step 4: 实现布局模块并在组件中复用**

`frontend/src/types/workflow.ts` 增加：

```ts
export interface NodePosition {
  x: number
  y: number
}
```

`frontend/src/views/jobs/dagreLayout.ts`：

```ts
import dagre from 'dagre'
import type { DagData, NodePosition } from '@/types/workflow'

/** Compute top-to-bottom node positions with dagre; falls back to a grid. */
export function computeDagreLayout(
  nodes: DagData['nodes'],
  edges: DagData['edges'],
): Map<string, NodePosition> {
  const positions = new Map<string, NodePosition>()
  if (nodes.length === 0) return positions

  const grid = () =>
    new Map(
      nodes.map((node, index) => [
        node.node_id,
        { x: 120, y: 100 + index * 90 },
      ]),
    )

  try {
    const g = new dagre.graphlib.Graph()
    g.setGraph({
      rankdir: 'TB',
      nodesep: 60,
      ranksep: 80,
      marginx: 80,
      marginy: 80,
    })
    g.setDefaultEdgeLabel(() => ({}))
    for (const node of nodes) {
      g.setNode(node.node_id, { width: 150, height: 50 })
    }
    for (const edge of edges) {
      g.setEdge(edge.source, edge.target)
    }
    dagre.layout(g)
    for (const node of nodes) {
      const pos = g.node(node.node_id)
      if (pos) positions.set(node.node_id, { x: pos.x, y: pos.y })
    }
  } catch (error) {
    console.error('Dagre layout error, falling back to grid:', error)
    return grid()
  }
  return positions.size > 0 ? positions : grid()
}
```

`WorkflowEditor.vue`：删除 `import dagre, { Graph } from 'dagre'` 与本地
`computeDagreLayout`，改为 `import { computeDagreLayout } from './dagreLayout'`；
`loadDag` 内调用改为 `computeDagreLayout(data.nodes, data.edges)`；
拖动后的自动布局复用同一函数：

```ts
function applyAutoLayout() {
  if (!lfInstance.value) return
  const graphData = lfInstance.value.getGraphData() as LfGraphData
  const rawNodes = graphData.nodes || []
  const rawEdges = graphData.edges || []
  if (rawNodes.length === 0) return

  const positions = computeDagreLayout(
    rawNodes.map((node) => ({
      node_id: node.id,
      task_node: { name: node.id, func: {} },
    })) as any,
    rawEdges.map((edge) => ({
      source: edge.sourceNodeId,
      target: edge.targetNodeId,
    })) as any,
  )

  for (const [nodeId, pos] of positions) {
    const nodeModel = lfInstance.value.getNodeModelById(nodeId)
    if (nodeModel) {
      nodeModel.moveTo(pos.x, pos.y)
      if (props.readonly) nodeModel.draggable = false
    }
  }
}
```

- [ ] **Step 5: 运行确认通过**

Run: `cd frontend && npm test && npm run type-check && npm run build-only`
Expected: 测试 PASS，类型检查与构建无错误。

- [ ] **Step 6: 提交**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/types/workflow.ts frontend/src/views/jobs/dagreLayout.ts frontend/src/views/jobs/__tests__/dagreLayout.spec.ts frontend/src/views/jobs/WorkflowEditor.vue
git commit -m "fix(frontend): render workflow DAG with dagre 0.8 entrypoint"
```

---

### Task 9: 全局组件层样式

**Files:**
- Create: `frontend/src/styles/components.css`
- Modify: `frontend/src/main.ts`、`frontend/src/views/jobs/JobList.vue`、`frontend/src/views/jobs/JobDetail.vue`、`frontend/src/views/jobs/NodeInfoSidebar.vue`、`frontend/src/views/settings/SystemSettings.vue`、`frontend/src/views/settings/ApiKeyManager.vue`、`frontend/src/views/settings/VariablesManager.vue`

- [ ] **Step 1: 建立组件层文件**

`frontend/src/styles/components.css`：

```css
/* Component layer — references the semantic tokens declared in App.vue. */

.page-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 var(--space-lg);
}

.settings-tabs {
  display: flex;
  gap: 0;
  margin-bottom: var(--space-lg);
  border-bottom: 1px solid var(--border-subtle);
}

.settings-card {
  padding: var(--space-lg);
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--color-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
  transform: translateY(-1px);
  box-shadow: var(--shadow-glow);
}
.btn-primary:active:not(:disabled) { transform: translateY(0) scale(0.98); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

.action-btn {
  padding: 4px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: 12px;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.action-btn:hover {
  background: var(--bg-surface-hover);
  color: var(--text-primary);
  border-color: var(--border-default);
}
.action-btn.danger:hover {
  background: var(--color-danger-soft);
  color: var(--color-danger);
  border-color: rgba(239, 68, 68, 0.3);
}

.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group > label { font-size: 13px; font-weight: 500; color: var(--text-secondary); }
.form-group .field-hint { font-size: 12px; color: var(--text-muted); }

.form-input,
.form-select {
  padding: 10px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 14px;
  font-family: var(--font-body);
  outline: none;
  transition: border-color var(--transition-fast);
}
.form-input:focus,
.form-select:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-soft);
}

.toggle-switch {
  position: relative;
  width: 40px;
  height: 22px;
  border-radius: 11px;
  border: none;
  background: var(--border-default);
  cursor: pointer;
  transition: background var(--transition-fast);
  flex-shrink: 0;
}
.toggle-switch.active { background: var(--color-success); }
.toggle-switch.loading { opacity: 0.6; cursor: wait; }
.toggle-switch .toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform var(--transition-fast);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}
.toggle-switch.active .toggle-thumb { transform: translateX(18px); }
```

`frontend/src/main.ts` 在 `import App from './App.vue'` 之前加入
`import './styles/components.css'`。

- [ ] **Step 2: 删除重复定义**

- `JobList.vue`：删除 scoped 中的 `.btn-primary`、`.action-btn`、`.toggle-switch` 及其状态规则；
- `JobDetail.vue`：删除同名的 `.btn-primary`、`.action-btn`、`.toggle-switch`、`.form-input`、`.form-group` 规则；
- `SystemSettings.vue`：删除 `.page-title`、`.settings-tabs`；
- `ApiKeyManager.vue`、`VariablesManager.vue`：删除 `.section-title`、`.section-desc`；
- `NodeInfoSidebar.vue`：删除 `.section-title`（改用全局令牌）。

- [ ] **Step 3: 回归验证计算样式**

在隔离实例前端逐页比较同一选择器的计算样式：

```js
const cs = getComputedStyle(document.querySelector('.btn-primary'))
;[cs.backgroundColor, cs.borderRadius, cs.padding]
```

Expected：`/jobs`、`/settings`、`/observability-settings` 三页均为
`rgb(59, 130, 246)` / `10px` / `9px 18px`；`.toggle-switch` 高度 22px；
`.form-input` 不再是浏览器默认 `inset` 边框。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/styles/components.css frontend/src/main.ts frontend/src/views
git commit -m "refactor(frontend): share component styles across pages"
```

---

### Task 10: 设置页信息架构

**Files:**
- Modify: `frontend/src/views/settings/SystemSettings.vue`、`frontend/src/views/settings/ObservabilitySettings.vue`、`frontend/src/api/settings.ts`、`frontend/src/components/layout/AppSidebar.vue`、`frontend/src/router/index.ts`

- [ ] **Step 1: 系统设置新增「API 写限流」标签页**

`SystemSettings.vue` 的 `tabs` 增加 `{ key: 'rate-limit', label: 'API 写限流' }`，模板新增
`v-show="activeTab === 'rate-limit'"` 区块（启用开关 + rpm 输入 + 保存按钮），并补说明：

```html
<p class="section-desc">
  仅作用于 <code>POST/PUT/PATCH/DELETE /api/**</code> 的写请求，按登录主体（未认证时按客户端 IP）计数；
  计数在单进程内存中完成，多 worker 各自独立；与任务的触发频率无关。
</p>
```

脚本复用 `getRateLimit` / `setRateLimit`，保存成功提示 `限流配置已保存`。

- [ ] **Step 2: 集成页重写**

`ObservabilitySettings.vue`：标题改为 `<h1 class="page-title gradient-text">集成</h1>`；
移除限流卡片；Webhook 行改为带 label 的表单：

```html
<div v-for="(hook, index) in webhooks" :key="index" class="webhook-row">
  <div class="form-group">
    <label :for="`hook-url-${index}`">回调地址</label>
    <input
      :id="`hook-url-${index}`"
      v-model="hook.url"
      class="form-input"
      placeholder="https://example.com/hook"
    />
  </div>
  <div class="form-group">
    <label :for="`hook-events-${index}`">订阅事件</label>
    <select :id="`hook-events-${index}`" v-model="hook.events" class="form-select" multiple>
      <optgroup v-for="group in eventGroups" :key="group.label" :label="group.label">
        <option v-for="kind in group.kinds" :key="kind" :value="kind">{{ kind }}</option>
      </optgroup>
    </select>
    <span class="field-hint">可多选；全部不选表示订阅所有事件（*）</span>
  </div>
  <div class="form-group">
    <label :for="`hook-secret-${index}`">签名密钥（可选）</label>
    <input
      :id="`hook-secret-${index}`"
      v-model="hook.secret"
      class="form-input"
      placeholder="作为 X-SchedFlow-Secret 头发送"
    />
  </div>
  <div class="webhook-actions">
    <button class="action-btn" @click="testWebhook(hook)">发送测试</button>
    <button class="action-btn danger" @click="webhooks.splice(index, 1)">删除</button>
  </div>
</div>
```

事件分组常量与 `core/events.py` 的 `EVENT_KINDS` 一致：

```ts
const EVENT_KINDS = [
  'scheduler.started', 'scheduler.paused', 'scheduler.resumed', 'scheduler.shutdown',
  'scheduler.error',
  'job.added', 'job.updated', 'job.removed', 'job.paused', 'job.resumed', 'job.completed',
  'job.cancelled', 'job.started', 'job.succeeded', 'job.failed', 'job.missed',
  'job.max_instances',
  'task.executed', 'task.error', 'task.skipped', 'task.cancelled',
]

const eventGroups = [
  { prefix: 'scheduler', label: '调度器' },
  { prefix: 'job', label: '任务' },
  { prefix: 'task', label: '节点' },
].map(({ prefix, label }) => ({
  label,
  kinds: EVENT_KINDS.filter((kind) => kind.startsWith(`${prefix}.`)),
}))
```

测试按钮：

```ts
async function testWebhook(hook: { url: string; events: string[]; secret?: string }) {
  if (!hook.url.trim()) {
    ElMessage.warning('请先填写回调地址')
    return
  }
  const result = await testWebhookDelivery({
    url: hook.url.trim(),
    events: hook.events,
    secret: hook.secret || undefined,
  })
  if (result.ok) {
    ElMessage.success(`测试投递成功（HTTP ${result.status_code}）`)
  } else {
    ElMessage.error(`测试投递失败：${result.error}`)
  }
}
```

`frontend/src/api/settings.ts` 增加：

```ts
export function testWebhookDelivery(params: {
  url: string
  events?: string[]
  secret?: string
}): Promise<{
  ok: boolean
  status_code: number | null
  error: string | null
  duration_ms: number
}> {
  return client.post('/settings/webhooks/test', params)
}
```

- [ ] **Step 3: 侧栏与路由标题**

`AppSidebar.vue` 的导航文案与 `title` 由“可观测性与集成”改为“集成”；
`router/index.ts` 中该路由的 `meta.title` 同步为“集成”（路径 `/observability-settings` 不变）。

- [ ] **Step 4: 验证**

Run: `cd frontend && npm test && npm run type-check && npm run build-only`
Expected: 全部通过；浏览器回归确认系统设置四个标签页可切换、集成页无控制台报错、测试按钮有反馈。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/settings frontend/src/api/settings.ts frontend/src/components/layout/AppSidebar.vue frontend/src/router/index.ts
git commit -m "feat(frontend): move api rate limit to settings and rework integration page"
```

---

### Task 11: 构建确定性

**Files:**
- Create: `frontend/scripts/clean-dist.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: 新增清理脚本**

```js
import { rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const distDir = resolve(projectDir, 'dist')
rmSync(distDir, { recursive: true, force: true })
console.log('[clean-dist] removed', distDir)
```

`package.json` 增加 `"prebuild-only": "node scripts/clean-dist.mjs"`（npm 会在
`build-only` 之前自动执行）。

- [ ] **Step 2: 验证只剩一套入口包**

Run: `cd frontend && npm run build-only; (Get-ChildItem dist/assets -Filter "index-*.js").Count`
Expected: `1`。

- [ ] **Step 3: 提交**

```bash
git add frontend/scripts/clean-dist.mjs frontend/package.json
git commit -m "chore(frontend): clean dist before production build"
```

---

### Task 12: nginx 容器化生产前端

**Files:**
- Create: `frontend/nginx.conf.template`
- Modify: `Dockerfile`、`docker-compose.yml`、`README.md`

- [ ] **Step 1: 编写 nginx 模板**

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    location = /index.html {
        add_header Cache-Control "no-store";
    }

    location /api/v1/sse/ {
        proxy_pass ${SCHEDFLOW_API_URL};
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 1h;
    }

    location /api/ {
        proxy_pass ${SCHEDFLOW_API_URL};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri /index.html;
    }
}
```

- [ ] **Step 2: 改写 Dockerfile 的 web 阶段**

```dockerfile
FROM node:22-alpine AS web-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/vite.config.ts frontend/env.d.ts frontend/tsconfig*.json ./
COPY frontend/src ./src
COPY frontend/scripts ./scripts

RUN npm run build-only

FROM nginx:alpine AS web

ENV SCHEDFLOW_API_URL=http://api:8000
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=web-build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80
```

- [ ] **Step 3: compose 调整**

```yaml
  web:
    build:
      context: .
      target: web
    environment:
      SCHEDFLOW_API_URL: ${SCHEDFLOW_API_URL:-http://api:8000}
    ports:
      - "${SCHEDFLOW_BIND_HOST:-127.0.0.1}:${SCHEDFLOW_WEB_PORT:-18001}:80"
    depends_on:
      - api
    restart: unless-stopped
```

- [ ] **Step 4: 文档更新**

`README.md` 启动章节说明：容器部署使用 `docker compose up --build`；
`schedflow-frontend`（无 `--dev`）为本地预览（build + `vite preview`）；生产静态托管由 `web`
容器内的 nginx 完成（`/assets` immutable、`index.html` no-store、`/api` 与 SSE 反代）。

- [ ] **Step 5: 验证**

Run: `docker compose build web`，然后 `docker compose up -d web`，
`curl.exe -sI http://127.0.0.1:18001/`（应含 `Cache-Control: no-store`）与
`curl.exe -sI http://127.0.0.1:18001/assets/<哈希文件>.js`（应含 `public, immutable`）。
Expected: 200，且响应头符合预期。

- [ ] **Step 6: 提交**

```bash
git add frontend/nginx.conf.template Dockerfile docker-compose.yml README.md
git commit -m "build(web): serve production bundle with nginx"
```

---

### Task 13: 整栈验收

**Files:** 无新增，执行验证。

- [ ] **Step 1: 后端**

Run: `.\.venv\Scripts\python.exe -m pytest -q` 与 `.\.venv\Scripts\python.exe -m ruff check .`
Expected: 全部通过。

- [ ] **Step 2: 前端**

Run: `cd frontend && npm test && npm run type-check && npm run build-only`
Expected: 全部通过。

- [ ] **Step 3: 浏览器回归（隔离实例）**

1. 任务详情页 DAG：画布内节点数等于工作流节点数，控制台无 `TypeError`；
2. 暂停任务：`pause` 后 90 秒内 `GET /api/jobs/{id}/runs` 数量不增加；
3. 编辑任务保存（含触发器与工作流）返回 200；
4. `/settings` 与 `/observability-settings` 的 `.btn-primary` 计算样式一致；
5. 集成页在未填回调地址时点“发送测试”给出明确提示。

- [ ] **Step 4: 容器**

Run: `docker compose build && docker compose up -d`，访问 `http://127.0.0.1:18001` 登录并确认
实时事件（SSE）可用、静态资源命中缓存头。
Expected: 页面正常、事件实时刷新。

- [ ] **Step 5: 收尾**

关闭本计划使用的隔离实例进程与临时目录；确认 `git status` 只包含本计划涉及的文件。
