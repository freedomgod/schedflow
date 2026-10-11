import { describe, expect, it, vi } from 'vitest'
import { useSettingsEditor } from '../settings'
import type { AgentConfig } from '../types'
const config: AgentConfig = { enabled: false, configured: true, provider: 'openai', protocol: 'responses', base_url: 'https://api.openai.com/v1', model: 'saved', has_api_key: true }
const providers = [{ id: 'openai', label: 'OpenAI', protocol: 'responses' as const, base_url: 'https://api.openai.com/v1', models: ['suggested'], requires_api_key: true }, { id: 'deepseek', label: 'DeepSeek', protocol: 'chat_completions' as const, base_url: 'https://api.deepseek.com', models: ['deepseek-chat'], requires_api_key: true }]
function dependencies() {
  return { settings: vi.fn(async () => config), providers: vi.fn(async () => ({ providers })), saveSettings: vi.fn(async () => config), testSettings: vi.fn(async () => ({ success: true, message: '连接与工具调用成功' })), refreshConfig: vi.fn(async () => config) }
}

describe('Agent settings editor lifecycle', () => {
  it('loads profiles and config and invalidates tested success immediately on edits', async () => {
    const deps = dependencies(); const editor = useSettingsEditor(deps)
    await editor.load(); await editor.test()
    expect(editor.testResult.value?.success).toBe(true)
    expect(editor.dirty.value).toBe(false)
    editor.draft.value.model = 'edited'
    expect(editor.testResult.value).toBe(null)
    expect(editor.dirty.value).toBe(true)
  })
  it('discards a late test result when its settings have changed', async () => {
    const deps = dependencies(); let complete!: (value: { success: boolean; message: string }) => void
    deps.testSettings.mockReturnValue(new Promise(resolve => { complete = resolve }))
    const editor = useSettingsEditor(deps); await editor.load()
    const pending = editor.test(); editor.draft.value.model = 'edited'
    complete({ success: true, message: '旧配置连接成功' }); await pending
    expect(editor.testResult.value).toBe(null)
    expect(editor.testing.value).toBe(false)
  })
  it('clears the typed key as soon as provider or endpoint changes', async () => {
    const editor = useSettingsEditor(dependencies()); await editor.load()
    editor.draft.value.api_key = 'typed'; editor.draft.value.base_url = 'https://other.example/v1'
    expect(editor.draft.value.api_key).toBe('')
    editor.draft.value.api_key = 'typed-again'; editor.selectProvider('deepseek')
    expect(editor.draft.value.api_key).toBe('')
    expect(editor.draft.value.protocol).toBe('chat_completions')
    expect(editor.draft.value.model).toBe('deepseek-chat')
  })
  it('keeps separate testing and saving progress and does not save during a test', async () => {
    const deps = dependencies(); let complete!: (value: { success: boolean; message: string }) => void
    deps.testSettings.mockReturnValue(new Promise(resolve => { complete = resolve }))
    const editor = useSettingsEditor(deps); await editor.load()
    const pending = editor.test()
    expect(editor.testing.value).toBe(true); expect(editor.saving.value).toBe(false)
    await editor.save(); expect(deps.saveSettings).not.toHaveBeenCalled()
    complete({ success: true, message: '成功' }); await pending
  })
  it('clears the typed key after saving and refreshes shared chat config', async () => {
    const deps = dependencies(); const editor = useSettingsEditor(deps); await editor.load()
    editor.draft.value.api_key = 'new-secret'; await editor.save()
    expect(deps.saveSettings.mock.calls[0][0]).toMatchObject({ api_key: 'new-secret' })
    expect(editor.draft.value.api_key).toBe('')
    expect(editor.dirty.value).toBe(false)
    expect(deps.refreshConfig).toHaveBeenCalledOnce()
  })
  it('keeps unsaved edits and reports save failures next to the form', async () => {
    const deps = dependencies(); deps.saveSettings.mockRejectedValue(new Error('模型服务不可用'))
    const editor = useSettingsEditor(deps); await editor.load(); editor.draft.value.model = 'edited'; await editor.save()
    expect(editor.error.value).toBe('模型服务不可用')
    expect(editor.draft.value.model).toBe('edited')
    expect(editor.saving.value).toBe(false)
    expect(deps.refreshConfig).not.toHaveBeenCalled()
  })
  it('shows connection-test rejection without saving or enabling settings', async () => {
    const deps = dependencies(); deps.testSettings.mockResolvedValue({ success: false, message: '工具调用协议不兼容' })
    const editor = useSettingsEditor(deps); await editor.load(); await editor.test()
    expect(editor.testResult.value).toEqual({ success: false, message: '工具调用协议不兼容' })
    expect(deps.saveSettings).not.toHaveBeenCalled()
    expect(editor.saved.value?.enabled).toBe(false)
  })
})
