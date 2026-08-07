# SchedFlow 项目架构与特性说明（给人类/Agent）

> 目标：帮助第一次进入仓库的同学/Agent 快速理解“这个项目是什么、怎么组织、怎么跑、关键扩展点在哪里”。

## 1. 项目是什么

`SchedFlow` 是一个把传统“一个 Job=一个函数调用”升级为 **“一个 Job=一个 DAG 工作流（多个任务节点 + 依赖边）”** 的调度框架。全项目围绕**单一的 core 调度栈**（`schedflow.core`）构建：

- `Workflow`（DAG）：节点 = `TaskSpec`（可重试、可回调、可序列化的函数/命令调用），边可带条件；
- `Scheduler`：调度主循环（后台线程），支持多执行器、多存储器（按 alias 路由）、触发器调度、事件订阅与 jobstore 迁移；
- 执行后产出 `ExecutionLog`（含每个节点的状态、耗时、异常、stdout/stderr），并持久化到 JobStore；
- 触发器（`interval` / `cron` / `date` / `calendarinterval` / `and` / `or`）与运行器（`runners/`）为各模块共用组件。

> 注意：`schedulers/`、`executors/`、`jobstores/`、`models/`、`events/` 等旧包结构已删除，**不要重新引入**。

## 2. 目录结构（只列关键）

```
src/schedflow/
  core/               核心调度栈（唯一实现）
    scheduler.py      Scheduler：主循环、多执行器/存储器路由、jobstore 迁移、事件
    workflow.py       Workflow：DAG 构建/校验/执行（拓扑分层并行、_pre_results 注入、条件边）
    spec.py           TaskSpec：任务类型（python_callable/bash/python/python_script）
    executor.py       Executor 接口 + Debug/ThreadPool/ProcessPool
    async_executors.py 异步执行器：AsyncIO/Gevent/Tornado/Twisted
    jobstore.py       JobStore 接口 + MemoryJobStore
    stores/           SQLAlchemy / Redis / MongoDB 持久化存储
    job.py / log.py / events.py / resolve.py / result.py / context.py
    plugins.py        执行器/存储器静态注册表（EXECUTOR_PLUGINS / JOBSTORE_PLUGINS）
  api/                FastAPI 层（单一 Scheduler 实例）
    __init__.py       create_app(scheduler)：/api + /api/v1 统一入口，lifespan 启停调度器
    rest/             /api 调度 REST（jobs / scheduler / logs），结构化 schemas
    routers/          /api/v1 管理（auth / settings / components / sse）
    deps.py / exceptions.py / schemas.py / middleware.py
  triggers/           触发器（共享），registry.py 为静态注册表
  runners/            运行器（共享）：python_callable / bash / python / python_script
  auth/ settings/ configs/ exceptions/ utils/ display/ cli.py

examples/             推荐从这里理解 API（quick_start_guide / basic_workflow_example / advanced_workflow_example）
tests/                单元/集成测试：tests/core、tests/test_api_rest、tests/test_api、tests/triggers
docs/                 Sphinx/mkdocs 文档
```

## 3. 核心概念（面向使用者）

### 3.1 TaskSpec：任务节点描述

代码位置：`src/schedflow/core/spec.py`

- `TaskSpec(type, func/ref, command, script_path, script, args, kwargs, timeout)`；
- 四种类型：`python_callable`（函数或 `"module:func"` 引用，惰性解析）、`bash`（shell 命令）、`python`（脚本文件）、`python_script`（内联代码）；
- JSON 序列化用 `to_dict()` / `from_dict()`，函数引用保存为 `ref` 字符串，执行时经 `core.resolve.resolve_ref()` 恢复；
- 执行由 `runners/` 的 `RunnerRegistry` 完成（类型名唯一拼写：`python_script`，无 `python_scripts` 别名）。

### 3.2 Workflow：DAG 工作流（Job 的主体）

代码位置：`src/schedflow/core/workflow.py`

- `add_task(node_id, func=None, type=..., kwargs=..., retries=..., timeout=..., on_success=..., on_failure=..., name=..., description=...)`；
- `add_edge(source, target, condition=callable, name=..., description=...)`：成环检测（`CycleError`），条件函数签名 `condition(record, **kwargs) -> bool`；
- `run(max_workers=...)`：
  - 按拓扑分层执行，同层并行、层间串行；
  - 前置必须 `succeeded`（或条件满足），否则节点标记 `skipped` 并记录 `skip_reason`；
  - 前置结果汇总为 `_pre_results: Dict[node_id, result]` 注入后继（函数不接受该参数时自动剔除）；
  - 支持重试（`retries`）、超时（`timeout`）、成功/失败回调；
  - 过程中发布任务级事件。

### 3.3 ExecutionLog / TaskRecord：执行日志

代码位置：`src/schedflow/core/log.py`

- `ExecutionLog`：`log_id`、`flow_id`、`start_time/end_time/duration`、`records: Dict[node_id, TaskRecord]`、`succeeded`；
- `TaskRecord`：`status`（`pending/running/succeeded/failed/skipped`）、`result`、`error`、`skip_reason`、`duration`、`exit_code`、`stdout/stderr`；
- 日志通过 JobStore 的 `add_log(job_id, log)` 持久化，`/api/jobs/{id}/logs` 可查询。

## 4. 运行时数据流（从调度到执行）

