<template>
  <header class="app-topbar">
    <div class="topbar-left">
      <span class="page-title">{{ title }}</span>
    </div>
    <div class="topbar-right">
      <!-- Scheduler status pill: click to toggle pause/resume/start -->
      <button
        class="status-pill"
        :class="statusPillClass"
        :title="statusActionTitle"
        :disabled="schedulerStore.busy"
        @click="toggleScheduler"
      >
        <span class="status-dot" :class="statusDotClass"></span>
        <span class="status-label">{{ statusLabel }}</span>
        <svg v-if="schedulerStore.busy" class="status-spinner" width="12" height="12" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" opacity="0.25"/>
          <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
        </svg>
      </button>

      <!-- Theme toggle -->
      <button class="topbar-icon-btn" @click="toggleTheme" :title="settingsStore.theme === 'dark' ? '切换到明亮模式' : '切换到暗黑模式'">
        <!-- Sun icon (shown in dark mode → click to switch to light) -->
        <svg v-if="settingsStore.theme === 'dark'" width="18" height="18" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.5"/>
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        <!-- Moon icon (shown in light mode → click to switch to dark) -->
        <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>

      <div class="topbar-divider"></div>

      <span class="user-name">{{ authStore.username }}</span>
      <button class="logout-btn" @click="handleLogout">退出</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSchedulerStore } from '@/stores/scheduler'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const router = useRouter()
const schedulerStore = useSchedulerStore()
const authStore = useAuthStore()
const settingsStore = useSettingsStore()

const title = computed(() => (route.meta.title as string) || '')

const statusDotClass = computed(() => {
  if (schedulerStore.isRunning) return 'status-dot--running'
  if (schedulerStore.isPaused) return 'status-dot--paused'
  return 'status-dot--stopped'
})

const statusLabel = computed(() => {
  if (schedulerStore.isRunning) return '运行中'
  if (schedulerStore.isPaused) return '已暂停'
  return '已停止'
})

const statusPillClass = computed(() => {
  if (schedulerStore.isRunning) return 'pill-running'
  if (schedulerStore.isPaused) return 'pill-paused'
  return 'pill-stopped'
})

const statusActionTitle = computed(() => {
  if (schedulerStore.isRunning) return '点击暂停调度器'
  if (schedulerStore.isPaused) return '点击恢复调度器'
  return '点击启动调度器'
})

async function toggleScheduler() {
  try {
    await schedulerStore.toggle()
  } catch {
    // Error toast is already shown by the API client interceptor.
  }
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

function toggleTheme() {
  settingsStore.switchTheme(settingsStore.theme === 'dark' ? 'light' : 'dark')
}
</script>

<style scoped>
.app-topbar {
  height: var(--topbar-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-xl);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border-bottom: 1px solid var(--glass-border);
  transition: background var(--transition-base), border-color var(--transition-base);
  position: relative;
  z-index: 5;
}

.topbar-left {
  display: flex;
  align-items: center;
}

.page-title {
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── Status Pill ─── */
.status-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast),
              border-color var(--transition-fast), opacity var(--transition-fast);
  font-family: var(--font-body);
}

.status-pill:hover:not(:disabled) {
  border-color: currentColor;
  opacity: 0.9;
}

.status-pill:disabled {
  cursor: default;
  opacity: 0.75;
}

.pill-running {
  background: var(--color-success-soft);
  color: var(--color-success);
}

.pill-paused {
  background: var(--color-warning-soft);
  color: var(--color-warning);
}

.pill-stopped {
  background: var(--bg-surface);
  color: var(--text-muted);
}

.status-label {
  white-space: nowrap;
}

.status-dot {
  transition: background var(--transition-fast), box-shadow var(--transition-fast);
}

@keyframes status-spin {
  to {
    transform: rotate(360deg);
  }
}

.status-spinner {
  animation: status-spin 0.8s linear infinite;
}

/* ── Divider ─────── */
.topbar-divider {
  width: 1px;
  height: 20px;
  background: var(--border-subtle);
  flex-shrink: 0;
}

/* ── Icon button ─── */
.topbar-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.topbar-icon-btn:hover {
  background: var(--bg-surface-hover);
  color: var(--text-secondary);
}

/* ── User ────────── */
.user-name {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.logout-btn {
  background: none;
  border: none;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background var(--transition-fast);
  font-family: var(--font-body);
}
.logout-btn:hover {
  color: var(--color-danger);
  background: var(--color-danger-soft);
}
</style>
