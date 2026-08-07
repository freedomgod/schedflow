# 高级用法

## 重试、超时与回调

`Workflow.add_task()` 支持为每个节点独立配置重试次数、单次执行超时与成功/失败回调：

```python
def flaky_func() -> str:
    return "ok"


def on_success(retval):
    print("任务成功，结果：", retval)


def on_failure(error):
    print("任务失败，原因：", error)


wf.add_task(
    "flaky",
    func=flaky_func,
    retries=3,              # 最多尝试 3 次（包含首次）
    timeout=10,             # 单次尝试的超时秒数
    on_success=on_success,  # 成功回调，参数为任务返回值
    on_failure=on_failure,  # 失败回调，参数为错误信息字符串
)
```

行为说明：

- 节点只有在重试次数用尽后才会被标记为 `failed`；
- 超时发生在单次尝试级别（`python_callable` 通过独立线程执行并限制等待时间，子进程类任务直接透传给 subprocess 的 `timeout`）；
- 回调本身失败不会影响任务结果（回调在记录节点状态之后执行）。

## 条件边进阶

条件函数接收**上游节点的 `TaskRecord`**（不是原始返回值），返回 `True` 放行、`False` 将下游标记为 `skipped`：

```python
def high_value(record) -> bool:
    return bool(record.result) and record.result.get("value", 0) > 100


wf.add_edge("fetch", "transform", condition=high_value)
```

一个节点有多个前置时，**所有**前置都必须成功且对应条件边全部满足，节点才会执行；否则跳过。前置节点的结果统一以 `_pre_results`（节点 ID → 返回值）注入：

```python
def combine(_pre_results):
    left = _pre_results["left"]
    right = _pre_results["right"]
    return left + right
```

## 函数引用与 project_root

`func` 可以直接传可调用对象，也可以传字符串引用。字符串引用**只在执行时解析**，支持三种形式：

```python
wf.add_task("a", func="my_package.tasks:fetch")         # 可导入模块
wf.add_task("b", func="./tasks/hello.py:main")          # 相对 project_root 的路径
wf.add_task("c", func="D:/proj/tasks/hello.py:main")    # 绝对路径（Windows 盘符已处理）
```

解析基准目录通过 `Workflow(project_root=...)` 或 `Scheduler(project_root=...)` 配置（默认进程当前工作目录）。解析失败抛出 `RefResolveError`，错误信息会列出所有尝试过的路径，方便排查：

```text
Could not resolve reference 'my_package.tasks:fetch'. Attempted: file D:\proj\my_package\tasks; file D:\proj\my_package\tasks.py; import 'my_package.tasks' via sys.path
```

!!! tip "为什么延迟解析"
    创建、持久化、重启作业时都**不会**解析引用，只有真正执行到该节点时才解析。因此目标模块暂时缺失不会导致作业被静默丢弃，重启后补上依赖即可恢复执行。

## 进程池执行器

```python
from schedflow.core import Scheduler
from schedflow.core.executor import ProcessPoolExecutor

scheduler = Scheduler(executor=ProcessPoolExecutor(max_workers=4))
```

`ProcessPoolExecutor` 通过 **JSON worker 协议**工作：主进程只把 `Job.to_dict()`（纯 JSON）发送给子进程，子进程用 `Job.from_dict()` 重建后执行，再把 `ExecutionLog` JSON 返回。因此：

- Windows（spawn）下同样可用；
- 工作流节点必须使用**字符串引用**（可导入模块或脚本路径），不能是闭包、lambda 或本地嵌套函数；
- 节点返回结果必须可 JSON 序列化，否则日志持久化会失败。

## 序列化契约（JSON 唯一出口）

所有持久化都使用 JSON，且只有一套序列化出口：`to_dict()/from_dict()`。

```python
from schedflow.triggers.base import Trigger

data = workflow.to_dict()                # Workflow JSON
wf2 = Workflow.from_dict(data)

data = job.to_dict()                     # Job JSON（含 workflow、trigger、元数据）
job2 = Job.from_dict(data)

data = trigger.to_dict()                 # {"type": "interval", "args": {...}}
trigger2 = Trigger.from_dict(data)
```

`Workflow.to_dict()` 的结构：

```json
{
  "flow_id": "etl",
  "project_root": null,
  "nodes": [
    {
      "node_id": "fetch",
      "task": {"type": "python_callable", "ref": "my_package.tasks:fetch", "args": [], "kwargs": {"source": "api"}, "timeout": null},
      "name": "下载",
      "description": null,
      "retries": 1,
      "on_success": null,
      "on_failure": null
    }
  ],
  "edges": [
    {"source": "fetch", "target": "transform", "condition": null, "name": null, "description": null}
  ]
}
```

`Job.to_dict()` 额外包含 `job_id`、`status`、`trigger`、`executor_alias`、`jobstore_alias`、`misfire_grace_time`、`coalesce`、`max_instances`、`next_run_time` 等字段。反序列化时引用字符串**保持原样不解析**。

## Misfire 与并发控制

