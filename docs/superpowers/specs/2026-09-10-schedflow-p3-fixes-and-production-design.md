# SchedFlow P3 修复与生产化设计（前端一致性 / 调度状态机 / 容器部署）

> 日期：2026-09-10
> 状态：待评审
> 范围：DAG 画布渲染、调度暂停语义、REST 更新端点、前端样式体系、设置页信息架构、容器化生产前端。不做多实例/HA，不改插件注册表与序列化契约。

## 1. 背景

使用者在实际运行中报告了四类问题，并要求“生产环境更正式、性能更佳”：

1. 工作流 DAG 画布不显示工作流；
2. 新增页面（可观测性与集成）样式与既有页面不一致；
3. “运行限流”语义不清、Webhook 不知道如何配置使用；
4. 任务在前端显示为“关闭”，但日志显示仍按触发器持续执行。

### 1.1 实测证据（本设计的依据，均已在隔离实例复现）

| # | 现象 | 复现方式 | 证据 |
|---|------|----------|------|
| 1 | DAG 画布空白 | 打开任务详情页 | 控制台 `TypeError: ac.Graph is not a constructor`（`WorkflowEditor` 分包）；节点添加在布局函数之后，异常使 `loadDag` 中断，画布无任何节点 |
| 2 | 暂停任务仍执行 | 隔离实例 pause → reschedule | 返回 `status=paused` 且 `next_run_time=22:07`；随后连续执行 3 次 |
| 2 | 暂停任务仍执行 | 读取现有 `data/jobs.db` | 任务 `test` 为 `status=paused`、`next_run_utc=2026-09-10T14:02:00+00:00`，已有 587 条执行日志，最近一次 22:01 |
| 3 | 编辑保存失败 | `PUT /api/jobs/{id}` 携带 trigger | HTTP 500 `AttributeError: 'dict' object has no attribute 'to_trigger'`（`api/rest/routers.py:99`） |
| 4 | 新页面样式异常 | 计算样式对比 `/jobs` 与 `/observability-settings` | `.btn-primary`：`rgb(59,130,246)`/圆角 10px/padding 9-18px → `rgb(240,240,240)`/outset 边框/圆角 0/padding 0；`.toggle-switch` 高度 3.6px；`.form-input` 为默认 inset 白框 |
| 5 | 构建产物不干净 | `npm run build-only` 前后对比 | `dist/assets` 残留 94 个文件、含 5 份旧 `index-*.js`；marker 文件在构建后仍存在，`--emptyOutDir` 亦未清理 |

限流与 Webhook 的现状（代码核对）：限流只作用于 `/api/**` 的写请求（`api/middleware.py` 的 `RateLimitMiddleware` + `TokenBucketLimiter`），按登录主体或客户端 IP 计数，进程内生效；Webhook 由 `core/webhook.py` 的 `WebhookEventSink` 投递，配置 `{url, events, secret, timeout}`，保存后经 `_apply_webhook_sink` 热加载，事件名取自 `core/events.py` 的 `EVENT_KINDS`。

## 2. 范围

### 2.1 纳入范围

| 阶段 | 内容 |
|------|------|
| P3-A | 调度暂停语义修复：`status` 作为唯一可调度真值、存储层过滤、启动自愈 |
| P3-B | `PUT /api/jobs/{id}` 500 修复 |
| P3-C | 前端 DAG 渲染修复与依赖显式化 |
| P3-D | 前端样式体系：组件层样式全局化，消除页面级重复定义 |
| P3-E | 信息架构：API 写限流归入系统设置；集成页 Webhook 可用化 |
| P3-F | 生产前端容器化：`nginx:alpine` 托管构建产物并反代 `/api` |

### 2.2 明确不做

