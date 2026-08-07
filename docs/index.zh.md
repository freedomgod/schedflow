# SchedFlow

<div align="center" markdown>

**以有向无环图（DAG）模式运行定时任务**

[![PyPI](https://img.shields.io/pypi/v/schedflow)](https://pypi.org/project/schedflow/)
[![Python](https://img.shields.io/pypi/pyversions/schedflow)](https://pypi.org/project/schedflow/)
[![License](https://img.shields.io/github/license/freedomgod/schedflow)](https://github.com/freedomgod/schedflow/blob/main/LICENSE.txt)

</div>

SchedFlow 是一个轻量级的 **DAG 工作流调度框架**：一个“作业”不再只是一个函数调用，而是一张包含多个任务节点与依赖边的有向无环图。你可以定义具有依赖关系、条件分支和并行执行的复杂任务管道，并内置 cron/interval/date 等触发器、多种执行器与作业存储，以及完整的 REST API。

!!! note "接口说明"
    底层接口采用**显式参数签名**（IDE 可直接提示），用户不需要了解任何 Pydantic 验证模型。新代码统一从 `schedflow.core`、`schedflow.triggers`、`schedflow.api.rest` 导入。

## 核心特性

| 分类 | 特性 |
|------|------|
| **DAG 工作流** | `Workflow` 定义节点与依赖边：拓扑排序执行、同层并行、条件边、环路检测 |
| **任务类型** | Python 可调用对象 / `"模块:函数"` 字符串引用、`.py` 脚本文件、内联代码片段、Shell 命令 |
| **显式 API** | 所有公开方法均为显式关键字签名；`func` 直接传可调用对象，字符串引用延迟到执行时解析 |
| **触发器** | `DateTrigger` / `IntervalTrigger` / `CronTrigger` / `CalendarIntervalTrigger` / `AndTrigger` / `OrTrigger`，统一支持 `to_dict()/from_dict()` |
| **持久化** | `MemoryJobStore` / `SQLAlchemyJobStore` / `RedisJobStore` / `MongoDBJobStore`，统一 JSON 序列化，引用不预先解析 |
| **执行器** | `ThreadPoolExecutor` / `ProcessPoolExecutor`（JSON worker 协议，Windows 可用）/ `DebugExecutor` / `AsyncIOExecutor` 等 |
| **执行日志** | `ExecutionLog` 记录每个节点的状态、结果、错误、耗时与 DAG 快照，可持久化可查询 |
| **Web API** | FastAPI 结构化 REST API（`/api`），统一 `{"code": 0, "data": ..., "message": "ok"}` 响应格式 |
| **管理面板** | Vue 3 + Element Plus Web 界面：DAG 编辑器、作业管理、执行日志、暗色/亮色主题 |

## 快速示例

一个完整、可直接复制运行的示例：混合了多种任务类型，既可以直接执行，也可以交给调度器每 60 秒执行一次。

```python
from schedflow.core import Scheduler, Workflow
from schedflow.triggers import IntervalTrigger


# 任务函数 1：普通 Python 函数
def fetch(source: str) -> str:
    return f"data from {source}"


# 任务函数 2：通过 _pre_results 参数获取前一个节点的结果
def process(_pre_results) -> str:
    # _pre_results 是 {"上游节点ID": 返回值} 字典，这里是 {"fetch": "data from api"}
    return _pre_results["fetch"].upper()


# 条件边回调：接收上游节点的 TaskRecord，返回 True 才放行下游节点
def should_report(record) -> bool:
    return record.status == "succeeded" and bool(record.result)


# 1. 定义工作流，混合多种任务类型
wf = Workflow("etl")

# 任务类型 1：Python 函数（python_callable，默认）
wf.add_task("fetch", func=fetch, kwargs={"source": "api"}, retries=2)
# 任务类型 2：同上，但 func 也可以传 "模块:函数" 字符串，执行时才解析
wf.add_task("process", func=process)   # 例如 func="my_module:process"
# 任务类型 3：Shell 命令（bash，子进程执行）
wf.add_task("report", type="bash", command="echo report generated")
# 任务类型 4：内联 Python 代码（python_script，以 python -c 执行）
wf.add_task("summary", type="python_script", script="print('summary ok')")

wf.add_edge("fetch", "process")
wf.add_edge("process", "report", condition=should_report)  # 条件边
wf.add_edge("process", "summary")

# 2. 不经过调度器，直接执行一次
log = wf.run(max_workers=3)
print(log.succeeded, log.records["process"].result)  # True DATA FROM API

# 3. 交给调度器：每 60 秒执行一次
scheduler = Scheduler()
scheduler.on("job.succeeded", lambda e: print(f"job {e.job_id} 执行成功"))  # 事件订阅
scheduler.add_job(
    wf,
    trigger=IntervalTrigger(seconds=60),
    job_id="etl_job",
    misfire_grace_time=30,   # 错过执行的最大容忍秒数，超过则发布 job.missed
    max_instances=2,         # 同一作业的最大并发实例数
)
scheduler.start()

# Scheduler 的主循环运行在后台守护线程里：主线程必须保持存活，
# 否则程序一退出调度器也会停止，作业永远不会按 60 秒触发。
# 按 Ctrl+C 即可正常停止：
try:
    import time

    while True:
        time.sleep(1)
except KeyboardInterrupt:
    scheduler.shutdown()
    print("调度器已停止。")
```

!!! tip "想了解更完整的 API？"
    上面的示例演示了 DAG 定义、多种任务类型（`python_callable` / `bash` / `python_script`，第四种 `python` 脚本文件见下文）、`_pre_results` 结果传递、条件边、重试与调度器事件。更详细的逐步讲解见[快速上手](quickstart.md)，完整的 `Workflow` 用法见[DAG 工作流](user-guide/dag-workflow.md)。

## 开始探索

- **[项目介绍](introduction.md)** — 设计动机与整体架构
- **[安装指南](installation.md)** — 选择合适的 extras 安装
- **[快速上手](quickstart.md)** — 5 分钟完成第一个工作流
- **[用户指南](user-guide/core-features.md)** — 调度器、触发器、存储、执行器详解
- **[API 参考](api-reference/index.md)** — 完整 API 文档

!!! tip "语言切换"
    本网站默认展示中文文档；英文版位于 `/en/`。点击页面右上角的语言下拉框即可切换。