作业错过预定运行时间时的行为由三个参数控制：

```python
scheduler.add_job(
    workflow,
    trigger=IntervalTrigger(seconds=30),
    job_id="my_job",
    misfire_grace_time=60,   # 允许的最大延迟秒数；超过则发布 job.missed 事件并跳过本次
    coalesce=True,           # True：多次错过的运行合并为一次；False：逐个补跑
    max_instances=1,         # 同一作业的最大并发实例数；超出发布 job.max_instances 事件
)
```

可以在 `Scheduler(job_defaults={...})` 中设置全局默认值。

## Web API

### 启动

```python
from fastapi import FastAPI

from schedflow.api.rest import create_app
from schedflow.core import Scheduler

scheduler = Scheduler()
app = create_app(scheduler, title="调度器 API")

# 或挂载到已有应用
from schedflow.api.rest import mount_routes
mount_routes(app, scheduler)
```

所有端点统一返回 `{"code": 0, "data": ..., "message": "ok"}`。

### 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/jobs` | 创建作业（`workflow` + `trigger` JSON） |
| GET | `/api/jobs` | 列出所有作业 |
| GET | `/api/jobs/{job_id}` | 获取单个作业 |
| PUT | `/api/jobs/{job_id}` | 修改作业字段 |
| DELETE | `/api/jobs/{job_id}` | 删除作业 |
| POST | `/api/jobs/{job_id}/pause` | 暂停作业 |
| POST | `/api/jobs/{job_id}/resume` | 恢复作业 |
| POST | `/api/jobs/{job_id}/run` | 立即执行一次 |
| POST | `/api/jobs/{job_id}/reschedule` | 重新调度（body：`{"trigger": {...}}`） |
| GET | `/api/jobs/{job_id}/logs` | 执行日志列表 |
| GET | `/api/jobs/{job_id}/logs/{log_id}` | 单条日志详情 |
| GET | `/api/scheduler/status` | 调度器状态（state/state_name/job_count） |
| POST | `/api/scheduler/start` | 启动调度器 |
| POST | `/api/scheduler/pause` | 暂停调度器 |
| POST | `/api/scheduler/resume` | 恢复调度器 |
| POST | `/api/scheduler/shutdown` | 关闭调度器 |

### 创建作业示例

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": {
      "flow_id": "etl",
      "nodes": [
        {"node_id": "fetch", "task": {"ref": "my_package.tasks:fetch", "kwargs": {"source": "api"}}},
        {"node_id": "process", "task": "my_package.tasks:process"}
      ],
      "edges": [{"source": "fetch", "target": "process"}]
    },
    "trigger": {"type": "interval", "args": {"seconds": 60}},
    "job_id": "etl_job",
    "name": "数据管道"
  }'
```

要点：

- `task` 字段可以直接写字符串，等价于 `{"type": "python_callable", "ref": "..."}`；
- `trigger.args` 对应触发器构造参数（`interval` 支持 `weeks/days/hours/minutes/seconds/start_date/end_date/timezone/jitter`，`cron` 支持 `year/month/day/week/day_of_week/hour/minute/second/...`，其余类型同理）；
- 成环或边指向不存在的节点返回 **422**；重复 `job_id` 返回 **409**；不存在的 `job_id` 返回 **404**；`JobNotFoundError`/`JobConflictError` 会自动转成对应 HTTP 状态码。

### 认证

Web API 默认不启用认证。需要认证时，给 FastAPI 应用手动挂载中间件即可（内置的 `JWTBackend` / `APIKeyBackend` 位于 `schedflow.auth.security`，或实现自定义 `AuthBackend`）：

```python
from schedflow.api.middleware import AuthMiddleware
from schedflow.auth.security import APIKeyBackend

# APIKeyBackend 校验请求头 X-API-Key，并与元数据库中的 API Key 记录比对
app.add_middleware(AuthMiddleware, backends=[APIKeyBackend()])
```

```python
from schedflow.auth.security import AuthBackend, AuthResult


class MyAuth(AuthBackend):
    async def authenticate(self, request) -> AuthResult:
        token = request.headers.get("Authorization")
        ok = token == "Bearer my-token"
        return AuthResult(success=ok, user_id="u1", method="custom")


app.add_middleware(AuthMiddleware, backends=[MyAuth()])
```

!!! note
    `AuthResult` 的字段为 `success` / `user_id` / `method`。使用内置 `APIKeyBackend` 前需要先在元数据库中配置好 API Key 记录（该后端校验 `X-API-Key` 请求头）。

### 实时推送

Web API 目前未内置 SSE 路由，前端可基于 `GET /api/jobs/{job_id}/logs` 轮询，或订阅 SDK 事件自行实现推送。

## 自定义组件

自定义组件通过**继承公开基类**实现，直接以实例注入，无需注册入口点：

### 自定义触发器

```python
from datetime import datetime, timedelta

from pydantic import BaseModel

from schedflow.triggers.base import BaseTrigger, Trigger


