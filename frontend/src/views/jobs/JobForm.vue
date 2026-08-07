<template>
  <transition name="overlay-fade">
    <div v-if="visible" class="form-overlay">
      <div class="form-overlay-panel glass-panel">
        <!-- Header -->
        <div class="form-overlay-header">
          <h2 class="form-overlay-title">{{ isEdit ? '编辑工作流' : '创建工作流' }}</h2>
          <button class="close-btn" @click="$emit('update:visible', false)">
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none"><line x1="5" y1="5" x2="15" y2="15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><line x1="15" y1="5" x2="5" y2="15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          </button>
        </div>

        <!-- Body -->
        <div class="form-overlay-body">
          <div class="form-tabs">
            <button v-for="tab in tabs" :key="tab.key" class="form-tab" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">{{ tab.label }}</button>
          </div>

          <!-- Basic tab -->
          <div v-show="activeTab === 'basic'" class="tab-panel">
            <div class="form-grid form-grid-single">
              <div class="form-group"><label>工作流名称</label><input v-model="form.name" class="form-input" placeholder="输入工作流名称" /></div>
            </div>
            <div class="form-grid form-grid-single">
              <div class="form-group"><label>描述</label><textarea v-model="form.description" class="form-input form-textarea" rows="3" placeholder="输入工作流描述（支持 Markdown）"></textarea></div>
            </div>
            <div class="form-grid">
              <div class="form-group">
                <label>执行器</label>
                <select v-model="form.executor" class="form-input"><option v-for="e in configuredExecutors" :key="e" :value="e">{{ e }}</option></select>
                <span class="field-hint">未找到需要的执行器？<router-link to="/executor-config">前往配置</router-link></span>
              </div>
              <div class="form-group">
                <label>存储后端</label>
                <select v-model="form.jobstore" class="form-input"><option v-for="j in jobstores" :key="j.name" :value="j.name">{{ j.name }}</option></select>
                <span class="field-hint">未找到需要的存储后端？<router-link to="/storage-config">前往配置</router-link></span>
              </div>
            </div>
            <div class="form-divider">高级选项</div>
            <div class="form-grid form-grid-3">
              <div class="form-group"><label>合并执行</label><button class="toggle-switch" :class="{ active: form.coalesce }" @click="form.coalesce = !form.coalesce"><span class="toggle-thumb"></span></button></div>
              <div class="form-group"><label>最大实例数</label><input v-model.number="form.max_instances" type="number" min="1" class="form-input" /></div>
              <div class="form-group"><label>错过宽限(s)</label><input v-model.number="form.misfire_grace_time" type="number" min="0" class="form-input" /></div>
            </div>
            <p class="form-hint">提示：具体任务节点请在「工作流 DAG」标签页中添加和配置，每个节点可设置为不同的任务类型（Python Callable / Python 文件 / Python 脚本 / Bash 命令）。</p>
          </div>

          <!-- Trigger tab -->
          <div v-show="activeTab === 'trigger'" class="tab-panel">
            <TriggerConfig ref="triggerConfigRef" :trigger-type="triggerType" @update:trigger-type="triggerType = $event" @update:trigger-args="triggerArgs = $event" />
          </div>

          <!-- DAG tab -->
          <div v-show="activeTab === 'workflow'" class="tab-panel tab-dag-panel">
            <WorkflowEditor ref="workflowEditorRef" />
          </div>
        </div>

        <!-- Footer -->
        <div class="form-overlay-footer">
          <p v-if="formError" class="form-error">{{ formError }}</p>
          <div class="footer-btns">
            <button class="btn-ghost" @click="$emit('update:visible', false)">取消</button>
            <button class="btn-primary" :disabled="submitting" @click="handleSubmit">
              <span v-if="submitting" class="btn-spinner"></span>
              <span v-else>{{ isEdit ? '保存修改' : '创建工作流' }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, reactive, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import type { Job, JobCreateParams } from '@/types'
import type { DagData } from '@/types/workflow'
import { getExecutorConfigs, getConfiguredJobstores } from '@/api/components'
import { normalizeTriggerType } from '@/api/mappers'
import WorkflowEditor from './WorkflowEditor.vue'
import TriggerConfig from './TriggerConfig.vue'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ 'update:visible': [value: boolean]; submit: [params: JobCreateParams] }>()

