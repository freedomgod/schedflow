<template>
  <section class="agent-settings glass-card" aria-labelledby="agent-settings-title" :aria-busy="loading">
    <header class="settings-heading">
      <div>
        <h3 id="agent-settings-title" class="section-title">AI Agent</h3>
        <p class="section-desc">连接模型服务，用自然语言查询、创建和管理调度工作流。</p>
      </div>
      <div class="enabled-control">
        <span id="agent-enabled-label">{{ effectiveConfig?.enabled ? '已启用' : '已停用' }}</span>
        <el-switch
          :model-value="!!effectiveConfig?.enabled"
          :loading="store.configPending"
          :disabled="busy || store.configPending || dirty || !effectiveConfig || (!effectiveConfig.enabled && !effectiveConfig.configured)"
          aria-describedby="agent-enabled-label"
          aria-label="启用 AI Agent"
          @change="toggleEnabled"
        />
      </div>
    </header>

    <p class="switch-hint field-hint" role="status">
      {{ dirty ? '表单有未保存的修改。请先保存，再切换启用状态。' : effectiveConfig?.configured ? '开关立即应用于已保存配置。关闭后停止接收新请求，已有会话仍可查看。' : '选择服务商并保存连接信息后，即可启用 Agent。' }}
    </p>
    <div v-if="store.configError" class="form-feedback danger" role="alert">{{ store.configError }}</div>
    <p v-if="loading" class="loading-message" role="status">正在读取模型配置…</p>
    <div v-if="!loading && !saved" class="load-error">
      <p v-if="error" class="form-feedback danger" role="alert">{{ error }}</p>
      <el-button @click="loadSettings">重新加载</el-button>
    </div>

    <template v-if="saved">
      <div class="config-summary">
        <span class="status-tag" :class="{ configured: effectiveConfig?.configured }">{{ effectiveConfig?.configured ? '连接信息已配置' : '等待配置' }}</span>
        <span class="field-hint">{{ saved.source === 'environment' ? '当前来自环境变量；保存后使用系统设置。' : '配置保存在服务端。' }}</span>
      </div>
      <el-form label-position="top" :disabled="busy || store.configPending" @submit.prevent="save">
        <div class="form-grid">
          <el-form-item label="模型服务商" label-for="agent-provider">
            <el-select id="agent-provider" :model-value="draft.provider" @change="selectProvider" style="width: 100%">
              <el-option v-for="profile in providers" :key="profile.id" :label="profile.label" :value="profile.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="模型名称" label-for="agent-model">
            <el-select id="agent-model" v-model="draft.model" filterable allow-create default-first-option placeholder="选择或输入模型名称" style="width: 100%">
              <el-option v-for="model in provider?.models || []" :key="model" :label="model" :value="model" />
            </el-select>
            <span class="field-hint">建议列表可直接选用，也可以输入服务商支持的其他模型。</span>
          </el-form-item>
          <el-form-item v-if="provider?.regions?.length" label="服务区域" label-for="agent-region">
            <el-select id="agent-region" :model-value="draft.region" @change="selectRegion" style="width: 100%">
              <el-option v-for="region in provider.regions" :key="region.id" :label="region.label" :value="region.id" />
            </el-select>
            <span class="field-hint">区域决定默认 API 地址，请使用该区域对应的 API Key。</span>
          </el-form-item>
          <el-form-item v-if="['qwen', 'claude'].includes(draft.provider)" :label="draft.provider === 'claude' ? '工作空间 ID（可选）' : '工作空间 ID（Workspace ID）'" label-for="agent-workspace">
            <el-input id="agent-workspace" :model-value="draft.workspace_id" @update:model-value="setWorkspace" :placeholder="draft.provider === 'claude' ? '可留空，或输入 Anthropic 工作空间 ID' : '输入百炼工作空间 ID'" />
            <span class="field-hint">{{ draft.provider === 'claude' ? '填写后，请求将使用此 Anthropic 工作空间；留空使用账户默认工作空间。' : '自动补全区域地址中的工作空间；使用自定义 API 根地址时可留空。' }}</span>
          </el-form-item>
          <el-form-item class="full-width" label="API 根地址" label-for="agent-base-url">
            <el-input id="agent-base-url" v-model="draft.base_url" placeholder="https://api.example.com/v1" autocomplete="off" />
            <span class="field-hint">已按服务商填好，可以修改。填写 API 根地址，无需添加具体请求路径。</span>
          </el-form-item>
          <el-form-item class="full-width" label="API Key" label-for="agent-api-key">
            <el-input id="agent-api-key" v-model="draft.api_key" type="password" show-password autocomplete="new-password" :disabled="draft.clear_api_key" :placeholder="savedKeyMatches ? '已保存密钥；留空保留，输入新值替换' : '输入此服务商的 API Key'" />
            <span class="field-hint">{{ savedKeyMatches ? '此连接已保存密钥。原值不会返回浏览器。' : saved.has_api_key ? '连接信息已变更，请输入新密钥，或明确选择清除密钥。' : '尚未保存密钥。' }}</span>
            <el-checkbox v-model="draft.clear_api_key" class="clear-key">清除已保存密钥并停用 Agent</el-checkbox>
          </el-form-item>
          <el-form-item class="full-width" label="连接协议" label-for="agent-protocol">
            <el-select id="agent-protocol" v-model="draft.protocol" style="width: 100%">
              <el-option v-for="protocol in protocols" :key="protocol" :label="protocolLabels[protocol]" :value="protocol" />
            </el-select>
            <span class="field-hint">已为服务商选择默认协议。使用网关或自定义服务时，可按接口兼容性调整。</span>
          </el-form-item>
        </div>

        <div class="code-generation-option">
          <el-checkbox v-model="draft.allow_code_generation">允许 Agent 生成任务代码</el-checkbox>
          <p class="field-hint">默认关闭。开启后，Agent 可生成 Python 或 Shell 任务候选；创建、修改和执行仍需要你检查并确认。</p>
        </div>

        <el-collapse v-model="advancedOpen" class="advanced-settings">
          <el-collapse-item title="高级设置 · 执行预算与保留期限" name="budgets">
            <div class="form-grid budgets">
              <el-form-item label="最大模型步骤（1–32）" label-for="agent-max-steps"><el-input-number id="agent-max-steps" v-model="draft.max_steps" :min="1" :max="32" :step="1" :precision="0" /></el-form-item>
              <el-form-item label="回答超时（秒，最多 600）" label-for="agent-timeout"><el-input-number id="agent-timeout" v-model="draft.timeout" :min="1" :max="600" /></el-form-item>
              <el-form-item label="最大输出 Token（64–32768）" label-for="agent-max-tokens"><el-input-number id="agent-max-tokens" v-model="draft.max_tokens" :min="64" :max="32768" :step="256" :precision="0" /></el-form-item>
              <el-form-item label="历史保留天数（1–3650）" label-for="agent-retention"><el-input-number id="agent-retention" v-model="draft.retention_days" :min="1" :max="3650" :precision="0" /></el-form-item>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-form>

      <div class="settings-footer">
        <div class="feedback-area" aria-live="polite">
          <p v-if="error" class="form-feedback danger" role="alert">{{ error }}</p>
          <p v-else-if="testResult" class="form-feedback" :class="testResult.success ? 'success' : 'danger'" :role="testResult.success ? 'status' : 'alert'">{{ testResult.success ? '连接测试通过：' : '连接测试失败：' }}{{ testResult.message }}</p>
          <p v-else-if="notice" class="form-feedback success" role="status">{{ notice }}</p>
          <p v-else class="field-hint">测试使用当前表单检查连接与工具调用，不保存配置，不创建或执行工作流。</p>
        </div>
        <div class="settings-actions">
          <el-button :loading="testing" :disabled="loading || saving || store.configPending || draft.clear_api_key" @click="test">测试连接</el-button>
          <el-button type="primary" :loading="saving" :disabled="loading || testing || store.configPending" @click="save">保存配置</el-button>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { agentApi } from '@/agent/api'
