<template>
  <div class="job-logs">
    <el-page-header @back="$router.push('/jobs')">
      <template #content>
        <span>任务日志 - {{ jobName || jobId }}</span>
      </template>
    </el-page-header>

    <div class="logs-container" v-loading="loading">
      <div class="logs-left">
        <ExecutionList
          :logs="logs"
          :selected-index="selectedIndex"
          @select="selectLog"
        />
      </div>
      <div class="logs-right">
        <div v-if="selectedLog" class="canvas-wrapper">
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
        <el-empty v-else description="选择左侧执行记录查看详情" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getJobLogs } from '@/api/logs'
import type { ExecutionLog, NodeExecutionRecord, DagData } from '@/types/workflow'
import ExecutionList from './ExecutionList.vue'
import WorkflowEditor from '@/views/jobs/WorkflowEditor.vue'
import TaskExecutionDetailDrawer from './TaskExecutionDetailDrawer.vue'

const route = useRoute()
const jobId = route.params.jobId as string
const jobName = (route.query.jobName as string) || ''
const logs = ref<ExecutionLog[]>([])
const loading = ref(false)
const selectedIndex = ref(0)
const drawerVisible = ref(false)
const selectedRecord = ref<NodeExecutionRecord | null>(null)
const workflowEditorRef = ref<InstanceType<typeof WorkflowEditor> | null>(null)

const selectedLog = computed(() => logs.value[selectedIndex.value] ?? null)

const selectedNodeStatusMap = computed<Record<string, string>>(() => {
  if (!selectedLog.value?.node_records) return {}
  const map: Record<string, string> = {}
  for (const [key, record] of Object.entries(selectedLog.value.node_records)) {
    if (record.status) {
      // node_id is the primary identifier matching dagNode.node_id in WorkflowEditor
      const id = record.node_id || key
      if (id) {
        map[id] = record.status
      }
    }
  }
  return map
})

async function fetchLogs() {
  loading.value = true
  try {
    logs.value = (await getJobLogs(jobId) as ExecutionLog[])
      .sort((a, b) => new Date(b.start_time ?? 0).getTime() - new Date(a.start_time ?? 0).getTime())
    if (logs.value.length > 0) {
      selectLog(0)
    }
  } catch {
    logs.value = []
  } finally {
    loading.value = false
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

onMounted(fetchLogs)
</script>

<style scoped>
.job-logs {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 140px);
}

.logs-container {
  display: flex;
  flex: 1;
  margin-top: 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
}

.logs-left {
  width: 320px;
  flex-shrink: 0;
}

.logs-right {
  flex: 1;
  max-width: 800px;
  background: var(--el-bg-color, #fff);
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
  background: var(--el-bg-color, #fff);
  border-left: 1px solid var(--el-border-color);
  box-shadow: -4px 0 12px rgba(0, 0, 0, 0.08);
  z-index: 100;
  overflow-y: auto;
}

.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: transform 0.3s ease;
}

.panel-slide-enter-from,
.panel-slide-leave-to {
  transform: translateX(100%);
}
</style>
