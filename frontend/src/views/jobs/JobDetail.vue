<template>
  <div class="job-detail page-wrapper" v-loading="loading">
    <!-- Page header -->
    <div class="detail-header glass-card">
      <button class="back-btn" @click="$router.push('/jobs')">
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none"><path d="M13 4L7 10l6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <div class="header-info">
        <h1 class="header-title">{{ job?.name || '任务详情' }}</h1>
        <span v-if="job" class="header-id">{{ job.id }}</span>
      </div>
      <div class="header-actions">
        <button v-if="!isConfigEditing" class="btn-primary" @click="enterConfigEdit">编辑配置</button>
        <button class="btn-ghost" @click="$router.push({ path: '/logs', query: { jobId: job?.id, jobName: job?.name } })">查看日志</button>
      </div>
    </div>

    <div v-if="!job" class="empty-state">
      <p>任务不存在或加载失败</p>
    </div>

    <template v-if="job">
      <!-- Read mode: Info cards -->
      <div v-if="!isConfigEditing" class="detail-grid">
        <!-- Left column: Key info -->
        <div class="glass-card info-card">
          <h3 class="card-section-title">基本信息</h3>
          <dl class="info-list">
            <div class="info-row"><dt>名称</dt><dd>{{ job.name }}</dd></div>
            <div class="info-row"><dt>状态</dt><dd><span class="status-badge" :class="'badge-' + statusType(job.job_status)">{{ job.job_status === 'RUNNING' ? '启用' : '暂停' }}</span></dd></div>
            <div class="info-row"><dt>执行器</dt><dd><span class="config-link" @click="showExecutorConfig(job.executor)">{{ job.executor }}</span></dd></div>
            <div class="info-row"><dt>存储后端</dt><dd><span class="config-link" @click="showJobstoreConfig(job.jobstore)">{{ job.jobstore }}</span></dd></div>
            <div class="info-row"><dt>触发器</dt><dd><span class="config-link" @click="showTriggerConfig">{{ job.trigger || '-' }}</span></dd></div>
          </dl>
        </div>

        <!-- Right column: SSE + Config -->
        <div class="glass-card info-card">
          <h3 class="card-section-title">运行信息</h3>
          <dl class="info-list">
            <div class="info-row"><dt>下次运行</dt><dd>{{ displayNextRunTime }}</dd></div>
            <div class="info-row"><dt>容错时间</dt><dd>{{ job.misfire_grace_time ?? '-' }}s</dd></div>
            <div class="info-row"><dt>合并执行</dt><dd>{{ job.coalesce ? '是' : '否' }}</dd></div>
            <div class="info-row"><dt>最大实例数</dt><dd>{{ job.max_instances ?? '-' }}</dd></div>
          </dl>
        </div>

        <!-- Description card -->
        <div class="glass-card desc-card" v-if="job.description">
          <h3 class="card-section-title">描述</h3>
          <div class="desc-md" v-html="renderMarkdown(job.description)"></div>
        </div>

        <!-- DAG Card -->
        <div class="glass-card dag-card">
          <h3 class="card-section-title">工作流 DAG</h3>
          <div class="dag-container">
            <WorkflowEditor ref="viewWorkflowEditorRef" :readonly="true" @node-click="handleNodeClick" @canvas-click="handleSidebarClose" />
            <NodeInfoSidebar
              :visible="infoSidebarVisible"
              :node-id="infoSidebarNodeId"
              :node-data="infoSidebarNodeData"
              @close="handleSidebarClose"
            />
          </div>
        </div>
      </div>

      <!-- Edit mode -->
      <div v-else class="edit-section">
        <div class="glass-card edit-card">
          <div class="edit-tabs">
            <button
              v-for="tab in editTabs"
              :key="tab.key"
              class="edit-tab"
              :class="{ active: editActiveTab === tab.key }"
              @click="editActiveTab = tab.key"
            >{{ tab.label }}</button>
          </div>

          <!-- Basic tab -->
          <div v-show="editActiveTab === 'basic'" class="tab-panel">
            <div class="form-grid">
              <div class="form-group"><label>名称</label><input v-model="configForm.name" class="form-input" /></div>
              <div class="form-group">
                <label>状态</label>
                <button class="toggle-switch" :class="{ active: configForm.job_status === 'RUNNING' }" @click="configForm.job_status = configForm.job_status === 'RUNNING' ? 'PAUSED' : 'RUNNING'">
                  <span class="toggle-thumb"></span>
                </button>
              </div>
              <div class="form-group"><label>执行器</label>
                <select v-model="configForm.executor" class="form-input"><option v-for="e in executorOptions" :key="e" :value="e">{{ e }}</option></select>
              </div>
              <div class="form-group"><label>存储后端</label>
                <select v-model="configForm.jobstore" class="form-input"><option v-for="j in jobstoreOptions" :key="j" :value="j">{{ j }}</option></select>
              </div>
            </div>
            <div class="form-divider">高级选项</div>
            <div class="form-grid form-grid-3">
              <div class="form-group"><label>容错时间 (s)</label><input v-model.number="configForm.misfire_grace_time" type="number" min="0" class="form-input" /></div>
              <div class="form-group"><label>合并执行</label>
                <button class="toggle-switch" :class="{ active: configForm.coalesce }" @click="configForm.coalesce = !configForm.coalesce"><span class="toggle-thumb"></span></button>
              </div>
              <div class="form-group"><label>最大实例数</label><input v-model.number="configForm.max_instances" type="number" min="1" class="form-input" /></div>
            </div>
            <div class="form-group" style="margin-top: 16px;">
              <label>描述 <span class="label-hint">（支持 Markdown）</span></label>
              <div class="desc-editor-toolbar">
                <button class="mode-btn" :class="{ active: descEditMode === 'source' }" @click="descEditMode = 'source'">源码</button>
                <button class="mode-btn" :class="{ active: descEditMode === 'preview' }" @click="descEditMode = 'preview'">预览</button>
              </div>
              <textarea v-if="descEditMode === 'source'" v-model="configForm.description" class="form-input form-textarea" rows="5"></textarea>
              <div v-else class="desc-md desc-preview" v-html="previewMarkdown"></div>
            </div>
          </div>

          <!-- Trigger tab -->
          <div v-show="editActiveTab === 'trigger'" class="tab-panel">
            <TriggerConfig
              ref="triggerConfigRef"
              :trigger-type="editTriggerType"
              @update:trigger-type="editTriggerType = $event"
              @update:trigger-args="editTriggerArgs = $event"
            />
          </div>

          <!-- DAG tab -->
          <div v-show="editActiveTab === 'workflow'" class="tab-panel tab-dag-panel">
            <WorkflowEditor ref="editWorkflowEditorRef" />
          </div>

          <div class="edit-actions">
            <button class="btn-ghost" @click="cancelConfigEdit">取消</button>
            <button class="btn-primary" :disabled="savingConfig" @click="handleSaveConfig">
              <span v-if="savingConfig" class="btn-spinner"></span>
              <span v-else>保存配置</span>
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Config dialogs -->
    <ComponentConfigDialog v-model:visible="executorDialogVisible" :title="executorDialogTitle" :fields="executorFields" />
    <ComponentConfigDialog v-model:visible="jobstoreDialogVisible" :title="jobstoreDialogTitle" :fields="jobstoreFields" />
    <ComponentConfigDialog v-model:visible="triggerDialogVisible" :title="triggerDialogTitle" :fields="triggerFields" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getJob, updateJob, connectNextRunTimeSSE } from '@/api/jobs'
