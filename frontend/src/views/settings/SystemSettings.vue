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

import { getRateLimit, setRateLimit } from '@/api/settings'
import { useSettingsStore } from '@/stores/settings'
import VariablesManager from './VariablesManager.vue'
import ApiKeyManager from './ApiKeyManager.vue'

const settingsStore = useSettingsStore()
const activeTab = ref('theme')
const savingRateLimit = ref(false)
const rateLimit = reactive({ enabled: false, rpm: 120 })

const tabs = [
  { key: 'theme', label: '主题设置' },
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

onMounted(() => {
  settingsStore.fetchTheme()
  loadRateLimit()
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
