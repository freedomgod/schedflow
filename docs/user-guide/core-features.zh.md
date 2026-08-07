# 核心功能

## 调度器（Scheduler）

调度器是管理作业执行的中央组件：它运行一个主循环，从作业存储拉取到期作业、计算下次运行时间、交给执行器执行、发布事件并持久化执行日志。

框架提供**一个统一的 `Scheduler` 类**（`schedflow.core.Scheduler`），通过构造参数选择作业存储、执行器与时区：

```python
from schedflow.core import Scheduler

scheduler = Scheduler(
    timezone="Asia/Shanghai",          # 可选，默认使用本地时区
    project_root="./my_project",       # 可选，字符串引用的相对路径解析基准
)
```

!!! note "调度器选择"
    `schedflow.core.Scheduler` 是核心调度器，`start()` 在后台线程运行主循环；若需要阻塞式前台运行，自行 `join` 或等待事件即可。

### 生命周期

```python
scheduler.start(paused=False)   # 启动主循环；paused=True 时先不处理作业
scheduler.pause()               # 暂停作业处理（不中断正在运行的作业）
scheduler.resume()              # 恢复作业处理
scheduler.shutdown(wait=True)   # 停止调度器；wait=True 等待正在运行的作业完成
```

## 触发器（Triggers）

触发器决定作业**何时**运行。每个触发器都使用显式关键字构造，并统一支持 `to_dict()/from_dict()` 序列化：

```python
from schedflow.triggers import (
    AndTrigger,
    CalendarIntervalTrigger,
    CronTrigger,
    DateTrigger,
    IntervalTrigger,
    OrTrigger,
)
```

### DateTrigger（日期触发器）

在指定日期/时间运行一次：

```python
trigger = DateTrigger(run_date="2026-08-01 10:00:00")
trigger = DateTrigger(datetime(2026, 8, 1, 10, 0))       # 也接受 datetime 对象
```

### IntervalTrigger（间隔触发器）

按固定间隔重复运行：

```python
IntervalTrigger(seconds=30)
IntervalTrigger(minutes=5, hours=1)
IntervalTrigger(days=1, start_date="2026-01-01", end_date="2026-12-31")
IntervalTrigger(seconds=60, jitter=5)          # jitter：最多随机延迟 5 秒
```

### CronTrigger（Cron 触发器）

使用类 Cron 的表达式进行调度：

```python
# 每天凌晨 3:00
CronTrigger(hour=3)

# 每周一中午
CronTrigger(day_of_week="mon", hour=12)

# 工作日每 15 分钟
CronTrigger(minute="*/15", day_of_week="mon-fri")

# 每月第一天零点
CronTrigger(day=1, hour=0)

# 从标准 5 段 crontab 表达式创建
CronTrigger.from_crontab("0 9 * * 1-5", timezone="Asia/Shanghai")
```

### CalendarIntervalTrigger（日历间隔触发器）

按日历边界对齐的间隔运行，始终保持每天同一时刻：

```python
CalendarIntervalTrigger(months=1, hour=9, minute=0)   # 每月同一日期 09:00 执行
CalendarIntervalTrigger(days=7, hour=18, minute=30)   # 每 7 天 18:30
```

!!! warning
    若使用 `months`/`years`，起始日期尽量避开月末（29–31 日）与闰日，否则某些月份会被跳过。

### 组合触发器（AND/OR）

```python
# 所有子触发器都能触发的时刻才触发（交集）
AndTrigger(triggers=[CronTrigger(hour=9), IntervalTrigger(seconds=30)])

# 任一子触发器触发即触发（并集）
OrTrigger(triggers=[DateTrigger(run_date="2026-01-01"), CronTrigger(day_of_week="fri")])
```

!!! warning
    `AndTrigger` 只适合组合“固定时刻”型触发器（如 Cron / CalendarInterval），与 `IntervalTrigger` 组合可能导致调度循环长时间找不到交集。

### 触发器的序列化

```python
from schedflow.triggers.base import Trigger

data = trigger.to_dict()        # {"type": "interval", "args": {"seconds": 60, ...}}
trigger = Trigger.from_dict(data)   # 从 JSON 重建（Trigger 即 BaseTrigger 的别名）
```

