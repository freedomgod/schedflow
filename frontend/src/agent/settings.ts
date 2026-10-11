import type { AgentConfig, AgentConfigUpdate, AgentProvider, AgentProtocol } from './types'
import { computed, ref, watch } from 'vue'

export type AgentSettingsDraft = Omit<AgentConfigUpdate, 'enabled'> & { api_key: string; region: string; workspace_id: string }
export function providerProtocols(provider: string): AgentProtocol[] {
  if (provider === 'openai') return ['responses', 'chat_completions']
  if (provider === 'custom') return ['chat_completions', 'responses', 'anthropic_messages']
  return provider === 'claude' ? ['anthropic_messages'] : ['chat_completions']
}
export function settingsDraft(config?: AgentConfig | null): AgentSettingsDraft {
  return {
    provider: config?.provider || 'openai', protocol: config?.protocol || 'responses',
    base_url: config?.base_url || 'https://api.openai.com/v1', model: config?.model || '',
    region: config?.region || '', workspace_id: config?.workspace_id || '', api_key: '', clear_api_key: false,
    max_steps: config?.max_steps ?? 8, timeout: config?.timeout ?? 60, max_tokens: config?.max_tokens ?? 4096,
    allow_code_generation: config?.allow_code_generation ?? false, retention_days: config?.retention_days ?? 30,
  }
}
const normalizedRoot = (root?: string) => (root || '').trim().replace(/\/+$/, '')
export function credentialMatches(draft: AgentSettingsDraft, saved?: AgentConfig | null): boolean {
  return !!saved && draft.provider === saved.provider && draft.protocol === saved.protocol
    && normalizedRoot(draft.base_url) === normalizedRoot(saved.base_url)
    && draft.workspace_id.trim() === (saved.workspace_id || '').trim()
}
export function chooseProvider(draft: AgentSettingsDraft, provider: AgentProvider): AgentSettingsDraft {
  const region = provider.regions?.[0]?.id || ''
  return { ...draft, provider: provider.id, protocol: provider.protocol, model: provider.models[0] || '',
    region, workspace_id: '', base_url: regionBaseUrl(provider, region, ''), api_key: '', clear_api_key: false }
}
export function regionBaseUrl(provider: AgentProvider, region: string, workspace: string): string {
  const template = provider.regions?.find(item => item.id === region)?.base_url || provider.base_url
  return workspace.trim() ? template.replace(/\{WorkspaceId\}/g, () => workspace.trim()) : template
}
export function settingsPayload(draft: AgentSettingsDraft, saved?: AgentConfig | null): AgentConfigUpdate {
  const { api_key, ...rest } = draft
  return { ...rest, base_url: normalizedRoot(draft.base_url), model: draft.model.trim(),
    workspace_id: draft.workspace_id.trim(), enabled: !draft.clear_api_key && !!saved?.enabled,
    ...(!draft.clear_api_key && api_key.trim() ? { api_key: api_key.trim() } : {}) }
}
export function validateSettings(draft: AgentSettingsDraft, provider?: AgentProvider, saved?: AgentConfig | null, intent: 'save' | 'test' = 'save'): string {
  if (!draft.model.trim() && (intent === 'test' || (saved?.enabled && !draft.clear_api_key))) return '请输入模型名称。'
  if (draft.base_url.includes('{') || draft.base_url.includes('}')) return '请填写工作空间 ID，或手动输入完整的 API 根地址。'
  try {
    const url = new URL(draft.base_url.trim())
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) return 'API 根地址需为 HTTP(S) 地址，不能包含凭据、查询参数或片段。'
  } catch { return '请输入完整的 API 根地址。' }
  const hasSavedKey = !!saved?.has_api_key && credentialMatches(draft, saved)
  if (!draft.clear_api_key && !draft.api_key.trim() && (!hasSavedKey && (saved?.has_api_key || provider?.requires_api_key))) {
    return saved?.has_api_key ? '连接信息已变更，请输入此连接的新密钥，或明确勾选清除密钥。' : '请输入 API 密钥，或勾选清除密钥以保存停用配置。'
  }
  if (!Number.isInteger(draft.max_steps) || draft.max_steps < 1 || draft.max_steps > 32
    || !Number.isFinite(draft.timeout) || draft.timeout <= 0 || draft.timeout > 600
    || !Number.isInteger(draft.max_tokens) || draft.max_tokens < 64 || draft.max_tokens > 32768
    || !Number.isInteger(draft.retention_days) || draft.retention_days < 1 || draft.retention_days > 3650) return '高级设置超出允许范围，请检查各字段。'
  return ''
}

