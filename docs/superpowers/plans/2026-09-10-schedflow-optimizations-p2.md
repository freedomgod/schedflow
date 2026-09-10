# SchedFlow P2 优化实施计划（可观测性与外部集成）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 P2：WebhookEventSink、Prometheus `/metrics`、SSE 执行状态推送、结构化 JSON 日志、API 限流，以及对应前端设置与文档。

**Architecture:** 全部保持单进程；EventBus 仍是唯一事件源，新增 Webhook sink 与 SSE bridge 作为订阅者；`core/metrics.py` 提供无强依赖的指标注册表；`utils/logging.py` 提供 JSON formatter；`api/middleware.py` 增加进程内 token bucket 限流。

**Tech Stack:** Python 标准库（queue/urllib/http.server/threading/json）、FastAPI/Starlette、Vue 3 + TypeScript。

---

### Task 1: 指标注册表

**Files:** 新增 `src/schedflow/core/metrics.py`；新增 `tests/core/test_metrics.py`

- [ ] 写失败测试：

```python
from schedflow.core.metrics import (
    counter_inc, gauge_set, histogram_observe, render_prometheus,
)


def test_metrics_render_prometheus_text():
    counter_inc("schedflow_job_runs_total", labels={"outcome": "succeeded"})
    gauge_set("schedflow_dispatch_queue_depth", 3)
    histogram_observe("schedflow_job_run_duration_seconds", 1.5)

    text = render_prometheus()

    assert 'schedflow_job_runs_total{outcome="succeeded"} 1' in text
    assert "schedflow_dispatch_queue_depth 3" in text
    assert "schedflow_job_run_duration_seconds_count 1" in text
```

- [ ] 实现最小 registry：`Counter/Gauge/Histogram`（Histogram 固定 buckets
  `(.005,.01,.025,.05,.1,.25,.5,1,2.5,5,10)`）、`counter_inc/gauge_set/histogram_observe/render_prometheus`。
- [ ] 运行 `pytest tests/core/test_metrics.py -q`，`ruff check`，提交
  `feat(core): add minimal prometheus metrics registry`。

### Task 2: Scheduler/EventBus 埋点

**Files:** `core/events.py`、`core/scheduler.py`、`tests/core/test_metrics.py`

- [ ] 测试：publish 一个抛异常的 listener 后
  `schedflow_event_listener_errors_total` 增加；启动/暂停/恢复/关闭后
  `schedflow_scheduler_state` 分别为 1/2/1/0；派发队列深度可读。
- [ ] 实现：
  - EventBus listener except 分支调用 `counter_inc("schedflow_event_listener_errors_total")`；
  - Scheduler `start/pause/resume/shutdown` 调用 `gauge_set("schedflow_scheduler_state", ...)`；
  - `_run_due_job`/`_dispatch_loop` 后 `gauge_set("schedflow_dispatch_queue_depth", queue.size())`；
  - `_on_job_finished` 调用 `counter_inc("schedflow_job_runs_total", labels={"outcome": kind.split(".")[-1]})`
    与 `histogram_observe("schedflow_job_run_duration_seconds", log.duration or 0)`；
  - 主循环异常计数器 `schedflow_main_loop_errors_total`。
- [ ] 运行测试并提交 `feat(core): instrument scheduler and event bus metrics`。

### Task 3: `/api/metrics` 端点

**Files:** `api/rest/routers.py`、`tests/test_api_rest/test_api_rest.py`

- [ ] 测试：`GET /api/metrics` 返回 200、`text/plain; version=0.0.4`、包含
  `schedflow_scheduler_state`。
- [ ] 实现：

```python
from fastapi.responses import PlainTextResponse
from schedflow.core.metrics import render_prometheus

@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def metrics():
    return PlainTextResponse(
        render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
```

- [ ] 运行 `pytest tests/test_api_rest -q` 并提交 `feat(api): expose prometheus metrics endpoint`。

### Task 4: 结构化 JSON 日志

**Files:** 新增 `src/schedflow/utils/logging.py`；`configs/settings.py`；`api/__init__.py`；
新增 `tests/core/test_logging.py`

- [ ] 测试：`JsonFormatter` 输出可 `json.loads`，包含 message 与 extra 字段
  （job_id/node_id/status/duration_ms）；`SCHEDFLOW_LOG_FORMAT=json` 时
  `configure_logging()` 给 root handler 安装该 formatter。
- [ ] 实现：
  - settings 增加 `LOG_FORMAT: str = "text"`（env `SCHEDFLOW_LOG_FORMAT`）；
  - `JsonFormatter` 白名单字段输出 JSON；
  - `configure_logging(force=False)`；`create_app()` 调用一次。
- [ ] 运行测试并提交 `feat(utils): add structured json logging`。

### Task 5: Webhook sink

**Files:** 新增 `src/schedflow/core/webhook.py`；新增 `tests/core/test_webhook.py`

- [ ] 测试：用 `http.server` 起本地接收端；配置
  `{"url": "http://127.0.0.1:<port>/hook", "events": ["job.succeeded"], "secret": "s"}`；
  sink 订阅 EventBus 并 publish 一条 `job.succeeded`，断言收到 JSON 与
  `X-SchedFlow-Secret` header；publish 一条 `job.started` 断言不投递。
- [ ] 实现 `WebhookConfig`、`WebhookEventSink`：
  - 有界 `queue.Queue(maxsize=1000)` + 单 worker 线程；
  - `urllib.request` POST，`timeout=5`，重试 3 次指数退避；
  - 失败日志 + 指标 `schedflow_webhook_failures_total`；
  - `start(scheduler)` 订阅 `"*"`，`close()` 停线程；
  - payload：kind/job_id/run_time/detail/record 摘要/log 摘要。