import { credentialMatches, providerProtocols, useSettingsEditor } from '@/agent/settings'
import { useAgentStore } from '@/stores/agent'

const store = useAgentStore()
const { draft, saved, providers, provider, dirty, busy, loading, saving, testing, error, notice, testResult, load, save, test, selectProvider, selectRegion, setWorkspace } = useSettingsEditor({
  ...agentApi,
  saveSettings: async config => { const result = await agentApi.saveSettings(config); store.applySavedConfig(result); return result },
  refreshConfig: store.refreshConfig,
})
const advancedOpen = ref<string[]>([])
const protocols = computed(() => providerProtocols(draft.value.provider))
const protocolLabels = { responses: 'Responses API', chat_completions: 'Chat Completions（OpenAI 兼容）', anthropic_messages: 'Anthropic Messages' }
const effectiveConfig = computed(() => store.config || saved.value)
const savedKeyMatches = computed(() => !!saved.value?.has_api_key && credentialMatches(draft.value, saved.value))
async function loadSettings() { await load(); if (saved.value) await store.refreshConfig() }
async function toggleEnabled(value: string | number | boolean) { await store.setEnabled(!!value) }
watch(() => store.config, value => { if (saved.value && value) saved.value = { ...saved.value, enabled: value.enabled, configured: value.configured, has_api_key: value.has_api_key ?? saved.value.has_api_key } })
onMounted(loadSettings)
</script>

