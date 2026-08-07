<template>
  <div class="dashboard page-wrapper">
    <!-- Welcome -->
    <div class="welcome-section">
      <div>
        <h1 class="welcome-title">
          <span class="gradient-text">仪表盘</span>
        </h1>
        <p class="welcome-sub">{{ greeting }}，欢迎使用 SchedFlow</p>
      </div>
      <div class="welcome-time">{{ currentTime }}</div>
    </div>

    <!-- Infrastructure alerts -->
    <transition-group name="page-fade" tag="div" class="infra-alerts">
      <div
        v-for="[alias, error] in failedJobstoreEntries"
        :key="'js-' + alias"
        class="alert-card alert-error"
      >
        <div class="alert-icon">
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="8" stroke="#EF4444" stroke-width="1.5"/>
            <line x1="10" y1="6" x2="10" y2="11" stroke="#EF4444" stroke-width="1.5" stroke-linecap="round"/>
            <circle cx="10" cy="14" r="0.75" fill="#EF4444"/>
          </svg>
        </div>
        <div class="alert-body">
          <div class="alert-title">存储后端 "{{ alias }}" 启动失败</div>
          <div class="alert-desc">{{ error }}</div>
        </div>
        <button class="alert-close" @click="dismissAlert('js-' + alias)">&times;</button>
      </div>
      <div
        v-for="[alias, error] in failedExecutorEntries"
        :key="'ex-' + alias"
        class="alert-card alert-error"
      >
        <div class="alert-icon">
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="8" stroke="#EF4444" stroke-width="1.5"/>
            <line x1="10" y1="6" x2="10" y2="11" stroke="#EF4444" stroke-width="1.5" stroke-linecap="round"/>
            <circle cx="10" cy="14" r="0.75" fill="#EF4444"/>
          </svg>
        </div>
        <div class="alert-body">
          <div class="alert-title">执行器 "{{ alias }}" 启动失败</div>
          <div class="alert-desc">{{ error }}</div>
        </div>
        <button class="alert-close" @click="dismissAlert('ex-' + alias)">&times;</button>
      </div>
    </transition-group>

    <!-- Stat Cards -->
    <div v-if="loading" class="stats-grid">
      <div class="skeleton" v-for="n in 4" :key="n" style="height: 100px; border-radius: var(--radius-lg);"></div>
    </div>
    <div v-else class="stats-grid">
      <div class="stat-card glass-card-interactive" style="animation-delay: 0s">
        <div class="stat-icon-wrapper" style="background: var(--color-primary-soft);">
          <svg width="22" height="22" viewBox="0 0 20 20" fill="none">
            <rect x="2" y="2" width="7" height="7" rx="1.5" stroke="var(--color-primary)" stroke-width="1.5"/>
            <rect x="11" y="2" width="7" height="4" rx="1.5" stroke="var(--color-primary)" stroke-width="1.5"/>
            <rect x="2" y="11" width="7" height="7" rx="1.5" stroke="var(--color-primary)" stroke-width="1.5"/>
            <rect x="11" y="8" width="7" height="10" rx="1.5" stroke="var(--color-primary)" stroke-width="1.5"/>
          </svg>
        </div>
        <div class="stat-body">
          <div class="stat-value">
            <span class="status-dot" :class="schedulerStatusDotClass" style="margin-right: 6px;"></span>
            {{ store.status?.state_name || 'UNKNOWN' }}
          </div>
          <div class="stat-label">调度器状态</div>
        </div>
      </div>

      <div class="stat-card glass-card-interactive" style="animation-delay: 0.08s">
        <div class="stat-icon-wrapper" style="background: var(--color-success-soft);">
          <svg width="22" height="22" viewBox="0 0 20 20" fill="none">
            <rect x="2" y="2" width="16" height="16" rx="2" stroke="var(--color-success)" stroke-width="1.5"/>
            <line x1="2" y1="7" x2="18" y2="7" stroke="var(--color-success)" stroke-width="1.5"/>
            <line x1="7" y1="2" x2="7" y2="7" stroke="var(--color-success)" stroke-width="1.5"/>
          </svg>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ store.status?.job_count ?? 0 }}</div>
          <div class="stat-label">任务总数</div>
        </div>
      </div>

      <div class="stat-card glass-card-interactive" style="animation-delay: 0.16s">
        <div class="stat-icon-wrapper" style="background: var(--color-warning-soft);">
          <svg width="22" height="22" viewBox="0 0 20 20" fill="none">
            <polygon points="10,3 18,17 2,17" stroke="var(--color-warning)" stroke-width="1.5" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ runningCount }}</div>
          <div class="stat-label">启用</div>
        </div>
      </div>

      <div class="stat-card glass-card-interactive" style="animation-delay: 0.24s">
        <div class="stat-icon-wrapper" style="background: var(--color-info-soft);">
          <svg width="22" height="22" viewBox="0 0 20 20" fill="none">
            <rect x="3" y="4" width="4" height="12" rx="1" stroke="var(--color-info)" stroke-width="1.5"/>
            <rect x="9" y="4" width="4" height="12" rx="1" stroke="var(--color-info)" stroke-width="1.5"/>
          </svg>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ pausedCount }}</div>
          <div class="stat-label">暂停</div>
        </div>
      </div>
    </div>

    <!-- Recent Jobs + Quick Actions -->
    <div class="dashboard-grid">
      <!-- Recent jobs -->
      <div class="glass-card recent-jobs-card">
        <div class="section-header">
          <h3 class="section-title">最近任务</h3>
          <router-link to="/jobs" class="section-link">查看全部 →</router-link>
        </div>
        <template v-if="loading">
          <div class="skeleton" v-for="n in 4" :key="n" style="height: 52px; margin-bottom: 8px;"></div>
        </template>
        <template v-else-if="recentJobs.length > 0">
          <div
            v-for="(job, i) in recentJobs"
            :key="job.id"
            class="job-list-item"
            :style="{ animationDelay: (0.3 + i * 0.06) + 's' }"
            @click="$router.push(`/jobs/${job.id}`)"
          >
            <div class="job-list-left">
              <span class="job-list-name">{{ job.name }}</span>
              <span class="job-list-meta">{{ job.executor }} / {{ job.jobstore }}</span>
            </div>
            <div class="job-list-right">
              <span class="job-status-badge" :class="job.job_status === 'RUNNING' ? 'badge-running' : 'badge-paused'">
                {{ job.job_status === 'RUNNING' ? '启用' : '暂停' }}
              </span>
              <span class="job-list-time" v-if="job.next_run_time">
                {{ formatTime(job.next_run_time) }}
              </span>
            </div>
          </div>
        </template>
        <div v-else class="empty-state">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" opacity="0.3">
            <rect x="6" y="6" width="36" height="36" rx="4" stroke="currentColor" stroke-width="2"/>
            <line x1="6" y1="18" x2="42" y2="18" stroke="currentColor" stroke-width="2"/>
            <line x1="18" y1="6" x2="18" y2="18" stroke="currentColor" stroke-width="2"/>
          </svg>
          <p>暂无任务，点击下方按钮创建</p>
          <router-link to="/jobs" class="empty-cta">前往创建</router-link>
        </div>
      </div>

      <!-- Quick actions -->
      <div class="glass-card quick-actions-card">
        <h3 class="section-title" style="margin-bottom: var(--space-md);">快捷操作</h3>
        <div class="quick-actions-grid">
          <button class="quick-action-btn" @click="$router.push('/jobs')">
            <span class="qa-icon" style="background: var(--color-primary-soft); color: var(--color-primary);">
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none"><line x1="10" y1="3" x2="10" y2="17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><line x1="3" y1="10" x2="17" y2="10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
            </span>
            <span class="qa-label">管理任务</span>
          </button>
          <button class="quick-action-btn" @click="$router.push('/executor-config')">
            <span class="qa-icon" style="background: var(--color-info-soft); color: var(--color-info);">
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none"><rect x="2" y="2" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="11" y="2" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="2" y="11" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="11" y="11" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/></svg>
            </span>
            <span class="qa-label">执行器配置</span>
          </button>
          <button class="quick-action-btn" @click="$router.push('/settings')">
            <span class="qa-icon" style="background: var(--bg-surface-hover); color: var(--text-secondary);">
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none"><path d="M8.61 2.54a1.46 1.46 0 012.78 0l.23.88a6.18 6.18 0 011.48.65l.82-.37a1.46 1.46 0 012.08 1.84l-.48.77a6.18 6.18 0 01.57 1.5l.87.15a1.46 1.46 0 010 2.78l-.87.15a6.18 6.18 0 01-.57 1.5l.48.77a1.46 1.46 0 01-2.08 1.84l-.82-.37a6.18 6.18 0 01-1.48.65l-.23.88a1.46 1.46 0 01-2.78 0l-.23-.88a6.18 6.18 0 01-1.48-.65l-.82.37A1.46 1.46 0 014 13.83l.48-.77a6.18 6.18 0 01-.57-1.5l-.87-.15a1.46 1.46 0 010-2.78l.87-.15a6.18 6.18 0 01.57-1.5l-.48-.77a1.46 1.46 0 012.08-1.84l.82.37a6.18 6.18 0 011.48-.65l.23-.88z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><circle cx="10" cy="10" r="3.5" stroke="currentColor" stroke-width="1.5"/></svg>
            </span>
            <span class="qa-label">系统设置</span>
          </button>
          <button class="quick-action-btn" @click="$router.push('/logs')">
            <span class="qa-icon" style="background: var(--bg-surface-hover); color: var(--text-secondary);">
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none"><rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/><line x1="7" y1="6" x2="13" y2="6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><line x1="7" y1="9" x2="13" y2="9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </span>
            <span class="qa-label">查看日志</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useSchedulerStore } from '@/stores/scheduler'
