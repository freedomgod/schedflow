# Changelog

## Unreleased

### Added

- **优先级与协作式取消**：`Job.priority` 决定派发顺序；`cancel_job` /
  `POST /api/jobs/{id}/cancel` 取消未开始任务，运行中任务在节点边界协作式停止；
- **一次性任务保留**：单次触发器耗尽后任务置为 `completed` 并保留，不再自动删除；
- **调度可靠性**：Memory/SQLAlchemy/MongoDB 到期查询改为索引结构；主循环与
  EventBus 监听器异常可见化。
- **运行快照与断点续跑**：RunSnapshot（四类 JobStore 持久化）、full/resume
  执行模式、`on_restart` 自动恢复、`workflow_timeout` 总超时。
- **可观测性与集成**：Prometheus `/api/metrics`、SSE 执行事件、Webhook 通知、
  JSON 结构化日志与写请求限流。
- **系统默认时区**：`GET/PUT /api/v1/settings/timezone` 设置默认时区，未显式指定
  时区的触发器按「触发器参数 → 系统默认 → 进程本地时区」解析，容器以 UTC 运行时
  不再把业务时间算错；系统设置页新增时区选择，cron/interval 触发器表单默认填入
  并显示该时区。
- **Webhook 平台适配**：支持通用 JSON / 钉钉 / 企业微信 / 飞书四种通知目标，
  按平台生成报文（钉钉加签、飞书签名），并把平台以 `HTTP 200 + errcode/code`
  表达的失败识别为投递失败；集成页改为卡片式配置，可选择平台与事件并就地查看
  测试结果。
- **会话与操作交互**：登录过期后清空登录态、提示一次并跳转登录页（登录后回跳原页面），
  不再跳回首页或透出 `Forbidden` 原文；任务列表按「详情 / 执行 / 复制 / 删除」重排，
  取消执行改到详情页且仅在确有运行中任务时可用；执行记录不再标注「全量执行」，
  续跑记录保留「续跑」角标。
- **空触发器守卫**：Web API 拒绝会「每秒执行」的触发器配置——cron 未填任何时间字段、
  interval 间隔为 0、date 缺少运行时间都会返回 422 并给出原因（此前会静默变成每秒执行）；
  触发器类本身语义不变，显式写 `second='*'` 仍可表达每秒，任务表单也在提交前本地拦截。

## 0.0.1 (2026-08-08)

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
