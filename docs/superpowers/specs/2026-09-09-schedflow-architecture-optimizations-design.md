# SchedFlow 架构优化设计（P0/P1/P2）

> 日期：2026-09-09
> 状态：待评审
> 范围：单进程、轻量的工作流调度系统架构改进；不包含多实例/HA。

## 1. 背景与目标

SchedFlow 是一个把“一个 Job = 一个 DAG 工作流”的调度框架。核心调度栈位于
`schedflow.core`：后台线程主循环轮询 JobStore 到期任务，按 alias 交给多执行器，
执行后产出 `ExecutionLog` 并持久化；`EventBus` 提供进程内事件订阅；REST/SSE API
围绕唯一 `Scheduler` 实例构建。

现有实现已经具备清晰的分层与序列化契约，但作为工作流调度系统仍有可优化点，合并自
两轮架构分析：

- 调度主循环与 JobStore 的 O(n) 扫描、静默吞错、单一大锁；
- 一次性任务执行后被删除，历史不可见；
- 无 Job 优先级、无取消、无工作流级总超时；
- 执行过程不可中途查看、进程崩溃后无法恢复；
- 事件/指标/日志等可观测性薄弱；
- API 写入端点缺少背压保护。

本设计把可纳入的改进整理为三个阶段（P0/P1/P2），每阶段可在后续单独进入实施计划。

## 2. 范围与明确不做

### 2.1 纳入范围

| 阶段 | 内容 |
|------|------|
| P0 | JobStore 到期索引；Scheduler 派发队列与优先级；协作式取消；一次性任务保留并停用；循环与 listener 错误可见化；锁拆分 |
| P1 | 增量可见执行状态；运行快照与 full/resume 执行模式；job 级自动恢复策略；工作流级总超时 |
| P2 | listener 异常日志化；WebhookEventSink；Prometheus 文本 `/metrics`；SSE 执行状态推送；结构化日志；API 限流 |

### 2.2 明确不做（本设计范围外）

- 多 Scheduler 实例、Leader 选举、分布式锁、job 租约（HA）；
- 跨进程事件总线（Redis Pub/Sub / outbox）；
- 强制中断正在运行的节点（仅协作式取消）；
- 幂等键与跨执行去重（用户已明确暂不考虑）；
- 动态 DAG / fan-out / 子 DAG；
- 把旧包结构（`schedulers/executors/jobstores/models/events`）重建为独立包；
- 重新引入 entry-points 插件注册。

## 3. 关键设计决策汇总

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| D1 | 到期查找结构 | Memory 最小堆；SQLAlchemy/MongoDB 索引查询；Redis 排序集（可选） | 避免每轮全量扫描 |
| D2 | 主循环与执行器关系 | 主循环 → 进程内派发队列 → Executor | 主循环不再被 executor 提交阻塞 |
| D3 | Job 优先级 | `Job.priority` 整数，小值优先 | 默认 FIFO 语义不变 |
| D4 | 取消方式 | 协作式：节点边界检查 `cancel_requested` | 不做强制中断，跨执行器语义一致 |
| D5 | 一次性任务 | 执行后 `job.status="completed"`、`next_run_time=None`，保留在 JobStore | 用户可查历史；需要时可删除或显式重跑 |
| D6 | 调度锁 | 拆为 job 管理锁与派发/循环锁，固定加锁顺序 | 减少 `add_job` 对主循环的阻塞 |
| D7 | 每次执行身份 | 每次执行（full/resume）都生成新的 `execution_id`；正常结束后生成对应的不可变 `ExecutionLog` | 历史不可变，审计清晰 |
| D8 | 运行快照 | 独立 `RunSnapshot` 持久化节点级状态与结果；`ExecutionLog` 只在结束时落库 | 恢复状态与审计日志职责分离 |
| D9 | resume 不兼容 | 返回明确错误，不自动降级全量重跑 | 避免在 DAG 变更后产生错误结果 |
| D10 | 恢复策略 | `Job.on_restart`：`none`（默认）/`resume`/`rerun` | 显式优于隐式 |
| D11 | 工作流总超时 | `Workflow.run(timeout=...)` + Job 级 `workflow_timeout` | 复用协作式停止路径 |
| D12 | 观测端点 | 内置最小指标注册表与文本导出，默认无第三方强依赖 | 保持轻量 |

## 4. 现状核对（依据源码）

设计以下列现状为准，后续实施若与现状不符应先更新本设计：

- `Job.status` 语义：默认 `"running"` 表示“启用/可调度”，`pause_job()` 改为 `"paused"`
  并把 `next_run_time` 置空。它不是执行状态，不能用于表达“正在运行中的执行实例”。
- `Scheduler._advance()`：当触发器不再产生下一次运行时间时，当前代码
  `store.remove(job.job_id)` 直接删除任务并发布 `job.removed`——这是 P0 要改变的删除语义。
- `Scheduler._main_loop()`：每轮调用 `_process_due()`；随后对所有 JobStore 调
  `get_next_run_time()` 计算休眠时间。异常被 `except Exception: pass` 吞掉。