- 多 Scheduler 实例、Leader 选举、分布式锁（HA）；
- 引入 Tailwind / shadcn / 其它 UI 框架或替换 Element Plus；
- 全量收敛历史硬编码色值（`views` 内约 360 处、`components` 内约 23 处，只收敛本次改动涉及的）；
- 改动 `TaskSpec` / `Workflow` / `Job` / `ExecutionLog` 的 JSON 契约、`EVENT_KINDS` 列表、插件注册表（`EXECUTOR_PLUGINS` / `JOBSTORE_PLUGINS` / `TRIGGER_PLUGINS`）；
- 重建 `schedulers/`、`executors/`、`jobstores/`、`models/`、`events/` 等旧包结构。

## 3. 关键设计决策

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| D1 | 可调度真值 | `Job.status == "running"` 是唯一判定；不变式 `next_run_time is not None → status == "running"` | 消除“状态与下次运行时间各说各话” |
| D2 | 写入点收敛 | Scheduler 内集中 `_arm(job, now)` / `_disarm(job)` 两个助手 | 只有一处允许计算 `next_run_time`，避免再出现旁路 |
| D3 | reschedule 语义 | 对 `paused` 任务只更新触发器、保持未武装；对 `completed` 保持现有“提供触发器即恢复为 running”的行为 | 修复故障路径，同时不改动 P0/P1 已确立的一次性任务语义 |
| D4 | 存储层防御 | 四个 JobStore 的 `get_due()` / `get_next_run_time()` 均跳过非 `running` 任务 | 即使有旁路写入也不会执行，且避免主循环空转 |
| D5 | SQL/Mongo 过滤实现 | 新增 `status` 列/字段（可空）+ 回填 + 索引，查询直接过滤 | 若只在内存里过滤，`get_next_run_time()` 可能返回陈旧时间导致主循环 0 秒忙等 |
| D6 | 存量坏数据 | `Scheduler.start()` 启动时自愈：非 `running` 却已武装的任务清空 `next_run_time` 并写回，记 WARNING | 使用者库中已存在该状态，需自动纠正而非手工修库 |
| D7 | 更新端点 | `PUT /api/jobs/{id}` 先取 pydantic 模型对象再 `model_dump`，dump 时排除 `workflow`/`trigger` | 修掉嵌套模型被转 dict 后调用方法导致的 500 |
| D8 | DAG 布局 | 改为 `new dagre.graphlib.Graph()` + `dagre.layout(g)`，并把 `dagre` 提升为显式依赖 | 当前 `import dagre, { Graph } from 'dagre'` 与实际安装的 dagre 0.8.5 导出不符 |
| D9 | 布局失败降级 | 布局异常时回退到简单纵向栅格并 `console.error`，仍渲染节点 | 一个布局异常不应导致整张画布空白 |
| D10 | 样式体系 | 保留 `App.vue` 的语义层令牌；新增组件层 `src/styles/components.css` 作为全局共享样式 | 三层令牌（primitive→semantic→component）中缺的是组件层 |
| D11 | 限流归位 | “运行限流”正名为 **API 写限流**，并入“系统设置”标签页 | 它只限制 API 写请求，与“可观测性”无关 |
| D12 | Webhook 位置 | 保留独立“集成”页，补齐标签、事件多选、说明与测试能力 | 集成配置与主题/变量不同类，但表单可用性必须达标 |
| D13 | 生产前端 | 构建产物由 `nginx:alpine` 托管，反代 `/api` 到 `api:8000`；镜像内不再包含 Node | 容器部署下最小改动、可获得缓存与 gzip 控制 |
| D14 | SSE 代理 | nginx 对 `/api/v1/sse/` 关闭 `proxy_buffering` 并放宽超时 | 否则 SSE 事件会被缓冲，前端收不到实时推送 |
| D15 | 构建确定性 | 构建前显式清理 `dist`（脚本级，不新增依赖） | 现状残留 94 个文件/5 份旧入口包 |

## 4. 详细设计

### 4.1 调度状态机（P3-A）

**不变式**：`status == "running"` ⟺ 任务可被调度；`next_run_time` 非空只允许出现在 `running` 状态。

写入点收敛为两个助手（`core/scheduler.py`）：