- [ ] 运行测试并提交 `feat(core): add webhook event sink`。

### Task 6: Webhook / 限流 settings 持久化与 API

**Files:** `settings/services.py`、`api/routers/settings.py`、`api/schemas.py`、
`api/__init__.py`、`tests/test_api/test_settings_ops.py`

- [ ] 测试：`GET/PUT /api/v1/settings/webhooks` 与
  `GET/PUT /api/v1/settings/rate-limit` 往返持久化；PUT 更新后
  `app.state.webhook_sink.reload(config)` 被调用（可用 stub 断言）。
- [ ] 实现：
  - services：`get_webhooks_config/set_webhooks_config`（JSON 字符串存
    system_settings key `webhooks`）、`get_rate_limit_config/set_rate_limit_config`
    （key `rate_limit`，默认 `{"enabled": False, "rpm": 120}`）；
  - settings router 四个端点；
  - `create_app` 在 lifespan 中根据配置启动 `WebhookEventSink`，保存到
    `app.state.webhook_sink`；shutdown 时 close。
- [ ] 运行测试并提交 `feat(api): webhook and rate-limit settings`。

### Task 7: API 限流

**Files:** `src/schedflow/api/middleware.py`、`api/__init__.py`、
`tests/test_api/test_middleware.py`

- [ ] 测试：token bucket 单测（rpm=60，连续 2 次通过、第 3 次拒绝）；
  端点测试：`rate_limit={"enabled":True,"rpm":1}` 下第二次写请求返回 429 且带
  `Retry-After`；GET 请求不受限。
- [ ] 实现 `TokenBucketLimiter` 与 `RateLimitMiddleware`：
  - 仅拦截 `POST/PUT/PATCH/DELETE` 且路径以 `/api/` 开头；
  - key 优先 `request.state.auth.subject`，回退 `request.client.host`；
  - 超限返回 `APIResponse(code=-1,message="Too many requests")` 与 `Retry-After`；
  - `create_app` 根据 persisted rate_limit 配置安装中间件（默认关闭）。
- [ ] 运行测试并提交 `feat(api): in-process rate limiting`。

### Task 8: SSE 执行状态推送

**Files:** `api/routers/sse.py`、`tests/test_api/test_sse.py`

- [ ] 测试（generator 级）：

```python
async def test_job_events_stream_first_event():
    scheduler = Scheduler()
    stream = _job_events_stream(scheduler, "j1")
    agen = stream.__aiter__()
    scheduler._events.publish(SchedulerEvent("job.started", job_id="j1"))
    chunk = await asyncio.wait_for(agen.__anext__(), timeout=2)
    assert "job.started" in chunk
```

- [ ] 实现 `_job_events_stream(scheduler, job_id)`：
  - `scheduler.on("*", on_event)`，用 `loop.call_soon_threadsafe` 写入
    `asyncio.Queue`；
  - 连接时先回放 `scheduler.list_job_runs(job_id)[:1]` 的快照摘要；
  - `asyncio.wait_for(queue.get(), 15)` 超时发 `: heartbeat` 注释；
  - finally `scheduler.off("*", on_event)`；
  - 新增 `GET /sse/jobs/{job_id}/events`。
- [ ] 运行测试并提交 `feat(api): stream job execution events over sse`。

### Task 9: 前端 P2

**Files:** `frontend/src/composables/useJobSse.ts`、`views/jobs/JobDetail.vue`、
`views/logs/ExecutionOutput.vue`、`views/settings/WebhookSettings.vue`、
`views/settings/SystemSettings.vue`、`api/settings.ts`、`types/*`、`router/index.ts`、
`components/layout/AppSidebar.vue`

- [ ] 新增 `useJobSse(jobId, handlers)`：EventSource + token query，返回 cleanup；
- [ ] JobDetail 接入：显示最近一次 `job.*`/`task.*` 事件，收到 task 事件刷新运行详情；
- [ ] 新增 WebhookSettings 页面：URL/事件/secret 的增删改 + 保存；
- [ ] SystemSettings 增加限流开关与 rpm；settings API/类型补齐；
- [ ] 注册路由与侧栏入口；
- [ ] `npm run type-check && npm run build` 通过后提交
  `feat(frontend): live job events and observability settings`。

### Task 10: 文档 / 示例 / 架构图 / changelog（P2）

**Files:** `docs/installation.*`、`docs/user-guide/core-features.*`、`advanced-usage.*`、
`docs/api-reference/index.*`、`docs/index.*`、`docs/images/schedflow-architecture.json`、
`CHANGELOG.md`、`docs/changelog.*`

- [ ] 文档：`SCHEDFLOW_LOG_FORMAT=json`、`/api/metrics`、SSE events、
  webhook 配置示例、限流配置与 429；
- [ ] 架构图卡片补一句“Webhook / Prometheus / SSE 事件外发”；
- [ ] archify `validate` + `deliver` + `visual-check`；
- [ ] changelog 增加 P2 条目；
- [ ] 提交 `docs: P2 observability and integrations`。

### Task 11: 最终验证（P2 DoD）

- [ ] `python -m pytest` 全绿（外部服务缺失仅 skip）
- [ ] `ruff check .` 无告警
- [ ] 前端 type-check/build 通过
- [ ] `/api/metrics`、webhook、SSE、JSON 日志、限流各有测试覆盖
- [ ] 文档 zh/en 与 changelog 更新；架构图重新交付