class BusinessHoursTriggerModel(BaseModel):
    """内部校验模型：触发器仍以 Pydantic 模型做序列化契约。"""

    interval_minutes: int = 30


class BusinessHoursTrigger(BaseTrigger):
    """仅在工作时间（周一至周五 9:00-17:00）每 30 分钟触发。"""

    _trigger_type = "business_hours"    # 设置后会自动注册到 from_dict 的查找表
    _pydantic_model_cls = BusinessHoursTriggerModel

    def __init__(self, *, interval_minutes: int = 30):
        super().__init__(None, interval_minutes=interval_minutes)
        self.interval = timedelta(minutes=interval_minutes)

    def get_next_fire_time(self, previous_fire_time, now):
        next_time = (previous_fire_time or now) + self.interval
        if next_time.weekday() >= 5:
            next_time += timedelta(days=7 - next_time.weekday())
        if next_time.hour < 9:
            next_time = next_time.replace(hour=9, minute=0, second=0)
        elif next_time.hour >= 17:
            next_time = next_time.replace(hour=9, minute=0, second=0) + timedelta(days=1)
        return next_time.astimezone()   # 保持时区信息（调度器使用带时区的 now 做比较）


scheduler.add_job(workflow, trigger=BusinessHoursTrigger(interval_minutes=15))
```

!!! note
    触发器对外构造使用显式关键字参数，但内部仍以 Pydantic 模型承载序列化契约，因此自定义触发器需要同时提供 `_trigger_type` 与 `_pydantic_model_cls`。设置 `_trigger_type` 后，`Trigger.from_dict()` 会自动识别该类型。

### 自定义作业存储

继承 `schedflow.core.jobstore.JobStore`，实现 `add / update / remove / get / get_due / get_all / get_next_run_time / add_log / get_logs / get_log / close`：

```python
from schedflow.core.jobstore import JobStore


class MyJobStore(JobStore):
    def add(self, job): ...
    def update(self, job): ...
    def remove(self, job_id): ...
    def get(self, job_id): ...
    def get_due(self, now): ...
    def get_all(self): ...
    def get_next_run_time(self): ...
    def add_log(self, job_id, log): ...
    def get_logs(self, job_id): ...
    def get_log(self, job_id, log_id): ...
    def close(self): ...


scheduler = Scheduler(jobstore=MyJobStore())
```

### 自定义执行器

继承 `schedflow.core.executor.Executor`，实现 `submit(job, run_time)`（可选覆写 `start(shutdown)`）：

```python
from schedflow.core.executor import Executor


class MyExecutor(Executor):
    def submit(self, job, run_time):
        log = job.run()
        self._scheduler._on_job_finished(job, run_time, log)


scheduler = Scheduler(executor=MyExecutor())
```

### 自定义任务运行器

任务类型由 `RunnerRegistry` 分发（`TaskSpec.type` → `BaseRunner` 实例）。可以为内置类型替换实现；`Workflow.add_task(type=...)` 目前只接受四种内置类型，新增自定义类型需要同时扩展 `TaskSpec` 的类型校验：

```python
from schedflow.core.result import TaskResult
from schedflow.runners.base import BaseRunner
from schedflow.runners.registry import RunnerRegistry


class MyRunner(BaseRunner):
    """示例：用自定义实现替换内置 bash 类型的执行方式。"""

    def run(self, spec, *, context=None, **kwargs) -> TaskResult:
        return TaskResult(succeeded=True, result=spec.command.upper())


RunnerRegistry.register("bash", MyRunner())
```

!!! note
    `TaskSpec` 只接受 `python_callable` / `python` / `python_script` / `bash` 四种 `type`；注册全新任务类型时，还需要同步修改 `TaskSpec` 的校验逻辑（当前版本未开放该扩展点）。

!!! note "插件入口点"
    项目已移除 entry-points 插件注册。执行器/存储器通过静态注册表
    `schedflow.core.plugins`（`EXECUTOR_PLUGINS` / `JOBSTORE_PLUGINS`）
    注册，触发器通过 `schedflow.triggers.registry.TRIGGER_PLUGINS`
    注册；配置接口（`/api/v1/components`）直接读取这些注册表。

## 事件订阅进阶

事件回调接收 `SchedulerEvent`，可按事件类型携带不同负载：

```python
def on_job_missed(event):
    print(f"作业 {event.job_id} 错过运行时间 {event.run_time}")


def on_task_error(event):
    # task.* 事件携带对应节点的 TaskRecord
    record = event.record
    print(f"节点 {record.node_id} 失败：{record.error}")


scheduler.on("job.missed", on_job_missed)
scheduler.on("task.error", on_task_error)
scheduler.on("*", lambda event: print("任何事件：", event.kind))
```

!!! note "任务事件与作业事件的关系"
    `task.*` 事件在调度器执行作业后逐节点发布（`event.record` 为对应节点的 `TaskRecord`）；随后才发布 `job.succeeded` / `job.failed` 作业级事件。只订阅 `job.*` 也可以从 `event.log.records` 读取同样的节点状态。直接调用 `Workflow.run()` 不会发布任何事件。
