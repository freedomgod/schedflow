# SchedFlow 交互优化与 Webhook 平台适配实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复会话过期跳转、收敛任务列表/详情/日志的低价值操作，并让 Webhook 真正支持钉钉/企业微信/飞书。

**Architecture:** 前端把"会话失效"收敛为独立模块（`utils/session.ts`）供拦截器与路由/登录页共用；后端在 `core/webhook.py` 内做平台报文适配与签名，不动调度栈；集成页改为卡片式配置。

**Tech Stack:** Vue 3 + TypeScript + Vite + Element Plus + Pinia；Python 3.11 + FastAPI；`urllib`/`hmac`/`hashlib`/`base64`（无新依赖）。

**设计依据:** `docs/superpowers/specs/2026-09-16-ux-and-integration-design.md`

---

## 文件结构

| 文件 | 职责 | 动作 |
|------|------|------|
| `frontend/src/utils/session.ts` | 会话失效的单一入口（去重 + 回跳目标） | 新增 |
| `frontend/src/utils/__tests__/session.spec.ts` | 会话模块单测 | 新增 |
| `frontend/src/api/client.ts` | 401/403 交给 session 模块 | 修改 |
| `frontend/src/main.ts` | 注册失效回调（清 store + 跳登录） | 修改 |
| `frontend/src/router/index.ts` | `/login` 携带 `redirect` | 修改 |
| `frontend/src/views/auth/Login.vue` | 登录后回跳 | 修改 |
| `frontend/src/views/jobs/JobList.vue` | 行内「执行」、移除「取消」 | 修改 |
| `frontend/src/views/jobs/JobDetail.vue` | 「取消当前执行」按运行状态启用 | 修改 |
| `frontend/src/views/logs/ExecutionList.vue` | 移除 mode 标签，保留「续跑」角标 | 修改 |
| `src/schedflow/core/webhook.py` | 平台报文/签名/失败识别 | 修改 |
| `src/schedflow/api/schemas.py` | `WebhookConfigItem.platform` | 修改 |
| `tests/core/test_webhook.py` | 平台适配单测 | 修改 |
| `tests/test_api/test_settings_ops.py` | platform 透传 | 修改 |
| `frontend/src/api/settings.ts` | `WebhookConfig.platform` | 修改 |
| `frontend/src/views/settings/ObservabilitySettings.vue` | 集成页重做 | 重写 |

---

### Task 1: 会话失效整理

**Files:**
- Create: `frontend/src/utils/session.ts`
- Create: `frontend/src/utils/__tests__/session.spec.ts`
- Modify: `frontend/src/api/client.ts:27-38`
- Modify: `frontend/src/main.ts:16-22`
- Modify: `frontend/src/router/index.ts:70-96`
- Modify: `frontend/src/views/auth/Login.vue:56-80`

- [ ] **Step 1: 写失败测试**

```ts
import { describe, expect, it, vi } from 'vitest'
import { expireSession, onSessionExpired, resetSessionState } from '../session'

describe('session expiry', () => {
  it('notifies once per expiry and keeps the redirect target', () => {
    resetSessionState()
    const handler = vi.fn()
    onSessionExpired(handler)
    expireSession('/jobs/abc')
    expireSession('/jobs/abc')
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenCalledWith('/jobs/abc')
  })

  it('ignores public routes when computing the redirect target', () => {
    resetSessionState()
    const handler = vi.fn()
    onSessionExpired(handler)
    expireSession('/login')
    expect(handler).toHaveBeenCalledWith('/dashboard')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/utils/__tests__/session.spec.ts`
Expected: FAIL — `Failed to resolve import "../session"`

- [ ] **Step 3: 实现会话模块**

