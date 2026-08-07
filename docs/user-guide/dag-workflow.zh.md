# DAG 工作流

DAG 工作流引擎是 SchedFlow 的核心差异化特性。本指南覆盖 `Workflow` 的完整用法：节点、边、执行模型、结果传递、条件分支、序列化与执行日志。

## Workflow 概览

`Workflow` 是一张有向无环图：**节点 = 任务，边 = 依赖**。它负责定义、校验与直接执行工作流，不依赖调度器。

```python
from schedflow.core import Workflow

wf = Workflow("etl", project_root="./my_project")   # flow_id 可选；project_root 用于解析相对路径引用
```

## 添加任务节点（add_task）

```python
node_id = wf.add_task(
    "fetch",                          # 节点 ID（工作流内唯一，必填）
    func=fetch_data,                  # Python 可调用对象或 "模块:函数" 字符串
    name="获取数据",                   # 可选，可读名称
    description="从 API 拉取数据",     # 可选，描述
    type="python_callable",           # 任务类型，见下表
    command=None,                     # type="bash" 时的 Shell 命令
    script_path=None,                 # type="python" 时的 .py 脚本路径
    script=None,                      # type="python_script" 时的内联代码
    args=[],                          # 位置参数（python_callable 使用）
    kwargs={"source": "api"},         # 关键字参数
    retries=1,                        # 最多尝试次数（含首次）
    timeout=None,                     # 单次尝试超时（秒）
    on_success=None,                  # 成功回调（接收返回值）
    on_failure=None,                  # 失败回调（接收错误信息）
)
```

### 任务类型

| type | 必填字段 | 执行方式 |
|------|----------|----------|
| `python_callable`（默认） | `func`（可调用对象或字符串引用） | 当前进程内直接调用 |
| `python` | `script_path` | 子进程执行 `python <script_path>` |
| `python_script` | `script` | 子进程执行 `python -c <script>` |
| `bash` | `command` | 子进程执行 Shell 命令（Windows 下自动回退 `cmd /c`） |

```python
wf.add_task("bash_step", type="bash", command="echo hello && ls", timeout=30)
wf.add_task("script_step", type="python", script_path="./run.py", args=["--fast"])
wf.add_task("inline", type="python_script", script="print(sum(range(10)))")
```

重复的节点 ID 会抛出 `ValueError`。

## 添加依赖边（add_edge）

```python
wf.add_edge(
    "fetch",                # 源节点 ID（必须已存在）
    "process",              # 目标节点 ID（必须已存在）
    condition=None,         # 条件函数或字符串引用：condition(record) -> bool
    name=None,              # 可选
    description=None,       # 可选
)
```

添加边时自动做**环路检测**：若新边会形成环，抛出 `CycleError` 且该边不会写入。端点不存在的边同样会被拒绝：

```python
from schedflow.core import CycleError

try:
    wf.add_edge("c", "a")          # 若 a→b→c 已存在，这会产生环
except CycleError as exc:
    print(exc)                     # Edge 'c' -> 'a' would create a cycle; not added
```

### 未连接的“孤岛”节点

`Workflow` **允许**存在没有任何入边/出边的节点——不报错，`to_dict()`/持久化也正常。执行时这类节点：

- 没有前置依赖，会被放入**第 0 代**，与其它根节点并行执行（占用一个 `max_workers` 名额，不注入 `_pre_results`）；
- 结果/错误照常记录到 `ExecutionLog` 的 `TaskRecord`，并发布对应的 `task.*` 事件；
- 由于**代与代之间串行**，一个很慢的孤岛节点会拖慢整份工作流的完成时间——第 0 代必须整体结束才会进入下一层；
- 失败语义不受“隔离”保护：孤岛节点失败会把整份作业标记为 `failed`（发布 `job.failed`），但主链节点不受影响、照常执行。

如果你的本意是让某个独立任务**不与主链互相拖累**，建议把它拆成单独的 `Job` 注册到调度器，而不是放进同一张工作流。

## 直接执行（run）

```python
log = wf.run(
    max_workers=3,      # 同一拓扑层的并行度上限
    executor="thread",  # 目前仅支持线程执行（默认）
    inputs={"api_key": "secret"},   # 注入到每个节点的额外关键字参数
)
```

执行模型：

