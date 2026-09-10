<template>
  <div class="page-wrapper observability-settings">
    <div class="glass-card settings-card">
      <h2 class="card-title">运行限流</h2>
      <div class="form-group">
        <label>启用写入限流</label>
        <button
          class="toggle-switch"
          :class="{ active: rateLimit.enabled }"
          @click="rateLimit.enabled = !rateLimit.enabled"
        >
          <span class="toggle-thumb"></span>
        </button>
      </div>
      <div class="form-group">
        <label>每分钟请求上限（rpm）</label>
        <input v-model.number="rateLimit.rpm" type="number" min="1" class="form-input" />
      </div>
      <button class="btn-primary" :disabled="saving" @click="saveRateLimit">保存限流</button>
    </div>

    <div class="glass-card settings-card">
      <h2 class="card-title">Webhook 通知</h2>
      <div v-for="(hook, index) in webhooks" :key="index" class="webhook-row">
        <input v-model="hook.url" class="form-input" placeholder="https://example.com/hook" />
        <input
          v-model="hook.eventsText"
          class="form-input"
          placeholder="事件：job.succeeded, job.failed 或 *"
        />
        <input v-model="hook.secret" class="form-input" placeholder="Secret（可选）" />
        <button class="action-btn danger" @click="webhooks.splice(index, 1)">删除</button>
      </div>
      <div class="settings-actions">
        <button class="action-btn" @click="addWebhook">添加 Webhook</button>
        <button class="btn-primary" :disabled="saving" @click="saveWebhooks">保存 Webhook</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getRateLimit,
  getWebhooks,
  setRateLimit,
  setWebhooks,
} from '@/api/settings'

const saving = ref(false)
const rateLimit = reactive({ enabled: false, rpm: 120 })
const webhooks = ref<Array<{ url: string; eventsText: string; secret?: string }>>([])

async function load() {
  const [limit, hooks] = await Promise.all([getRateLimit(), getWebhooks()])
  rateLimit.enabled = limit.enabled
  rateLimit.rpm = limit.rpm
  webhooks.value = hooks.map((hook) => ({
    url: hook.url,
    eventsText: (hook.events || ['*']).join(', '),
    secret: hook.secret || undefined,
  }))
}

function addWebhook() {
  webhooks.value.push({ url: '', eventsText: 'job.succeeded, job.failed' })
}

function parseEvents(text: string): string[] {
  const events = text
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
  return events.length ? events : ['*']
}

async function saveRateLimit() {
  saving.value = true
  try {
    await setRateLimit({ enabled: rateLimit.enabled, rpm: rateLimit.rpm })
    ElMessage.success('限流配置已保存')
  } catch {
    ElMessage.error('限流配置保存失败')
  } finally {
    saving.value = false
  }
}

async function saveWebhooks() {
  saving.value = true
  try {
    await setWebhooks(
      webhooks.value
        .filter((hook) => hook.url.trim())
        .map((hook) => ({
          url: hook.url.trim(),
          events: parseEvents(hook.eventsText),
          secret: hook.secret || undefined,
        })),
    )
    ElMessage.success('Webhook 配置已保存')
  } catch {
    ElMessage.error('Webhook 配置保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.observability-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.settings-card {
  padding: 20px;
}

.card-title {
  margin-bottom: 16px;
  font-size: 16px;
  font-weight: 600;
}

.webhook-row {
  display: grid;
  grid-template-columns: 2fr 2fr 1fr auto;
  gap: 8px;
  margin-bottom: 8px;
}

.settings-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
</style>
