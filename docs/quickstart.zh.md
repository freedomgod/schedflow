# 快速上手

本指南将带你创建并运行第一个 SchedFlow DAG 工作流。示例代码均可直接复制运行。

## 准备工作

确保已[安装](installation.md) SchedFlow：

```bash
pip install schedflow
```

## 步骤 1：定义任务函数

创建一个 Python 文件（例如 `my_workflow.py`），定义工作流中需要执行的函数：

```python
def fetch_data(**kwargs):
    """模拟从 API 获取数据。"""
    print("正在获取数据...")
    return {"temperature": 25.4, "humidity": 0.68}


def process_data(_pre_results=None, **kwargs):
    """处理数据，接收上游任务的输出结果。"""
    upstream = list(_pre_results.values())[0] if _pre_results else {}
    temp = upstream.get("temperature", 0)
    humidity = upstream.get("humidity", 0)
    return {"heat_index": temp * humidity * 100}


def alert(**kwargs):
    """发送告警。"""
    print("告警！工作流已完成。")
    return "alert sent"
```

!!! tip "函数参数"
    - 上游节点的返回值会通过 `_pre_results` 关键字参数注入（它是“节点 ID → 结果”的字典）；
    - 框架会根据函数签名自动过滤不接受的参数，所以给函数多传参数也不会报 `TypeError`；
    - 也可以直接传 `"模块:函数"` 字符串（例如 `"my_workflow:fetch_data"`），字符串引用会在执行时解析。

## 步骤 2：构建 DAG 工作流

使用 `Workflow` 定义节点与依赖边：

```python
from schedflow.core import Workflow

wf = Workflow("data_pipeline")

# 添加任务节点：fetch → process → alert
wf.add_task("fetch", func=fetch_data, name="获取数据")
wf.add_task("process", func=process_data, name="处理数据")
wf.add_task("alert", func=alert, name="发送告警")

# 添加依赖边，决定执行顺序
wf.add_edge("fetch", "process")
wf.add_edge("process", "alert")
```

`add_task()` 的第一个参数是节点 ID（同一工作流内必须唯一），`func` 可以直接传函数对象或字符串引用。`add_edge(source, target)` 定义依赖关系；添加边时会自动做**环路检测**，若成环会抛出 `CycleError` 且不落边。

## 步骤 3：直接执行工作流

不经过调度器，直接调用 `run()` 执行一次：

```python
log = wf.run(max_workers=3)

print("执行成功:", log.succeeded)
for node_id, record in log.records.items():
    print(f"  {node_id}: {record.status} 结果={record.result}")
```

执行模型：同一拓扑层的节点并行执行（`max_workers` 控制并行度），层与层之间串行。执行结束后返回 `ExecutionLog`，其中 `records` 按节点 ID 记录状态、结果、错误、耗时等。

## 步骤 4：交给调度器定时执行

```python
from schedflow.core import Scheduler
from schedflow.triggers import IntervalTrigger

scheduler = Scheduler()

scheduler.add_job(
    wf,
    trigger=IntervalTrigger(seconds=60),   # 每 60 秒执行一次
    job_id="data_pipeline_job",
    name="数据管道",
    max_instances=2,
    misfire_grace_time=30,
)

scheduler.start()

import time
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    scheduler.shutdown()
    print("调度器已停止。")
```

!!! note "为什么需要循环保持进程存活？"
    `Scheduler.start()` 的主循环运行在**后台守护线程**中，`start()` 本身会立即返回。如果主线程随后直接退出，进程结束、调度器也随之停止——这是“加了作业却看不到定时执行”的最常见原因。上面的 `while True` 只是让主线程保持存活，也可以用任何其他方式阻塞主线程（例如等待事件、运行 Web 服务等）。

所有触发器都用显式关键字构造：`IntervalTrigger(seconds=60)`、`CronTrigger(hour=3, minute=0)`、`DateTrigger(run_date="2026-08-01 10:00:00")` 等，详见[核心功能](user-guide/core-features.md)。

## 步骤 5：添加条件分支

给边附加一个条件函数，只有当上游满足条件时下游节点才会执行，否则被标记为 `skipped`：

```python
def should_alert(record) -> bool:
    """仅当 heat_index 超过 1500 时触发告警。"""
    return bool(record.result) and record.result.get("heat_index", 0) > 1500


wf.add_edge("process", "alert", condition=should_alert)

log = wf.run()
# 本例 heat_index = 25.4 * 0.68 * 100 = 1727 > 1500，条件成立，alert 会正常执行
print(log.records["alert"].status)          # succeeded
```

条件函数接收上游节点的 `TaskRecord`，返回 `True` 放行、`False` 跳过。若上游节点执行失败，下游节点也会被自动标记为 `skipped`，不受影响的分支继续执行。

## 步骤 6：通过 Web API 管理（可选）

Web API 提供结构化 REST 接口，与 SDK 一一对应：

```python
from schedflow.api.rest import create_app
from schedflow.core import Scheduler

scheduler = Scheduler()
app = create_app(scheduler, title="调度器 API")

# 启动：uvicorn my_module:app
```

也可以直接用项目自带的 CLI 同时启动后端与前端管理面板。两个命令**默认生产模式**，只有添加 `--dev` 才切换为开发环境：

```bash
uv run schedflow-backend         # 生产模式：关闭热重载、INFO 日志（默认）
uv run schedflow-backend --dev   # 开发模式：热重载 + DEBUG 日志
uv run schedflow-frontend        # 生产模式：构建（按需）后 vite preview（默认）
uv run schedflow-frontend --dev  # 开发模式：Vite 开发服务器（热更新）
```

完整端点列表与请求示例见[高级用法](user-guide/advanced-usage.md)中的 Web API 章节。

## 下一步

- 了解**[核心功能](user-guide/core-features.md)**——触发器、作业存储、执行器与事件
- 学习**[高级用法](user-guide/advanced-usage.md)**——重试、超时、序列化与自定义组件
- 深入**[DAG 工作流](user-guide/dag-workflow.md)**——完整的 Workflow API 参考
- 浏览**[API 参考](api-reference/index.md)**——完整的 API 文档