- `MemoryJobStore.get_due()/get_next_run_time()` 均为全量扫描 O(n)。
- `Scheduler._lock` 为单一 `threading.RLock`，`add_job/update_job/pause/resume` 与
  主循环扫描共用；高并发 `add_job` 可能阻塞调度。
- `EventBus.publish()` 中 listener 异常被 `except Exception: pass` 静默吞掉。
- `_running: dict[str, int]` 仅存内存，进程崩溃后运行中执行实例无持久记录。
- `ExecutionLog` 在 job 完成后一次性 `store.add_log()`，运行过程中无中间可见状态。
- 现有事件种类覆盖 `job.added/updated/removed/paused/resumed/started/succeeded/
  failed/missed/max_instances` 与 `scheduler.*`、`task.*`。

## 5. P0：调度可靠性与性能

### 5.1 JobStore 到期索引

**目标：** 到期查询与“下一次运行时间”查询不再随 job 数线性退化；JobStore 公共接口不变。

**MemoryJobStore**

- 内部增加按 `(next_run_time, enqueue_seq)` 排序的最小堆；`enqueue_seq` 单调递增，
  保证同刻到期任务按入队顺序出队（维持 FIFO 语义）。
- `add/update/remove` 不主动删除堆中旧条目，采用“惰性删除 + 版本号”：
  - 每条 job 维护递增 `version`；
  - 堆条目保存 `(next_run_time, seq, job_id, version)`；
  - `get_due(now)` 弹出堆顶直至堆顶未到期或为空；弹出时若版本不匹配则丢弃并继续；
  - `get_next_run_time()` 同样清理过期堆顶后返回堆顶时间（无任务返回 `None`）；
  - 提供 `__len__`/快照等既有语义不变。
- 需要保留一个“当前有效”的 `next_run_time` 字典做 O(1) 判定，避免清理堆时误判。

**SQLAlchemyJobStore**

- `next_run_time` 列建索引；
- `get_due`/`get_next_run_time` 改为 SQL 过滤
  （`WHERE next_run_time <= :now ORDER BY next_run_time LIMIT ...` 或聚合 `MIN`），
  禁止先全表加载再在 Python 中过滤。

**MongoDBJobStore**

- `next_run_time` 建索引；`get_due`/`get_next_run_time` 用带索引的查询下推。

**RedisJobStore**

- 现状已基于 sorted set（`stores/redis.py` 的 `run_times` key）实现 O(log n) 的
  `get_due`/`get_next_run_time`，无需改造；P0 只需补充等价测试与文档说明。

**测试要点**

- 接口行为与现状逐项对齐：insert/update/remove/reschedule/pause/resume 后到期结果一致；
- 新增基准：10k job 时 `get_due`/`get_next_run_time` 不应随每轮全量扫描而线性劣化
  （用单元级计时断言阈值，阈值取宽松值避免 CI 抖动）。

### 5.2 派发队列与优先级

**新增组件：** `src/schedflow/core/dispatch.py` —— `DispatchQueue`。

- 元素：`(priority, enqueue_seq, job_id, executor_alias, run_time, due_job_snapshot)`；
- `priority` 来自 `Job.priority`（新增字段，默认 `0`，小值先出队）；
- `enqueue_seq` 单调递增，同优先级按先到先出；
- 队列有界（默认容量可配置，例如 10_000），满时记录 `scheduler.error` 并保留到期
  job 于 JobStore（依赖下一轮/手动触发），不允许无限堆积内存；
- 提供 `put/get/cancel(job_id)/size` 线程安全接口；
- `cancel` 只移除尚未出队的条目；出队后由“运行中取消”路径接管。

**主循环改动：**

- `_process_due()` 不再直接调用 `executor.submit`，改为把到期 job 投递进
  `DispatchQueue`；
- 独立“派发线程/消费者”从队列取任务并调用对应 `executor.submit(job, run_time)`；
- `max_instances`/misfire 判断仍在入队前完成，避免队列积压不可调度任务；
- `job.started` 事件保持“入队并即将执行”或“实际 submit”的位置——设计选
  **实际 submit 时**发布，避免 started 后进程崩溃造成误报。

**Executor 接口不变。** 优先级在 Scheduler 侧统一实现，避免逐个改造 7 种执行器。

### 5.3 协作式取消

**API：** `Scheduler.cancel_job(job_id) -> Job`

- 未开始（仍在 DispatchQueue）：移除队列条目；记录取消原因；不触发执行；
- 运行中：设置内存中的取消标志（`job` 运行时对象持有，不序列化）；
- 运行结束后发布 `job.cancelled` 事件（新增事件种类）。

**Workflow 停止路径：**

- `Workflow.run(..., cancel_event=None)`：`cancel_event` 为可选 `threading.Event`；
- 执行引擎在“拓扑层之间与节点开始前”检查事件；置位后停止派发后续节点；
- 已运行节点不做强制中断；当前节点完成后正常收尾并进入取消处理；
- 取消产生的 `ExecutionLog`：`succeeded=False`；未执行节点记录
  `TaskRecord(status="cancelled", skip_reason="job_cancelled")`（状态向后兼容扩展）；
- 新增事件种类 `job.cancelled`，`_publish_task_events` 相应识别 `cancelled` 记录。