interface SettingsApi {
  settings(): Promise<AgentConfig>
  providers(): Promise<{ providers: AgentProvider[] }>
  saveSettings(config: AgentConfigUpdate): Promise<AgentConfig>
  testSettings(config: AgentConfigUpdate): Promise<{ success: boolean; message: string }>
  refreshConfig(): Promise<AgentConfig | null>
}

export function useSettingsEditor(api: SettingsApi) {
  const draft = ref(settingsDraft())
  const saved = ref<AgentConfig | null>(null)
  const providers = ref<AgentProvider[]>([])
  const loading = ref(false); const saving = ref(false); const testing = ref(false)
  const error = ref(''); const notice = ref('')
  const testResult = ref<{ success: boolean; message: string } | null>(null)
  let baseline = ''; let revision = 0; let applying = false
  const provider = computed(() => providers.value.find(item => item.id === draft.value.provider))
  const dirty = computed(() => !!saved.value && JSON.stringify(draft.value) !== baseline)
  const validation = computed(() => validateSettings(draft.value, provider.value, saved.value))
  const busy = computed(() => loading.value || saving.value || testing.value)
  watch(draft, () => { ++revision; testResult.value = null; error.value = ''; notice.value = '' }, { deep: true, flush: 'sync' })
  watch(() => [draft.value.provider, draft.value.protocol, draft.value.base_url, draft.value.workspace_id], () => {
    if (!applying) draft.value.api_key = ''
  }, { flush: 'sync' })
  function apply(config: AgentConfig) {
    applying = true
    saved.value = { ...config }; draft.value = settingsDraft(config)
    baseline = JSON.stringify(draft.value)
    applying = false
  }
  function report(cause: unknown) { error.value = cause instanceof Error ? cause.message : String(cause) }
  async function load() {
    if (busy.value) return
    loading.value = true; error.value = ''
    try { const [config, profiles] = await Promise.all([api.settings(), api.providers()]); providers.value = profiles.providers; apply(config) }
    catch (cause) { report(cause) } finally { loading.value = false }
  }
  function selectProvider(id: string) {
    const selected = providers.value.find(item => item.id === id)
    if (selected) draft.value = chooseProvider(draft.value, selected)
  }
  function selectRegion(region: string) {
    if (!provider.value) return
    draft.value.region = region
    draft.value.base_url = regionBaseUrl(provider.value, region, draft.value.workspace_id)
  }
  function setWorkspace(workspace: string) {
    const profile = provider.value
    const generated = profile && draft.value.base_url === regionBaseUrl(profile, draft.value.region, draft.value.workspace_id)
    draft.value.workspace_id = workspace
    if (profile && generated) draft.value.base_url = regionBaseUrl(profile, draft.value.region, workspace)
  }
  async function test() {
    if (busy.value || !saved.value) return
    const testValidation = validateSettings(draft.value, provider.value, saved.value, 'test')
    if (testValidation) { error.value = testValidation; return }
    if (draft.value.clear_api_key) { error.value = '清除密钥的配置无法进行连接测试，请先输入用于测试的密钥。'; return }
    testing.value = true; error.value = ''; testResult.value = null
    const testedRevision = revision
    try { const result = await api.testSettings(settingsPayload(draft.value, saved.value)); if (revision === testedRevision) testResult.value = result }
    catch (cause) { if (revision === testedRevision) report(cause) } finally { testing.value = false }
  }
  async function save() {
    if (busy.value || !saved.value) return
    if (validation.value) { error.value = validation.value; return }
    saving.value = true; error.value = ''; notice.value = ''
    try {
      const config = await api.saveSettings(settingsPayload(draft.value, saved.value))
      apply(config)
      notice.value = config.enabled ? '配置已保存，Agent 正在使用新的连接。' : '配置已保存。准备好后，可打开上方开关开始使用。'
      await api.refreshConfig()
    } catch (cause) { report(cause) } finally { saving.value = false }
  }
  return { draft, saved, providers, provider, dirty, validation, busy, loading, saving, testing, error, notice, testResult, load, save, test, selectProvider, selectRegion, setWorkspace }
}
