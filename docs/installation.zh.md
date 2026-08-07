# 安装指南

## 环境要求

- **Python** 3.11 及以上
- **pip**（或 [uv](https://docs.astral.sh/uv/)、[pipx](https://pipx.pypa.io/)）

## 基础安装

安装核心包，包含默认的内存作业存储和线程池执行器：

```bash
pip install schedflow
```

安装后即可使用：

- 完整的 DAG 工作流引擎（`Workflow`、`TaskSpec`、`ExecutionLog`）
- 所有触发器类型（`date`、`interval`、`cron`、`calendarinterval`、`and`、`or`）
- 内存作业存储（`MemoryJobStore`）
- 线程池执行器（`ThreadPoolExecutor`）与调试执行器（`DebugExecutor`）
- 统一的 `Scheduler` 与 Web API 骨架（`create_app` 需要额外安装 FastAPI，见下）

## 可选依赖

SchedFlow 使用 extras 机制保持依赖最小化，按需安装：

### 数据库作业存储

```bash
# SQLAlchemy（SQLite、PostgreSQL、MySQL 等）
pip install schedflow[sqlalchemy]

# MongoDB
pip install schedflow[mongodb]

# Redis
pip install schedflow[redis]
```

### 可选执行器

```bash
# Gevent 执行器
pip install schedflow[gevent]

# Tornado 执行器
pip install schedflow[tornado]

# Twisted 执行器
pip install schedflow[twisted]
```

!!! note "关于 AsyncIO"
    核心调度器提供两类执行器：常规的 `ThreadPoolExecutor` / `ProcessPoolExecutor` /
    `DebugExecutor`（`core.executor`）与异步系的 `AsyncIOExecutor` /
    `GeventExecutor` / `TornadoExecutor` / `TwistedExecutor`
    （`core.async_executors`），均实现统一的 `Executor` 接口。

### Web API

```bash
pip install schedflow[web]
```

此命令会安装 FastAPI、Uvicorn 与认证依赖（passlib、PyJWT）。Vue 3 前端管理面板随包一同分发。

### 一次性安装全部

```bash
pip install schedflow[all]  # 安装全部可选依赖
```

!!! tip "推荐使用 uv 加速安装"
    ```bash
    uv pip install schedflow[web,sqlalchemy]
    ```

## 从源码安装

```bash
git clone https://github.com/freedomgod/schedflow.git
cd schedflow
pip install -e .[web,sqlalchemy,test]
```

## 验证安装

```python
import schedflow
print(schedflow.__version__)

from schedflow.core import Scheduler, Workflow


def hello() -> str:
    return "hello"


workflow = Workflow("smoke")
workflow.add_task("hello", func=hello)

scheduler = Scheduler()
scheduler.add_job(workflow, job_id="smoke_job")   # 无触发器：仅手动执行
log = scheduler.run_job_now("smoke_job")
print(log.records["hello"].result)                # hello
scheduler.shutdown()
```

## 构建文档（开发用）

```bash
pip install -e .[doc]
mkdocs serve      # 本地预览 http://localhost:8000
mkdocs build      # 构建静态站点到 site/
```

## 下一步

- 跟随**[快速上手](quickstart.md)**创建你的第一个 DAG 工作流
- 浏览**[核心功能](user-guide/core-features.md)**了解调度器、触发器与存储
- 浏览**[API 参考](api-reference/index.md)**了解完整接口