import { normalizeTriggerType } from '@/api/mappers'
import type { Job } from '@/types'
import type { DagData, TaskNodeProperties } from '@/types/workflow'
import { getExecutorConfigs, getConfiguredJobstores, getJobstoreConfig } from '@/api/components'
import type { ComponentConfig, JobstoreDetailConfig } from '@/api/components'
import { marked } from 'marked'
import WorkflowEditor from './WorkflowEditor.vue'
import TriggerConfig from './TriggerConfig.vue'
import ComponentConfigDialog from './ComponentConfigDialog.vue'
import NodeInfoSidebar from './NodeInfoSidebar.vue'

const route = useRoute()
const job = ref<Job | null>(null)
const loading = ref(false)
const savingConfig = ref(false)
const isConfigEditing = ref(false)
const sseNextRunTime = ref<string | null>(null)
const sseHasUpdate = ref(false)
const viewWorkflowEditorRef = ref<InstanceType<typeof WorkflowEditor> | null>(null)
const editWorkflowEditorRef = ref<InstanceType<typeof WorkflowEditor> | null>(null)
const infoSidebarVisible = ref(false)
const infoSidebarNodeId = ref<string | null>(null)
const infoSidebarNodeData = ref<TaskNodeProperties | null>(null)
let sseCleanup: (() => void) | null = null

