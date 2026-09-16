# SchedFlow 交互优化与 Webhook 平台适配设计

> 目标：修正会话过期后的跳转行为，收敛工作流列表/详情/日志中的低价值操作，
> 并让 Webhook 通知真正可以投递到钉钉、企业微信、飞书。

## 1. 背景与问题

| # | 现象 | 根因 |
|---|------|------|
| 1 | 长时间不操作后页面报 `Forbidden: invalid or missing credentials` 并跳回首页 | 前端只清了 `localStorage`，未清 Pinia `auth.token`，路由守卫据内存 token 判定"已登录"，把 `/login` 弹回 `/dashboard` |
| 2 | 列表行内"取消"按钮点完提示"任务未在运行，无法取消" | 按钮可见性依据 `job_status`（启用/暂停），与"是否正在执行"无关 |
| 3 | 详情页并列「全量执行」「恢复执行」，列表无执行入口 | 操作位置与实际使用场景不匹配 |
| 4 | 执行记录中每条都显示"全量执行" | mode 为默认值，对每条记录展示属于噪音 |
| 5 | Webhook 配置后收不到通知，测试却可能显示成功 | 报文不是平台要求的结构；平台用 `HTTP 200 + errcode/code` 表达失败，而 `deliver_once` 只看 HTTP 状态码 |

### 1.1 Webhook 问题的实测证据

用模拟平台响应的本地服务调用现有 `deliver_once`：

```
/dingtalk-bad-format  -> {'ok': True, 'status_code': 200, 'error': None}   # 平台响应 errcode=300001
/wecom-bad-format     -> {'ok': True, 'status_code': 200, 'error': None}   # 平台响应 errcode=40008
/feishu-bad-format    -> {'ok': True, 'status_code': 200, 'error': None}   # 平台响应 code=19021
```

发送的 body 为内部结构 `{"kind","job_id","run_time","detail"}`，平台会拒收；
而"测试投递成功"来自对 HTTP 200 的误判。

## 2. 目标 / 非目标

**目标**

- 会话失效时清空内存态并跳转 `/login`，只提示一次可读文案，登录后回到原页面。
- 移除列表行内"取消"，改为在详情页依据真实运行状态操作。
- 执行入口统一到列表操作栏；详情页承载"取消当前执行"。
- Webhook 支持 通用 JSON / 钉钉 / 企业微信 / 飞书 四种目标，且失败可被准确识别。
- 集成页重做为卡片式配置，平台与事件选择有明确的可视反馈。

**非目标**

- 不引入第三方 SDK 或新依赖（`urllib` + `hmac/hashlib/base64` 足够）。
- 不改动 `events` 匹配语义（`*` / 精确 / `前缀.*` 保持不变）。
- 不改动 generic 模式的既有 JSON 契约，存量配置零迁移。
- 不为"平台参数错误"做重试（重试仅对网络/5xx 有意义）。

## 3. 设计

### 3.1 会话失效（前端）

新增 `frontend/src/utils/session.ts`，避免 `api/client.ts` 与 `stores/auth` 之间形成
循环依赖：

```ts
export function onSessionExpired(handler: (redirect: string) => void): void
export function expireSession(reason?: 'expired' | 'forbidden'): void
```

- `expireSession()` 幂等（同一轮失效只回调一次），记录当前路由作为回跳目标。
- `api/client.ts` 的响应拦截器在 **401/403** 时调用 `expireSession()`，且不再把
  后端原文 `Forbidden: ...` 当作用户提示。
- `main.ts` 注册回调：清空 auth store → `router.replace({ path: '/login', query: { redirect } })`
  → 单次 `ElMessage.warning('登录状态已失效，请重新登录')`。
- 路由守卫在跳 `/login` 时携带 `redirect`；`Login.vue` 登录成功后回跳该地址，
  非法值回落到 `/dashboard`。
- 跳转导致详情页卸载，`useJobSse`/`connectNextRunTimeSSE` 的 `onBeforeUnmount`
  自动关闭 SSE，避免过期 token 触发 EventSource 无限重连。

### 3.2 任务列表 / 详情 / 日志

- `JobList.vue`：行内移除「取消」，操作栏变为 `详情 | 执行 | 复制 | 删除`；「执行」
  调 `POST /api/jobs/{id}/run`（`mode=full`）。
- `JobDetail.vue`「运行信息 → 执行」：移除两个执行按钮，改为单个「取消当前执行」，
  依据 `GET /api/jobs/{id}/runs` 中是否存在 `status === 'running'` 的运行决定
  可用性（`_prepare_run()` 对每种模式都会落一条 running 快照，运行结束才改状态，
  因此该信号可靠）；无运行中任务时按钮置灰并给出说明。
- `ExecutionList.vue`：移除 mode 标签；仅当 `mode === 'resume'` 且带
  `resumes_from` 时保留一个轻量「续跑」角标。

### 3.3 Webhook 平台适配（后端）