- `_arm(job, now)`：仅当 `status == "running"` 且有触发器时计算 `next_run_time`，否则等价于 `_disarm`；
- `_disarm(job)`：`next_run_time = None`。

调用关系：

| 入口 | 变更后行为 |
|------|------------|
| `pause_job()` | `status="paused"` + `_disarm` + `store.update`（行为不变） |
| `resume_job()` | `status="running"` + `_arm` + `store.update`（`completed` 早返回保持现状） |
| `update_job(trigger=...)` | 触发器与参数照常更新；`status == "running"` 才 `_arm`；`paused` 保持未武装；`completed` 保持现有恢复语义 |
| `reschedule_job()` | 复用 `update_job`，因此同样不会唤醒 `paused` 任务 |
| `_advance()` | 仍在派发前持久化下一次运行时间，但改为经 `_arm` 语义计算，`status != "running"` 时 `_disarm` |

存储层防御（四个实现）：

| Store | 到期查询 | 下次运行时间查询 |
|-------|----------|------------------|
| `MemoryJobStore` | `_clean_heap()` 额外弹出 `status != "running"` 的堆项 | 同左，天然生效 |
| `SQLAlchemyJobStore` | `next_run_utc IS NOT NULL AND next_run_utc <= now AND status = 'running'` | 同条件 + `ORDER BY next_run_utc LIMIT 1` |
| `MongoDBJobStore` | `next_run_utc <= now AND status = 'running'` | 同条件 + 升序取首条 |
| `RedisJobStore` | zset 取到期 id 后按 `status == "running"` 过滤 | 按分数升序扫描直至首个 `running` 条目 |

SQL/Mongo 的 `status` 列/字段沿用现有迁移风格（`_ensure_schema` 检测缺列 → 补列 → `_backfill_*` 回填），与最近一次“schema migration concurrency-safe”改动保持一致。

启动自愈：`Scheduler.start()` 在启动线程前调用 `_repair_armed_paused_jobs()`，遍历各 store 的 `get_all()`，对 `status != "running" and next_run_time is not None` 的任务 `_disarm` + `store.update`，并记录一条 WARNING（包含任务 id 列表）。

### 4.2 更新端点（P3-B）

```python
workflow = request.workflow.to_workflow() if request.workflow is not None else None
trigger = request.trigger.to_trigger() if request.trigger is not None else None
changes = request.model_dump(exclude_none=True, exclude={"workflow", "trigger"})
```

保持 `JobUpdateRequest` 字段不变，响应仍为 `job.to_dict()`。

### 4.3 前端 DAG 渲染（P3-C）

- `import dagre from 'dagre'` + `const g = new dagre.graphlib.Graph()` + `dagre.layout(g)`，`computeDagreLayout` 与 `applyAutoLayout` 两处一致；
- `frontend/package.json` 显式声明 `dagre@^0.8.5`，`@types/dagre` 进 devDependencies（不再依赖 `@logicflow/layout` 的传递依赖被提升）；
- 布局异常时降级：按 `rankdir: 'TB'` 的简单栅格摆放节点，保证节点与连线可见，同时输出 `console.error`；
- 只读视图继续禁用拖拽与文本编辑（现状保持）。

### 4.4 前端样式体系（P3-D）

保留 `App.vue` 中的语义层令牌与明暗两套主题（视为唯一真值），新增 `frontend/src/styles/components.css` 作为**组件层**，`main.ts` 引入。组件层类清单：

| 类名 | 令牌来源 | 状态要求 |
|------|----------|----------|
| `.btn-primary` | `--color-primary` / `--radius-md` / `--shadow-glow` | default / hover / active / disabled |
| `.btn-ghost`、`.action-btn`（含 `.danger`） | `--bg-surface` / `--border-default` / `--color-danger` | hover / active / disabled |
| `.form-group`、`.form-input`、`.form-select` | `--text-secondary` / `--bg-surface` / `--border-default` | focus 可见描边 |
| `.toggle-switch` | `--color-success` / `--border-default` | on / off / disabled / loading |
| `.settings-tabs`、`.settings-card`、`.page-title`、`.section-title`、`.section-desc` | `--space-*` / `--border-subtle` | 与系统设置一致 |

