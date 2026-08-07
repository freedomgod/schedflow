<template>
  <div class="job-list page-wrapper">
    <!-- Toolbar -->
    <div class="toolbar glass-card">
      <div class="toolbar-actions">
        <button class="btn-primary" @click="showCreateDialog">
          <svg width="16" height="16" viewBox="0 0 20 20" fill="none"><line x1="10" y1="3" x2="10" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="3" y1="10" x2="17" y2="10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          创建工作流
        </button>
        <button class="btn-ghost" @click="$router.push('/logs')">
          <svg width="16" height="16" viewBox="0 0 20 20" fill="none"><rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/><line x1="7" y1="6" x2="13" y2="6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><line x1="7" y1="10" x2="13" y2="10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
          查看日志
        </button>
      </div>
      <div class="toolbar-filters">
        <div class="filter-input">
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none"><circle cx="9" cy="9" r="6" stroke="currentColor" stroke-width="1.5"/><line x1="13.5" y1="13.5" x2="17" y2="17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
          <input v-model="search" placeholder="搜索任务名称..." class="filter-text-input" />
        </div>
        <select v-model="statusFilter" class="filter-select">
          <option value="">全部状态</option>
          <option value="RUNNING">启用</option>
          <option value="PAUSED">暂停</option>
        </select>
        <select v-model="executorFilter" class="filter-select">
          <option value="">全部执行器</option>
          <option v-for="e in executorOptions" :key="e" :value="e">{{ e }}</option>
        </select>
        <select v-model="jobstoreFilter" class="filter-select">
          <option value="">全部存储</option>
          <option v-for="j in jobstoreOptions" :key="j" :value="j">{{ j }}</option>
        </select>
      </div>
    </div>

    <!-- Table -->
    <div class="glass-card table-card">
      <div v-if="loading" class="table-loading">
        <div class="skeleton" v-for="n in 5" :key="n" style="height: 48px; margin-bottom: 8px;"></div>
      </div>
      <table v-else-if="filteredJobs.length > 0" class="data-table">
        <thead>
          <tr>
            <th>名称</th>
            <th>ID</th>
            <th>状态</th>
            <th>执行器</th>
            <th>存储</th>
            <th>下次运行</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in filteredJobs" :key="job.id" class="data-row">
            <td class="cell-name">{{ job.name }}</td>
            <td class="cell-id">{{ job.id }}</td>
            <td>
              <button
                class="toggle-switch"
                :class="{ active: job.job_status === 'RUNNING', loading: togglingStatus.has(job.id) }"
                @click="handleToggleStatus(job, job.job_status !== 'RUNNING')"
                :disabled="togglingStatus.has(job.id)"
              >
                <span class="toggle-thumb"></span>
              </button>
            </td>
            <td><span class="cell-tag">{{ job.executor }}</span></td>
            <td><span class="cell-tag">{{ job.jobstore }}</span></td>
            <td class="cell-time">{{ job.next_run_time ? formatTime(job.next_run_time) : '-' }}</td>
            <td class="cell-actions">
              <button class="action-btn" @click="$router.push(`/jobs/${job.id}`)">详情</button>
              <button class="action-btn" @click="handleCopy(job.id)">复制</button>
              <button class="action-btn danger" @click="handleDelete(job.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none" opacity="0.3">
          <rect x="6" y="6" width="36" height="36" rx="4" stroke="currentColor" stroke-width="2"/>
          <line x1="6" y1="18" x2="42" y2="18" stroke="currentColor" stroke-width="2"/>
        </svg>
        <p>{{ search || statusFilter ? '没有匹配的任务' : '暂无任务，点击上方按钮创建' }}</p>
      </div>
    </div>

    <!-- Create Dialog -->
    <JobForm
      ref="jobFormRef"
      v-model:visible="dialogVisible"
      @submit="handleCreate"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getJobs, getJob, createJob, deleteJob, pauseJob, resumeJob,
  connectAllJobsNextRunTimeSSE,
} from '@/api/jobs'
import type { Job, JobCreateParams } from '@/types'
import { useSchedulerStore } from '@/stores/scheduler'
import JobForm from './JobForm.vue'

const jobs = ref<Job[]>([])
const loading = ref(false)
const search = ref('')
const statusFilter = ref('')
const executorFilter = ref('')
const jobstoreFilter = ref('')
const dialogVisible = ref(false)
const togglingStatus = ref(new Set<string>())
const jobFormRef = ref<InstanceType<typeof JobForm>>()
let sseCleanup: (() => void) | null = null

const executorOptions = computed(() =>
  [...new Set(jobs.value.map((j) => j.executor).filter(Boolean))].sort()
)
const jobstoreOptions = computed(() =>
  [...new Set(jobs.value.map((j) => j.jobstore).filter(Boolean))].sort()
)

const filteredJobs = computed(() => {
  let list = jobs.value
  if (search.value) {
    const kw = search.value.toLowerCase()
    list = list.filter((j) => j.name?.toLowerCase().includes(kw) || j.id?.toLowerCase().includes(kw))
  }
  if (statusFilter.value) list = list.filter((j) => j.job_status === statusFilter.value)
  if (executorFilter.value) list = list.filter((j) => j.executor === executorFilter.value)
  if (jobstoreFilter.value) list = list.filter((j) => j.jobstore === jobstoreFilter.value)
  return [...list].sort((a, b) => (a.name || '').localeCompare(b.name || '', 'zh'))
})