`WebhookConfig` 新增 `platform` 字段（`generic` / `dingtalk` / `wecom` / `feishu`，
缺省 `generic`，未知值回落 `generic` 并保持可用）。

| 平台 | 请求体 | `secret` 用途 | 失败判定 |
|------|--------|---------------|----------|
| generic | 现有完整 JSON | `X-SchedFlow-Secret` 请求头 | HTTP 状态码 |
| dingtalk | `{"msgtype":"markdown","markdown":{"title","text"}}` | 加签：`timestamp` + HMAC-SHA256(Base64) 追加到 URL 查询串 | `errcode != 0` |
| wecom | `{"msgtype":"markdown","markdown":{"content"}}` | 无签名（关键词/IP 白名单由平台侧配置） | `errcode != 0` |
| feishu | `{"msg_type":"text","content":{"text"}}` | 签名：body 内 `timestamp` + `sign`（key = `timestamp\nsecret`） | `code != 0` |

- 通知正文由事件生成：标题（事件中文名）+ 任务名/ID + 状态 + 时间 + 节点/错误摘要。
  任务名在事件入队时用 `scheduler.get_job(job_id)` 尽力补齐（失败不阻塞投递）。
- `deliver_once()` 读取响应体（截断保存），命中平台错误即返回 `ok=False`
  并带上 `errmsg`，不再重试；网络错误/5xx 仍按 3 次退避重试。
- 返回值扩展为 `{ok, status_code, error, duration_ms, platform, response}`，
  供测试端点与日志使用。

### 3.4 集成页重做（前端）

`ObservabilitySettings.vue` 由"表格式多行"改为**每个 webhook 一张卡片**：

1. 平台选择（分段按钮）：通用 JSON / 钉钉 / 企业微信 / 飞书 —— 用户据此创建对应类型的通知。
2. 回调地址：按平台给出占位与提示（钉钉加签、企微关键词、飞书校验）。
3. 订阅事件：`el-select` 多选（分组、标签展示、`collapse-tags`），并显示
   "已选 N 个事件 / 未选择表示订阅全部事件"，解决原 `<select multiple>`
   选中后看不出结果的问题。
4. 密钥：标签随平台变化（企微不显示签名输入）。
5. 「发送测试」就地展示结果面板：状态徽标、HTTP 状态码、平台返回、耗时。

### 3.5 空触发器守卫（补充）

验收时发现：不填任何触发器字段就创建工作流，会生成全 `*` 的 cron
（或 0 间隔的 interval），任务因此**每秒执行一次**。这是既有行为，与本次改动无关，
但用户极易踩到，故一并修复。

守护放在 **API 边界**（`api/trigger_validation.py` 的 `ensure_schedulable()`），
而不是触发器类内部：触发器需要保留「空 cron = 每秒」的既有语义，因为
pickle 反序列化会以部分字段重建模型、既有测试也用 `CronTrigger(start_date=...)`
构造只带时间窗的触发器。规则：

| 触发器 | 规则 | 例外 |
|--------|------|------|
| cron | 至少要有一个时间字段（8 个字段之一，空串/None 不算） | 显式写 `second='*'` 仍可表达"每秒" |
| interval | 周/天/时/分/秒换算后必须 > 0 | — |
| date | 必须有 `run_date`，否则永不执行 | — |
| and / or | 递归校验嵌套触发器 | — |

违规抛 `TriggerValidationError` → 新增全局处理器映射为 **422**（此前触发器类异常
会落到 catch-all 变成 500）。前端 `TriggerConfig` 暴露 `validate()`，创建/编辑任务
时先本地拦截并自动切到「触发器配置」页签，把同一句话给用户看。

## 4. 兼容性

- `WebhookConfig.from_dict()` 对缺失/未知 `platform` 回落 `generic`，存量配置无需迁移。
- generic 的请求体、`X-SchedFlow-Secret` 头、事件匹配规则均不变。
- `Job`/`ExecutionLog` 的 REST 序列化契约不变（本次不动后端调度栈）。
- 触发器类本身语义不变（库调用、pickle、既有测试不受影响），只新增 Web API 边界校验；
  全 `*` 的 cron 仍可用 `second='*'` 显式表达。

## 5. 测试策略

- 后端：`tests/core/test_webhook.py` 先写失败用例（平台报文、加签、平台错误识别、
  未知平台回落）；`tests/test_api/test_settings_ops.py` 覆盖 platform 透传与测试端点。
- 前端：`vitest` 覆盖会话失效去重与回跳目标计算；类型检查 + 构建作为回归门槛。
- 端到端：真实启动后端 + 构建产物，人工验证 5 项：过期 token 跳登录、列表无取消、
  详情可取消（无运行时置灰）、日志无"全量执行"字样、集成页可选平台并发送测试。

## 6. 风险

- 钉钉加签/飞书签名依赖平台文档的正确实现，若平台调整算法需同步更新；两者均有单测覆盖。
- 会话失效回调依赖 `main.ts` 注册；未注册时退化为仅清理存储（不跳转），不影响主流程。
