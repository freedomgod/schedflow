<template>
  <div class="system-settings page-wrapper">
    <h1 class="page-title gradient-text">系统设置</h1>

    <div class="settings-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="settings-tab"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >{{ tab.label }}</button>
    </div>

    <!-- Theme tab -->
    <div v-show="activeTab === 'theme'" class="tab-content">
      <div class="glass-card" style="padding: var(--space-xl);">
        <h3 class="section-title">界面主题</h3>
        <p class="section-desc">选择系统的显示主题，即时生效并持久化保存。</p>
        <div class="theme-cards">
          <button
            class="theme-card"
            :class="{ active: settingsStore.theme === 'light' }"
            @click="handleThemeChange('light')"
          >
            <div class="theme-preview theme-preview-light">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.5"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </div>
            <span class="theme-name">明亮模式</span>
            <span class="theme-desc">适合光线充足的办公环境</span>
          </button>
          <button
            class="theme-card"
            :class="{ active: settingsStore.theme === 'dark' }"
            @click="handleThemeChange('dark')"
          >
            <div class="theme-preview theme-preview-dark">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" fill="currentColor"/></svg>
            </div>
            <span class="theme-name">暗黑模式</span>
            <span class="theme-desc">适合开发者，减少视觉疲劳</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Variables tab -->
    <div v-show="activeTab === 'variables'" class="tab-content">
      <VariablesManager />
    </div>

    <!-- Timezone tab -->
    <div v-show="activeTab === 'timezone'" class="tab-content">
      <div class="glass-card" style="padding: var(--space-xl);">
        <h3 class="section-title">默认时区</h3>
        <p class="section-desc">
          新建任务时，Cron / Interval / Date 触发器的默认计算时区。未显式指定时区的任务都会用它，
          因此容器以 UTC 运行时也不会再把北京时间填成 09:00 UTC。
        </p>
        <div class="rate-limit-form">
          <div class="form-group">
            <label for="default-timezone">当前默认时区</label>
            <el-select
              id="default-timezone"
              v-model="timezone"
              filterable
              allow-create
              default-first-option
              placeholder="选择时区"
              style="width: 100%"
            >
              <el-option v-for="tz in timezoneOptions" :key="tz" :label="tz" :value="tz" />
            </el-select>
            <span class="field-hint">
              生效范围：<strong>{{ timezoneConfigured ? '系统设置' : '跟随系统时区' }}</strong>
              （进程时区 {{ systemTimezone || '-' }}）。
              已创建任务的时区保存在各自触发器里，不受此处影响。
            </span>
          </div>
          <div class="settings-actions">
            <el-button
              :disabled="savingTimezone || !timezoneConfigured"
              @click="resetTimezone"
            >
              跟随系统
            </el-button>
            <button
              type="button"
              class="btn-primary"
              :disabled="savingTimezone"
              @click="saveTimezone"
            >
              保存时区
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- API Keys tab -->
    <div v-show="activeTab === 'apikeys'" class="tab-content">
      <ApiKeyManager />
    </div>

    <!-- API write rate limit tab -->
    <div v-show="activeTab === 'rate-limit'" class="tab-content">
      <div class="glass-card" style="padding: var(--space-xl);">
        <h3 class="section-title">API 写限流</h3>
        <p class="section-desc">
          仅作用于 <code>POST/PUT/PATCH/DELETE /api/**</code> 的写请求，按登录主体（未认证时按客户端 IP）计数；
          计数在单进程内存中完成，多 worker 各自独立；与任务的触发频率无关。
        </p>
        <div class="rate-limit-form">
          <div class="form-group">
            <label>启用写入限流</label>
            <button
              type="button"
              class="toggle-switch"
              :class="{ active: rateLimit.enabled }"
              @click="rateLimit.enabled = !rateLimit.enabled"
            >
              <span class="toggle-thumb"></span>
            </button>
          </div>
          <div class="form-group">
            <label for="rate-limit-rpm">每分钟请求上限（rpm）</label>
            <input
              id="rate-limit-rpm"
              v-model.number="rateLimit.rpm"
              type="number"
              min="1"
              class="form-input"
            />
            <span class="field-hint">例如 120 表示平均每分钟允许 120 次写请求。</span>
          </div>
          <div class="settings-actions">
            <button
              type="button"
              class="btn-primary"
              :disabled="savingRateLimit"
              @click="saveRateLimit"
            >
              保存限流
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  browserTimezones,
  getRateLimit,
  getTimezone,
  setRateLimit,
  setTimezone,
} from '@/api/settings'
import type { TimezoneInfo } from '@/api/settings'
import { useSettingsStore } from '@/stores/settings'
import VariablesManager from './VariablesManager.vue'
import ApiKeyManager from './ApiKeyManager.vue'

const settingsStore = useSettingsStore()
const activeTab = ref('theme')
const savingRateLimit = ref(false)
const rateLimit = reactive({ enabled: false, rpm: 120 })
const savingTimezone = ref(false)
const timezone = ref('')
const timezoneConfigured = ref(false)
const systemTimezone = ref('')
const timezoneOptions = ref<string[]>([])

const tabs = [
  { key: 'theme', label: '主题设置' },
  { key: 'timezone', label: '时区设置' },
  { key: 'variables', label: '变量管理' },
  { key: 'apikeys', label: 'API Key' },
  { key: 'rate-limit', label: 'API 写限流' },
]

function handleThemeChange(val: string) {
  settingsStore.switchTheme(val as 'light' | 'dark')
}

async function loadRateLimit() {
  const config = await getRateLimit()
  rateLimit.enabled = config.enabled
  rateLimit.rpm = config.rpm
}

async function saveRateLimit() {
  savingRateLimit.value = true
  try {
    await setRateLimit({ enabled: rateLimit.enabled, rpm: rateLimit.rpm })
    ElMessage.success('限流配置已保存')
  } catch {
    ElMessage.error('限流配置保存失败')
  } finally {
    savingRateLimit.value = false
  }
}

function applyTimezoneInfo(info: TimezoneInfo) {
  timezone.value = info.timezone
  timezoneConfigured.value = info.configured
  systemTimezone.value = info.system_timezone
  // The server list can be empty on a tzdata-less image; the browser list
  // keeps the picker usable so users can still type an IANA name.
  timezoneOptions.value = Array.from(
    new Set([...info.available, ...browserTimezones(), info.timezone]),
  ).sort()
}

async function loadTimezone() {
  try {
    applyTimezoneInfo(await getTimezone())
  } catch {
    /* keep whatever the user typed */
  }
}