const activeTab = ref('basic')
const submitting = ref(false)
const formError = ref('')
const configuredExecutors = ref<string[]>([])
const jobstores = ref<Array<{ name: string; alias: string }>>([])
const workflowEditorRef = ref<InstanceType<typeof WorkflowEditor> | null>(null)
const triggerConfigRef = ref<InstanceType<typeof TriggerConfig> | null>(null)
const triggerType = ref('cron')
const triggerArgs = ref<Record<string, unknown>>({})
const isEdit = ref(false)

const form = reactive({
  name: '', description: '', executor: '', jobstore: '',
  coalesce: false, max_instances: 1, misfire_grace_time: 0,
})

const tabs = [{ key: 'basic', label: '基本信息' }, { key: 'trigger', label: '触发器配置' }, { key: 'workflow', label: '工作流 DAG' }]

function resetForm() {
  Object.assign(form, { name: '', description: '', executor: '', jobstore: '', coalesce: false, max_instances: 1, misfire_grace_time: 0 })
  triggerType.value = 'cron'; triggerArgs.value = {}
  activeTab.value = 'basic'; formError.value = ''; isEdit.value = false
}

function fillFromJob(job: Job) {
  // Copying always creates a brand-new workflow, so stay in create mode.
  isEdit.value = false
  Object.assign(form, { name: job.name || '', description: job.description || '', executor: job.executor, jobstore: job.jobstore, coalesce: job.coalesce ?? false, max_instances: job.max_instances ?? 1, misfire_grace_time: job.misfire_grace_time ?? 0 })
  triggerType.value = normalizeTriggerType(job.trigger)
  triggerArgs.value = { ...(job.trigger_args || {}) }
  activeTab.value = 'basic'

  nextTick(() => {
    // The trigger component resets its fields when the type changes, so
    // populate its args after that watcher has flushed.
    if (job.trigger_args && Object.keys(job.trigger_args).length > 0) {
      triggerConfigRef.value?.setTriggerArgs(job.trigger_args as Record<string, unknown>)
    }
    if (job.dag) {
      void loadCopiedDag(job.dag as DagData)
    }
  })
}

/** Load the copied DAG once the editor is mounted, retrying briefly. */
async function loadCopiedDag(dag: DagData) {
  for (let attempt = 0; attempt < 30; attempt++) {
    const editor = workflowEditorRef.value
    if (editor) {
      editor.loadDag(dag)
      if (editor.getDagData().nodes.length > 0) return
    }
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
}

watch(() => props.visible, async (v) => {
  if (!v) { resetForm(); return }
  try {
    const [execs, stores] = await Promise.all([getExecutorConfigs(), getConfiguredJobstores()])
    configuredExecutors.value = execs.map((c: any) => c.name)
    jobstores.value = stores.map((j: any) => ({ name: j.alias, alias: j.alias }))
  } catch { /* defaults */ }
})

async function handleSubmit() {
  formError.value = ''
  if (!form.name.trim()) { formError.value = '请输入工作流名称'; return }
  if (!form.executor) { formError.value = '请选择执行器'; return }
  if (!form.jobstore) { formError.value = '请选择存储后端'; return }

  const finalTriggerArgs = triggerConfigRef.value?.getTriggerArgs()
  const dagData = workflowEditorRef.value?.getDagData()

  if (dagData && dagData.nodes.length > 0 && dagData.edges.length > 0) {
    const nodeIds = new Set(dagData.nodes.map(n => n.node_id))
    for (const edge of dagData.edges) { if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) { formError.value = `连线引用了不存在的节点`; return } }
  }

  const params: JobCreateParams = {
    name: form.name, description: form.description || undefined, executor: form.executor, jobstore: form.jobstore,
    coalesce: form.coalesce, max_instances: form.max_instances, misfire_grace_time: form.misfire_grace_time || undefined,
    trigger: triggerType.value, trigger_args: finalTriggerArgs && Object.keys(finalTriggerArgs).length > 0 ? finalTriggerArgs : undefined,
    dag: dagData || undefined,
  }

  submitting.value = true
  try {
    emit('submit', params)
  } finally { submitting.value = false }
}

defineExpose({ fillFromJob })
</script>

<style scoped>
.form-overlay { position: fixed; top: 0; right: 0; bottom: 0; left: var(--sidebar-width); z-index: 100; background: rgba(0,0,0,0.45); backdrop-filter: blur(6px); display: flex; }
html:not(.dark) .form-overlay { background: rgba(0,0,0,0.15); }
.form-overlay-panel { flex: 1; display: flex; flex-direction: column; max-width: 100%; }

