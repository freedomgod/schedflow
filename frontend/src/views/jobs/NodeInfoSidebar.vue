<template>
  <transition name="panel-slide">
    <div v-if="visible" class="node-info-sidebar">
      <div class="panel-header">
        <span class="panel-title">{{ nodeData?.name || '节点详情' }}</span>
        <el-button :icon="Close" text size="small" @click="emit('close')" />
      </div>
      <div class="panel-body">
        <template v-if="nodeData">
          <el-descriptions :column="1" border class="info-descriptions">
            <el-descriptions-item label="Node ID">
              <code class="mono-text">{{ nodeId }}</code>
            </el-descriptions-item>
            <el-descriptions-item label="名称">
              {{ nodeData.name }}
            </el-descriptions-item>
            <el-descriptions-item v-if="nodeData.description" label="描述">
              {{ nodeData.description }}
            </el-descriptions-item>
            <el-descriptions-item label="任务类型">
              <el-tag size="small">{{ nodeData.type || 'python_callable' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item v-if="nodeData.type === 'python_callable' || !nodeData.type" label="函数引用">
              <code class="mono-text">{{ nodeData.func_ref || '-' }}</code>
            </el-descriptions-item>
            <el-descriptions-item v-if="nodeData.type === 'python'" label="脚本路径">
              <code class="mono-text">{{ nodeData.script_path || '-' }}</code>
            </el-descriptions-item>
            <el-descriptions-item v-if="nodeData.type === 'python_script'" label="代码片段">
              <div class="code-block"><code>{{ nodeData.script || '-' }}</code></div>
            </el-descriptions-item>
            <el-descriptions-item v-if="nodeData.type === 'bash'" label="命令">
              <div class="code-block"><code>{{ nodeData.command || '-' }}</code></div>
            </el-descriptions-item>
          </el-descriptions>

          <div v-if="nodeData.kwargs && nodeData.kwargs.length > 0" class="kwargs-section">
            <h4 class="section-title">参数 (kwargs)</h4>
            <el-table :data="nodeData.kwargs" size="small" border class="kwargs-table">
              <el-table-column prop="key" label="Key" width="140" />
              <el-table-column prop="value" label="Value" />
              <el-table-column prop="type" label="Type" width="90">
                <template #default="{ row }">
                  <el-tag size="small" :type="kwargTypeTag(row.type)">{{ row.type }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <el-descriptions :column="1" border class="info-descriptions">
            <el-descriptions-item v-if="nodeData.done_callback_ref" label="完成回调">
              <code class="mono-text">{{ nodeData.done_callback_ref }}</code>
            </el-descriptions-item>
            <el-descriptions-item v-if="nodeData.stop_max_attempt_number != null" label="最大重试次数">
              {{ nodeData.stop_max_attempt_number }}
            </el-descriptions-item>
          </el-descriptions>
        </template>
        <el-empty v-else description="选择节点查看详情" />
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { Close } from '@element-plus/icons-vue'
import type { TaskNodeProperties } from '@/types/workflow'

defineProps<{
  visible: boolean
  nodeId: string | null
  nodeData: TaskNodeProperties | null
}>()

const emit = defineEmits<{
  close: []
}>()

function kwargTypeTag(type: string): string {
  switch (type) {
    case 'number': return 'warning'
    case 'boolean': return 'success'
    default: return ''
  }
}
</script>

<style scoped>
.node-info-sidebar {
  position: absolute;
  top: 0;
  right: 0;
  width: 360px;
  height: 100%;
  background: var(--el-bg-color, #fff);
  border-left: 1px solid var(--el-border-color);
  box-shadow: -4px 0 12px rgba(0, 0, 0, 0.08);
  z-index: 100;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.mono-text {
  font-family: 'Cascadia Code', 'Fira Code', 'Courier New', monospace;
  font-size: 13px;
  color: var(--el-text-color-primary);
  word-break: break-all;
}

.info-descriptions {
  margin-bottom: 16px;
}

.info-descriptions:last-child {
  margin-bottom: 0;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin: 0 0 8px 0;
}

.kwargs-section {
  margin-bottom: 16px;
}

.kwargs-table {
  width: 100%;
}

.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: transform 0.3s ease;
}

.panel-slide-enter-from,
.panel-slide-leave-to {
  transform: translateX(100%);
}

.code-block {
  background: #1e1e1e;
  color: #4ec9b0;
  padding: 8px 12px;
  border-radius: 4px;
  font-family: 'Cascadia Code', 'Fira Code', 'Courier New', monospace;
  font-size: 12px;
  max-height: 120px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

:deep(.el-descriptions__label) {
  min-width: 90px;
  white-space: nowrap;
}
</style>
