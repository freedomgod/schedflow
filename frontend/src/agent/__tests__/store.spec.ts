import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
const api = vi.hoisted(() => ({ config: vi.fn(), sessions: vi.fn(), createSession: vi.fn(), session: vi.fn(), send: vi.fn(), turn: vi.fn(), cancel: vi.fn(), proposal: vi.fn(), approve: vi.fn(), reject: vi.fn(), revise: vi.fn(), operation: vi.fn(), deleteSession: vi.fn() }))
const stream = vi.hoisted(() => vi.fn(async () => {}))
vi.mock('../api', () => ({ agentApi: api, streamTurn: stream }))
import { useAgentStore } from '../../stores/agent'
const session = { session_id: 's', title: '测试', messages: [], turns: [], proposals: [] }
beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks(); vi.stubGlobal('localStorage', { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() }) })
describe('Agent session state', () => {
  it('loads history and restores the last session', async () => {
    api.config.mockResolvedValue({ enabled: true, configured: true, model: 'test' }); api.sessions.mockResolvedValue([session]); api.session.mockResolvedValue(session)
    const store = useAgentStore(); await store.initialize()
    expect(store.session?.session_id).toBe('s'); expect(store.config?.model).toBe('test')
  })
  it('resumes from the coherent session snapshot and appends to persisted partial text', async () => {
    api.session.mockResolvedValue({ ...session, last_seq: 5, turns: [{ turn_id: 't', status: 'running' }], messages: [{ message_id: 'm', turn_id: 't', role: 'assistant', status: 'streaming', blocks: [{ type: 'assistant_text', text: '已保存' }] }] })
    api.turn.mockResolvedValue({ turn_id: 't', status: 'running', last_seq: 7 })
    stream.mockImplementation(async (_id, _seq, _signal, onEvent) => { onEvent({ seq: 6, turn_id: 't', type: 'message.delta', payload: { message_id: 'm', text: '的新文本' } }); await new Promise(() => {}) })
    const store = useAgentStore(); await store.openSession('s')
    expect(stream.mock.calls[0][1]).toBe(5)
    expect(store.messages[0].blocks[0]).toEqual({ type: 'assistant_text', text: '已保存的新文本' })
    store.disconnect()
  })
  it('reloads the terminal session snapshot when a turn ends between reads', async () => {
    api.session.mockResolvedValueOnce({ ...session, last_seq: 5, turns: [{ turn_id: 't', status: 'running' }] }).mockResolvedValueOnce({ ...session, turns: [{ turn_id: 't', status: 'completed' }], messages: [{ message_id: 'final', role: 'assistant', status: 'completed', blocks: [{ type: 'assistant_text', text: '完成' }] }] })
    api.turn.mockResolvedValue({ turn_id: 't', status: 'completed', last_seq: 7 })
    const store = useAgentStore(); await store.openSession('s')
    expect(store.messages[0].message_id).toBe('final')
    expect(store.busy).toBe(false)
  })
  it('returns a failed submission without consuming the draft or leaving busy state', async () => {
    api.send.mockRejectedValue(new Error('provider offline'))
    const store = useAgentStore(); store.session = session; store.config = { enabled: true, configured: true, model: 'test' }
    expect(await store.send('保留我的输入')).toBe(false)
    expect(store.busy).toBe(false); expect(store.error).toBe('provider offline')
  })
  it('does not schedule operation polling after the page has disconnected', async () => {
    vi.useFakeTimers()
    try {
      api.operation.mockResolvedValue({ operation_id: 'o', status: 'running', action: 'run' })
      const store = useAgentStore(); store.disconnect(); await store.refreshOperation('o')
      expect(vi.getTimerCount()).toBe(0)
    } finally { vi.useRealTimers() }
  })
  it('rejects repeated confirmation while a proposal commit is pending', async () => {
    const proposal = { proposal_id: 'p', version: 1, status: 'pending', action: 'create', before: null, after: {}, payload: {}, diff: [] }
    let resolve!: (value: unknown) => void
    api.approve.mockReturnValue(new Promise(r => { resolve = r })); api.proposal.mockResolvedValue({ ...proposal, status: 'approved' })
    const store = useAgentStore(); store.proposals.p = proposal as any
    const first = store.approve('p'); await store.approve('p')
    expect(api.approve).toHaveBeenCalledTimes(1)
    resolve({ operation_id: 'o', status: 'succeeded', action: 'create' }); await first
    expect(store.operations.o.status).toBe('succeeded')
  })
  it('adds the persisted operation receipt to chat immediately after confirmation', async () => {
    const proposal = { proposal_id: 'p', version: 1, status: 'awaiting_confirmation', action: 'create', before: null, after: {}, payload: {}, diff: [] }
    api.approve.mockResolvedValue({ operation_id: 'o', status: 'succeeded', action: 'create' }); api.proposal.mockResolvedValue({ ...proposal, status: 'committed', operation_id: 'o' })
    api.session.mockResolvedValue({ ...session, messages: [{ message_id: 'receipt', role: 'assistant', status: 'completed', blocks: [{ type: 'operation_receipt', operation_id: 'o' }] }] })
    const store = useAgentStore(); store.session = session; store.proposals.p = proposal as any
    await store.approve('p')
    expect(store.messages[0].blocks[0]).toEqual({ type: 'operation_receipt', operation_id: 'o' })
  })
  it('uses the saved cancelled message instead of a stale streaming overlay', async () => {
    api.cancel.mockResolvedValue({ turn_id: 't', status: 'cancelled' }); api.session.mockResolvedValue({ ...session, messages: [{ message_id: 'm', turn_id: 't', role: 'assistant', status: 'cancelled', blocks: [{ type: 'assistant_text', text: 'saved' }] }] })
    const store = useAgentStore(); store.session = session; store.activeTurn = { turn_id: 't', status: 'running', lastSeq: 1, messages: [{ message_id: 'm', turn_id: 't', role: 'assistant', status: 'streaming', blocks: [{ type: 'assistant_text', text: 'stale' }] }], proposals: [], error: null }
    await store.cancel()
    expect(store.messages[0].status).toBe('cancelled'); expect(store.messages[0].blocks[0]).toEqual({ type: 'assistant_text', text: 'saved' })
  })
  it('cancels only the active answer and keeps accepted operations visible', async () => {
    api.cancel.mockResolvedValue({ turn_id: 't', status: 'cancelled' }); api.session.mockResolvedValue(session)
    const store = useAgentStore(); store.session = session; store.activeTurn = { turn_id: 't', status: 'running', lastSeq: 0, messages: [], proposals: [], error: null }; store.operations.o = { operation_id: 'o', status: 'running', action: 'run' }
    await store.cancel()
    expect(api.cancel).toHaveBeenCalledWith('t'); expect(store.operations.o.status).toBe('running'); expect(store.activeTurn?.status).toBe('cancelled')
  })
})