import { getJobs, connectAllJobsNextRunTimeSSE } from '@/api/jobs'
import type { Job } from '@/types'

const store = useSchedulerStore()
const jobs = ref<Job[]>([])
const loading = ref(true)
const dismissedAlerts = ref(new Set<string>())
let sseCleanup: (() => void) | null = null

const runningCount = computed(() => jobs.value.filter(j => j.job_status === 'RUNNING').length)
const pausedCount = computed(() => jobs.value.filter(j => j.job_status !== 'RUNNING').length)
const recentJobs = computed(() => jobs.value.slice(0, 5))

const currentTime = computed(() => new Date().toLocaleDateString('zh-CN', {
  year: 'numeric', month: 'long', day: 'numeric', weekday: 'long'
}))

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 9) return '早上好'
  if (h < 12) return '上午好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const schedulerStatusDotClass = computed(() => {
  if (store.isRunning) return 'status-dot--running'
  if (store.isPaused) return 'status-dot--paused'
  return 'status-dot--stopped'
})

const failedJobstoreEntries = computed(() => {
  const status = store.status
  if (!status?.failed_jobstores) return []
  return Object.entries(status.failed_jobstores).filter(([k]) => !dismissedAlerts.value.has('js-' + k))
})
const failedExecutorEntries = computed(() => {
  const status = store.status
  if (!status?.failed_executors) return []
  return Object.entries(status.failed_executors).filter(([k]) => !dismissedAlerts.value.has('ex-' + k))
})