### 5.4 一次性任务保留并停用

**现状问题：** `_advance()` 在单次触发完成后 `store.remove()`，任务与历史入口消失。

**新语义：**

- date/单次触发器执行完毕后不再删除 job；
- `job.status = "completed"`（新增状态值，语义为“已完成/不再启用”），
  `next_run_time = None`，更新并保留在 JobStore；
- 发布新增事件 `job.completed`；
- job 保留期间不计入 `get_due`（`next_run_time is None` 天然排除）；
- 用户可显式 `DELETE /api/jobs/{id}` 删除；也可用 P1 的 `mode=full` 手动重跑；
- 保留策略：默认不设自动清理，避免“删了又看不见”；后续如需容量控制再单独加
  “清理策略”，不隐含删除。

**序列化兼容：**

- `Job.status` 允许值从 `{"running", "paused"}` 扩展为
  `{"running", "paused", "completed"}`；
- 前端契约与 `tests/test_api_rest/test_frontend_parity.py` 同步更新；
- `resume_job()` 对 `completed` job：若触发器已耗尽（`get_next_fire_time` 返回
  `None`），job 保持 `completed`；若用户显式提供新触发器（`reschedule_job`），
  则恢复正常调度并把状态改回 `running`。

### 5.5 错误可见化

**主循环：**

- `_main_loop()` 的异常不再 `pass`：`LOGGER.exception("scheduler loop error")`；
- 发布节流后的 `scheduler.error` 事件（新增事件种类），payload 含
  `error_type` 与 `message`；同一错误类型在 60s 窗口内最多发布一次，避免错误风暴。

**EventBus：**

- `publish()` 中 listener 异常改为捕获后记日志：
  `LOGGER.exception("event listener error", extra={"kind": ..., "listener": ...})`；
- listener 失败隔离语义保留（不中断其他 listener、不中断 publish）；
- 新增可观测计数器（见 P2），统计 listener 失败次数。

### 5.6 锁拆分

- `Scheduler` 内部拆为：
  - `_manage_lock`：保护 jobstore/executor 注册表与 job CRUD/迁移；
  - `_dispatch_lock`：保护 `_running`、DispatchQueue 状态、`cancel_requested` 集合。
- 固定加锁顺序：任何路径先拿 `_manage_lock` 再拿 `_dispatch_lock`；禁止反向，
  并以注释与并发测试固化；
- `add_job/update_job/remove_job` 不再与主循环扫描共享同一把全局锁；写 store 的
  短临界区保留。
- 并发测试：多线程同时 `add_job/run_job_now/cancel_job/pause_job` 无死锁、无
  lost update（用 MemoryJobStore 断言最终状态）。

## 6. P1：Workflow 执行语义

### 6.1 执行身份与日志关联

- 新增执行元数据：`mode: "full" | "resume"`、`resumes_from: log_id | None`；
- 每次执行（含 resume）都创建新的 `execution_id`（即新的 `ExecutionLog.log_id`）
  与新的不可变 `ExecutionLog`；
- resume 的新日志通过 `resumes_from` 指向被恢复的那次执行：其 execution_id 与
  未完成日志的 `log_id` 相同；若崩溃发生在日志落库前，该 execution_id 只存在于
  RunSnapshot，运行概览会把这次执行列为“snapshot-only”，直到恢复执行结束并
  生成新日志；
- `ExecutionLog.to_dict()/from_dict()` 序列化契约做向后兼容扩展
  （新字段默认值：`mode="full"`、`resumes_from=None`）。

### 6.2 运行快照（RunSnapshot）

**为什么独立于 ExecutionLog：**

- `ExecutionLog` 是运行结束后的审计记录，应保持不可变；
- 恢复需要“运行中可更新”的状态与结果，因此用独立的 `RunSnapshot`。

**模型（新增 `src/schedflow/core/snapshot.py`）：**

```python
@dataclass
class RunSnapshot:
    execution_id: str            # 与本次 ExecutionLog.log_id 一致
    job_id: str
    workflow_fingerprint: str
    mode: str                    # "full" | "resume"
    resumes_from: str | None
    started_at: datetime
    updated_at: datetime
    records: dict[str, TaskRecordSnapshot]  # node_id -> 状态/结果
```

- `TaskRecordSnapshot`：`status`、`result`（仅 succeeded 节点）、
  `skip_reason`、`started_at/end_at`；不保存 stdout/stderr 全量，控制体积；
- `Workflow.fingerprint()`：对节点集合、依赖边、TaskSpec 序列化后的稳定哈希；
  函数引用用 `ref` 字符串参与哈希（与执行时解析保持一致）。

**JobStore 接口扩展：**

- `save_snapshot(job_id, snapshot)`（按 `execution_id` upsert）；
- `get_snapshot(job_id, execution_id)`；
- `list_snapshots(job_id)`（按开始时间倒序）；
- `delete_snapshot(job_id, execution_id)`（执行结束后按保留策略清理）。
- Memory/SQLAlchemy/Redis/MongoDB 四种实现都提供；SQLAlchemy/MongoDB 增加
  snapshot 表/集合；Redis 用 hash + sorted set 维护索引。