<style scoped>
.agent-settings { padding: var(--space-xl); }
.settings-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-lg); }
.settings-heading .section-desc { margin-bottom: 0; max-width: 540px; }
.enabled-control { display: flex; align-items: center; gap: var(--space-sm); white-space: nowrap; min-height: 44px; font-size: 13px; color: var(--text-secondary); }
.switch-hint { display: block; margin: var(--space-md) 0; line-height: 1.7; }
.config-summary { display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-sm); padding-block: var(--space-md); border-top: 1px solid var(--border-subtle); margin-bottom: var(--space-md); }
.status-tag { font-size: 12px; padding: 4px 9px; border-radius: var(--radius-sm); color: var(--text-secondary); background: var(--bg-surface); border: 1px solid var(--border-default); }
.status-tag.configured { color: var(--color-success); background: var(--color-success-soft); }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 var(--space-lg); }
.full-width { grid-column: 1 / -1; }
.field-hint { font-size: 12px; line-height: 1.7; color: var(--text-secondary); }
:deep(.el-form-item__content) > .field-hint { display: block; width: 100%; margin-top: 7px; }
:deep(.el-form-item__label) { font-weight: 500; color: var(--text-primary); }
.clear-key { margin-top: 6px; }
.code-generation-option { padding: var(--space-md); border: 1px solid var(--border-default); border-radius: var(--radius-md); background: var(--bg-surface); margin-block: var(--space-sm) var(--space-lg); }
.code-generation-option p { margin-top: 4px; }
.advanced-settings { --el-collapse-border-color: var(--border-subtle); --el-collapse-header-bg-color: transparent; --el-collapse-content-bg-color: transparent; --el-collapse-header-text-color: var(--text-primary); --el-collapse-content-text-color: var(--text-secondary); }
.budgets { padding-top: var(--space-md); }
.budgets :deep(.el-input-number) { width: 100%; }
.settings-footer { border-top: 1px solid var(--border-subtle); margin-top: var(--space-lg); padding-top: var(--space-lg); display: flex; flex-direction: column; gap: var(--space-md); }
.settings-actions { display: flex; justify-content: flex-end; gap: var(--space-sm); }
.settings-actions :deep(.el-button) { min-height: 44px; margin-left: 0; }
.form-feedback { padding: 10px 12px; border-radius: var(--radius-sm); line-height: 1.7; font-size: 13px; overflow-wrap: anywhere; }
.form-feedback.danger { color: var(--color-danger); background: var(--color-danger-soft); }
.form-feedback.success { color: var(--color-success); background: var(--color-success-soft); }
.loading-message { color: var(--text-secondary); padding-block: var(--space-lg); font-size: 13px; }
.load-error { display: grid; gap: var(--space-md); justify-items: start; }
@media (max-width: 600px) {
  .agent-settings { padding: 20px 16px; }
  .settings-heading { flex-wrap: wrap; gap: var(--space-sm); }
  .form-grid { grid-template-columns: minmax(0, 1fr); }
  .settings-actions { flex-wrap: wrap; }
  .settings-actions :deep(.el-button) { flex: 1; }
  :deep(.el-checkbox) { height: auto; min-height: 44px; white-space: normal; }
  :deep(.el-checkbox__label) { white-space: normal; }
}
</style>