1. 对 DAG 做**拓扑排序**，按“代”分组；
2. 同一代内的节点并行执行（受 `max_workers` 限制），代与代之间串行；
3. 执行前置检查：前置节点必须 `succeeded`，且所有入边条件必须为 `True`；不满足则节点标记为 `skipped`；
4. 所有代执行完成后生成 `ExecutionLog`。

```text
    A ──→ C ──→ E
    ↓     ↓
    B ──→ D

第 0 代: [A, B]   ← 并行
第 1 代: [C, D]   ← 并行（A、B 完成后）
第 2 代: [E]      ← C、D 完成后
```

!!! warning "进程执行"
    目前 `Workflow.run()` 只支持线程执行（`executor="process"` 会抛出 `NotImplementedError`）。需要进程池时，请把工作流交给 `Scheduler` + `ProcessPoolExecutor`，由执行器层在子进程中重建并运行作业。

## 前置结果（_pre_results）

下游节点通过 `_pre_results` 关键字参数接收所有已成功前置节点的返回值（节点 ID → 结果）：

```python
def combine(_pre_results):
    total = sum(value["amount"] for value in _pre_results.values())
    return {"total": total}
```

框架会根据函数签名**自动过滤**不接受的参数——即使你的函数不声明 `_pre_results`，也不会因为多传参数而报错。

## 条件边

条件函数接收上游节点的 `TaskRecord`，返回 `True` 放行、`False` 跳过：

```python
def should_continue(record) -> bool:
    return record.status == "succeeded" and record.result.get("value", 0) > 100


wf.add_edge("check", "next", condition=should_continue)
```

条件不满足时，目标节点标记为 `skipped` 并记录 `skip_reason`。前置节点失败同样会导致下游 `skipped`；不受影响的并行分支继续执行。若整个工作流没有任何节点 `failed`，`log.succeeded` 为 `True`（`skipped` 不视为失败）。

## 重试、超时与回调

```python
def notify_success(retval):
    print("完成：", retval)


def notify_failure(error):
    print("失败：", error)


wf.add_task(
    "flaky",
    func=flaky_func,
    retries=5,           # 最多尝试 5 次
    timeout=30,          # 单次尝试 30 秒超时
    on_success=notify_success,
    on_failure=notify_failure,
)
```

重试用尽后节点才记为 `failed`；回调在节点状态记录之后调用，回调自身的异常不会影响节点结果。

## 执行日志（ExecutionLog）

每次执行返回一个 `ExecutionLog`：

```python
log = wf.run()

log.log_id                 # 自动生成的日志 ID（flowlog_xxx）
log.flow_id                # "etl"
log.job_id                 # 调度器执行时填充，直接 run 时为 None
log.start_time / log.end_time / log.duration
log.succeeded              # 没有节点 failed 即为 True
log.failed_nodes()         # [TaskRecord, ...]
log.skipped_nodes()        # [TaskRecord, ...]
log.records                # {node_id: TaskRecord}
log.dag_snapshot           # 执行时的 DAG 结构快照（JSON）

record = log.records["fetch"]
record.status              # pending/running/succeeded/failed/skipped
record.result              # 节点返回值
record.error               # 失败原因
record.skip_reason         # 跳过原因
record.stdout / record.stderr / record.exit_code   # 子进程类任务
record.start_time / record.end_time / record.duration
```

## 序列化与反序列化

```python
data = wf.to_dict()          # 唯一 JSON 出口
restored = Workflow.from_dict(data)
```

序列化规则：

- 引用字符串（`ref`）**原样存储**，反序列化绝不解析；
- 直接传入且无法转为引用（如 lambda、嵌套闭包）的可调用对象在 `to_dict()` 时会抛出 `ValueError`——跨进程/持久化场景请使用字符串引用；
- 工作流执行时会把结构快照写入 `log.dag_snapshot`；若快照失败（例如含 lambda），会降级为只记录节点与边的结构。

## 与调度器配合

工作流定义与执行解耦：同一份 `Workflow` 可以同时用于直接执行、注册到调度器、或通过 Web API 创建：

```python
scheduler.add_job(wf, trigger=IntervalTrigger(hours=1), job_id="etl_hourly")

# 也可以直接传 JSON 字典（等价于先 from_dict 再注册）
scheduler.add_job(wf.to_dict(), trigger=IntervalTrigger(hours=1), job_id="etl_hourly")
```