这也是 Web API `{"trigger": {"type": ..., "args": {...}}}` 的 JSON 契约。

## 作业存储（Job Stores）

作业存储持久化作业定义与执行日志。`JobStore` 是显式接口，所有实现都使用 **JSON 序列化**（不再使用 pickle），且**反序列化时不会解析函数引用**——目标模块暂时不可导入也不会导致作业丢失。

| 作业存储 | 适用场景 | 安装 |
|----------|----------|------|
| `MemoryJobStore` | 内存（易失），开发/测试 | 内置 |
| `SQLAlchemyJobStore` | SQLite / PostgreSQL / MySQL 等 | `[sqlalchemy]` |
| `RedisJobStore` | Redis | `[redis]` |
| `MongoDBJobStore` | MongoDB | `[mongodb]` |

```python
from schedflow.core import Scheduler
from schedflow.core.stores.sqlalchemy import SQLAlchemyJobStore

store = SQLAlchemyJobStore(url="sqlite:///jobs.db")
scheduler = Scheduler(jobstore=store)
```

统一的存储接口（`JobStore`）：

```python
store.add(job)                  # 写入作业（重复 ID 抛 JobConflictError）
store.update(job)               # 更新作业（不存在抛 JobNotFoundError）
store.remove(job_id)            # 删除作业
store.get(job_id)               # 查询单个作业
store.get_all()                 # 全部作业（调度中的在前，暂停的在后）
store.get_due(now)              # 到期的作业（按 next_run_time 升序）
store.get_next_run_time()       # 最近一次到期时间
store.add_log(job_id, log)      # 保存执行日志
store.get_logs(job_id)          # 查询执行日志列表
store.get_log(job_id, log_id)   # 查询单条执行日志
store.close()                   # 关闭底层连接
```

## 执行器（Executors）

执行器决定作业**如何**运行：

| 执行器 | 并发模型 | 适合场景 |
|--------|----------|----------|
| `ThreadPoolExecutor` | 线程池（默认 10 线程） | IO 密集型任务 |
| `ProcessPoolExecutor` | 进程池（JSON worker 协议） | CPU 密集型任务；Windows 可用 |
| `DebugExecutor` | 同步直跑（调用线程内） | 开发/测试 |

!!! note
    核心执行器统一实现 `schedflow.core.executor.Executor` 接口：常规的
    `ThreadPoolExecutor` / `ProcessPoolExecutor` / `DebugExecutor` 位于
    `core.executor`，异步系的 `AsyncIOExecutor` / `GeventExecutor` /
    `TornadoExecutor` / `TwistedExecutor` 位于 `core.async_executors`。

```python
from schedflow.core import Scheduler
from schedflow.core.executor import ProcessPoolExecutor, ThreadPoolExecutor

scheduler = Scheduler(
    executor=ProcessPoolExecutor(max_workers=4),
)
```

### 进程池的注意事项

`ProcessPoolExecutor` 只把 `Job.to_dict()`（纯 JSON）发送给子进程，子进程重建作业并执行，因此 **Windows（spawn）下同样可用**。代价是：进程池执行时，工作流节点必须使用**字符串引用**（可导入的 `"模块:函数"` 或脚本路径），不能是闭包/lambda。

## 作业管理

### 添加作业

```python
job = scheduler.add_job(
    workflow,                                   # Workflow 实例或其 JSON 字典
    trigger=IntervalTrigger(seconds=30),        # 可选；为 None 时只能手动触发
    job_id="my_job",                            # 可选，缺省自动生成
    name="我的作业",
    description="示例作业",
    misfire_grace_time=60,                      # 错过执行的最大容忍秒数
    coalesce=True,                              # 合并多次错过的执行为一次
    max_instances=1,                            # 最大并发实例数
    replace=False,                              # 已存在同名作业时是否替换
)
```