**写入时机：**

- 执行开始时创建快照（full 或 resume 都创建）；
- 每个节点结束时 upsert 该节点记录与 `updated_at`；
- 执行结束时若成功，快照标记完成，可保留短期（默认保留最近 N 份，如 20）后清理。

### 6.3 full / resume 执行

**核心接口：**

```python
# Workflow / Job 层
job.run(mode="full", resume_from_log_id=None, timeout=None, cancel_event=None)
```

- `full`：从零开始执行整个 DAG（现状语义，默认）；
- `resume`：读取该 job 最近一份**未终结的 RunSnapshot**（崩溃/失败后快照仍在，
  但对应的不可变 `ExecutionLog` 可能尚未落库）；
  - 校验 `workflow_fingerprint` 与当前 `job.workflow.fingerprint()` 一致；
  - 不一致：抛出 `DagChangedError`（映射 HTTP 409），不自动降级；
  - 一致：已 `succeeded` 节点直接以“恢复”身份进入结果集，不再执行；
    状态记为 `succeeded`，新增可选字段 `TaskRecord.resumed: bool = True`，
    `duration=None`，保留 `result` 供 `_pre_results` 注入；
  - 仅执行 `failed`/`skipped`/缺失节点及其下游。

**REST API：**

- `POST /api/jobs/{job_id}/run` 请求体新增可选：
  `{"mode": "full" | "resume"}`（默认 `"full"`）；
- `resume` 无可用未完成快照 → 404/409 明确错误（设计选 409 + `code=no_snapshot`）；
- `resume` DAG 变更 → 409 + `code=dag_changed`；
- 新增查询 `GET /api/jobs/{job_id}/runs` 概览：`log_id/mode/resumes_from/status/
  started_at/ended_at`。

### 6.4 job 级自动恢复策略

- `Job` 新增字段 `on_restart: str = "none"`，允许值：
  - `none`：什么都不做；
  - `resume`：有兼容快照则恢复，否则标记失败并发 `job.failed`（原因
    `resume_incompatible`），**不自动全量重跑**；
  - `rerun`：直接以 `mode=full` 重跑。
- Scheduler `start()` 流程中，扫描“执行中但进程已重启”的持久化标记：
  - P1 起执行开始时在 JobStore 写入 `running` 运行标记（独立于 `Job.status`，
    例如 snapshot 状态为 `running` + 心跳时间）；
  - `start()` 时对遗留 running snapshot 按 `on_restart` 处理；
  - 处理完成后发布事件（`job.recovered`/`job.failed`，新增种类按需）。

### 6.5 工作流级总超时

- `Workflow.run(..., timeout: float | None = None)`：
  - `timeout` 为整个 DAG 的墙钟上限；
  - 超时后复用协作式停止路径：不再派发新节点；
  - 未执行节点记录 `TaskRecord(status="skipped", skip_reason="workflow_timeout")`；
  - 正在运行节点等待其结束（不强制中断），整体 `ExecutionLog.succeeded=False`；
- `Job` 新增 `workflow_timeout: float | None = None`（秒），调度执行时默认传入；
- `run_job_now`/`run` API 支持可选 `timeout` 覆盖。

### 6.6 增量可见执行状态

- 运行期间节点结束即更新 RunSnapshot，并发布 `task.*` 事件（现状已有事件，改为
  “边跑边发”，而不是结束后再统一补发）；
- 运行中查询：`GET /api/jobs/{job_id}/runs/{execution_id}` 对 running 状态返回
  RunSnapshot 视图（节点状态/耗时/错误摘要），完成后返回不可变 ExecutionLog；
- SSE 侧增加执行状态订阅（见 P2），事件源为进程内 EventBus；迟到订阅者从
  RunSnapshot 做尽力回放。

## 7. P2：事件与可观测性

### 7.1 EventBus listener 异常日志化

- 见 5.5：异常记日志并计数；语义不变。

### 7.2 WebhookEventSink

**新增 `src/schedflow/core/webhook.py`：**

- 配置：事件种类 → URL 列表 + 可选 secret header；
- 通过已有 settings 配置持久化（/api/v1/settings），进程内生效；
- 投递：有界内存队列 + 单 worker 线程；`urllib.request` 带 `timeout`，
  避免强加第三方依赖；
- 失败策略：单次重试 3 次（指数退避），仍失败记日志并计数，不阻塞主流程；
- 发送内容：`SchedulerEvent` 的 JSON 序列化（kind/job_id/run_time/log 摘要）。

### 7.3 Prometheus `/metrics`

**新增 `src/schedflow/core/metrics.py`：**

- 内置最小 registry：`Counter/Gauge/Histogram` + 文本格式导出（`prometheus_client`
  留作可选 extra，不设为硬依赖）；
- 指标初集：
  - `schedflow_jobs_total{status}`（running/paused/completed）
  - `schedflow_job_runs_total{outcome}`（succeeded/failed/cancelled）
  - `schedflow_job_run_duration_seconds`（直方图）
  - `schedflow_scheduler_state`（0/1/2）
  - `schedflow_dispatch_queue_depth`
  - `schedflow_event_listener_errors_total`
  - `schedflow_main_loop_errors_total`
