import { describe, expect, it } from 'vitest'
import { SseDecoder, applyAgentEvent, createTurnState, isTurnActive, canApprove, operationLabel, shouldSend } from '../protocol'

describe('Agent stream protocol', () => {
  it('decodes split UTF-8, CRLF, multiline data and ignores heartbeat comments', () => {
    const decoder = new SseDecoder()
    const bytes = new TextEncoder().encode(': ping\r\ndata: {"seq":1,\r\ndata: "turn_id":"t","type":"message.delta","payload":{"text":"你好"}}\r\n\r\n')
    const events = []
    for (const byte of bytes) events.push(...decoder.push(new Uint8Array([byte])))
    expect(events).toEqual([{ seq: 1, turn_id: 't', type: 'message.delta', payload: { text: '你好' } }])
  })
  it('rejects malformed or untrusted control events', () => {
    const decoder = new SseDecoder()
    expect(decoder.push(new TextEncoder().encode('data: broken\n\ndata: {"seq":1,"type":"execute","payload":{"command":"rm"}}\n\n'))).toEqual([])
  })
  it('deduplicates events and never mixes turns', () => {
    const state = createTurnState('t')
    const event = { seq: 1, turn_id: 't', type: 'message.delta', payload: { message_id: 'm', text: 'Hello' } }
    applyAgentEvent(state, event)
    applyAgentEvent(state, event)
    applyAgentEvent(state, { ...event, seq: 2, turn_id: 'other' })
    expect(state.messages[0].blocks).toEqual([{ type: 'assistant_text', text: 'Hello' }])
    expect(state.lastSeq).toBe(1)
  })
  it('replaces a streamed message with its authoritative completed blocks', () => {
    const state = createTurnState('t')
    applyAgentEvent(state, { seq: 1, turn_id: 't', type: 'message.delta', payload: { message_id: 'm', text: 'draft' } })
    applyAgentEvent(state, { seq: 2, turn_id: 't', type: 'message.completed', payload: { message: { message_id: 'm', role: 'assistant', status: 'completed', blocks: [{ type: 'assistant_text', text: 'final' }] } } })
    expect(state.messages).toHaveLength(1)
    expect(state.messages[0].blocks[0]).toEqual({ type: 'assistant_text', text: 'final' })
  })
  it('records actual turn failure instead of leaving a pending spinner', () => {
    const state = createTurnState('t')
    applyAgentEvent(state, { seq: 1, turn_id: 't', type: 'turn.failed', payload: { message: 'provider unavailable' } })
    expect(state.status).toBe('failed')
    expect(state.error).toBe('provider unavailable')
    expect(isTurnActive(state.status)).toBe(false)
  })
  it('only allows current unexpired pending proposals to be approved', () => {
    const proposal = { status: 'pending', version: 2, expires_at: '2030-01-01T00:00:00Z' }
    expect(canApprove(proposal, 2, new Date('2029-01-01'))).toBe(true)
    expect(canApprove(proposal, 1, new Date('2029-01-01'))).toBe(false)
    expect(canApprove(proposal, 2, new Date('2031-01-01'))).toBe(false)
    expect(canApprove({ ...proposal, status: 'approved' }, 2, new Date('2029-01-01'))).toBe(false)
  })
  it('distinguishes scheduler acceptance from successful execution', () => {
    expect(operationLabel('accepted')).toBe('调度器已接收')
    expect(operationLabel('running')).toBe('正在执行')
    expect(operationLabel('succeeded')).toBe('执行成功')
    expect(operationLabel('unknown')).toBe('结果待核实')
  })
  it('does not send during Chinese IME composition or Shift+Enter', () => {
    expect(shouldSend({ key: 'Enter', isComposing: true, shiftKey: false })).toBe(false)
    expect(shouldSend({ key: 'Enter', isComposing: false, shiftKey: true })).toBe(false)
    expect(shouldSend({ key: 'Enter', isComposing: false, shiftKey: false })).toBe(true)
  })
})
