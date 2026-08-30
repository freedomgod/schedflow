# SchedFlow

<div align="center">

**🌐 [中文](README.md) · [English](README_EN.md)**

</div>

> **文档**：[中文文档](https://schedflow.readthedocs.io/zh-cn/latest/) · [English Docs](https://schedflow.readthedocs.io/zh-cn/latest/en/)

**轻量级定时任务工作流框架——每个 Job 以有向无环图（DAG）工作流的方式执行。**

[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE.txt)
[![PyPI](https://img.shields.io/badge/pypi-schedflow-orange)](https://pypi.org/project/schedflow/)
[![Documentation](https://img.shields.io/badge/docs-readthedocs-brightgreen)](https://schedflow.readthedocs.io/zh-cn/latest/)

SchedFlow 把传统“一个 Job = 一次函数调用”的定时任务模型升级为“一个 Job = 一张 DAG 工作流图”：任务节点 + 依赖边、条件分支、并行执行、逐节点重试与回调、结构化执行日志、持久化、REST API 与 Web 管理面板。

新代码统一从 `schedflow.core`、`schedflow.triggers` 与 `schedflow.api.rest` 导入。

## 核心特性

| 分类 | 特性 |
|------|------|
| **DAG 工作流** | `Workflow`：`add_task()` 定义节点、`add_edge()` 定义依赖边，内置环路检测、拓扑排序执行、同层并行 |
| **任务类型** | `python_callable`（可调用对象或 `"模块:函数"` 字符串）、`python`（`.py` 脚本）、`python_script`（内联代码）、`bash`（Shell 命令） |
| **显式 API** | 全部显式关键字签名；字符串引用只在执行时解析 |
| **触发器** | `DateTrigger`、`IntervalTrigger`、`CronTrigger`、`CalendarIntervalTrigger`、`AndTrigger`、`OrTrigger`；统一 `to_dict()/from_dict()` |
| **持久化** | `MemoryJobStore`、`SQLAlchemyJobStore`、`RedisJobStore`、`MongoDBJobStore`；纯 JSON 序列化，反序列化不解析引用 |
| **执行器** | `ThreadPoolExecutor`、`ProcessPoolExecutor`（JSON worker 协议，Windows 可用）、`DebugExecutor` |
| **执行日志** | `ExecutionLog` / `TaskRecord`：逐节点状态、结果、错误、耗时、stdout/stderr 与 DAG 快照 |
| **Web API** | FastAPI REST API（`/api`），统一 `{"code": 0, "data": ..., "message": "ok"}` 响应 |
| **管理面板** | Vue 3 + Element Plus：DAG 编辑器、作业管理、执行日志、暗色/亮色主题 |

## 快速开始

一个完整、可直接运行的示例：混合多种任务类型，演示直接执行与每 60 秒定时执行：

```python
from schedflow.core import Scheduler, Workflow
from schedflow.triggers import IntervalTrigger


def fetch(source: str) -> str:
    return f"data from {source}"


def process(_pre_results) -> str:
    # _pre_results = {"fetch": "data from api"} —— 前置节点的返回值字典
    return _pre_results["fetch"].upper()


def should_report(record) -> bool:
    return record.status == "succeeded" and bool(record.result)


wf = Workflow("etl")
# 任务类型 1：Python 函数（python_callable，默认）
wf.add_task("fetch", func=fetch, kwargs={"source": "api"}, retries=2)
# 任务类型 2：func 也可以传 "模块:函数" 字符串引用
wf.add_task("process", func=process)
# 任务类型 3：Shell 命令（bash）
wf.add_task("report", type="bash", command="echo report generated")
# 任务类型 4：内联 Python 代码（python_script）
wf.add_task("summary", type="python_script", script="print('summary ok')")

wf.add_edge("fetch", "process")
wf.add_edge("process", "report", condition=should_report)  # 条件边
wf.add_edge("process", "summary")

# 不经过调度器，直接执行一次
log = wf.run(max_workers=3)
print(log.succeeded, log.records["process"].result)   # True DATA FROM API

# 交给调度器：每 60 秒执行一次
scheduler = Scheduler()
scheduler.add_job(
    wf,
    trigger=IntervalTrigger(seconds=60),
    job_id="etl_job",
    misfire_grace_time=30,
    max_instances=2,
)
scheduler.start()

# 调度器主循环运行在后台守护线程中——主线程必须保持存活，
# 否则进程退出后作业永远不会按 60 秒触发。
try:
    import time

    while True:
        time.sleep(1)
except KeyboardInterrupt:
    scheduler.shutdown()
```

## 安装

需要 Python 3.11 及以上版本。

```bash
pip install schedflow                  # 核心包
pip install schedflow[sqlalchemy]      # SQLAlchemy 作业存储
pip install schedflow[redis]           # Redis 作业存储
pip install schedflow[mongodb]         # MongoDB 作业存储
pip install schedflow[web]             # FastAPI Web API
pip install schedflow[all]             # 全部可选依赖
```

## 核心概念

- **Workflow**——DAG 工作流。`add_task()` 添加节点、`add_edge()` 添加（可带条件的）依赖边并自动做环路检测；`run()` 直接执行；`to_dict()/from_dict()` 是唯一的 JSON 序列化路径。
- **TaskSpec**——一个节点“做什么”，四种类型：`python_callable`、`python`、`python_script`、`bash`。
- **Trigger**——作业“何时运行”：`DateTrigger`、`IntervalTrigger`、`CronTrigger`、`CalendarIntervalTrigger`、`AndTrigger`/`OrTrigger`。
- **Job**——把 `Workflow` 与触发器及调度元数据（misfire 容差、合并、最大并发实例）绑定在一起。
- **Scheduler**——调度主循环。增删改查、暂停/恢复、立即执行、持久化与查询执行日志、事件订阅。
- **JobStore**——作业与日志的持久化：`MemoryJobStore`、`SQLAlchemyJobStore`、`RedisJobStore`、`MongoDBJobStore`。
- **Executor**——作业“如何运行”：`ThreadPoolExecutor`、`ProcessPoolExecutor`、`DebugExecutor`。
- **ExecutionLog / TaskRecord**——每次执行、每个节点的状态、结果、错误、耗时与输出捕获。

## Web API（FastAPI）

```python
from schedflow.api.rest import create_app
from schedflow.core import Scheduler

app = create_app(Scheduler(), title="调度器 API")
# uvicorn my_module:app
```

主要端点（均在 `/api` 下）：作业 CRUD + `pause` / `resume` / `run` / `reschedule`、作业执行日志、调度器 `status` / `start` / `pause` / `resume` / `shutdown`。所有响应统一为 `{"code": 0, "data": ..., "message": "ok"}`。

## 启动 Web 管理面板

两个 CLI 命令默认以**生产模式**运行；只有显式添加 `--dev` 才切换为开发模式：

```bash
uv run schedflow-backend        # 生产模式：关闭热重载、INFO 日志（默认）
uv run schedflow-backend --dev  # 开发模式：热重载 + DEBUG 日志

uv run schedflow-frontend        # 生产模式：构建（按需）后以 vite preview 提供服务（默认）
uv run schedflow-frontend --dev  # 开发模式：Vite 开发服务器（热更新）
```

生产模式默认不启用文件监听，避免 `data/jobs.db` 等运行期文件的写入被 uvicorn 热重载器当作“变更”打印，也不会因热重载产生多个调度器进程。开发模式下，`data/jobs.db`、`.git` 等文件已被加入重载排除列表，不会触发重启或刷屏。

## 开发

```bash
python -m pytest          # 运行测试
ruff check .              # 代码检查
```

可运行示例见 [`examples/`](examples/README.md)。

## 许可证

MIT —— 详见 [LICENSE.txt](LICENSE.txt)。