function formatTime(iso: string) {
  return new Date(iso).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function fetchJobs(quiet = false) {
  if (!quiet) loading.value = true
  try { jobs.value = await getJobs() }
  finally { if (!quiet) loading.value = false }
}

function showCreateDialog() { dialogVisible.value = true }

async function handleCopy(id: string) {
  try {
    const job = await getJob(id)
    dialogVisible.value = true
    await nextTick()
    jobFormRef.value?.fillFromJob(job)
  } catch { ElMessage.error('获取任务信息失败') }
}

async function handleCreate(params: JobCreateParams) {
  await createJob(params)
  dialogVisible.value = false
  await fetchJobs(true)
  useSchedulerStore().fetchStatus(true)
}

async function handleToggleStatus(row: Job, active: boolean) {
  togglingStatus.value.add(row.id)
  const previous = row.job_status
  row.job_status = active ? 'RUNNING' : 'PAUSED'
  try {
    if (active) await resumeJob(row.id)
    else await pauseJob(row.id)
    await fetchJobs(true)
    useSchedulerStore().fetchStatus(true)
  } catch {
    row.job_status = previous
    await fetchJobs(true)
  } finally {
    togglingStatus.value.delete(row.id)
  }
}

async function handleDelete(id: string) {
  await ElMessageBox.confirm('确定删除该任务？此操作不可恢复', '确认删除', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
  await deleteJob(id)
  await fetchJobs(true)
  useSchedulerStore().fetchStatus(true)
}

function applyNextRunSnapshot(snapshot: Record<string, string | null>) {
  jobs.value = jobs.value.map((job) => {
    if (job.id in snapshot) {
      return { ...job, next_run_time: snapshot[job.id] ?? undefined }
    }
    return job
  })
}

function startSSE() {
  sseCleanup = connectAllJobsNextRunTimeSSE(
    applyNextRunSnapshot,
    (error) => console.warn('SSE error:', error),
  )
}

function stopSSE() {
  sseCleanup?.()
  sseCleanup = null
}

onMounted(() => { fetchJobs(); startSSE() })
onBeforeUnmount(stopSSE)
</script>

<style scoped>
.job-list { max-width: 1400px; }

/* ── Toolbar ─────── */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  margin-bottom: var(--space-md);
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--color-primary);
  color: white;
  font-size: 13px;
  font-weight: 600;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.btn-primary:hover { opacity: 0.9; transform: translateY(-1px); box-shadow: var(--shadow-glow); }
.btn-primary:active { transform: translateY(0) scale(0.98); }

.btn-ghost {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.btn-ghost:hover { background: var(--bg-surface-hover); color: var(--text-primary); }

.toolbar-filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.filter-input {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  transition: border-color var(--transition-fast);
}
.filter-input:focus-within { border-color: var(--color-primary); }

.filter-text-input {
  border: none;
  background: none;
  outline: none;
  color: var(--text-primary);
  font-size: 13px;
  font-family: var(--font-body);
  width: 160px;
}
.filter-text-input::placeholder { color: var(--text-muted); }

.filter-select {
  padding: 7px 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 13px;
  font-family: var(--font-body);
  outline: none;
  cursor: pointer;
  transition: border-color var(--transition-fast);
}
.filter-select:focus { border-color: var(--color-primary); }

/* ── Table ──────── */
.table-card { padding: 4px 0; overflow: hidden; }

.table-loading { padding: 16px; }

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table thead th {
  padding: 12px 16px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  text-align: left;
  border-bottom: 1px solid var(--border-subtle);
}

.data-row { transition: background var(--transition-fast); }
.data-row:hover { background: var(--bg-surface); }
.data-row:not(:last-child) td { border-bottom: 1px solid var(--border-subtle); }

.data-row td {
  padding: 12px 16px;
  font-size: 13px;
  vertical-align: middle;
}

.cell-name { font-weight: 500; color: var(--text-primary); }
.cell-id { font-family: 'Fira Code', monospace; font-size: 12px; color: var(--text-muted); }
.cell-tag { font-size: 12px; color: var(--text-secondary); }
.cell-time { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.cell-actions { display: flex; gap: 4px; }

.action-btn {
  padding: 4px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: 12px;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.action-btn:hover { background: var(--bg-surface-hover); color: var(--text-primary); border-color: var(--border-default); }
.action-btn.danger:hover { background: var(--color-danger-soft); color: var(--color-danger); border-color: rgba(239,68,68,0.3); }

/* ── Toggle Switch ── */
.toggle-switch {
  position: relative;
  width: 40px;
  height: 22px;
  border-radius: 11px;
  border: none;
  background: var(--border-default);
  cursor: pointer;
  transition: background var(--transition-fast);
  flex-shrink: 0;
}
.toggle-switch.active { background: var(--color-success); }
.toggle-switch.loading { opacity: 0.6; cursor: wait; }
.toggle-switch .toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: white;
  transition: transform var(--transition-fast);
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
.toggle-switch.active .toggle-thumb { transform: translateX(18px); }

/* ── Empty ──────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 16px;
  color: var(--text-muted);
  font-size: 13px;
}

@media (max-width: 768px) {
  .toolbar { flex-direction: column; align-items: stretch; }
  .toolbar-filters { flex-direction: column; }
  .filter-text-input { width: 100%; }
}
</style>