function dismissAlert(key: string) {
  dismissedAlerts.value.add(key)
}

function formatTime(iso: string) {
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function applyNextRunSnapshot(snapshot: Record<string, string | null>) {
  jobs.value = jobs.value.map((job) => {
    if (job.id in snapshot) {
      return { ...job, next_run_time: snapshot[job.id] ?? undefined }
    }
    return job
  })
}

onMounted(async () => {
  try {
    jobs.value = await getJobs()
  } catch {
    jobs.value = []
  } finally {
    loading.value = false
  }
  sseCleanup = connectAllJobsNextRunTimeSSE(
    applyNextRunSnapshot,
    (error) => console.warn('SSE error:', error),
  )
})

onBeforeUnmount(() => {
  sseCleanup?.()
  sseCleanup = null
})
</script>

<style scoped>
.dashboard {
  /* max-width inherited from .page-wrapper */
}

/* ── Welcome ─────── */
.welcome-section {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-lg);
}

.welcome-title {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 4px;
  font-family: var(--font-heading);
}

.welcome-sub {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.welcome-time {
  font-size: 13px;
  color: var(--text-muted);
  white-space: nowrap;
  padding-top: 6px;
}

/* ── Alerts ──────── */
.infra-alerts {
  margin-bottom: var(--space-md);
}

.alert-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  margin-bottom: 8px;
  border-radius: var(--radius-md);
  background: var(--color-danger-soft);
  border: 1px solid rgba(239, 68, 68, 0.25);
}

