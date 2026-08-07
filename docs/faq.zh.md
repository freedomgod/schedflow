# 常见问题

## 工作流与任务

### 支持哪些 Python 版本？

Python 3.11、3.12、3.13。

### 能否在一个工作流中混合多种任务类型？

可以。每个节点独立配置 `type`：一个节点调用 Python 函数，另一个节点运行 `.py` 脚本，第三个节点执行 Shell 命令，互不影响。

### 任务失败时会发生什么？

依赖失败节点的下游会被标记为 `skipped`（`skip_reason` 说明原因）；不受影响的并行分支继续执行。节点可配置 `retries` 重试。若工作流存在任一 `failed` 节点，`log.succeeded` 为 `False`，调度器会发布 `job.failed` 事件。

### 下游任务如何访问上游结果？

在任务函数中声明 `_pre_results` 关键字参数，它会收到“前置节点 ID → 返回值”的字典。框架会自动过滤函数不接受的参数，所以不声明也不会报错。

### `Workflow("etl")` 的 flow_id 和 `add_job(..., job_id=...)` 的 job_id 有什么区别？

它们属于不同层级：

- `flow_id` 是 **Workflow（工作流定义）** 的名字，创建时可选（省略则为 `None`）。它出现在 `ExecutionLog.flow_id` 与 `Workflow.to_dict()` 的 `flow_id` 字段中，只作为工作流的标识/标签，**不要求唯一**——多份作业可以共享同一个 `flow_id`；
- `job_id` 是 **Job（调度作业）** 在 JobStore 中的**唯一键**，用于 `get_job()` / `update_job()` / `remove_job()` / `pause_job()`，也是事件里的 `event.job_id` 与日志查询（`/api/jobs/{job_id}/logs`）的键；省略时自动生成 UUID。

执行产生的 `ExecutionLog` 会同时携带两者：`log.flow_id` 来自工作流，`log.job_id` 来自作业。直接调用 `Workflow.run()` 时没有 Job，`log.job_id` 为 `None`。典型场景：同一份工作流（相同 `flow_id`）可以按不同触发器注册成多个 `job_id` 的作业。

### 能创建循环依赖吗？

不能。`Workflow.add_edge()` 会做环路检测，成环时抛出 `CycleError` 且不写入该边。

### 为什么 `func` 传 lambda 或嵌套函数会报错？

`to_dict()` 需要把函数转成字符串引用才能持久化；lambda、局部嵌套函数没有稳定引用，序列化时会抛出 `ValueError`。仅限当前进程直接执行且不需要持久化的场景可以使用；跨进程（进程池）或持久化场景请使用 `"模块:函数"` 字符串引用。

### 字符串引用为什么“创建时不报错”？

引用在**执行时**才解析（延迟解析）。这样做的目的是：作业创建、持久化、重启都不依赖目标模块是否可导入，模块缺失只会让对应节点在执行时失败并记录到 `TaskRecord`，而不会让作业本身被静默丢弃。

## 调度与部署

### 如何在调度器重启后持久化作业？

使用持久化作业存储，如 `SQLAlchemyJobStore`、`RedisJobStore` 或 `MongoDBJobStore`，并保证工作流节点使用字符串引用：

```python
from schedflow.core import Scheduler
from schedflow.core.stores.sqlalchemy import SQLAlchemyJobStore

scheduler = Scheduler(jobstore=SQLAlchemyJobStore(url="sqlite:///jobs.db"))
```

### 能否运行多个调度器实例？

多个实例共享同一个持久化存储即可看到相同的作业定义，但目前**没有内置分布式锁**——请自行确保同一作业不会被多个实例重复触发（例如按实例拆分作业，或只在主实例上运行调度器）。

### 启动后端时为什么输出大量 “X changes detected”？

那是 uvicorn **热重载（reload）** 的文件监听器（watchfiles）打印的。默认启动方式是生产模式（`RELOAD=false`），不会监听文件；只有使用 `schedflow-backend --dev` 时才会开启热重载。开发模式下已把运行期会持续变化的路径加入排除列表（`jobs.db`、`*.db-journal`、`.git/**`、`node_modules/**`、`dist/**`），因此 jobs.db 写入和 Git fsmonitor 的临时文件不会再触发这类输出。

另外，热重载会在代码变更时重建调度器进程，若旧进程没有干净退出，会出现多个调度器同时写同一个 `jobs.db`，可能造成同一作业重复执行（这也是此前“几秒内执行几十次”的诱因之一）。**生产部署请直接运行 `uv run schedflow-backend`（不带 `--dev`），并确保同一时间只有一个后端进程。**

### 进程池在 Windows 上能用吗？

可以。`ProcessPoolExecutor` 通过 JSON worker 协议在子进程重建作业（`spawn`），不再 pickle 调度器/函数对象。前提是节点使用字符串引用，且节点结果可 JSON 序列化。

### 作业没有在预期时间运行？

- 确认调度器已 `start()` 且状态不是 `paused`；
- 检查作业的 `next_run_time` 与触发器配置；
- 检查是否超过 `misfire_grace_time`（超出的运行会被跳过并发布 `job.missed`）；
- 检查是否达到 `max_instances`（超出会发布 `job.max_instances`）；
- 查看 `get_job_logs()` 中的执行日志定位具体节点的失败原因。

### 订阅了 `scheduler.on("task.executed", ...)` 却没有输出？

请确认两点：

- **作业确实经过调度器执行**——`task.*` 事件只在调度器执行路径发布（定时触发或 `run_job_now()`）。直接调用 `Workflow.run()` 不经过调度器，不会发布任何事件，此时请读取返回的 `ExecutionLog`；
- **订阅的是同一个调度器**——每个 `Scheduler` 有自己独立的 `EventBus`，`scheduler.on(...)` 只接收该调度器发布的事件；在独立创建的 `EventBus()` 上订阅、却期待其它调度器的事件，同样收不到。

## Web API 与前端

### 如何启用认证？

Web API（`create_app`）默认不启用认证，可手动挂载 `AuthMiddleware`，使用内置的 `JWTBackend`/`APIKeyBackend` 或自定义 `AuthBackend`，示例见[高级用法](user-guide/advanced-usage.md)的“认证”章节。

### 前端支持移动端吗？

Vue 3 管理面板通过 Element Plus 与响应式 CSS 适配平板和桌面端；手机端优化尚未完成。

### Web API 有 SSE 实时推送吗？

目前没有。Web API 提供日志查询端点，前端可轮询，或订阅 SDK 事件自行实现推送。

## 文档与构建

### 为什么 `mkdocs serve` 出现“Material for MkDocs / MkDocs 2.0”警告？

这是 Material 主题对新版 MkDocs 2.0 的**信息性公告**，不影响当前构建与使用（警告链接自 squidfunk.github.io）。本仓库锁定的依赖为 MkDocs 1.x 系列，构建正常。

### 构建文档时提示需要 Black 或 Ruff？

`mkdocstrings` 需要其一才能格式化函数签名。安装 `.[doc]`（已包含 `ruff`）即可消除该提示。

### 为什么 readthedocs 的 `/zh-cn/latest/` 链接会 404？

这是站点根路径与 RTD 语言前缀不匹配造成的。当前配置已把中文设为默认语言，并把 `site_url` 指向 `https://schedflow.readthedocs.io/zh-cn/latest/`，语言切换链接会带上该前缀。若仍出现 404，请确认 RTD 项目的语言设置为“Chinese (Simplified)”，并使用最新构建版本。
