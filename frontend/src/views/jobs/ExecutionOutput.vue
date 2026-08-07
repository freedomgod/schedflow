<template>
  <div class="execution-output">
    <!-- Result panel -->
    <div v-if="hasResult" class="eo-panel">
      <div class="eo-panel-header">
        <span class="eo-panel-title">输出结果</span>
        <el-button text size="small" @click="copyContent(formattedResult)">复制</el-button>
      </div>
      <pre class="eo-content eo-content-result">{{ formattedResult }}</pre>
    </div>

    <!-- Stdout panel -->
    <div v-if="hasStdout" class="eo-panel">
      <div class="eo-panel-header">
        <span class="eo-panel-title">stdout</span>
        <el-button text size="small" @click="copyContent(record.stdout || '')">复制</el-button>
      </div>
      <pre class="eo-content eo-content-stdout">{{ record.stdout }}</pre>
    </div>

    <!-- Stderr panel -->
    <div v-if="hasStderr" class="eo-panel">
      <div class="eo-panel-header">
        <span class="eo-panel-title">stderr</span>
        <el-button text size="small" @click="copyContent(record.stderr || '')">复制</el-button>
      </div>
      <pre class="eo-content eo-content-stderr">{{ record.stderr }}</pre>
    </div>

    <!-- Error panel -->
    <div v-if="record.error" class="eo-panel">
      <div class="eo-panel-header">
        <span class="eo-panel-title">错误信息</span>
        <el-button text size="small" @click="copyContent(record.error)">复制</el-button>
      </div>
      <pre class="eo-content eo-content-error">{{ record.error }}</pre>
    </div>

    <!-- Empty state -->
    <div v-if="!hasResult && !hasStdout && !hasStderr && !record.error" class="eo-empty">
      （无输出内容）
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { NodeExecutionRecord } from '@/types/workflow'

const props = defineProps<{
  record: NodeExecutionRecord
}>()

const hasResult = computed(() => {
  const r = props.record.result
  return r != null && r !== '' && r !== 'null'
})
const hasStdout = computed(() => {
  const s = props.record.stdout
  return s != null && s !== ''
})
const hasStderr = computed(() => {
  const s = props.record.stderr
  return s != null && s !== ''
})

const formattedResult = computed(() => {
  const raw = props.record.result
  if (raw == null || raw === '') return ''
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return JSON.stringify(parsed, null, 2)
  } catch {
    return String(raw)
  }
})

function copyContent(text: string) {
  navigator.clipboard.writeText(text).then(
    () => ElMessage.success('已复制到剪贴板'),
    () => ElMessage.error('复制失败'),
  )
}
</script>

<style scoped>
.execution-output {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.eo-panel {
  border: 1px solid var(--el-border-color, #e4e7ed);
  border-radius: 6px;
  overflow: hidden;
}

.eo-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: var(--el-fill-color-light, #f5f7fa);
  border-bottom: 1px solid var(--el-border-color, #e4e7ed);
}

.eo-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.eo-content {
  margin: 0;
  padding: 10px 12px;
  font-family: 'Cascadia Code', 'Fira Code', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-wrap: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.eo-content-result {
  background: var(--el-fill-color-lighter, #fafafa);
  color: var(--el-text-color-primary);
}

.eo-content-stdout {
  background: #1e1e1e;
  color: #4ec9b0;
}

.eo-content-stderr {
  background: #1e1e1e;
  color: #f14c4c;
}

.eo-content-error {
  background: var(--el-color-danger-light-9, #fef0f0);
  color: var(--el-color-danger, #f56c6c);
}

.eo-empty {
  text-align: center;
  color: var(--el-text-color-placeholder, #c0c4cc);
  font-size: 13px;
  padding: 12px 0;
}
</style>