规则：

1. 组件层内禁止裸 hex，一律引用语义令牌；
2. 按下表移除重复定义，改为共用组件层；
3. 新页面统一结构：`<h1 class="page-title gradient-text">` + `.settings-card` + `.section-title` / `.section-desc`；
4. 表单可用性遵循 ui-ux-pro-max 规则：每个输入框有可见 `<label>`（不得仅用 placeholder）、关键字段带 helper text、提交后给出成功/失败反馈、交互元素具备可见焦点态、可点击控件高度不低于 32px（桌面端）。

**重复定义清单（自检结果）**：

| 文件 | 本地定义 | 与全局的差异 | 处理 |
|------|----------|--------------|------|
| `views/jobs/JobList.vue` | `.btn-primary`、`.action-btn`、`.toggle-switch` | 与 `JobDetail.vue` 中的同名定义逐值一致 | 直接上移，无视觉变化 |
| `views/jobs/JobDetail.vue` | `.btn-primary`、`.action-btn`、`.toggle-switch`、`.form-input`、`.form-group` | 同上 | 直接上移，无视觉变化 |
| `views/settings/SystemSettings.vue` | `.page-title`、`.settings-tabs` | 其它页面缺失这两个类（`AppTopbar` 自带一份 `.page-title`） | 上移为组件层，系统设置页改用全局 |
| `views/settings/ApiKeyManager.vue`、`views/settings/VariablesManager.vue` | `.section-title`、`.section-desc` | `.section-desc` 用 `var(--el-text-color-secondary)` 与 `16px`，全局用 `var(--text-muted)` 与 `var(--space-md)` | 统一到全局令牌，属**有意的视觉收敛**，需逐页回归 |
| `views/jobs/NodeInfoSidebar.vue` | `.section-title`（13px、裸 hex `#606266`） | 与全局 15px 规格不同，含硬编码色 | 统一到全局令牌，属**有意的视觉收敛**，需逐页回归 |

收敛后的组件规格以 `design-system` 的组件状态表为准（default / hover / active / disabled 四态齐全），并保留现有主色与圆角令牌取值——本次不换配色，只消除“同一类名、多份实现”的漂移。

### 4.5 信息架构（P3-E）

**API 写限流**（`SystemSettings.vue` 新增标签页）：

- 名称：“API 写限流”；
- 说明文案：仅作用于 `POST/PUT/PATCH/DELETE /api/**`；按登录主体（未认证时按客户端 IP）计数；进程内计数，多 worker 场景各自独立；与任务执行频率无关；
- 字段：启用开关、每分钟请求上限（rpm），沿用 `GET/PUT /api/v1/settings/rate-limit`。

**集成页**（`ObservabilitySettings.vue`，标题由“可观测性与集成”改为“集成”，路由 `/observability-settings` 不变）：

- 移除限流卡片；
- Webhook 表单重构：可见 label、URL 校验提示、事件多选（按 `scheduler.* / job.* / task.*` 分组列出 `EVENT_KINDS`）、secret 说明（投递时作为 `X-SchedFlow-Secret` 头）、启用/停用由“是否在列表中”表达；
- 新增“发送测试”按钮，调用新增端点 `POST /api/v1/settings/webhooks/test`；
- 保留每行的删除与整体保存，保存结果给出明确反馈；
- 侧栏与路由标题同步为“集成”。

**新增端点**：`POST /api/v1/settings/webhooks/test`

- 请求体：`{"url": str, "events": [str] | null, "secret": str | null, "timeout": float | null}`（未提供 `url` 时使用已保存的第一条配置）；
- 行为：构造示例事件负载（`kind` 取请求中事件的第一个，默认 `job.succeeded`，`job_id="test"`，附带说明性 `detail`），走与真实投递相同的代码路径（`core/webhook.py` 抽出可复用的 `deliver_once()`），返回投递结果；
- 响应：`{"ok": bool, "status_code": int | null, "error": str | null, "duration_ms": float}`；
- 说明：该端点为同步投递（最长等于 `timeout`，默认 5s），仅用于人工验证。

