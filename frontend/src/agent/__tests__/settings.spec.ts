import { describe, expect, it } from 'vitest'
import { settingsDraft, settingsPayload, validateSettings, chooseProvider, credentialMatches, regionBaseUrl, providerProtocols } from '../settings'
import type { AgentConfig, AgentProvider } from '../types'

const saved: AgentConfig = { enabled: true, configured: true, model: 'gpt-4.1-mini', provider: 'openai', protocol: 'responses', base_url: 'https://api.openai.com/v1', has_api_key: true }
const qwen: AgentProvider = { id: 'qwen', label: '百炼', protocol: 'responses', base_url: 'https://a.example/workspaces/{WorkspaceId}/v1', models: ['qwen-plus'], requires_api_key: true, regions: [{ id: 'cn-beijing', label: '中国内地', base_url: 'https://cn.example/workspaces/{WorkspaceId}/v1' }, { id: 'ap-southeast-1', label: '新加坡', base_url: 'https://sg.example/workspaces/{WorkspaceId}/v1' }] }

describe('Agent settings draft and credentials', () => {
  it.each([
    ['openai', ['responses', 'chat_completions']],
    ['custom', ['chat_completions', 'responses', 'anthropic_messages']],
    ['claude', ['anthropic_messages']],
    ['qwen', ['chat_completions']],
    ['deepseek', ['chat_completions']],
    ['kimi', ['chat_completions']],
    ['glm', ['chat_completions']],
    ['gemini', ['chat_completions']],
  ])('only offers supported protocols for %s', (id, protocols) => {
    expect(providerProtocols(String(id))).toEqual(protocols)
  })
  it('loads public configuration without inventing a masked API key', () => {
    const draft = settingsDraft(saved)
    expect(draft.model).toBe(saved.model)
    expect(draft.api_key).toBe('')
    expect(draft.clear_api_key).toBe(false)
  })
  it('allows a disabled incomplete model to be saved but requires a model for testing', () => {
    const disabled = { ...saved, enabled: false }; const draft = settingsDraft(disabled); draft.model = ''
    expect(validateSettings(draft, undefined, disabled)).toBe('')
    expect(validateSettings(draft, undefined, disabled, 'test')).toMatch(/模型/)
    expect(validateSettings(draft, undefined, saved)).toMatch(/模型/)
  })
  it('omits blank credentials so unchanged saved identity keeps its key', () => {
    const payload = settingsPayload(settingsDraft(saved), saved)
    expect(payload).not.toHaveProperty('api_key')
    expect(payload.clear_api_key).toBe(false)
    expect(payload.enabled).toBe(true)
  })
  it('allows editable model names and sends newly typed credentials', () => {
    const draft = settingsDraft(saved); draft.model = 'custom-model'; draft.api_key = ' new-key '
    const payload = settingsPayload(draft, saved)
    expect(payload.model).toBe('custom-model')
    expect(payload.api_key).toBe('new-key')
  })
  it('normalizes trailing slashes when matching saved endpoint', () => {
    const draft = settingsDraft(saved); draft.base_url += '/'
    expect(credentialMatches(draft, saved)).toBe(true)
  })
  it.each(['provider', 'protocol', 'base_url', 'workspace_id'] as const)('prevents silently reusing a key after changing %s', key => {
    const draft = settingsDraft(saved)
    Object.assign(draft, { [key]: key === 'base_url' ? 'https://other.example/v1' : 'changed' })
    expect(credentialMatches(draft, saved)).toBe(false)
    expect(validateSettings(draft, undefined, saved)).toMatch(/密钥/)
  })
  it('clears typed secrets and selects first region and model when switching provider', () => {
    const draft = settingsDraft(saved); draft.api_key = 'old-typed'; draft.clear_api_key = true
    const next = chooseProvider(draft, qwen)
    expect(next.api_key).toBe(''); expect(next.clear_api_key).toBe(false)
    expect(next.provider).toBe('qwen'); expect(next.region).toBe('cn-beijing')
    expect(next.workspace_id).toBe(''); expect(next.model).toBe('qwen-plus')
  })
  it('substitutes the exact Qwen WorkspaceId placeholder for the selected region', () => {
    expect(regionBaseUrl(qwen, 'ap-southeast-1', 'workspace-123')).toBe('https://sg.example/workspaces/workspace-123/v1')
    expect(regionBaseUrl(qwen, 'cn-beijing', '')).toContain('{WorkspaceId}')
  })
  it('requires filling workspace placeholder but permits a manually entered API root', () => {
    const draft = chooseProvider(settingsDraft(saved), qwen); draft.api_key = 'new'
    expect(validateSettings(draft, qwen, saved)).toMatch(/工作空间/)
    draft.base_url = 'https://manual.example/v1'
    expect(validateSettings(draft, qwen, saved)).toBe('')
  })
  it('explicit key clearing disables saved config and excludes a competing typed key', () => {
    const draft = settingsDraft(saved); draft.clear_api_key = true; draft.api_key = 'do-not-send'
    const payload = settingsPayload(draft, saved)
    expect(payload.enabled).toBe(false); expect(payload.clear_api_key).toBe(true)
    expect(payload).not.toHaveProperty('api_key')
  })
  it('allows intentional clearing after an endpoint change', () => {
    const draft = settingsDraft(saved); draft.base_url = 'https://other.example/v1'; draft.clear_api_key = true
    expect(validateSettings(draft, undefined, saved)).toBe('')
  })
  it.each([{ max_steps: 33 }, { timeout: 0 }, { max_tokens: 63 }, { retention_days: 0 }])('validates advanced budget boundaries %o', change => {
    const draft = { ...settingsDraft(saved), ...change }
    expect(validateSettings(draft, undefined, saved)).toMatch(/范围/)
  })
  it.each(['javascript:alert(1)', 'https://key:secret@host/v1', 'https://host/v1?api_key=secret', 'https://host/v1#key'])('rejects unsafe or credential-bearing roots %s', root => {
    const draft = settingsDraft(saved); draft.base_url = root; draft.api_key = 'new'
    expect(validateSettings(draft, undefined, saved)).not.toBe('')
  })
})
