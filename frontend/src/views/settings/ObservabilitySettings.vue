<template>
  <div class="page-wrapper integration-settings">
    <h1 class="page-title gradient-text">集成</h1>

    <div class="glass-card settings-card">
      <h3 class="section-title">Webhook 通知</h3>
      <p class="section-desc">
        任务与调度器事件会推送到下面配置的目标。通用模式按原始 JSON 投递（便于自建服务消费），
        钉钉 / 企业微信 / 飞书会按各自的消息格式发送；投递失败会重试 3 次，平台拒收时会把原因直接回显。
      </p>

      <p v-if="!webhooks.length" class="empty-hint">
        还没有通知目标，点击下方「添加通知」开始配置。
      </p>

      <section v-for="(hook, index) in webhooks" :key="hook.key" class="webhook-card">
        <header class="webhook-head">
          <span class="webhook-title">{{ platformOf(hook).label }}通知</span>
          <button type="button" class="action-btn danger" @click="removeWebhook(index)">删除</button>
        </header>

        <div class="platform-picker">
          <button
            v-for="option in PLATFORMS"
            :key="option.value"
            type="button"
            class="platform-btn"
            :class="{ active: hook.platform === option.value }"
            @click="hook.platform = option.value"
          >
            {{ option.label }}
          </button>
        </div>
        <p class="platform-hint">{{ platformOf(hook).hint }}</p>

        <el-form label-position="top" class="webhook-form">
          <el-form-item label="回调地址">
            <el-input
              v-model="hook.url"
              :placeholder="platformOf(hook).placeholder"
            />
          </el-form-item>

          <el-form-item label="订阅事件">
            <el-select
              v-model="hook.events"
              multiple
              filterable
              clearable
              collapse-tags
              collapse-tags-tooltip
              placeholder="不选择表示订阅全部事件"
              style="width: 100%"
            >
              <el-option-group
                v-for="group in eventGroups"
                :key="group.label"
                :label="group.label"
              >
                <el-option
                  v-for="kind in group.kinds"
                  :key="kind"
                  :label="eventLabel(kind)"
                  :value="kind"
                />
              </el-option-group>
            </el-select>
            <span class="field-hint">{{ eventsSummary(hook) }}</span>
          </el-form-item>

          <el-form-item v-if="platformOf(hook).supportsSecret" :label="platformOf(hook).secretLabel">
            <el-input v-model="hook.secret" :placeholder="platformOf(hook).secretHint" />
            <span class="field-hint">{{ platformOf(hook).secretHint }}</span>
          </el-form-item>
        </el-form>

        <div class="webhook-actions">
          <button
            type="button"
            class="action-btn"
            :disabled="testingKey === hook.key"
            @click="testWebhook(hook)"
          >
            {{ testingKey === hook.key ? '发送中…' : '发送测试' }}
          </button>
          <div
            v-if="hook.result"
            class="test-result"
            :class="hook.result.ok ? 'is-ok' : 'is-fail'"
          >
            <span class="result-badge">{{ hook.result.ok ? '投递成功' : '投递失败' }}</span>
            <span class="result-meta">
              HTTP {{ hook.result.status_code ?? '-' }} ·
              {{ Math.round(hook.result.duration_ms) }}ms
            </span>
            <span v-if="hook.result.error" class="result-error">
              {{ hook.result.error }}
            </span>
            <code v-if="hook.result.response" class="result-body">
              {{ hook.result.response }}
            </code>
          </div>
        </div>
      </section>

      <div class="settings-actions">
        <button type="button" class="action-btn" @click="addWebhook">添加通知</button>
        <button
          type="button"
          class="btn-primary"
          :disabled="saving"
          @click="saveWebhooks"
        >
          保存配置
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getWebhooks, setWebhooks, testWebhookDelivery } from '@/api/settings'
import type { WebhookTestResult } from '@/api/settings'

interface PlatformOption {
  value: string
  label: string
  hint: string
  placeholder: string
  supportsSecret: boolean
  secretLabel: string
  secretHint: string
}

const PLATFORMS: PlatformOption[] = [
  {
    value: 'generic',
    label: '通用 JSON',
    hint: '按原始事件 JSON 投递，适合自建服务或中转网关。',
    placeholder: 'https://example.com/hook',
    supportsSecret: true,
    secretLabel: '签名密钥（可选）',
    secretHint: '作为 X-SchedFlow-Secret 请求头发送。',
  },
  {
    value: 'dingtalk',
    label: '钉钉',
    hint: '钉钉群机器人地址；安全设置选「加签」时填下面的密钥，选「自定义关键词」请确保关键词出现在通知里。',
    placeholder: 'https://oapi.dingtalk.com/robot/send?access_token=...',
    supportsSecret: true,
    secretLabel: '加签密钥（SEC 开头）',
    secretHint: '按钉钉加签算法把 timestamp/sign 追加到请求地址。',
  },
  {
    value: 'wecom',
    label: '企业微信',
    hint: '企业微信群机器人地址；安全设置请在群机器人侧配置关键词或 IP 白名单。',
    placeholder: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...',
    supportsSecret: false,
    secretLabel: '签名密钥',
    secretHint: '企业微信机器人不支持签名。',
  },
  {
    value: 'feishu',
    label: '飞书',
    hint: '飞书自定义机器人地址；开启「签名校验」时填下面的密钥。',
    placeholder: 'https://open.feishu.cn/open-apis/bot/v2/hook/...',
    supportsSecret: true,
    secretLabel: '签名校验密钥',
    secretHint: '按飞书签名算法在请求体中携带 timestamp/sign。',
  },
]