const editTabs = [
  { key: 'basic', label: '基本信息' },
  { key: 'trigger', label: '触发器配置' },
  { key: 'workflow', label: '工作流 DAG' },
]

const executorDialogVisible = ref(false); const executorDialogTitle = ref(''); const executorFields = ref<Array<{ label: string; value: unknown }>>([])
const jobstoreDialogVisible = ref(false); const jobstoreDialogTitle = ref(''); const jobstoreFields = ref<Array<{ label: string; value: unknown }>>([])
const triggerDialogVisible = ref(false); const triggerDialogTitle = ref(''); const triggerFields = ref<Array<{ label: string; value: unknown }>>([])

const editActiveTab = ref('basic')
const triggerConfigRef = ref<InstanceType<typeof TriggerConfig> | null>(null)
const editTriggerType = ref('cron')
const editTriggerArgs = ref<Record<string, unknown>>({})
const descEditMode = ref<'source' | 'preview'>('source')
const executorOptions = ref<string[]>([])
const jobstoreOptions = ref<string[]>([])

const previewMarkdown = computed(() => renderMarkdown(configForm.description))

const configForm = reactive({ name: '', description: '', job_status: 'RUNNING' as string, executor: '', jobstore: '', misfire_grace_time: 0, coalesce: false, max_instances: 1 })

const displayNextRunTime = computed(() => {
  const val = sseHasUpdate.value
    ? sseNextRunTime.value
    : (job.value?.next_run_time ?? null)
  return val ? new Date(val).toLocaleString() : '-'
})

function statusType(s: string) { return s === 'RUNNING' ? 'running' : s === 'PAUSED' ? 'paused' : 'warning' }

function handleNodeClick(nodeId: string, nodeData: TaskNodeProperties | null) { infoSidebarNodeId.value = nodeId; infoSidebarNodeData.value = nodeData; infoSidebarVisible.value = true }
function handleSidebarClose() { infoSidebarVisible.value = false }

async function fetchJob() {
  loading.value = true
  try {
    job.value = await getJob(route.params.id as string)
    if (job.value?.dag) setTimeout(() => viewWorkflowEditorRef.value?.loadDag(job.value!.dag as DagData), 100)
  } finally { loading.value = false }
}

async function enterConfigEdit() {
  if (!job.value) return
  Object.assign(configForm, { name: job.value.name, description: job.value.description || '', job_status: job.value.job_status || 'RUNNING', executor: job.value.executor, jobstore: job.value.jobstore, misfire_grace_time: job.value.misfire_grace_time ?? 0, coalesce: job.value.coalesce ?? false, max_instances: job.value.max_instances ?? 1 })
  editTriggerType.value = normalizeTriggerType(job.value.trigger)
  editTriggerArgs.value = {}; descEditMode.value = 'source'; editActiveTab.value = 'basic'; isConfigEditing.value = true
  await nextTick()
  try {
    const [ec, jc] = await Promise.all([getExecutorConfigs(), getConfiguredJobstores()])
    executorOptions.value = ec.map((c: ComponentConfig) => c.name)
    jobstoreOptions.value = jc.map((j: { alias: string }) => j.alias)
  } catch { executorOptions.value = [job.value.executor]; jobstoreOptions.value = [job.value.jobstore] }
  const args = job.value.trigger_args
  if (args && Object.keys(args).length > 0) triggerConfigRef.value?.setTriggerArgs(args as Record<string, unknown>)
  if (job.value?.dag) setTimeout(() => editWorkflowEditorRef.value?.loadDag(job.value!.dag as DagData), 300)
}

watch(editActiveTab, (tab) => {
  if (tab === 'workflow' && job.value?.dag) {
    const d = editWorkflowEditorRef.value?.getDagData()
    if (!d || d.nodes.length === 0) nextTick(() => editWorkflowEditorRef.value?.loadDag(job.value!.dag as DagData))
  }
})

function cancelConfigEdit() {
  isConfigEditing.value = false
  if (job.value?.dag) setTimeout(() => viewWorkflowEditorRef.value?.loadDag(job.value!.dag as DagData), 100)
}

async function handleSaveConfig() {
  if (!job.value) return
  savingConfig.value = true
  try {
    await updateJob(job.value.id, {
      name: configForm.name, description: configForm.description, job_status: configForm.job_status, executor: configForm.executor, jobstore: configForm.jobstore,
      misfire_grace_time: configForm.misfire_grace_time, coalesce: configForm.coalesce, max_instances: configForm.max_instances,
      trigger: editTriggerType.value, trigger_args: triggerConfigRef.value?.getTriggerArgs() || undefined,
      dag: editWorkflowEditorRef.value?.getDagData(),
    })
    await fetchJob(); isConfigEditing.value = false; ElMessage.success('配置已保存')
  } catch { ElMessage.error('保存失败') } finally { savingConfig.value = false }
}