```ts
const PUBLIC_PATHS = ['/login', '/init-setup']
export const DEFAULT_REDIRECT = '/dashboard'

let handler: ((redirect: string) => void) | null = null
let expired = false
let pendingRedirect: string | null = null

export function onSessionExpired(fn: (redirect: string) => void): void { handler = fn }
export function resetSessionState(): void { expired = false; pendingRedirect = null }
export function consumeRedirect(): string | null { const v = pendingRedirect; pendingRedirect = null; return v }

export function expireSession(currentPath = window.location.pathname): void {
  if (expired) return
  expired = true
  pendingRedirect = PUBLIC_PATHS.includes(currentPath) ? DEFAULT_REDIRECT : currentPath
  handler?.(pendingRedirect)
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/utils/__tests__/session.spec.ts`
Expected: PASS

- [ ] **Step 5: 接入拦截器 / main.ts / 路由 / 登录页**

`client.ts`：`if (status === 401 || status === 403) expireSession()`，认证类错误不再用后端原文提示。
`main.ts`：`onSessionExpired((redirect) => { useAuthStore(pinia).clearAuth(); router.replace({ path: '/login', query: { redirect } }); ElMessage.warning('登录状态已失效，请重新登录') })`。
`router/index.ts`：跳 `/login` 时带 `query.redirect`。
`Login.vue`：登录成功后 `router.push(consumeRedirect() || '/dashboard')`。

- [ ] **Step 6: 类型检查与构建**

Run: `cd frontend && npx vue-tsc --build --force && npm run build-only`
Expected: 无错误

### Task 2: 列表 / 详情 / 日志操作收敛

**Files:** `frontend/src/views/jobs/JobList.vue`、`frontend/src/views/jobs/JobDetail.vue`、`frontend/src/views/logs/ExecutionList.vue`

- [ ] **Step 1:** `JobList.vue` 删除 `handleCancel` 与行内「取消」按钮，操作栏改为 `详情 | 执行 | 复制 | 删除`；「执行」调用 `runJob(job.id, { mode: 'full' })`，成功后 `ElMessage.success('已发起执行')`。
- [ ] **Step 2:** `JobDetail.vue` 移除「全量执行」「恢复执行」，新增「取消当前执行」：`fetchRuns()` 调 `getJobRuns(id)`，`hasRunningRun = runs.some(r => r.status === 'running')`，按钮 `:disabled="!hasRunningRun || cancelling"`，无运行时提示"当前没有正在执行的运行"。
- [ ] **Step 3:** `ExecutionList.vue` 删除 mode 标签；`v-if="log.mode === 'resume' && log.resumes_from"` 时渲染 `.resume-tag`「续跑」。
- [ ] **Step 4:** `cd frontend && npx vue-tsc --build --force && npm run build-only`，Expected: 无错误。

### Task 3: Webhook 平台适配（TDD）

**Files:** `src/schedflow/core/webhook.py`、`tests/core/test_webhook.py`

- [ ] **Step 1: 先写失败测试**

```python
def test_dingtalk_payload_uses_markdown_envelope():
    config = WebhookConfig(url="http://x/hook", platform="dingtalk")
    body = build_request_body(config, _sample_payload())
    assert body["msgtype"] == "markdown"
    assert "文本内容" in body["markdown"]["text"]

def test_dingtalk_signature_is_appended_to_url():
    config = WebhookConfig(url="http://x/hook?access_token=t", platform="dingtalk", secret="SEC")
    url = sign_url(config, timestamp=1700000000000)
    assert "timestamp=1700000000000" in url and "sign=" in url

def test_wecom_uses_content_key():
    body = build_request_body(WebhookConfig(url="http://x/hook", platform="wecom"), _sample_payload())
    assert body["msgtype"] == "markdown"
    assert "content" in body["markdown"]

def test_feishu_signature_goes_into_body():
    body = build_request_body(WebhookConfig(url="http://x/hook", platform="feishu", secret="SEC"), _sample_payload(), timestamp=1700000000)
    assert body["msg_type"] == "text"
    assert body["timestamp"] == "1700000000" and body["sign"]

def test_platform_error_body_marks_delivery_failed():
    # 平台返回 HTTP 200 + errcode=300001
    result = deliver_once(WebhookConfig(url=..., platform="dingtalk"), payload)
    assert result["ok"] is False
    assert "300001" in result["error"]

def test_unknown_platform_falls_back_to_generic():
    assert WebhookConfig.from_dict({"url": "http://x", "platform": "slack"}).platform == "generic"
```