- 端点：`/api/metrics`（沿用统一前缀与认证可配置；metrics 默认放行，配置可关）。

### 7.4 SSE 执行状态推送

- 保留现有 `/api/v1/sse/jobs/{id}/next-run-time`；
- 新增或扩展 SSE 事件流：`job.started/succeeded/failed/cancelled/completed` 与
  `task.*` 增量；
- 连接建立后，对指定 job 先推送最近 RunSnapshot 概览（尽力回放），再实时推送；
- 心跳与断线重连策略由客户端负责，服务端只保证单进程内事件顺序。

### 7.5 结构化日志

- 默认保持人类可读日志；`SCHEDFLOW_LOG_FORMAT=json` 时切换 JSON formatter；
- 关键路径（add/update/remove/run 节点完成/执行结束/错误）输出结构化字段：
  `job_id`、`execution_id`、`node_id`、`status`、`duration_ms`、`event`；
- 不引入 logging 之外的强依赖（JSON 由标准库 `json` 序列化）。

### 7.6 API 限流

- `api/middleware.py` 增加进程内 token bucket 中间件；
- 配置项：`rate_limit.enabled`（默认 false）、`rate_limit.rpm`、按 client/IP；
- 覆盖写入端点：`POST /api/jobs`、`POST /api/jobs/{id}/run|pause|resume`、
  `DELETE /api/jobs/{id}`；
- 超限返回 429 + `Retry-After`；
- 单进程限制明确写入文档（多实例需网关层限流，本设计不实现）。

## 8. 跨阶段契约与兼容

### 8.1 序列化/状态值变更汇总

| 对象 | 变更 | 兼容策略 |
------|------|----------|
| `Job` | 新增 `priority`、`workflow_timeout`、`on_restart` | 新字段可选，`from_dict` 默认值 |
| `Job.status` | 新增 `"completed"` | 后端/前端白名单同步，旧值不变 |
| `TaskRecord.status` | 新增 `"cancelled"` | 枚举扩展 |
| `TaskRecord` | 新增可选 `resumed: bool` | 默认 `False` |
| `ExecutionLog` | 新增 `mode`、`resumes_from` | 默认值兼容旧数据 |
| 事件 | 新增 `job.cancelled/job.completed/scheduler.error` 等 | 订阅通配符不受影响 |
| JobStore | 新增 snapshot/运行标记接口 | 对旧数据无读取压力，写入时才创建 |

### 8.2 前端契约

- `tests/test_api_rest/test_frontend_parity.py` 是硬性门槛：每个状态/字段变更同步
  更新契约断言；
- 管理面板需要展示：completed 状态、priority、run 的 mode、resumes_from 链、
  cancelled/resumed 节点标记、/metrics 与 SSE 状态事件。

### 8.3 文档

- `docs/introduction.zh.md`、`docs/user-guide/*`、API 参考随阶段更新；
- 架构图中的 ExecutionLog/JobStore 说明同步补充“运行快照”职责。

> 注意：§8 只保留契约原则；逐文件的完整更新映射见 §11，§11 是各阶段验收的依据。

## 9. 测试与验收策略

每个阶段遵循 TDD：先写失败测试，再实现，再全量回归
（`python -m pytest` + `ruff check .`）。

### P0 验收

- JobStore 到期索引：行为等价测试 + 10k job 性能基准；
- DispatchQueue：优先级/FIFO/去重/有界/取消测试；
- cancel：未开始取消、运行中节点边界停止、ExecutionLog 状态正确；
- completed：date job 执行后仍在 store、`next_run_time=None`、`job.completed`
  事件、删除仍可用；
- 错误可见化：主循环异常与 listener 异常产生日志与 `scheduler.error`/计数；
- 锁拆分：并发 add/cancel/pause 压力测试无死锁。

### P1 验收

- fingerprint 稳定且对 DAG 变更敏感；
- full/resume 行为：resume 跳过 succeeded 并保留结果注入；失败节点重跑；
  无快照/不兼容 → 409；
- 崩溃恢复：模拟进程中断（直接丢弃内存状态）后按 `on_restart` 恢复；
- workflow_timeout：超时停止派发、记录正确；
- 增量可见：运行中查询与 SSE 能读到已完成节点状态。

### P2 验收

- listener 错误可见；webhook 收到事件并重试；/metrics 文本可被 Prometheus 解析；
- SSE 状态推送顺序与心跳正常；JSON 日志格式正确；限流 429 行为正确。

## 10. 风险与开放问题

- **存储写入放大**：P1 每节点 upsert snapshot。若节点数极大或 store 为远端 Redis/
  MongoDB，需要分批/心跳节流；实施计划中应提供可配置的
  `snapshot_flush_every_n_nodes`（默认 1）作为调优旋钮。
- **SQLAlchemy/Redis 表与 key 布局迁移**：新增 snapshot/运行标记需要 schema/key
  演进；SQLAlchemy 用轻量迁移（建表语句幂等），Redis 用独立 key 前缀，旧 key 不受影响。
