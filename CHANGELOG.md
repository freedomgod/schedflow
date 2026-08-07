# Changelog

## Unreleased

### Added

- **SchedFlow 首个版本**：轻量级 DAG 工作流调度框架。
- `Workflow`：以 `add_task()/add_edge()` 构建 DAG，支持拓扑分层并行、条件边、环路检测（`CycleError`）、`_pre_results` 注入、重试/超时/回调，`to_dict()/from_dict()` 作为唯一 JSON 序列化出口；
- `TaskSpec`：四种任务类型 `python_callable` / `python` / `python_script` / `bash`，子进程任务支持环境变量、工作目录、超时；
- `ExecutionLog` / `TaskRecord`：结构化执行日志，记录每个节点的状态、结果、错误、stdout/stderr、退出码与耗时；
- 触发器 6 种：`DateTrigger` / `IntervalTrigger` / `CronTrigger`（含 `from_crontab`）/ `CalendarIntervalTrigger` / `AndTrigger` / `OrTrigger`；
- `Scheduler`：后台线程主循环，多执行器/多存储器（alias 路由）、jobstore 迁移、事件订阅；
- 执行器 7 种（debug / threadpool / processpool / asyncio / gevent / tornado / twisted），存储器 4 种（memory / sqlalchemy / redis / mongodb）；
- FastAPI Web API：`/api` 调度 REST + `/api/v1` 管理（auth / settings / components / sse），统一 `{"code":0,"data":...,"message":"ok"}` 响应；
- Vue 3 管理面板：仪表盘、DAG 工作流编辑器、作业列表、执行日志查看器、执行/存储配置、暗色/亮色主题；
- CLI：`schedflow-backend` / `schedflow-frontend`。