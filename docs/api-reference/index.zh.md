# API 参考

本部分通过 `mkdocstrings` 直接从 Python 源码 docstring 生成 API 文档，对应项目的**公开接口**。用户侧只需关注 `schedflow.core`、`schedflow.triggers` 与 `schedflow.api.rest`。

## 核心对象（schedflow.core）

### 工作流（Workflow）

::: schedflow.core.workflow
    options:
      heading_level: 3

### 任务规格（TaskSpec）

::: schedflow.core.spec
    options:
      heading_level: 3

### 执行日志（ExecutionLog / TaskRecord）

::: schedflow.core.log
    options:
      heading_level: 3

### 任务结果（TaskResult）

::: schedflow.core.result
    options:
      heading_level: 3

### 作业（Job）

::: schedflow.core.job
    options:
      heading_level: 3

### 调度器（Scheduler）

::: schedflow.core.scheduler
    options:
      heading_level: 3

### 作业存储接口（JobStore / MemoryJobStore）

::: schedflow.core.jobstore
    options:
      heading_level: 3

### 执行器（Executor / Thread / Process / Debug）

::: schedflow.core.executor
    options:
      heading_level: 3

### 事件（EventBus / SchedulerEvent）

::: schedflow.core.events
    options:
      heading_level: 3

### 执行上下文（RunContext）

::: schedflow.core.context
    options:
      heading_level: 3

### 引用解析（resolve_ref / RefResolveError）

::: schedflow.core.resolve
    options:
      heading_level: 3

## 持久化实现（core.stores）

### SQLAlchemy 作业存储

::: schedflow.core.stores.sqlalchemy
    options:
      heading_level: 3

### Redis 作业存储

::: schedflow.core.stores.redis
    options:
      heading_level: 3

### MongoDB 作业存储

::: schedflow.core.stores.mongo
    options:
      heading_level: 3

## 触发器（schedflow.triggers）

### 触发器基类与序列化

::: schedflow.triggers.base
    options:
      heading_level: 3

### IntervalTrigger

::: schedflow.triggers.interval
    options:
      heading_level: 3

### CronTrigger

::: schedflow.triggers.cron
    options:
      heading_level: 3

### DateTrigger

::: schedflow.triggers.date
    options:
      heading_level: 3

### CalendarIntervalTrigger

::: schedflow.triggers.calendarinterval
    options:
      heading_level: 3

### 组合触发器（And / Or）

::: schedflow.triggers.combining
    options:
      heading_level: 3

## 运行器（schedflow.runners）

### 运行器基类

::: schedflow.runners.base
    options:
      heading_level: 3

### 运行器注册表

::: schedflow.runners.registry
    options:
      heading_level: 3

### Python 可调用运行器

::: schedflow.runners.python_callable_runner
    options:
      heading_level: 3

### Bash 运行器

::: schedflow.runners.bash_runner
    options:
      heading_level: 3

### Python 文件运行器

::: schedflow.runners.python_file_runner
    options:
      heading_level: 3

### Python 内联代码运行器

::: schedflow.runners.python_snippet_runner
    options:
      heading_level: 3

## Web API（schedflow.api.rest）

### 应用工厂与路由挂载

::: schedflow.api.rest
    options:
      heading_level: 3

### 请求/响应 Schema

::: schedflow.api.rest.schemas
    options:
      heading_level: 3

### 路由

::: schedflow.api.rest.routers
    options:
      heading_level: 3

## 工具（schedflow.utils）

::: schedflow.utils
    options:
      heading_level: 3