可选（低优先级，评审时可删）：在集成页增加“指标与端点”卡片，展示 Prometheus `/api/metrics` 与 SSE `/api/v1/sse/jobs/next-run-time` 的地址与用途说明。

### 4.6 生产前端容器化（P3-F）

`Dockerfile` 的 `web` 阶段：

```
FROM node:22-alpine AS web-build      # npm ci + 清理 dist + vite build
FROM nginx:alpine AS web              # 拷贝 dist + nginx 模板
```

`frontend/nginx.conf.template`（用官方镜像的 envsubst 模板机制，保持 `SCHEDFLOW_API_URL` 变量名不变）：

- `location /assets/` → `expires 1y` + `Cache-Control: public, immutable`；
- `location = /index.html` → `Cache-Control: no-store`；
- `location /` → `try_files $uri /index.html`（SPA fallback）；
- `location /api/` → `proxy_pass ${SCHEDFLOW_API_URL}`（不带尾斜杠，避免路径被重写），转发 `Host`/`X-Real-IP`/`X-Forwarded-For`/`X-Forwarded-Proto`；
- `location /api/v1/sse/` → 在上一段基础上 `proxy_buffering off`、`proxy_cache off`、`proxy_read_timeout 1h`、`proxy_http_version 1.1`、`Connection ""`；
- `gzip on` 且覆盖 `text/css`、`application/javascript`、`application/json`、`image/svg+xml`。

`docker-compose.yml` 的 `web` 服务：端口 `18001:80`，`SCHEDFLOW_API_URL` 默认 `http://api:8000`，依赖 `api`，`restart: unless-stopped`。

本地开发与预览：

- 开发仍用 `schedflow-frontend --dev`（Vite dev server + `/api` 代理）；
- `schedflow-frontend`（无 `--dev`）保留但明确为“本地预览构建产物”，并在构建前显式清理 `dist`（`frontend/scripts/clean-dist.mjs`，无新增依赖）；
- 生产部署文档指向 compose/nginx 路径。

### 4.7 实施顺序

按“先修正确性、再统一外观、最后改部署”的顺序推进，保证每一步都可独立验证：

1. P3-A + P3-B（后端状态机与更新端点，含回归测试）；
2. P3-C（DAG 渲染，先在隔离实例验证画布恢复）；
3. P3-D（组件层样式上移与漂移收敛，逐页计算样式回归）；
4. P3-E（限流标签页与集成页 Webhook 可用化，含新增测试端点）；
5. P3-F（nginx 容器化与构建确定性，最后做整栈验收）。

## 5. 契约与兼容性影响

| 面 | 影响 |
|----|------|
| REST | 新增 1 个端点（webhook 测试）；无删除、无重命名；统一响应封装与异常映射不变 |
| 序列化 | `TaskSpec` / `Workflow` / `Job` / `ExecutionLog` JSON 结构不变 |
| 事件 | `EVENT_KINDS` 不变（测试端点不发布事件，直接投递示例负载） |
| 数据库 | SQLAlchemy jobstore 新增可空 `status` 列、MongoDB jobstore 新增 `status` 字段，自动补列/回填；Redis 无 schema 变化 |
| 前端路由 | 无删除；“可观测性与集成”标题改为“集成”，`/observability-settings` 路径不变 |
| 插件契约 | 执行器/存储器/触发器名称与参数 schema 不变（`tests/test_api_rest/test_frontend_parity.py` 继续通过） |

已知不对称（本次记录不改）：`resume_job()` 对 `status == "completed"` 的任务直接返回，既不重新武装也不改状态；前端任务列表对已完成任务不提供恢复入口。若后续需要“重跑已完成任务”，另行设计。

## 6. 测试策略

后端（`pytest`，先写失败测试）：