!!! note "flow_id 与 job_id 的区别"
    `Workflow("etl")` 中的 `flow_id` 是**工作流定义**的标识（会写入 `log.flow_id`，不要求唯一）；`add_job(..., job_id=...)` 中的 `job_id` 是**调度作业**在 JobStore 中的唯一键（省略时自动生成 UUID），用于查询/修改/删除作业、事件 `event.job_id` 与日志查询。两者互不绑定：同一份工作流可以注册为多个不同 `job_id` 的作业；直接 `Workflow.run()` 时没有作业，`log.job_id` 为 `None`。

### 查询 / 修改 / 删除

```python
job = scheduler.get_job("my_job")
jobs = scheduler.get_jobs()

scheduler.update_job("my_job", name="新名字", trigger=CronTrigger(hour=3))
scheduler.remove_job("my_job")
```

### 暂停 / 恢复 / 重新调度 / 立即执行

```python
scheduler.pause_job("my_job")
scheduler.resume_job("my_job")
scheduler.reschedule_job("my_job", CronTrigger(hour=3))

log = scheduler.run_job_now("my_job")     # 无视触发器立即执行一次
```

### 执行日志

```python
logs = scheduler.get_job_logs("my_job")              # 该作业的全部执行日志
log = scheduler.get_job_log("my_job", log_id)        # 单条日志详情
```

## 事件（Events）

事件系统采用**发布/订阅（pub/sub）**模型：调度器在关键节点发布事件，应用通过订阅回调响应。回调签名统一为 `callback(event: SchedulerEvent) -> None`。

### 快速开始

```python
def on_job_succeeded(event):
    print(f"作业 {event.job_id} 执行成功")
    for node_id, record in event.log.records.items():
        print(f"  {node_id}: {record.status} 结果={record.result}")


scheduler = Scheduler()
scheduler.on("job.succeeded", on_job_succeeded)   # 订阅事件
# scheduler.off("job.succeeded", on_job_succeeded)  # 取消订阅（可选）
```

- `scheduler.on(kind, callback)` 把回调注册到**这个调度器实例**的事件总线上；`scheduler.off(kind, callback)` 取消订阅；
- 事件触发时，回调收到一个 `SchedulerEvent` 对象（属性见下文）；
- 同一个事件类型可以注册多个回调，按注册顺序依次执行；某个回调抛异常不会影响其它回调；
- 订阅 `"*"` 会收到该调度器发布的**所有**事件。

### EventBus 是什么？

`EventBus` 是一个线程安全的**发布/订阅容器**：`subscribe()` 注册回调、`unsubscribe()` 移除回调、`publish()` 触发事件。

```python
from schedflow.core import EventBus

bus = EventBus()
bus.subscribe("job.failed", my_callback)
```

!!! warning "EventBus 不是全局广播"
    `bus.subscribe("job.failed", callback)` 只是把回调注册到**这个 EventBus 实例**上。只有当某个调度器（或其它代码）在**同一个实例**上调用 `publish()` 时，订阅者才会收到事件；它不监听、也不接收其它总线上发布的事件。

每个 `Scheduler` 在构造时都会创建自己的 `EventBus` 作为内部总线（`scheduler._events`），`scheduler.on(...)` 等价于在它自己的总线上订阅：

```python
scheduler = Scheduler()
scheduler.on("job.failed", cb)                    # 订阅这个调度器
scheduler._events.subscribe("job.failed", cb)     # 等价写法（内部总线）
```

因此：

- **两个不同的 `Scheduler` 实例各自持有独立总线，事件互不相通**——`bus.subscribe(...)` 不会收到另一个调度器发布的事件；
- 直接创建 `EventBus()` 也不会收到任何调度器事件——除非你自己调用 `bus.publish(...)`（适合应用内部解耦通知，或自建事件转发）。

### 事件类型与触发时机

下表列出所有事件类型、触发时机，以及回调里除 `event.kind` 外**可用哪些属性**（其余属性为 `None`）：