- **Job.status 命名混淆**：`"running"` 实为“启用”。设计不重命名旧值（兼容性优先），
  但在 API schema 与文档中明确标注其含义为 enabled；后续可另立 issue 讨论改名。
- **Redis get_due 优化为可选**：若 P0 排期紧张，Redis 扫描问题会保留并记录限制。
- **开放问题**：completed job 是否需要区分“用户手动停用”与“单次触发完成”；
  本设计用同一 `completed` 表示“不再按计划启用”，若产品需要区分再扩展。

## 11. 交付物清单与同步范围（完整更新目标）

> 规则：P0/P1/P2 任一阶段落地时，必须按本清单同步更新对应文件，并跑 §11.5 的
> 验证命令。文档默认中英双语（`docs/*.zh.md` 与 `docs/*.en.md` 成对），以下列表
> 中“docs 双语”指同时更新两个文件。本清单是实施与验收的权威依据，取代 §8.2/
> §8.3 的概要描述。

### 11.1 后端源码映射

#### P0 涉及文件

- 修改 `src/schedflow/core/jobstore.py`：`MemoryJobStore` 到期最小堆、
  `get_due()/get_next_run_time()` 惰性删除与版本号校验；
- 修改 `src/schedflow/core/stores/sqlalchemy.py`：`next_run_time` 索引与 SQL
  过滤查询；
- 修改 `src/schedflow/core/stores/mongodb.py`：`next_run_time` 索引与查询下推；
- `src/schedflow/core/stores/redis.py`：已用 sorted set 满足 O(log n)，P0 不改；
  若后续调整存储布局需先做迁移设计；
- 修改 `src/schedflow/core/job.py`：新增 `priority`；`Job.status` 支持
  `"completed"`；`to_dict()/from_dict()` 兼容旧数据；
- 修改 `src/schedflow/core/scheduler.py`：接入 DispatchQueue、`cancel_job()`、
  `_advance()` 不再删除而是置 `completed`、主循环异常记录与 `scheduler.error`
  节流发布、锁拆分、事件发布位置调整；
- 新增 `src/schedflow/core/dispatch.py`：`DispatchQueue`（优先级/去重/有界/取消）；
- 修改 `src/schedflow/core/workflow.py`：`run(..., cancel_event=None)` 与节点
  边界停止检查；
- 修改 `src/schedflow/core/log.py`：`TaskRecord.status` 支持 `"cancelled"`、
  `skip_reason="job_cancelled"`；
- 修改 `src/schedflow/core/events.py`：新增 `job.completed/job.cancelled/
  scheduler.error`；`publish()` listener 异常记日志；
- 修改 `src/schedflow/api/rest/routers.py` 与 `src/schedflow/api/rest/schemas.py`：
  `POST /api/jobs/{id}/cancel`、completed 状态输出、`priority` 入参与响应；

#### P1 涉及文件

- 新增 `src/schedflow/core/snapshot.py`：`RunSnapshot`/`TaskRecordSnapshot` 模型、
  `Workflow.fingerprint()`、序列化；
- 修改 `src/schedflow/core/jobstore.py`：JobStore 接口新增
  `save_snapshot/get_snapshot/list_snapshots/delete_snapshot`；
- 修改 `src/schedflow/core/jobstore.py`（`MemoryJobStore` 所在文件）、
  `src/schedflow/core/stores/sqlalchemy.py`、`stores/redis.py`、
  `stores/mongodb.py`：四种存储的 snapshot 表/集合实现；
- 修改 `src/schedflow/core/job.py`：新增 `on_restart`、`workflow_timeout`；
- 修改 `src/schedflow/core/log.py`：`ExecutionLog` 新增 `mode`、`resumes_from`；
  `TaskRecord` 新增可选 `resumed`；
- 修改 `src/schedflow/core/workflow.py`：`run(mode=..., resume_from_snapshot=...,
  timeout=..., cancel_event=...)`、resume 节点结果注入、fingerprint 校验、
  `DagChangedError`；
- 修改 `src/schedflow/core/scheduler.py`：`run_job_now()`/调度执行传递 mode 与
  timeout；`start()` 时扫描遗留 running 快照并按 `on_restart` 恢复；
- 修改 `src/schedflow/api/rest/routers.py` 与 `schemas.py`：
  `POST /api/jobs/{id}/run` 支持 `mode`；新增
  `GET /api/jobs/{id}/runs`；运行概览含 snapshot-only；
- 修改 `src/schedflow/api/exceptions.py`：`DagChangedError` → 409、无快照 → 409；
- 修改 `src/schedflow/core/events.py`：新增 `job.recovered` 等事件种类（按实现
  需要）。

#### P2 涉及文件

- 新增 `src/schedflow/core/webhook.py`：`WebhookEventSink`（有界队列、重试、
  secret header、序列化）；
- 新增 `src/schedflow/core/metrics.py`：最小 registry（Counter/Gauge/Histogram）
  与文本导出；
- 修改 `src/schedflow/core/events.py`：listener 失败计数接入 metrics；
- 修改 `src/schedflow/core/scheduler.py`：关键路径埋点（job 计数、执行耗时、
  队列深度、主循环错误）；
