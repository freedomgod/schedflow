# 项目介绍

## SchedFlow 是什么？

SchedFlow 是一个轻量级的**定时任务工作流框架**，自带调度内核，提供触发器（何时运行）、执行器（如何运行）、作业存储（状态持久化）与后台调度循环等构件，并把“一个作业 = 一个函数调用”升级为“一个作业 = 一张 DAG 工作流图”。

底层接口采用显式、统一的设计：

- **显式 API**：所有公开方法都是显式关键字签名，`help()` 与 IDE 提示完整，没有 `*args/**kwargs` 魔法，也没有 `model=None, **kwargs` 式透传；
- **纯 Python 对象**：用户只接触 `Workflow`、`TaskSpec`、`Trigger`、`Job`、`Scheduler`、`JobStore`、`Executor` 等普通对象，Pydantic 模型降级为内部序列化层；
- **延迟引用解析**：函数可以传可调用对象，也可以传 `"模块:函数"` 字符串，字符串只在执行时解析——创建、持久化、重启都不会因模块缺失而失败；
- **不采用 `add_job(func, trigger, ...)` 式接口**：没有 `scheduled_job` 装饰器，接口按本库的语义设计。

## 设计动机

考虑一个典型的数据管道：

```text
数据提取 → 转换 → 验证 → 加载
                      ↘ 通知
```

在使用传统“一个作业 = 一个函数调用”的调度器时，你需要手工编排这些步骤——链接回调、协调并行、处理部分失败、收集执行日志。SchedFlow 把这些能力内置到框架里：

- **声明式依赖**——以 DAG 形式声明任务间的依赖关系；
- **自动并行**——同一拓扑层的无依赖任务自动并行执行；
- **失败传播**——上游失败或条件边不满足时，下游节点自动标记为 `skipped`；
- **执行追踪**——每次执行生成结构化 `ExecutionLog`，逐节点记录状态、结果、错误与耗时；
- **失败重试**——每个节点可独立配置重试次数、超时与成功/失败回调；
- **多样任务类型**——同一个工作流里可以混合 Python 函数、`.py` 脚本、内联代码片段与 Shell 命令。

## 架构总览

```text
┌──────────────────────────────────────────┐
│            Vue 3 管理面板                  │  ← DAG 编辑器、作业管理、执行日志
├──────────────────────────────────────────┤
│            FastAPI Web API (/api)         │  ← 结构化 JSON、统一响应
├──────────────────────────────────────────┤
│   Workflow（DAG 引擎）                     │  ← 拓扑排序、条件边、并行执行、环路检测
│   TaskSpec / Runner（任务定义与执行）       │
│   ExecutionLog（执行日志）                 │
├──────────────────────────────────────────┤
│   Scheduler → Trigger → JobStore          │  ← 调度循环、触发器、持久化
│                     → Executor            │  ← 线程/进程/异步执行
└──────────────────────────────────────────┘
```

### 核心对象

**Workflow（工作流，DAG）**——用户定义任务的主体。通过 `add_task()` 添加节点、`add_edge()` 添加带条件的依赖边，`run()` 直接执行，`to_dict()/from_dict()` 序列化。环路会在 `add_edge()` 时被检测并抛出 `CycleError`。

**TaskSpec（任务规格）**——描述一个节点“做什么”，支持四种执行类型：`python_callable`（Python 函数或字符串引用）、`python`（子进程运行 `.py` 脚本）、`python_script`（`python -c` 内联代码）、`bash`（Shell 命令）。用户通常通过 `Workflow.add_task()` 构建，无需直接构造。

**Trigger（触发器）**——决定作业“何时运行”。`DateTrigger` 单次、`IntervalTrigger` 固定间隔、`CronTrigger` 类 Cron 表达式、`CalendarIntervalTrigger` 日历边界对齐、`AndTrigger`/`OrTrigger` 组合。所有触发器都用显式关键字构造，并支持 `to_dict()/from_dict()`。

**Job（作业）**——顶层调度单元，把一个 `Workflow` 与触发器、执行器别名、存储别名、misfire 策略等元数据绑定在一起。

**Scheduler（调度器）**——调度主循环：从 JobStore 拉取到期的作业、计算下次运行时间、交给 Executor 执行、发布事件、持久化执行日志。仓库统一使用 `schedflow.core.Scheduler` 一个实现（主循环在后台线程中运行），支持多执行器/多存储器按 alias 路由；旧版 `schedflow.schedulers` 包已随迁移移除。

**JobStore（作业存储）**——作业与执行日志的持久化接口。内置 `MemoryJobStore`、`SQLAlchemyJobStore`、`RedisJobStore`、`MongoDBJobStore`，全部使用 JSON 序列化（不再使用 pickle），引用字符串在反序列化时绝不解析。

**Executor（执行器）**——决定作业“如何运行”。`ThreadPoolExecutor`（线程池，默认）、`ProcessPoolExecutor`（进程池，通过 JSON worker 协议在子进程重建作业，Windows 下可用）、`DebugExecutor`（同步直跑，用于测试）、`AsyncIOExecutor`（事件循环内执行）等。

**ExecutionLog（执行日志）**——一次工作流执行的完整记录：`log_id`、`flow_id`、`job_id`、起止时间、每个节点的 `TaskRecord`（状态、结果、错误、stdout/stderr、退出码、耗时）以及 DAG 快照。

## 数据流

一次完整的调度执行链路如下：

```text
定义 Workflow（add_task / add_edge）
      │
scheduler.add_job(workflow, trigger=..., job_id=...)   → 写入 JobStore（JSON）
      │
scheduler.start() → 主循环：get_due(now) → trigger 计算下次运行时间 → executor.submit(job, run_time)
      │
executor 调用 job.run() → workflow.run(max_workers=...) → 拓扑分组 → 组内并行、组间串行
      │
生成 ExecutionLog → jobstore.add_log() → 发布 job.succeeded / job.failed 等事件
      │
Web API / 前端消费：/api/jobs、/api/jobs/{id}/logs
```

## 项目状态

- 核心（Workflow / Trigger / Job / Scheduler / JobStore / Executor / Web API）均已可用并通过测试；
- 项目仍在积极开发中，功能演进见[更新日志](changelog.md)。