1. `POST /api/jobs`（`api/rest/routers.py`）→ `Scheduler.add_job(workflow, trigger, ...)`，按 `jobstore_alias` 存入对应 JobStore；
2. `Scheduler` 主循环（后台守护线程）每轮扫描所有 JobStore 的到期任务，按 `executor_alias` 交给对应 Executor；
3. Executor 执行 `job.run()`（即 `Workflow.run()`），完成后回调 `Scheduler._on_job_finished`：写入 `ExecutionLog`、发布 `job.succeeded/job.failed` 事件；
4. 一次性触发器（如 date）执行后 `next_run_time` 置空并从 store 移除；周期触发器计算下一次运行时间；
5. 前端通过 `/api/jobs`、`/api/scheduler/status`、`/api/jobs/{id}/logs`、`/api/v1/sse` 获取状态与结果。

## 5. 事件系统

代码位置：`src/schedflow/core/events.py`

- `EventBus.subscribe(kind, callback)` / `off(kind, callback)`，`SchedulerEvent(kind, **payload)`；
- 事件种类：`scheduler.started/paused/resumed/shutdown`、`job.added/updated/removed/paused/resumed/started/succeeded/failed/missed/max_instances`、任务级事件（按节点发布）。

## 6. 持久化与组件管理

代码位置：`src/schedflow/core/jobstore.py` + `core/stores/`

- `JobStore` 接口 + `MemoryJobStore`；持久化实现：`SQLAlchemyJobStore` / `RedisJobStore` / `MongoDBJobStore`（`core/stores/`）；
- 组件配置（执行器/存储器）持久化在 SQLite 元数据库（`configs/config.py`），应用启动时由 lifespan 恢复；
- `/api/v1/components` 提供插件列表、配置、更新、删除与 **jobstore 迁移**（`Scheduler.migrate_jobstore(source, target)`）。

## 7. 组件注册（静态注册表，无 entry-points）

- 执行器/存储器：`core/plugins.py` 的 `EXECUTOR_PLUGINS` / `JOBSTORE_PLUGINS`；
- 触发器：`triggers/registry.py` 的 `TRIGGER_PLUGINS`；
- `pyproject.toml` **不再包含**任何插件 entry-points；新增组件时只需更新注册表与参数 schema（`api/routers/components.py`）。

## 8. 一些“Flow 特性”速查

- DAG 校验：`add_edge` 成环抛 `CycleError`；
- 并行执行：`run(max_workers=...)` 控制并行度；
- 结果传递：自动注入 `_pre_results`（函数不收该参数则自动剔除）；
- 条件依赖：边可带 `condition(record, **kwargs) -> bool`；
- 失败传播：前置失败导致后继 `skipped`；任务失败时 `ExecutionLog.succeeded=False`；
- 重试：`retries` 控制重试次数；超时：`timeout`；
- 回调：`on_success(retval=...)` / `on_failure(exc_info=...)`；
- JSON 序列化：`TaskSpec.to_dict()` / `Workflow.to_dict()` / `from_dict()`；
- 组件：执行器 7 种（debug/threadpool/processpool/asyncio/gevent/tornado/twisted）、存储器 4 种（memory/sqlalchemy/redis/mongodb）、触发器 6 种。

## 9. Web API 模块

### 9.1 快速开始

```python
from schedflow.api import create_app
from schedflow.core import Scheduler

app = create_app(Scheduler(), title="调度器API")
# uvicorn my_module:app  （lifespan 会启动/关闭唯一调度器）
```

### 9.2 API 端点

- `/api/jobs`：任务 CRUD、`pause/resume/run`、`/logs`（结构化 REST，`api/rest/`）；
- `/api/scheduler/status`、`/start`、`/pause`、`/resume`、`/shutdown`；
- `/api/v1/auth`：登录/初始化/API Key；`/api/v1/settings`：主题/变量；
- `/api/v1/components`：执行器/存储器/触发器列表与配置、jobstore 迁移、`/jobs/{id}/reschedule`；
- `/api/v1/sse`：`/jobs/{id}/next-run-time` 实时推送（查 core 调度器）。

统一返回格式：`{"code": 0, "data": ..., "message": "ok"}`。

### 9.3 认证与异常

- `AuthMiddleware` 可插拔认证（JWT / API Key / 自定义 `AuthBackend`）；
- 异常映射：`JobNotFoundError`→404、`JobConflictError`/`ValueError`→409、`OSError`→502。

## 10. 开发与测试（给仓库贡献者/Agent）

### 10.1 运行测试

在仓库根目录执行：

- `python -m pytest`（外部服务用例在 redis/mongodb 不可用时自动跳过）
- `ruff check .`

### 10.2 修改时的“最重要约束”

- **单调度器**：进程内只有一个 `Scheduler()`；`app.state.scheduler` 与 `app.state.scheduler_api` 必须为同一实例；
- **组件集合稳定**：执行器/存储器/触发器插件名与参数 schema 保持与前端契约一致（见 `tests/test_api_rest/test_frontend_parity.py`）；
- **序列化稳定**：`TaskSpec` / `Workflow` / `Job` / `ExecutionLog` 的 JSON 结构是 JobStore 与 REST API 的契约，改动需同步测试；
- **Flow 语义与测试一致**：成环检测、`skipped` 传播、`_pre_results` 注入、失败转 `failed`/`job.failed`；
- **不要重建已删除的包结构**：不得创建 `schedflow.schedulers|executors|jobstores|models|events`，也不要重新引入 entry-points 插件注册。
