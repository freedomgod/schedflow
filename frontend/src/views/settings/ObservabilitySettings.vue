<template>
  <div class="page-wrapper integration-settings">
    <h1 class="page-title gradient-text">集成</h1>

    <div class="glass-card settings-card">
      <h3 class="section-title">Webhook 通知</h3>
      <p class="section-desc">
        任务事件会以 JSON 形式 POST 到你的回调地址；请求体包含
        <code>kind</code>、<code>job_id</code>、<code>run_time</code> 与 <code>detail</code>，
        配置了签名密钥时会附带 <code>X-SchedFlow-Secret</code> 头。投递失败会重试 3 次。
      </p>

      <p v-if="!webhooks.length" class="empty-hint">
        还没有回调地址，点击下方「添加 Webhook」开始配置。
      </p>

      <div v-for="(hook, index) in webhooks" :key="index" class="webhook-row">
        <div class="form-group">
          <label :for="`hook-url-${index}`">回调地址</label>
          <input
            :id="`hook-url-${index}`"
            v-model="hook.url"
            class="form-input"
            placeholder="https://example.com/hook"
          />
        </div>

        <div class="form-group">
          <label :for="`hook-events-${index}`">订阅事件</label>
          <select
            :id="`hook-events-${index}`"
            v-model="hook.events"
            class="form-select"
            multiple
            size="6"
          >
            <optgroup
              v-for="group in eventGroups"
              :key="group.label"
              :label="group.label"
            >
              <option v-for="kind in group.kinds" :key="kind" :value="kind">
                {{ kind }}
              </option>
            </optgroup>
          </select>
          <span class="field-hint">可多选（Ctrl/⌘ + 点击）；全部不选表示订阅所有事件（*）。</span>
        </div>

        <div class="form-group">
          <label :for="`hook-secret-${index}`">签名密钥（可选）</label>
          <input
            :id="`hook-secret-${index}`"
            v-model="hook.secret"
            class="form-input"
            placeholder="作为 X-SchedFlow-Secret 头发送"
          />
        </div>

        <div class="webhook-actions">
          <button type="button" class="action-btn" @click="testWebhook(hook)">
            发送测试
          </button>
          <button
            type="button"
            class="action-btn danger"
            @click="webhooks.splice(index, 1)"
          >
            删除
          </button>
        </div>
      </div>

      <div class="settings-actions">
        <button type="button" class="action-btn" @click="addWebhook">添加 Webhook</button>
        <button
          type="button"
          class="btn-primary"
          :disabled="saving"
          @click="saveWebhooks"
        >
          保存 Webhook
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  getWebhooks,
  setWebhooks,
  testWebhookDelivery,
} from '@/api/settings'

interface WebhookDraft {
  url: string
  events: string[]
  secret?: string
}

/** Mirrors schedflow.core.events.EVENT_KINDS. */
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

const eventGroups = [
  { prefix: 'scheduler', label: '调度器' },
  { prefix: 'job', label: '任务' },
  { prefix: 'task', label: '节点' },
].map(({ prefix, label }) => ({
  label,
  kinds: EVENT_KINDS.filter((kind) => kind.startsWith(`${prefix}.`)),
}))

const saving = ref(false)
const webhooks = ref<WebhookDraft[]>([])

async function load() {
  const hooks = await getWebhooks()
  webhooks.value = hooks.map((hook) => ({
    url: hook.url,
    events: hook.events || [],
    secret: hook.secret || undefined,
  }))
}

function addWebhook() {
  webhooks.value.push({
    url: '',
    events: ['job.succeeded', 'job.failed'],
  })
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
  const result = await testWebhookDelivery({
    url: hook.url.trim(),
    events: hook.events.length ? hook.events : ['*'],
    secret: hook.secret || undefined,
  })
  if (result.ok) {
    ElMessage.success(`测试投递成功（HTTP ${result.status_code}）`)
  } else {
    ElMessage.error(`测试投递失败：${result.error}`)
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

.webhook-row {
  display: grid;
  grid-template-columns: 2fr 2fr 1fr auto;
  gap: var(--space-md);
  align-items: start;
  padding: var(--space-md) 0;
  border-top: 1px solid var(--border-subtle);
}

.webhook-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 22px;
}

.settings-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: var(--space-md);
}

@media (max-width: 900px) {
  .webhook-row {
    grid-template-columns: 1fr;
  }

  .webhook-actions {
    flex-direction: row;
    padding-top: 0;
  }
}
</style>