1. `tests/core/test_scheduler_pause.py`（新增）：暂停后即使 `update_job(trigger=...)`/`reschedule_job()` 也不得产生执行；`get_due`/`get_next_run_time` 忽略非 running 任务；启动自愈纠正存量数据。
2. Memory 与 SQLAlchemy 两套 store 各覆盖一遍（Redis/Mongo 在服务不可用时按现有约定跳过）。
3. `tests/test_api_rest/`：`PUT /api/jobs/{id}` 带 `workflow`/`trigger` 返回 200 且字段生效；`POST /api/v1/settings/webhooks/test` 的成功与失败分支（用本地 HTTP 桩或 monkeypatch `deliver_once`）。
4. 既有 `tests/test_api_rest/test_frontend_parity.py` 必须保持通过。

前端：

1. `npm run type-check`（`vue-tsc`）+ `npm run build-only`；
2. 隔离实例（独立 meta 库 + 端口）逐页回归：任务详情 DAG 画布内 `svg` 节点数等于工作流节点数、连线存在；集成页 `.btn-primary` / `.toggle-switch` / `.form-input` 的计算样式与系统设置页一致；暂停任务 90 秒内无新增执行日志；
3. 构建产物校验：`dist/assets` 中 `index-*.js` 只有 1 份。

## 7. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 启动自愈会停止使用者当前“被唤醒的暂停任务” | 这是期望行为；WARNING 日志列出被修复的任务 id，需要继续运行时显式 resume |
| 组件层样式全局化影响既有页面 | 改动前后用计算样式对比回归关键页面（任务列表/详情/设置） |
| SQL/Mongo schema 变更 | 复用现有缺列检测 + 回填模式；写操作已有 `_with_write_retry` |
| nginx 模板变量缺失导致反代地址为空 | 模板提供 `${SCHEDFLOW_API_URL}` 默认值 `http://api:8000`；compose 显式传入 |
| SSE 经代理后失效 | 专门 location 关闭缓冲，并在验收中实测事件推送 |
| 清理 `dist` 影响增量构建 | 只作用于构建产物目录；保留 marker 校验用例证明每次构建后仅一套入口包 |

## 8. 验收标准

1. `pytest` 与 `ruff check .` 全绿（含新增回归测试）；
2. 暂停任务在 `pause` 后不再产生新的执行日志，即使调用 reschedule；现有库中的存量坏数据在启动后自动纠正；
3. 任务详情页 DAG 画布正常渲染节点与连线，控制台无异常；
4. 编辑任务（含触发器/工作流）保存返回 200，界面提示成功；
5. 集成页与系统设置页共用同一套组件样式，表单具备可见 label、helper text 与提交反馈；
6. `docker compose up` 后 `web` 容器为 nginx，前端资源带 `immutable` 缓存头，`/api` 与 SSE 均可用，镜像内无 `node_modules`；
7. 每次构建后 `dist/assets` 仅保留一套入口包。

## 9. 参考

- 技能：`systematic-debugging`（根因定位与复现）、`design-system`（三层令牌与组件状态规范）、`ui-ux-pro-max`（表单与无障碍规则、数据密集型仪表盘基调）、`brainstorming` → `writing-plans`（设计与计划流程）；
- `ui-ux-pro-max` 检索记录：`--design-system "internal ops dashboard scheduler monitoring data-dense dark"`（得到 ops/实时监控基调：深色中性底 + 状态色 + 高密度）、`--domain ux "form labels validation helper text settings"`（可见 label、onBlur 校验、提交反馈、对比度 4.5:1）、`--stack vue`；
- `design-system` 校验脚本记录：`validate-tokens.cjs --dir frontend/src/views`（360 处硬编码）与 `--dir frontend/src/components`（23 处硬编码），作为“只收敛改动范围”范围的量化依据；
- 既有设计：`docs/superpowers/specs/2026-09-09-schedflow-architecture-optimizations-design.md`（P0/P1/P2）与对应实施计划。
