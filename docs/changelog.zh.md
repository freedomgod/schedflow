# 更新日志

## 未发布（开发中）

### 新增

- **`Workflow`**：以 `add_task()/add_edge()` 构建 DAG，支持拓扑分层并行、条件边、环路检测（`CycleError`）、`_pre_results` 注入、重试/超时/回调，`to_dict()/from_dict()` 作为唯一 JSON 序列化出口；
- **`TaskSpec`**：四种任务类型 `python_callable` / `python` / `python_script` / `bash`，子进程任务支持环境变量、工作目录、超时；
- **`ExecutionLog` / `TaskRecord`**：结构化执行日志，记录每个节点的状态、结果、错误、stdout/stderr、退出码与耗时；
- **显式触发器构造**：`DateTrigger` / `IntervalTrigger` / `CronTrigger`（含 `from_crontab`）/ `CalendarIntervalTrigger` / `AndTrigger` / `OrTrigger` 使用关键字参数构造，支持 `to_dict()/from_dict()`；
- **`Scheduler`**：统一调度器（后台线程主循环），显式的 `add_job/update_job/remove_job/pause_job/resume_job/reschedule_job/run_job_now/get_job_logs/get_job_log`，字符串事件订阅 `on()`；
- **事件系统完善**：调度器执行作业后逐节点发布 `task.executed` / `task.error` / `task.skipped`（`event.record` 携带对应节点的 `TaskRecord`，`event.log` 携带完整执行日志）；新增 `Scheduler.off()` 用于取消事件订阅；
- **`JobStore` 统一接口**：`add/update/remove/get/get_due/get_all/get_next_run_time/add_log/get_logs/get_log/close`，含 `Memory` / `SQLAlchemy` / `Redis` / `MongoDB` 四个实现，统一 JSON 序列化；
- **`Executor` 统一接口**：`ThreadPoolExecutor`、`ProcessPoolExecutor`（JSON worker 协议，Windows spawn 可用）、`DebugExecutor`；
- **Web API**：`/api/jobs` 全套 CRUD + 立即执行/重新调度 + 日志查询 + 调度器生命周期控制，统一 `{"code":0,"data":...,"message":"ok"}` 响应与 404/409/422 错误映射；
- **Vue 3 管理面板**：仪表盘、DAG 工作流编辑器、作业列表、执行日志查看器、执行/存储配置、暗色/亮色主题；
- **CLI 入口**：`schedflow-backend` 与 `schedflow-frontend`。

### 修复与优化

- **CLI 默认生产模式**：`schedflow-backend` / `schedflow-frontend` 默认关闭热重载并启用 INFO 日志，开发模式仅通过 `--dev` 显式开启；开发模式的热重载排除 `jobs.db`、`.git`、`node_modules`、`dist` 等路径，避免运行期文件写入刷出 “changes detected”；
- **调度器防重入**：作业派发前先持久化下一次运行时间，写入失败即中止本次派发（下个循环重试），修复 SQLite 锁冲突等写入异常导致作业持续“到期”、几秒内重复执行刷大量日志的问题；SQLAlchemy 存储写操作增加锁冲突退避重试；
- **节点耗时统计修正**：`TaskRecord` 改为在节点真正执行前标记开始时间，节点“耗时”不再恒为 0。

### 环境要求

- Python 3.11+
