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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import VariablesManager from './VariablesManager.vue'
import ApiKeyManager from './ApiKeyManager.vue'

const settingsStore = useSettingsStore()
const activeTab = ref('theme')

const tabs = [
  { key: 'theme', label: '主题设置' },
  { key: 'variables', label: '变量管理' },
  { key: 'apikeys', label: 'API Key' },
]

function handleThemeChange(val: string) {
  settingsStore.switchTheme(val as 'light' | 'dark')
}

onMounted(() => {
  settingsStore.fetchTheme()
})
</script>

<style scoped>
.system-settings { max-width: 960px; }

.page-title { font-size: 22px; font-weight: 700; margin: 0 0 var(--space-lg); }

/* Tabs */
.settings-tabs { display: flex; gap: 0; margin-bottom: var(--space-lg); border-bottom: 1px solid var(--border-subtle); }
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
