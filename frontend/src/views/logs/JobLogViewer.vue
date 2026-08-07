<template>
  <div class="log-viewer">
    <el-page-header @back="$router.push('/jobs')">
      <template #content>
        <span>任务日志 - {{ currentJobName || '请选择任务' }}</span>
      </template>
    </el-page-header>

    <div class="viewer-container">
      <!-- 左栏：任务选择 -->
      <div class="viewer-left">
        <TaskSelector
          ref="taskSelectorRef"
          :active-job-id="currentJobId"
          @select="handleTaskSelect"
        />
      </div>

      <!-- 中栏：执行记录 -->
      <div class="viewer-middle" v-loading="logsLoading">
        <ExecutionList
          v-if="currentJobId"
          :logs="logs"
          :selected-index="selectedIndex"
          @select="selectLog"
        />
        <el-empty v-else description="请在左侧选择任务" />
      </div>

      <!-- 右栏：画布 + 侧边详情面板 -->
      <div class="viewer-right">
        <template v-if="selectedLog">
          <div class="canvas-wrapper">
            <WorkflowEditor
              ref="workflowEditorRef"
              :readonly="true"
              :node-status-map="selectedNodeStatusMap"
              @node-click="handleNodeClick"
            />
            <transition name="panel-slide">
              <div v-if="drawerVisible" class="execution-side-panel">
                <TaskExecutionDetailDrawer
                  v-model:visible="drawerVisible"
                  :record="selectedRecord"
                />
              </div>
            </transition>
          </div>
        </template>
        <el-empty v-else description="选择左侧执行记录查看详情" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getJobLogs } from '@/api/logs'
import type { ExecutionLog, NodeExecutionRecord, DagData } from '@/types/workflow'
import TaskSelector from './TaskSelector.vue'
import ExecutionList from './ExecutionList.vue'
import WorkflowEditor from '@/views/jobs/WorkflowEditor.vue'
import TaskExecutionDetailDrawer from './TaskExecutionDetailDrawer.vue'

const route = useRoute()

const currentJobId = ref<string | null>(null)
const currentJobName = ref('')

const logs = ref<ExecutionLog[]>([])
const logsLoading = ref(false)
const selectedIndex = ref(0)
const drawerVisible = ref(false)
const selectedRecord = ref<NodeExecutionRecord | null>(null)
const workflowEditorRef = ref<InstanceType<typeof WorkflowEditor> | null>(null)
let fetchId = 0

const selectedLog = computed(() => logs.value[selectedIndex.value] ?? null)

const selectedNodeStatusMap = computed<Record<string, string>>(() => {
  if (!selectedLog.value?.node_records) return {}
  const map: Record<string, string> = {}
  for (const [key, record] of Object.entries(selectedLog.value.node_records)) {
    if (record.status) {
      const id = record.node_id || key
      if (id) map[id] = record.status
    }
  }
  return map
})

function handleTaskSelect(jobId: string, jobName: string) {
  currentJobId.value = jobId
  currentJobName.value = jobName
  logs.value = []
  selectedIndex.value = 0
  drawerVisible.value = false
  selectedRecord.value = null
  fetchLogs(jobId)
}

async function fetchLogs(jobId: string) {
  const id = ++fetchId
  logsLoading.value = true
  try {
    const result = await getJobLogs(jobId)
    if (id !== fetchId) return
    logs.value = result
      .sort((a, b) => new Date(b.start_time ?? 0).getTime() - new Date(a.start_time ?? 0).getTime())
    if (logs.value.length > 0) {
      selectLog(0)
    }
  } catch {
    logs.value = []
  } finally {
    logsLoading.value = false
  }
}

function selectLog(index: number) {
  selectedIndex.value = index
  drawerVisible.value = false
  selectedRecord.value = null
  nextTick(() => {
    const log = logs.value[index]
    if (log?.dag && workflowEditorRef.value) {
      workflowEditorRef.value.loadDag(log.dag as DagData)
    }
  })
}

function handleNodeClick(nodeId: string) {
  if (!selectedLog.value?.node_records) return
  const record =
    selectedLog.value.node_records[nodeId] ??
    Object.values(selectedLog.value.node_records).find(
      (r) => r.node_id === nodeId || r.task_id === nodeId,
    )
  if (record) {
    selectedRecord.value = record
    drawerVisible.value = true
  }
}

// Auto-select task from query params
watch(() => route.query.jobId, (jobId) => {
  if (jobId && typeof jobId === 'string') {
    const name = (route.query.jobName as string) || ''
    handleTaskSelect(jobId, name)
  }
}, { immediate: true })
</script>

<style scoped>
.log-viewer {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 100px);
  padding: var(--space-lg) var(--space-xl);
}

.viewer-container {
  display: flex;
  flex: 1;
  margin-top: var(--space-md);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--bg-base);
}

.viewer-left {
  width: 220px;
  flex-shrink: 0;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  border-right: 1px solid var(--glass-border);
}

.viewer-middle {
  width: 300px;
  flex-shrink: 0;
  background: var(--bg-base);
  border-right: 1px solid var(--glass-border);
  overflow: hidden;
}

.viewer-right {
  flex: 1;
  background: var(--bg-deep);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.canvas-wrapper {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.execution-side-panel {
  position: absolute;
  top: 0;
  right: 0;
  width: 480px;
  height: 100%;
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-left: 1px solid var(--glass-border);
  box-shadow: var(--shadow-lg);
  z-index: 100;
  overflow-y: auto;
}
</style>