.form-overlay-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 24px; border-bottom: 1px solid var(--glass-border); flex-shrink: 0; }
.form-overlay-title { font-family: var(--font-heading); font-size: 16px; font-weight: 700; color: var(--text-primary); margin: 0; }
.close-btn { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: var(--bg-surface); color: var(--text-secondary); cursor: pointer; transition: all var(--transition-fast); }
.close-btn:hover { background: var(--bg-surface-hover); color: var(--text-primary); }

.form-overlay-body { flex: 1; overflow-y: auto; }

.form-tabs { display: flex; padding: 0 24px; border-bottom: 1px solid var(--border-subtle); }
.form-tab { padding: 12px 18px; border: none; background: none; color: var(--text-muted); font-size: 13px; font-weight: 500; font-family: var(--font-body); cursor: pointer; border-bottom: 2px solid transparent; transition: all var(--transition-fast); }
.form-tab:hover { color: var(--text-secondary); }
.form-tab.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }

.tab-panel { padding: 24px; max-width: 860px; }
.tab-dag-panel { max-width: none; height: calc(100vh - 240px); }

.form-overlay-footer { padding: 12px 24px; border-top: 1px solid var(--glass-border); flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; }
.footer-btns { display: flex; gap: 8px; margin-left: auto; }
.form-error { font-size: 13px; color: var(--color-danger); }

/* Shared form elements */
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.form-grid-single { grid-template-columns: 1fr; }
.form-grid-3 { grid-template-columns: 1fr 1fr 1fr; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 13px; font-weight: 500; color: var(--text-secondary); }
.form-input { padding: 10px 14px; background: var(--bg-surface); border: 1px solid var(--border-default); border-radius: var(--radius-sm); color: var(--text-primary); font-size: 14px; font-family: var(--font-body); outline: none; transition: border-color var(--transition-fast); }
.form-input:focus { border-color: var(--color-primary); box-shadow: 0 0 0 3px var(--color-primary-soft); }
select.form-input { cursor: pointer; }
.form-textarea { resize: vertical; min-height: 80px; }
.code-input { font-family: 'Fira Code', monospace; font-size: 13px; background: rgba(0,0,0,0.2); color: #4ec9b0; }
.field-hint { font-size: 11px; color: var(--text-muted); }
.field-hint a { color: var(--color-primary); }
.form-hint { font-size: 12px; color: var(--text-muted); line-height: 1.6; margin-top: var(--space-md); padding: 10px 14px; background: var(--bg-surface); border-radius: var(--radius-sm); border-left: 3px solid var(--color-primary); }
.form-divider { display: flex; align-items: center; gap: 12px; margin: 20px 0 14px; font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
.form-divider::after { content: ''; flex: 1; height: 1px; background: var(--border-subtle); }

/* Buttons */
.btn-primary { display: inline-flex; align-items: center; gap: 6px; padding: 9px 18px; border: none; border-radius: var(--radius-md); background: var(--color-primary); color: white; font-size: 13px; font-weight: 600; font-family: var(--font-body); cursor: pointer; transition: all var(--transition-fast); }
.btn-primary:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); box-shadow: var(--shadow-glow); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-ghost { display: inline-flex; align-items: center; gap: 6px; padding: 9px 18px; border: 1px solid var(--border-default); border-radius: var(--radius-md); background: var(--bg-surface); color: var(--text-secondary); font-size: 13px; font-weight: 500; font-family: var(--font-body); cursor: pointer; transition: all var(--transition-fast); }
.btn-ghost:hover { background: var(--bg-surface-hover); color: var(--text-primary); }
.btn-spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: spin 0.6s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Toggle */
.toggle-switch { position: relative; width: 40px; height: 22px; border-radius: 11px; border: none; background: var(--border-default); cursor: pointer; transition: background var(--transition-fast); flex-shrink: 0; }
.toggle-switch.active { background: var(--color-success); }
.toggle-switch .toggle-thumb { position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%; background: white; transition: transform var(--transition-fast); box-shadow: 0 1px 3px rgba(0,0,0,0.2); }

.overlay-fade-enter-active, .overlay-fade-leave-active { transition: opacity var(--transition-slow); }
.overlay-fade-enter-from, .overlay-fade-leave-to { opacity: 0; }
</style>