- 修改 `src/schedflow/api/rest/routers.py`：注册 `GET /api/metrics`；
- 修改 `src/schedflow/api/routers/sse.py`：新增 job 执行状态事件流与快照回放；
- 修改 `src/schedflow/api/middleware.py`：进程内 token bucket 限流；
- 修改 `src/schedflow/api/routers/settings.py` 与 `src/schedflow/api/rest/
  schemas.py`：webhook 订阅、限流开关与参数的持久化 settings；
- 新增 `src/schedflow/utils/logging.py`：JSON formatter 与
  `SCHEDFLOW_LOG_FORMAT=json` 支持。

### 11.2 测试文件映射

#### P0

- 修改 `tests/core/test_jobstore.py`：堆语义、惰性删除、FIFO 稳定；
- 新增 `tests/core/test_jobstore_scale.py`：10k job 的 `get_due/
  get_next_run_time` 基准断言（宽松阈值）；
- 修改 `tests/core/test_stores.py`：SQLAlchemy 索引查询；Redis/MongoDB 行为
  等价（外部服务不可用时保持自动跳过）；
- 新增 `tests/core/test_dispatch.py`：优先级/FIFO/去重/有界/取消；
- 修改 `tests/core/test_scheduler.py`：completed 保留、cancel、错误事件、
  锁拆分并发；
- 修改 `tests/core/test_workflow.py`：`cancel_event` 节点边界停止；
- 修改 `tests/core/test_log.py`：`cancelled` 记录序列化；
- 修改 `tests/core/test_events.py`：listener 异常日志、新事件种类；
- 修改 `tests/test_api_rest/test_api_rest.py`：cancel/completed 端点；
- 修改 `tests/test_api_rest/test_frontend_parity.py`：Job/TaskRecord 新状态与
  字段契约。

#### P1

- 新增 `tests/core/test_snapshot.py`：快照 CRUD、fingerprint 稳定性/敏感性、
  full/resume 单元行为；
- 修改 `tests/core/test_stores.py`：四种 store 的 snapshot 增删查与运行标记；
- 修改 `tests/core/test_workflow.py`：resume 跳过 succeeded、保留 result 注入、
  DAG 变更拒绝、`workflow_timeout` 停止派发；
- 修改 `tests/core/test_scheduler.py`：启动恢复扫描与 `on_restart=none|resume|
  rerun`；
- 修改 `tests/core/test_log.py`：`mode/resumes_from/resumed` 序列化与旧数据
  兼容；
- 修改 `tests/test_api_rest/test_api_rest.py`：run mode、runs 概览、409 错误；
- 修改 `tests/test_api_rest/test_frontend_parity.py`：run/mode/resumes_from 等
  契约；
- 修改 `tests/test_api/test_sse.py`：运行中状态推送（P1 若先落地运行中查询，
  SSE 部分在 P2 补）。

#### P2

- 新增 `tests/core/test_webhook.py`：配置解析、队列投递、重试、失败计数；
- 新增 `tests/core/test_metrics.py`：registry 与 Prometheus 文本格式；
- 修改 `tests/core/test_events.py`：listener 错误指标；
- 修改 `tests/test_api/test_middleware.py`：限流 429 与 Retry-After；
- 修改 `tests/test_api/test_sse.py`：job 状态事件流与回放；
- 修改 `tests/test_api/test_schemas.py`/`test_settings.py`（如存在）：
  webhook/限流 settings 校验；
- 修改 `tests/test_api_rest/test_frontend_parity.py`：新端点/字段的最终契约。

### 11.3 前端文件映射（`frontend/`，Vue 3 + TS）

#### P0

- 修改 `frontend/src/types/job.ts`：`Job.status` 支持 `completed`；新增
  `priority`；`TaskRecord.status` 支持 `cancelled`；请求/响应类型；
- 修改 `frontend/src/types/api.ts`、`frontend/src/types/index.ts`：导出新类型；
- 修改 `frontend/src/api/jobs.ts`：`cancelJob()`、创建/编辑传 `priority`；
- 修改 `frontend/src/api/mappers.ts`：状态文案/颜色加入 `completed`、
  `cancelled`；
- 修改 `frontend/src/views/jobs/JobForm.vue`：priority 输入；
- 修改 `frontend/src/views/jobs/JobList.vue`：completed 徽标、取消/运行操作；
- 修改 `frontend/src/views/jobs/JobDetail.vue`：取消按钮与状态展示；
- 修改 `frontend/src/views/logs/ExecutionOutput.vue`（及共用节点状态组件）：
  cancelled 节点标记。

#### P1

- 修改 `frontend/src/types/job.ts`：`Job.on_restart/workflow_timeout`；
  `ExecutionLog.mode/resumes_from`；`TaskRecord.resumed`；运行概览
  `RunSummary` 类型；
- 修改 `frontend/src/api/jobs.ts`：`runJob(jobId, {mode})`；
- 修改 `frontend/src/api/logs.ts`：获取运行概览
  `GET /api/jobs/{id}/runs`、运行中快照视图；
- 修改 `frontend/src/api/mappers.ts`：resumes_from 链、snapshot-only、
  resumed 标记映射；
