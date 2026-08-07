<template>
  <div class="execution-detail">
    <div class="panel-header">
      <span class="panel-title">节点执行详情</span>
      <el-button :icon="Close" text size="small" @click="emit('update:visible', false)" />
    </div>
    <div class="panel-body">
      <template v-if="record">
        <el-descriptions :column="1" border size="small" class="detail-table">
          <el-descriptions-item label="节点 ID">
            <code class="mono">{{ record.node_id || '-' }}</code>
          </el-descriptions-item>
          <el-descriptions-item v-if="record.node_name" label="名称">
            {{ record.node_name }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType" size="small">{{ record.status || '-' }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="record.duration != null" label="耗时">
            {{ formatDuration(record.duration) }}
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">
            {{ record.start_time ? new Date(record.start_time).toLocaleString() : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="结束时间">
            {{ record.end_time ? new Date(record.end_time).toLocaleString() : '-' }}
          </el-descriptions-item>
          <el-descriptions-item v-if="record.exit_code != null" label="退出码">
            <code>{{ record.exit_code }}</code>
          </el-descriptions-item>
          <el-descriptions-item v-if="record.skip_reason" label="跳过原因">
            {{ record.skip_reason }}
          </el-descriptions-item>

          <!-- Result (python_callable return value) -->
          <el-descriptions-item v-if="hasResult" label="返回值">
            <div class="cell-output">
              <div class="cell-toolbar">
                <el-button :icon="CopyDocument" text size="small" @click="copyContent(formattedResult)" />
              </div>
              <pre class="cell-pre cell-pre-light">{{ formattedResult }}</pre>
            </div>
          </el-descriptions-item>

          <!-- stdout -->
          <el-descriptions-item v-if="hasStdout" label="stdout">
            <div class="cell-output">
              <div class="cell-toolbar">
                <el-button :icon="CopyDocument" text size="small" @click="copyContent(record.stdout || '')" />
              </div>
              <pre class="cell-pre cell-pre-stdout">{{ record.stdout }}</pre>
            </div>
          </el-descriptions-item>

          <!-- stderr -->
          <el-descriptions-item v-if="hasStderr" label="stderr">
            <div class="cell-output">
              <div class="cell-toolbar">
                <el-button :icon="CopyDocument" text size="small" @click="copyContent(record.stderr || '')" />
              </div>
              <pre class="cell-pre cell-pre-stderr">{{ record.stderr }}</pre>
            </div>
          </el-descriptions-item>

          <!-- Error -->
          <el-descriptions-item v-if="record.error" label="错误信息">
            <div class="cell-output">
              <div class="cell-toolbar">
                <el-button :icon="CopyDocument" text size="small" @click="copyContent(record.error)" />
              </div>
              <pre class="cell-pre cell-pre-error">{{ record.error }}</pre>
            </div>
          </el-descriptions-item>

          <!-- Empty -->
          <el-descriptions-item v-if="noOutput" label="输出">
            <span class="cell-empty">（无输出内容）</span>
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <el-empty v-else description="无数据" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Close, CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { NodeExecutionRecord } from '@/types/workflow'

const props = defineProps<{
  visible: boolean
  record: NodeExecutionRecord | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

const hasResult = computed(() => {
  const r = props.record?.result
  return r != null && r !== '' && r !== 'null'
})
const hasStdout = computed(() => {
  const s = props.record?.stdout
  return s != null && s !== ''
})
const hasStderr = computed(() => {
  const s = props.record?.stderr
  return s != null && s !== ''
})
const noOutput = computed(() => !hasResult.value && !hasStdout.value && !hasStderr.value && !props.record?.error)

const formattedResult = computed(() => {
  const raw = props.record?.result
  if (raw == null || raw === '') return ''
  if (typeof raw === 'string') return raw
  try {
    return JSON.stringify(raw, null, 2)
  } catch {
    return String(raw)
  }
})

function statusTagType(status: string | null): string {
  switch (status) {
    case 'SUCCEEDED': return 'success'
    case 'FAILED': return 'danger'
    case 'SKIPPED': return 'warning'
    case 'RUNNING': return ''
    default: return 'info'
  }
}

function formatDuration(seconds: number): string {
  if (seconds < 0.001) return '< 0.001s'
  if (seconds < 1) return (seconds * 1000).toFixed(1) + 'ms'
  return seconds.toFixed(3) + 's'
}

function copyContent(text: string) {
  navigator.clipboard.writeText(text).then(
    () => ElMessage.success('已复制到剪贴板'),
    () => ElMessage.error('复制失败'),
  )
}
</script>

<style scoped>
.execution-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 0;
  flex-shrink: 0;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  min-width: 0;
}

.detail-table {
  min-width: 0;
}

/* Make label column take reasonable width, content column gets the rest */
.detail-table :deep(.el-descriptions__label) {
  width: 1%;
  white-space: nowrap;
  min-width: 80px;
}

.detail-table :deep(.el-descriptions__content) {
  min-width: 0;
}

.mono {
  font-family: 'Cascadia Code', 'Fira Code', 'Courier New', monospace;
  font-size: 12px;
}

/* Output cells */
.cell-output {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.cell-toolbar {
  display: flex;
  justify-content: flex-end;
  padding-bottom: 4px;
}

.cell-pre {
  margin: 0;
  padding: 8px 10px;
  border-radius: 4px;
  font-family: 'Cascadia Code', 'Fira Code', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-wrap: break-word;
  max-height: 280px;
  overflow-y: auto;
  min-width: 0;
}

.cell-pre-light {
  background: var(--el-fill-color-lighter, #fafafa);
  color: var(--el-text-color-primary);
  border: 1px solid var(--el-border-color-lighter);
}

.cell-pre-stdout {
  background: #1e1e1e;
  color: #4ec9b0;
}

.cell-pre-stderr {
  background: #1e1e1e;
  color: #f14c4c;
}

.cell-pre-error {
  background: var(--el-color-danger-light-9, #fef0f0);
  color: var(--el-color-danger, #f56c6c);
  border: 1px solid #fde2e2;
}

.cell-empty {
  color: var(--el-text-color-placeholder, #c0c4cc);
  font-size: 13px;
}
</style>