| 事件类型 | 触发时机 | 回调可用的属性 |
|----------|----------|----------------|
| `scheduler.started` | `start()` 启动成功 | 无（仅 `event.kind`） |
| `scheduler.paused` | 调度器暂停 | 无（仅 `event.kind`） |
| `scheduler.resumed` | 调度器恢复 | 无（仅 `event.kind`） |
| `scheduler.shutdown` | 调度器关闭 | 无（仅 `event.kind`） |
| `job.added` | `add_job()` 成功 | `job_id` |
| `job.updated` | `update_job()` 成功 | `job_id` |
| `job.removed` | `remove_job()`，或一次性作业执行完自动移除 | `job_id` |
| `job.paused` | 暂停某个作业 | `job_id` |
| `job.resumed` | 恢复某个作业 | `job_id` |
| `job.started` | 作业开始执行 | `job_id`、`run_time` |
| `job.succeeded` | 执行成功（无节点 `failed`） | `job_id`、`run_time`、`log` |
| `job.failed` | 执行失败（存在节点 `failed`） | `job_id`、`run_time`、`log` |
| `job.missed` | 超过 `misfire_grace_time` 被跳过 | `job_id`、`run_time` |
| `job.max_instances` | 达到 `max_instances` 上限被拒绝 | `job_id`、`run_time` |
| `task.executed` | 作业执行后，每个 `succeeded` 节点 | `job_id`、`run_time`、`log`、`record` |
| `task.error` | 作业执行后，每个 `failed` 节点 | `job_id`、`run_time`、`log`、`record` |
| `task.skipped` | 作业执行后，每个 `skipped` 节点 | `job_id`、`run_time`、`log`、`record` |

- 手动 `run_job_now()` 触发时 `run_time` 为 `None`；定时触发时为本次计划运行时间；
- 完整事件名清单见 `schedflow.core.events.EVENT_KINDS`。

!!! note "task.* 事件的发布位置"
    `task.*` 事件在**调度器执行作业**后逐节点发布——定时触发或 `run_job_now()` 均可。回调里的 `event.record` 是对应节点的 `TaskRecord`，`event.log` 是本次执行的 `ExecutionLog`。直接调用 `Workflow.run()`（不经过调度器）不会发布任何事件，此时请直接读取返回的 `ExecutionLog`。

### SchedulerEvent 的属性：分别是什么

回调收到的 `SchedulerEvent` 固定有 5 个属性。除 `kind` 外，其余属性在未填充时为 `None`：

| 属性 | 类型 | 何时有值 | 是什么 |
|------|------|----------|--------|
| `event.kind` | `str` | 总是有值 | 事件类型字符串，如 `"job.succeeded"`、`"task.error"` |
| `event.job_id` | `str` | `job.*` 与 `task.*` 事件 | 相关调度作业的唯一键（对应 `add_job(job_id=...)`） |
| `event.run_time` | `datetime` | 定时触发的事件 | 本次的计划运行时间；手动 `run_job_now()` 时为 `None` |
| `event.log` | `ExecutionLog` | `job.succeeded` / `job.failed` 与 `task.*` 事件 | 本次工作流执行的**完整日志对象**，见下 |
| `event.record` | `TaskRecord` | 仅 `task.*` 事件 | 对应节点的**执行记录对象**，见下 |

#### event.log —— ExecutionLog（一次执行的完整日志对象）

`event.log` 是 **`ExecutionLog`** 对象（`schedflow.core.log.ExecutionLog`），描述**一次工作流执行**的完整结果：

| 字段/方法 | 类型 | 含义 |
|-----------|------|------|
| `log.log_id` | `str` | 本次执行日志的唯一 ID（形如 `flowlog_xxx`） |
| `log.flow_id` | `str \| None` | 工作流的 `flow_id` |
| `log.job_id` | `str \| None` | 所属作业 ID（直接 `Workflow.run()` 时为 `None`） |
| `log.start_time` / `log.end_time` | `datetime` | 起止时间 |
| `log.duration` | `float \| None` | 总耗时（秒） |
| `log.records` | `dict[str, TaskRecord]` | “节点 ID → 该节点的 TaskRecord”字典 |
| `log.dag_snapshot` | `dict \| None` | 执行时的 DAG 结构快照（JSON） |
| `log.succeeded` | `bool` | 是否没有节点 `failed` |
| `log.failed_nodes()` | `list[TaskRecord]` | 所有失败节点的记录 |
| `log.skipped_nodes()` | `list[TaskRecord]` | 所有被跳过节点的记录 |