- 修改 `frontend/src/views/jobs/JobForm.vue`：`on_restart` 选择与
  `workflow_timeout` 输入；
- 修改 `frontend/src/views/jobs/JobDetail.vue`：full/resume 执行入口、
  不兼容/无快照错误提示、运行历史链；
- 修改 `frontend/src/views/logs/ExecutionList.vue`、`JobLogs.vue`、
  `JobLogViewer.vue`：显示 mode、resumes_from、恢复节点；
- 修改 `frontend/src/views/logs/ExecutionOutput.vue`：运行中部分记录与
  resumed 徽标。

#### P2

- 新增 `frontend/src/composables/useJobSse.ts`：订阅 job 执行状态事件；
- 修改 `frontend/src/views/jobs/JobDetail.vue` 与
  `frontend/src/views/logs/ExecutionOutput.vue`：接入 SSE 实时节点/运行状态；
- 新增 `frontend/src/views/settings/WebhookSettings.vue`：webhook 订阅配置；
- 修改 `frontend/src/api/settings.ts` 与 `frontend/src/types/`：webhook/限流
  settings 类型与 API；
- 修改 `frontend/src/router/index.ts`、`components/layout/AppSidebar.vue`：
  注册 WebhookSettings 页面；
- 修改 `frontend/src/views/settings/SystemSettings.vue`：限流开关入口（按需）；
- Dashboard 指标卡不列为必须项；若产品决定接入 `/api/metrics` 再追加任务。

### 11.4 文档与示例映射

#### P0

- `docs/user-guide/core-features.zh.md/.en.md`：Job 管理章节补充 `priority`、
  `cancel_job`、`completed` 状态与“一次性任务保留不删除”行为；
- `docs/user-guide/dag-workflow.zh.md/.en.md`：协作式取消与 `cancelled` 记录
  说明；
- `docs/api-reference/index.zh.md/.en.md`：cancel/completed/priority 的请求
  响应字段；
- `docs/index.zh.md/.en.md`：核心特性表补充优先级/取消/一次性任务保留；
- `CHANGELOG.md` 与 `docs/changelog.zh.md/.en.md`：P0 条目；
- `README.md`/`README_EN.md`（如特性清单处涉及 Job 管理）。

#### P1

- `docs/introduction.zh.md/.en.md`：架构/数据流补充 full/resume、运行快照职责；
- `docs/images/schedflow-architecture.json` 与
  `docs/images/schedflow-architecture.html`：更新 ExecutionLog/JobStore 卡片
  文案以说明运行快照与恢复（经 archify validate/deliver 重出）；
- `docs/user-guide/core-features.zh.md/.en.md`：`on_restart`、
  `workflow_timeout`、runs 概览；
- `docs/user-guide/dag-workflow.zh.md/.en.md`：`run(mode/resume/timeout)`、
  fingerprint 与恢复限制；
- `docs/user-guide/advanced-usage.zh.md/.en.md`：断点续跑场景与自动恢复策略
  章节；
- `docs/api-reference/index.zh.md/.en.md`：run body、runs 端点、日志新字段；
- 新增 `examples/resume_execution_example.py`，并在 `examples/README.md` 登记；
- `CHANGELOG.md` 与 `docs/changelog.zh.md/.en.md`：P1 条目。

#### P2

- `docs/installation.zh.md/.en.md`：`SCHEDFLOW_LOG_FORMAT=json` 与限流/指标
  配置；
- `docs/user-guide/core-features.zh.md/.en.md`：可观测性小节（/metrics、SSE、
  webhook、结构化日志、限流）；
- `docs/user-guide/advanced-usage.zh.md/.en.md`：webhook 配置示例；
- `docs/api-reference/index.zh.md/.en.md`：`/api/metrics`、SSE 事件流、429 响应；
- `docs/index.zh.md/.en.md`：核心特性表可观测性行；
- `CHANGELOG.md` 与 `docs/changelog.zh.md/.en.md`：P2 条目。

### 11.5 验证命令

每个阶段交付前必须通过：

```bash
python -m pytest
ruff check .
cd frontend && npm run type-check && npm run build
```

文档与架构图变更后：

```bash
python -m mkdocs build --strict   # 本机安装 mkdocs 依赖时执行
node "C:\Users\WWH\.agents\skills\archify\bin\archify.mjs" validate architecture docs/images/schedflow-architecture.json --quality showcase --json
node "C:\Users\WWH\.agents\skills\archify\bin\archify.mjs" deliver architecture docs/images/schedflow-architecture.json docs/images/schedflow-architecture.html --quality showcase --json
```

### 11.6 完成标准（DoD）

- 后端：本阶段功能实现并有对应测试，`pytest`/`ruff` 全绿；
- 契约：`test_frontend_parity.py` 与后端 schema 同步更新并通过；
- 前端：类型检查与构建通过，涉及页面交互完成；
- 文档：11.4 中该阶段文件全部更新（zh/en）；
- 记录：`CHANGELOG.md` 与站点 changelog 更新；
- 提交：后端、测试、前端、文档按任务粒度分次提交，禁用大杂烩 commit。
