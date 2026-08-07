<template>
  <div class="execution-list">
    <h4 class="execution-list-title">执行记录</h4>
    <div v-if="logs.length === 0" class="empty-hint">暂无执行记录</div>
    <div
      v-for="(log, index) in logs"
      :key="log.flow_log_id"
      class="execution-item"
      :class="{ 'is-active': selectedIndex === index }"
      @click="$emit('select', index)"
    >
      <div class="execution-time">
        {{ log.start_time ? new Date(log.start_time).toLocaleString() : '-' }}
      </div>
      <div class="execution-id">{{ log.flow_log_id }}</div>
      <div class="execution-summary">
        <span class="summary-item success">{{ succeededCount(log) }} 成功</span>
        <span class="summary-item failed">{{ failedCount(log) }} 失败</span>
        <span class="summary-item skipped">{{ skippedCount(log) }} 跳过</span>
      </div>
      <div v-if="log.duration != null" class="execution-duration">
        耗时: {{ log.duration.toFixed(1) }}s
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ExecutionLog } from '@/types/workflow'

defineProps<{
  logs: ExecutionLog[]
  selectedIndex: number
}>()

defineEmits<{
  select: [index: number]
}>()

function succeededCount(log: ExecutionLog): number {
  if (!log.node_records) return 0
  return Object.values(log.node_records).filter(r => r.status === 'SUCCEEDED').length
}

function failedCount(log: ExecutionLog): number {
  if (!log.node_records) return 0
  return Object.values(log.node_records).filter(r => r.status === 'FAILED').length
}

function skippedCount(log: ExecutionLog): number {
  if (!log.node_records) return 0
  return Object.values(log.node_records).filter(r => r.status === 'SKIPPED').length
}
</script>

<style scoped>
.execution-list {
  height: 100%;
  overflow-y: auto;
  padding: 12px;
  background: var(--el-fill-color-lighter, #fafafa);
  border-right: 1px solid var(--el-border-color, #e4e7ed);
}

.execution-list-title {
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.empty-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-align: center;
  padding: 20px 0;
}

.execution-item {
  padding: 10px 12px;
  margin-bottom: 6px;
  background: var(--el-bg-color, #fff);
  border: 1px solid var(--el-border-color, #e4e7ed);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.execution-item:hover {
  border-color: var(--el-color-primary, #409eff);
}

.execution-item.is-active {
  border-color: var(--el-color-primary, #409eff);
  background: var(--el-color-primary-light-9, #ecf5ff);
}

.execution-time {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.execution-id {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

.execution-summary {
  margin-top: 4px;
  font-size: 12px;
}

.summary-item {
  margin-right: 8px;
}

.summary-item.success {
  color: var(--el-color-success, #67c23a);
}

.summary-item.failed {
  color: var(--el-color-danger, #f56c6c);
}

.summary-item.skipped {
  color: var(--el-color-warning, #e6a23c);
}

.execution-duration {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