- [ ] **Step 2:** 运行确认失败：`.venv\Scripts\python.exe -m pytest tests/core/test_webhook.py -q` → 期望 `ImportError: cannot import name 'build_request_body'`。
- [ ] **Step 3:** 实现 `PLATFORMS`、`WebhookConfig.platform`、`build_request_body()`、`sign_url()`、`_platform_error()`、`deliver_once()` 扩展（`platform`/`response` 字段，平台错误不重试）。
- [ ] **Step 4:** 运行 `pytest tests/core/test_webhook.py -q` → 全部通过。

### Task 4: 测试端点与配置 schema 支持 platform

**Files:** `src/schedflow/api/schemas.py`、`src/schedflow/api/routers/settings.py`、`tests/test_api/test_settings_ops.py`

- [ ] **Step 1:** 先加断言：`PUT /api/v1/settings/webhooks` 携带 `platform: "dingtalk"` 后 `get_webhooks_config()` 保留该值；`POST /webhooks/test` 返回 `platform` 字段。
- [ ] **Step 2:** 运行确认失败。
- [ ] **Step 3:** `WebhookConfigItem` 增加 `platform: Literal[...] = "generic"`；测试端点透传 platform 并返回扩展字段。
- [ ] **Step 4:** 运行 `pytest tests/test_api/test_settings_ops.py -q` 通过。

### Task 5: 集成页重做

**Files:** `frontend/src/views/settings/ObservabilitySettings.vue`、`frontend/src/api/settings.ts`

- [ ] **Step 1:** `WebhookConfig` 增加 `platform?: string`；新增 `WebhookTestResult` 的 `platform`/`response` 字段。
- [ ] **Step 2:** 重写组件：平台分段选择、地址提示、`el-select` 多选事件（分组 + 标签 + 摘要）、按平台显示/隐藏密钥、测试结果面板。
- [ ] **Step 3:** `npx vue-tsc --build --force && npm run build-only && npm test`，Expected: 无错误。

### Task 6: 文档与端到端验证

- [ ] **Step 1:** `docs/user-guide/core-features.zh.md` / `.en.md` 补充 Webhook 平台说明；`CHANGELOG.md` 记录本次优化；`AGENTS.md` 增补 webhook 模块说明。
- [ ] **Step 2:** 后端全量 `python -m pytest -q` + `ruff check src tests`。
- [ ] **Step 3:** 启动后端 + 构建产物，人工验证：过期 token 跳登录且只提示一次、列表无「取消」且有「执行」、详情「取消当前执行」无运行时置灰、日志无「全量执行」、集成页可选四平台并发送测试。

### Task 7: 空触发器守卫（验收中发现，补充任务）

**Files:** `src/schedflow/api/trigger_validation.py`（新增）、`src/schedflow/api/rest/routers.py`、`src/schedflow/api/routers/components.py`、`src/schedflow/api/exceptions.py`、`frontend/src/views/jobs/TriggerConfig.vue`、`tests/test_trigger_guard.py`

- [ ] **Step 1:** 写失败测试 `tests/test_trigger_guard.py`：空 cron / 0 间隔 / 无 run_date 的 date 被拒，nested and/or 递归校验，API 层返回 422。
- [ ] **Step 2:** 运行确认失败（`ImportError: ensure_schedulable`）。
- [ ] **Step 3:** 实现 `ensure_schedulable()` 并接入 `_to_trigger()` 与 reschedule；`api/exceptions.py` 增加 `TriggerError → 422`。
- [ ] **Step 4:** 前端 `TriggerConfig.validate()` + `JobForm` / `JobDetail` 提交前拦截。
- [ ] **Step 5:** 运行 `pytest tests/test_trigger_guard.py -q`、`vue-tsc`、浏览器验证空触发器被拦下且 `*/5` 可正常创建。
