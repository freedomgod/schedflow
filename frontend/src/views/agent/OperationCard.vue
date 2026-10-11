<template>
  <section class="operation-card" :class="`operation-${operation?.status || 'loading'}`" aria-live="polite">
    <div class="operation-header"><span class="operation-dot" /><strong>{{ operation ? receiptLabel : '正在读取执行回执' }}</strong><button class="action-btn" :disabled="refreshing" @click="refresh">刷新</button></div>
    <p v-if="operation?.status === 'accepted'" class="field-hint">任务已进入调度器，等待执行结果。</p>
    <p v-if="operation?.status === 'unknown'" class="field-hint">提交结果尚未确定，请刷新回执核实后再操作。</p>
    <p v-if="operation?.error" class="operation-error">{{ operation.error }}</p>
    <dl v-if="operation" class="operation-meta"><div><dt>操作</dt><dd>{{ actionNames[operation.action] || operation.action }}</dd></div><div v-if="operation.job_id"><dt>工作流</dt><dd>{{ operation.job_id }}</dd></div><div v-if="operation.execution_id"><dt>执行 ID</dt><dd>{{ operation.execution_id }}</dd></div></dl>
    <div class="operation-links"><router-link v-if="operation?.job_id" :to="`/jobs/${encodeURIComponent(operation.job_id)}`">查看工作流</router-link><router-link v-if="operation?.job_id && operation?.execution_id" :to="{ path: '/logs', query: { jobId: operation.job_id, executionId: operation.execution_id } }">查看执行日志 ↗</router-link></div>
    <div v-if="execution" class="execution-summary"><div class="execution-counts"><span><strong>{{ execution.counts.total }}</strong> 节点</span><span class="node-succeeded">{{ execution.counts.succeeded }} 成功</span><span v-if="execution.counts.failed" class="node-failed">{{ execution.counts.failed }} 失败</span><span v-if="execution.counts.skipped" class="node-skipped">{{ execution.counts.skipped }} 跳过</span><span v-if="execution.duration !== undefined">耗时 {{ execution.duration.toFixed(2) }} s</span></div><details v-for="node in execution.nodes" :key="node.id" class="execution-node" :open="node.status === 'failed'"><summary><span>{{ node.id }}</span><span :class="`node-${node.status}`">{{ nodeStatusLabel(node.status) }}</span><small v-if="node.duration !== undefined">{{ node.duration.toFixed(2) }} s</small></summary><p v-if="node.error" class="operation-error">{{ node.error }}</p><p v-if="node.skipReason" class="field-hint">{{ node.skipReason }}</p><div v-if="node.stdout"><label>stdout</label><pre>{{ node.stdout }}</pre></div><div v-if="node.stderr"><label>stderr</label><pre class="stderr-output">{{ node.stderr }}</pre></div><p v-if="!node.error && !node.stdout && !node.stderr && !node.skipReason" class="field-hint">该节点没有文本输出。</p></details></div>
    <details v-if="operation?.result"><summary>执行结果</summary><pre>{{ JSON.stringify(operation.result, null, 2) }}</pre></details>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAgentStore } from '@/stores/agent'
import { operationLabel } from '@/agent/protocol'
import { executionView, nodeStatusLabel } from '@/agent/execution'
const props = defineProps<{ operationId: string }>()
const store = useAgentStore(); const refreshing = ref(false)
const operation = computed(() => store.operations[props.operationId])
const execution = computed(() => operation.value?.action === 'run' ? executionView(operation.value.result) : null)
const receiptLabel = computed(() => operation.value?.status === 'succeeded' && operation.value.action !== 'run' ? '工作流配置已保存' : operationLabel(operation.value?.status || ''))
const actionNames: Record<string, string> = { create: '创建工作流', update: '更新工作流', run: '立即执行' }
async function refresh() { refreshing.value = true; try { await store.refreshOperation(props.operationId) } finally { refreshing.value = false } }
onMounted(() => { if (!operation.value) void refresh() })
</script>
<style scoped>
.operation-card { margin: 12px 0; padding: 16px; border: 1px solid var(--border-default); border-radius: var(--radius-md); background: var(--bg-surface); }
.operation-header { display: flex; align-items: center; gap: 8px; }.operation-header strong { flex: 1; font-size: 13px; }
.operation-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-primary); }.operation-succeeded .operation-dot { background: var(--color-success); }.operation-failed .operation-dot { background: var(--color-danger); }.operation-unknown .operation-dot { background: var(--color-warning); }
.operation-meta { margin-top: 12px; display: grid; gap: 6px; font-size: 12px; }.operation-meta div { display: flex; gap: 14px; }.operation-meta dt { color: var(--text-muted); min-width: 52px; }.operation-meta dd { overflow-wrap: anywhere; }
.operation-links { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 12px; font-size: 12px; }.operation-links a { color: var(--color-primary-text); }.operation-error { color: var(--color-danger); white-space: pre-wrap; margin-top: 8px; }
.execution-summary { margin-top: 16px; }.execution-counts { display: flex; flex-wrap: wrap; gap: 10px; font-size: 11px; color: var(--text-muted); }.execution-counts strong { font-size: 16px; color: var(--text-primary); }.execution-node { border-bottom: 1px solid var(--border-subtle); padding-bottom: 8px; }.execution-node summary { display: flex; align-items: center; gap: 10px; font-size: 12px; }.execution-node summary span:first-child { flex: 1; overflow-wrap: anywhere; color: var(--text-primary); }.execution-node label { display: block; font-family: monospace; font-size: 10px; color: var(--text-muted); margin-top: 10px; }.node-succeeded { color: var(--color-success); }.node-failed { color: var(--color-danger); }.node-skipped { color: var(--color-warning); }.node-running { color: var(--color-primary-text); }.stderr-output { color: var(--code-error); }summary { cursor: pointer; color: var(--text-muted); margin-top: 12px; }pre { max-height: 260px; overflow: auto; font-size: 12px; background: var(--code-bg); color: var(--code-text); padding: 12px; border-radius: var(--radius-sm); margin-top: 8px; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