.alert-icon {
  flex-shrink: 0;
  margin-top: 1px;
}

.alert-body {
  flex: 1;
  min-width: 0;
}

.alert-title {
  font-size: 13px;
  font-weight: 600;
  color: #FCA5A5;
  margin-bottom: 2px;
}

.alert-desc {
  font-size: 12px;
  color: rgba(239, 68, 68, 0.8);
  word-break: break-all;
}

.alert-close {
  flex-shrink: 0;
  background: none;
  border: none;
  color: rgba(239, 68, 68, 0.6);
  font-size: 18px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
  transition: color var(--transition-fast);
}
.alert-close:hover {
  color: #EF4444;
}

/* ── Stat Cards ──── */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px;
  animation: card-in 0.4s ease both;
}

.stat-icon-wrapper {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-body {
  min-width: 0;
}

.stat-value {
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
  display: flex;
  align-items: center;
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* ── Dashboard Grid ─ */
.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: var(--space-md);
}

/* ── Recent Jobs ─── */
.recent-jobs-card {
  padding: var(--space-lg);
  animation: card-in 0.4s ease 0.3s both;
}

.section-link {
  font-size: 13px;
  color: var(--color-primary);
  text-decoration: none;
  font-weight: 500;
  transition: color var(--transition-fast);
}
.section-link:hover {
  color: var(--color-primary-hover);
}

.job-list-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: padding var(--transition-fast), background var(--transition-fast);
  animation: card-in 0.35s ease both;
  border-radius: var(--radius-sm);
}
.job-list-item:last-child {
  border-bottom: none;
}
.job-list-item:hover {
  background: var(--bg-surface);
  padding: 12px 12px;
  margin: 0 -12px;
  border-radius: var(--radius-sm);
}

.job-list-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.job-list-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}
.job-list-meta {
  font-size: 12px;
  color: var(--text-muted);
}
.job-list-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.job-status-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: var(--radius-full);
}
.badge-running {
  background: var(--color-success-soft);
  color: var(--color-success);
}
.badge-paused {
  background: var(--bg-surface);
  color: var(--text-muted);
}
.job-list-time {
  font-size: 12px;
  color: var(--text-muted);
}

/* ── Quick Actions ─ */
.quick-actions-card {
  padding: var(--space-lg);
  animation: card-in 0.4s ease 0.36s both;
}

.quick-actions-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-sm);
}

.quick-action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  color: var(--text-secondary);
  cursor: pointer;
  font-family: var(--font-body);
  font-size: 12px;
  font-weight: 500;
  transition: all var(--transition-fast);
}
.quick-action-btn:hover {
  background: var(--bg-surface-hover);
  border-color: var(--border-default);
  transform: translateY(-1px);
}
.quick-action-btn:active {
  transform: translateY(0) scale(0.97);
}

.qa-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
}
.qa-label {
  text-align: center;
  line-height: 1.2;
}

/* ── Empty State ─── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  color: var(--text-muted);
  font-size: 13px;
  gap: 12px;
}

.empty-cta {
  color: var(--color-primary);
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  padding: 6px 16px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}
.empty-cta:hover {
  background: var(--color-primary-soft);
}

/* ── Responsive ──── */
@media (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
  .quick-actions-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