function startSSE() {
  sseCleanup = connectNextRunTimeSSE(route.params.id as string,
    (nextRunTime) => {
      sseNextRunTime.value = nextRunTime
      sseHasUpdate.value = true
    },
    (error) => { console.warn('SSE error:', error) })
}
function stopSSE() { sseCleanup?.(); sseCleanup = null }

async function showExecutorConfig(name: string) { executorDialogTitle.value = `执行器配置 — ${name}`; executorDialogVisible.value = true; try { const c = await getExecutorConfigs(); const f = c.find((x: ComponentConfig) => x.name === name); executorFields.value = f ? Object.entries(f.config || {}).map(([k, v]) => ({ label: k, value: v })) : [] } catch { executorFields.value = [] } }
async function showJobstoreConfig(alias: string) { jobstoreDialogTitle.value = `存储后端配置 — ${alias}`; jobstoreDialogVisible.value = true; try { const d: JobstoreDetailConfig = await getJobstoreConfig(alias); jobstoreFields.value = Object.entries(d.config || {}).map(([k, v]) => ({ label: k, value: v })) } catch { jobstoreFields.value = [] } }
function showTriggerConfig() { if (!job.value) return; triggerDialogTitle.value = `触发器配置 — ${job.value.trigger || '-'}`; triggerDialogVisible.value = true; const a = job.value.trigger_args; triggerFields.value = a && Object.keys(a).length > 0 ? Object.entries(a).map(([k, v]) => ({ label: k, value: v })) : [] }
function renderMarkdown(text: string | undefined | null): string { if (!text) return ''; return marked(text) as string }

onMounted(() => { fetchJob(); startSSE() })
onBeforeUnmount(() => { stopSSE() })
</script>

<style scoped>
.job-detail { max-width: 1200px; padding-bottom: 60px; }

/* Header */
.detail-header { display: flex; align-items: center; gap: 16px; padding: 16px 20px; margin-bottom: var(--space-lg); }
.back-btn { display: flex; align-items: center; justify-content: center; width: 34px; height: 34px; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: var(--bg-surface); color: var(--text-secondary); cursor: pointer; transition: all var(--transition-fast); flex-shrink: 0; }
.back-btn:hover { background: var(--bg-surface-hover); color: var(--text-primary); }
.header-info { flex: 1; min-width: 0; }
.header-title { font-family: var(--font-heading); font-size: 18px; font-weight: 700; color: var(--text-primary); margin: 0; }
.header-id { font-family: 'Fira Code', monospace; font-size: 12px; color: var(--text-muted); }
.header-actions { display: flex; gap: 8px; flex-shrink: 0; }

/* Buttons */
.btn-primary { display: inline-flex; align-items: center; gap: 6px; padding: 9px 18px; border: none; border-radius: var(--radius-md); background: var(--color-primary); color: white; font-size: 13px; font-weight: 600; font-family: var(--font-body); cursor: pointer; transition: all var(--transition-fast); }
.btn-primary:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); box-shadow: var(--shadow-glow); }
.btn-primary:active:not(:disabled) { transform: translateY(0) scale(0.98); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-ghost { display: inline-flex; align-items: center; gap: 6px; padding: 9px 18px; border: 1px solid var(--border-default); border-radius: var(--radius-md); background: var(--bg-surface); color: var(--text-secondary); font-size: 13px; font-weight: 500; font-family: var(--font-body); cursor: pointer; transition: all var(--transition-fast); }
.btn-ghost:hover { background: var(--bg-surface-hover); color: var(--text-primary); }

.btn-spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: spin 0.6s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Info cards */
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-md); }
.info-card { padding: var(--space-lg); }
.desc-card { grid-column: 1 / -1; padding: var(--space-lg); }
.dag-card { grid-column: 1 / -1; padding: var(--space-lg); }

.card-section-title { font-family: var(--font-heading); font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; margin: 0 0 16px; }

.info-list { display: flex; flex-direction: column; gap: 0; }
.info-row { display: flex; padding: 10px 0; border-bottom: 1px solid var(--border-subtle); }
.info-row:last-child { border-bottom: none; }
.info-row dt { width: 80px; font-size: 13px; color: var(--text-muted); flex-shrink: 0; }
.info-row dd { font-size: 13px; color: var(--text-primary); font-weight: 500; }