/** Mirrors schedflow.core.events.EVENT_KINDS (labels mirror core.webhook.EVENT_TITLES). */
const EVENT_KINDS = [
  'scheduler.started',
  'scheduler.paused',
  'scheduler.resumed',
  'scheduler.shutdown',
  'scheduler.error',
  'job.added',
  'job.updated',
  'job.removed',
  'job.paused',
  'job.resumed',
  'job.completed',
  'job.cancelled',
  'job.started',
  'job.succeeded',
  'job.failed',
  'job.missed',
  'job.max_instances',
  'task.executed',
  'task.error',
  'task.skipped',
  'task.cancelled',
]

const EVENT_LABELS: Record<string, string> = {
  'scheduler.started': '调度器启动',
  'scheduler.paused': '调度器暂停',
  'scheduler.resumed': '调度器恢复',
  'scheduler.shutdown': '调度器关闭',
  'scheduler.error': '调度器错误',
  'job.added': '任务已创建',
  'job.updated': '任务已更新',
  'job.removed': '任务已删除',
  'job.paused': '任务已暂停',
  'job.resumed': '任务已恢复',
  'job.completed': '任务已完成',
  'job.cancelled': '任务已取消',
  'job.started': '任务开始执行',
  'job.succeeded': '任务成功',
  'job.failed': '任务失败',
  'job.missed': '任务错过执行时间',
  'job.max_instances': '任务实例数超限',
  'task.executed': '节点执行完成',
  'task.error': '节点执行失败',
  'task.skipped': '节点被跳过',
  'task.cancelled': '节点已取消',
}

const eventGroups = [
  { prefix: 'scheduler', label: '调度器' },
  { prefix: 'job', label: '任务' },
  { prefix: 'task', label: '节点' },
].map(({ prefix, label }) => ({
  label,
  kinds: EVENT_KINDS.filter((kind) => kind.startsWith(`${prefix}.`)),
}))

interface WebhookDraft {
  key: number
  url: string
  events: string[]
  secret: string
  platform: string
  result?: WebhookTestResult
}

const saving = ref(false)
const testingKey = ref<number | null>(null)
const webhooks = ref<WebhookDraft[]>([])
let nextKey = 1

function eventLabel(kind: string): string {
  return EVENT_LABELS[kind] ? `${EVENT_LABELS[kind]}（${kind}）` : kind
}

function platformOf(hook: WebhookDraft): PlatformOption {
  return PLATFORMS.find((item) => item.value === hook.platform) || PLATFORMS[0]
}

function eventsSummary(hook: WebhookDraft): string {
  if (!hook.events.length) return '未选择事件 = 订阅全部事件（*）'
  return `已选 ${hook.events.length} 个事件`
}

async function load() {
  const hooks = await getWebhooks()
  webhooks.value = hooks.map((hook) => ({
    key: nextKey++,
    url: hook.url,
    events: hook.events || [],
    secret: hook.secret || '',
    platform: hook.platform || 'generic',
  }))
}

function addWebhook() {
  webhooks.value.push({
    key: nextKey++,
    url: '',
    events: ['job.succeeded', 'job.failed'],
    secret: '',
    platform: 'dingtalk',
  })
}

function removeWebhook(index: number) {
  webhooks.value.splice(index, 1)
}

async function saveWebhooks() {
  saving.value = true
  try {
    await setWebhooks(
      webhooks.value
        .filter((hook) => hook.url.trim())
        .map((hook) => ({
          url: hook.url.trim(),
          events: hook.events.length ? hook.events : ['*'],
          secret: hook.secret || undefined,
          platform: hook.platform,
        })),
    )
    await load()
    ElMessage.success('Webhook 配置已保存')
  } catch {
    ElMessage.error('Webhook 配置保存失败')
  } finally {
    saving.value = false
  }
}

async function testWebhook(hook: WebhookDraft) {
  if (!hook.url.trim()) {
    ElMessage.warning('请先填写回调地址')
    return
  }
  testingKey.value = hook.key
  try {
    const result = await testWebhookDelivery({
      url: hook.url.trim(),
      events: hook.events.length ? hook.events : ['*'],
      secret: hook.secret || undefined,
      platform: hook.platform,
    })
    hook.result = result
    if (result.ok) {
      ElMessage.success('测试投递成功')
    } else {
      ElMessage.error(`测试投递失败：${result.error || '未知原因'}`)
    }
  } catch {
    hook.result = undefined
  } finally {
    testingKey.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.integration-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
  max-width: 960px;
}

.empty-hint {
  margin: 0 0 var(--space-md);
  font-size: 13px;
  color: var(--text-muted);
}

.webhook-card {
  padding: var(--space-lg) 0;
  border-top: 1px solid var(--border-subtle);
}

.webhook-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-sm);
}

.webhook-title {
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.platform-picker {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.platform-btn {
  padding: 6px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: 13px;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.platform-btn:hover {
  border-color: var(--border-default);
  color: var(--text-primary);
}

.platform-btn.active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.platform-hint {
  margin: 0 0 var(--space-md);
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.6;
}

.webhook-form {
  max-width: 640px;
}

.webhook-actions {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.test-result {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  max-width: 100%;
}

.test-result.is-ok {
  background: var(--color-success-soft, rgba(34, 197, 94, 0.12));
  color: var(--color-success, #16a34a);
}

.test-result.is-fail {
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.result-badge {
  font-weight: 600;
}

.result-meta,
.result-error {
  color: var(--text-secondary);
}

.result-body {
  font-family: 'Fira Code', monospace;
  font-size: 11px;
  color: var(--text-muted);
  word-break: break-all;
}

.settings-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: var(--space-md);
}
</style>