```python
def on_job_finished(event):
    log = event.log                 # ExecutionLog 对象
    print(f"{log.log_id} flow={log.flow_id} job={log.job_id} "
          f"耗时={log.duration}s 成功={log.succeeded}")
    for node_id, record in log.records.items():
        print(f"  {node_id}: {record.status} 结果={record.result} 错误={record.error}")
```

#### event.record —— TaskRecord（单个节点的执行记录对象）

`event.record` 是 **`TaskRecord`** 对象（`schedflow.core.log.TaskRecord`），描述**一个节点**在该次执行中的记录：

| 字段 | 类型 | 含义 |
|------|------|------|
| `record.node_id` | `str` | 节点 ID |
| `record.task_id` | `str \| None` | 任务 ID |
| `record.status` | `str` | `pending` / `running` / `succeeded` / `failed` / `skipped` |
| `record.result` | `Any` | 节点返回值（子进程类任务通常为 `None`，输出在 `stdout`） |
| `record.error` | `str \| None` | 失败原因 |
| `record.skip_reason` | `str \| None` | 被跳过的原因 |
| `record.stdout` / `record.stderr` | `str \| None` | 子进程类任务捕获的输出 |
| `record.exit_code` | `int \| None` | 子进程类任务的退出码 |
| `record.start_time` / `record.end_time` | `datetime` | 节点起止时间 |
| `record.duration` | `float \| None` | 节点耗时（秒） |

```python
def on_task_event(event):
    r = event.record                # TaskRecord 对象
    print(f"{event.job_id}/{r.node_id}: {r.status}")
    if r.error:
        print(f"  错误: {r.error}")
    if r.skip_reason:
        print(f"  跳过原因: {r.skip_reason}")
```

### 完整示例：监控一次作业执行

```python
def monitor(event):
    if event.kind in ("task.executed", "task.error", "task.skipped"):
        r = event.record
        print(f"[task] {event.job_id}/{r.node_id} -> {r.status}")
        if r.error:
            print(f"       错误: {r.error}")
    elif event.kind in ("job.succeeded", "job.failed"):
        log = event.log
        print(f"[job] {event.job_id} {event.kind} 耗时 {log.duration:.2f}s")


scheduler.on("*", monitor)
```

也可以直接使用 `EventBus`：

```python
from schedflow.core import EventBus

bus = EventBus()
bus.subscribe("job.failed", callback)
bus.unsubscribe("job.failed", callback)
```

## 配置

### 时区

调度器默认使用本地时区；可以通过 `timezone` 参数显式指定：

```python
from datetime import timezone

Scheduler(timezone="Asia/Shanghai")
Scheduler(timezone=timezone.utc)
```

### 作业默认值

```python
scheduler = Scheduler(job_defaults={
    "misfire_grace_time": 30,
    "coalesce": True,
    "max_instances": 2,
})
```

### 项目根目录

`project_root` 用于解析工作流中的相对路径字符串引用：

```python
Scheduler(project_root="/data/projects/my_app")
```

作业添加时若工作流本身未指定 `project_root`，会自动继承调度器的配置。

### 元数据库与 .env

项目附带的管理元数据（用户、API Key、主题、变量等）通过 `schedflow.configs.settings.Settings` 读取环境变量或 `.env` 文件：

```ini
# .env
APP_ENV=production
HOST=0.0.0.0
PORT=8000
SCHEDFLOW_META_DB=scheduler_meta.db
```

内置默认即为**生产环境**（`APP_ENV=production`、`RELOAD=false`、`LOG_LEVEL=INFO`），
`schedflow-backend` / `schedflow-frontend` 直接启动即为生产模式。开发模式
（热重载、DEBUG 日志、Vite 热更新）只通过显式参数开启：

```bash
uv run schedflow-backend --dev
uv run schedflow-frontend --dev
```

生产模式不监听文件系统，因此运行期写入（如 `jobs.db`）不会产生
“changes detected”输出，也不会因热重载产生多个调度器进程。
