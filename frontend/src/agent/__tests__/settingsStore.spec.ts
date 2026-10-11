import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
const api = vi.hoisted(() => ({ config: vi.fn(), setEnabled: vi.fn(), approve: vi.fn() }))
vi.mock('../api', () => ({ agentApi: api, streamTurn: vi.fn() }))
import { useAgentStore } from '../../stores/agent'
const enabled = { enabled: true, configured: true, model: 'test' }
beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks() })

describe('Agent configuration controls', () => {
  it('refreshes config without reloading the current answer or session', async () => {
    const store = useAgentStore(); store.config = enabled
    store.activeTurn = { turn_id: 't', status: 'running', lastSeq: 9, messages: [], proposals: [], error: null }
    api.config.mockResolvedValue({ ...enabled, enabled: false })
    await store.refreshConfig()
    expect(store.config?.enabled).toBe(false)
    expect(store.activeTurn?.lastSeq).toBe(9)
  })
  it('holds backend truth until toggle succeeds and refuses duplicate toggles', async () => {
    const store = useAgentStore(); store.config = enabled
    let finish!: (value: unknown) => void
    api.setEnabled.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const pending = store.setEnabled(false)
    expect(store.configPending).toBe(true)
    expect(store.config?.enabled).toBe(true)
    await store.setEnabled(false)
    expect(api.setEnabled).toHaveBeenCalledTimes(1)
    finish({ ...enabled, enabled: false }); await pending
    expect(store.config?.enabled).toBe(false)
    expect(store.configPending).toBe(false)
  })
  it('does not let an older config refresh overwrite a completed toggle', async () => {
    const store = useAgentStore(); store.config = enabled
    let finish!: (value: unknown) => void
    api.config.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const refresh = store.refreshConfig()
    api.setEnabled.mockResolvedValue({ ...enabled, enabled: false })
    await store.setEnabled(false)
    finish(enabled); await refresh
    expect(store.config?.enabled).toBe(false)
  })
  it('invalidates a refresh started while a toggle was awaiting its response', async () => {
    const store = useAgentStore(); store.config = enabled
    let toggleFinish!: (value: unknown) => void; let refreshFinish!: (value: unknown) => void
    api.setEnabled.mockReturnValue(new Promise(resolve => { toggleFinish = resolve }))
    api.config.mockReturnValue(new Promise(resolve => { refreshFinish = resolve }))
    const toggling = store.setEnabled(false); const refreshing = store.refreshConfig()
    toggleFinish({ ...enabled, enabled: false }); await toggling
    refreshFinish(enabled); await refreshing
    expect(store.config?.enabled).toBe(false)
  })
  it('does not let a stale read overwrite the confirmed result of saving settings', async () => {
    const store = useAgentStore(); store.config = enabled
    let finish!: (value: unknown) => void
    api.config.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const refreshing = store.refreshConfig()
    store.applySavedConfig({ ...enabled, enabled: false, model: 'new-model' })
    finish(enabled); await refreshing
    expect(store.config?.model).toBe('new-model')
    expect(store.config?.enabled).toBe(false)
  })
  it('reports toggle failure and refreshes backend truth after an ambiguous response', async () => {
    const store = useAgentStore(); store.config = enabled
    api.setEnabled.mockRejectedValue(new Error('连接中断'))
    api.config.mockResolvedValue({ ...enabled, enabled: false })
    expect(await store.setEnabled(false)).toBe(false)
    expect(store.config?.enabled).toBe(false)
    expect(store.configPending).toBe(false)
    expect(store.configError).toBe('连接中断')
  })
  it('keeps saved state if both toggle and refresh fail', async () => {
    const store = useAgentStore(); store.config = enabled
    api.setEnabled.mockRejectedValue(new Error('请求失败')); api.config.mockRejectedValue(new Error('离线'))
    await store.setEnabled(false)
    expect(store.config?.enabled).toBe(true)
    expect(store.configError).toBe('请求失败')
  })
  it('blocks enabling an unconfigured Agent and submitting while toggle is pending', async () => {
    const store = useAgentStore(); store.config = { ...enabled, enabled: false, configured: false }
    await store.setEnabled(true)
    expect(api.setEnabled).not.toHaveBeenCalled()
    store.config = enabled; store.configPending = true
    expect(await store.send('新请求')).toBe(false)
  })
  it('refuses proposal confirmation when Agent is disabled or changing state', async () => {
    const store = useAgentStore(); store.config = { ...enabled, enabled: false }
    store.proposals.p = { proposal_id: 'p', version: 1, status: 'awaiting_confirmation', action: 'create', before: null, after: null, payload: {}, diff: [] }
    await store.approve('p')
    store.config = enabled; store.configPending = true; await store.approve('p')
    expect(api.approve).not.toHaveBeenCalled()
  })
})