async function saveTimezone() {
  if (!timezone.value) {
    ElMessage.warning('请选择时区')
    return
  }
  savingTimezone.value = true
  try {
    const info = await setTimezone(timezone.value)
    applyTimezoneInfo(info)
    ElMessage.success(`默认时区已设为 ${info.timezone}，新建任务将使用该时区`)
  } catch {
    ElMessage.error('默认时区保存失败')
  } finally {
    savingTimezone.value = false
  }
}

async function resetTimezone() {
  savingTimezone.value = true
  try {
    const info = await setTimezone(null)
    applyTimezoneInfo(info)
    ElMessage.success(`已恢复为跟随系统时区（${info.system_timezone}）`)
  } catch {
    ElMessage.error('恢复系统时区失败')
  } finally {
    savingTimezone.value = false
  }
}

onMounted(() => {
  settingsStore.fetchTheme()
  loadRateLimit()
  loadTimezone()
})
</script>

<style scoped>
.system-settings { max-width: 960px; }

/* Tabs */
.settings-tab {
  padding: 12px 22px;
  border: none;
  background: none;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-body);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all var(--transition-fast);
}
.settings-tab:hover { color: var(--text-secondary); }
.settings-tab.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }

.tab-content { min-height: 200px; }

.rate-limit-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  max-width: 360px;
}

.settings-actions {
  display: flex;
  justify-content: flex-end;
}

/* Theme cards */
.theme-cards { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-md); margin-top: var(--space-md); }
.theme-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 28px 20px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  cursor: pointer;
  font-family: var(--font-body);
  transition: all var(--transition-fast);
  text-align: center;
}
.theme-card:hover { border-color: var(--border-default); background: var(--bg-surface-hover); }
.theme-card.active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  box-shadow: var(--shadow-glow);
}
.theme-preview {
  width: 56px; height: 56px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
}
.theme-preview-light { background: #FEF3C7; color: #D97706; }
.theme-preview-dark { background: #1E293B; color: #818CF8; }
.theme-name { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.theme-desc { font-size: 12px; color: var(--text-muted); }
</style>