.config-link { color: var(--color-primary); cursor: pointer; text-decoration: underline; text-decoration-style: dashed; text-underline-offset: 3px; transition: color var(--transition-fast); }
.config-link:hover { color: var(--color-primary-hover); }

/* Status badges */
.status-badge { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: var(--radius-full); }
.badge-running { background: var(--color-success-soft); color: var(--color-success); }
.badge-paused { background: var(--bg-surface); color: var(--text-muted); }
.badge-warning { background: var(--color-warning-soft); color: var(--color-warning); }

/* DAG */
.dag-container { height: 480px; position: relative; overflow: hidden; border-radius: var(--radius-sm); }

.desc-md { line-height: 1.7; font-size: 13px; color: var(--text-secondary); }
.desc-md :deep(h1), .desc-md :deep(h2), .desc-md :deep(h3) { color: var(--text-primary); margin: 12px 0 6px; }
.desc-md :deep(code) { padding: 2px 6px; background: var(--bg-surface); border-radius: 3px; font-family: 'Fira Code', monospace; font-size: 12px; }
.desc-md :deep(pre) { padding: 10px 14px; background: var(--bg-surface); border-radius: var(--radius-sm); overflow-x: auto; }
.desc-md :deep(blockquote) { border-left: 3px solid var(--color-primary); padding: 4px 12px; margin: 6px 0; color: var(--text-muted); }

/* Edit mode */
.edit-section { margin-top: 0; }
.edit-card { padding: 0; overflow: hidden; }

.edit-tabs { display: flex; border-bottom: 1px solid var(--border-subtle); padding: 0 var(--space-md); }
.edit-tab { padding: 14px 20px; border: none; background: none; color: var(--text-muted); font-size: 13px; font-weight: 500; font-family: var(--font-body); cursor: pointer; border-bottom: 2px solid transparent; transition: all var(--transition-fast); }
.edit-tab:hover { color: var(--text-secondary); }
.edit-tab.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }

.tab-panel { padding: var(--space-lg); }
.tab-dag-panel { height: 480px; }

.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.form-grid-3 { grid-template-columns: 1fr 1fr 1fr; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 13px; font-weight: 500; color: var(--text-secondary); }
.label-hint { font-weight: 400; color: var(--text-muted); font-size: 12px; }

.form-input { padding: 10px 14px; background: var(--bg-surface); border: 1px solid var(--border-default); border-radius: var(--radius-sm); color: var(--text-primary); font-size: 14px; font-family: var(--font-body); outline: none; transition: border-color var(--transition-fast); }
.form-input:focus { border-color: var(--color-primary); box-shadow: 0 0 0 3px var(--color-primary-soft); }
select.form-input { cursor: pointer; }
.form-textarea { resize: vertical; min-height: 100px; }

.form-divider { display: flex; align-items: center; gap: 12px; margin: 24px 0 16px; font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
.form-divider::after { content: ''; flex: 1; height: 1px; background: var(--border-subtle); }

.edit-actions { display: flex; justify-content: flex-end; gap: 8px; padding: 16px var(--space-lg); border-top: 1px solid var(--border-subtle); }

/* Toggle */
.toggle-switch { position: relative; width: 40px; height: 22px; border-radius: 11px; border: none; background: var(--border-default); cursor: pointer; transition: background var(--transition-fast); }
.toggle-switch.active { background: var(--color-success); }
.toggle-switch .toggle-thumb { position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%; background: white; transition: transform var(--transition-fast); box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
.toggle-switch.active .toggle-thumb { transform: translateX(18px); }

/* Desc editor */
.desc-editor-toolbar { display: flex; gap: 4px; margin-bottom: 8px; }
.mode-btn { padding: 4px 12px; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: var(--bg-surface); color: var(--text-muted); font-size: 12px; font-family: var(--font-body); cursor: pointer; transition: all var(--transition-fast); }
.mode-btn.active { background: var(--color-primary-soft); color: var(--color-primary); border-color: var(--color-primary); }
.desc-preview { border: 1px solid var(--border-default); border-radius: var(--radius-sm); padding: 12px; min-height: 100px; background: var(--bg-surface); }

.empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); }

@media (max-width: 768px) {
  .detail-grid { grid-template-columns: 1fr; }
  .detail-header { flex-wrap: wrap; }
  .form-grid, .form-grid-3 { grid-template-columns: 1fr; }
}
</style>
