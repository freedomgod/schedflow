import { describe, expect, it, vi, afterEach } from 'vitest'
import { agentRequest, streamTurn } from '../api'

afterEach(() => vi.unstubAllGlobals())
describe('Agent transport', () => {
  it('sends bearer auth in headers without placing credentials in URL', async () => {
    vi.stubGlobal('localStorage', { getItem: () => 'secret-token' })
    let calledUrl = ''; let headers: Headers | undefined
    vi.stubGlobal('fetch', async (url: string, options: RequestInit) => { calledUrl = url; headers = new Headers(options.headers); return new Response(JSON.stringify({ code: 0, data: { enabled: true } })) })
    expect(await agentRequest('/config-status')).toEqual({ enabled: true })
    expect(calledUrl).not.toContain('secret-token')
    expect(headers?.get('Authorization')).toBe('Bearer secret-token')
  })
  it('surfaces API envelopes with a failure code', async () => {
    vi.stubGlobal('localStorage', { getItem: () => null })
    vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ code: 409, message: '版本已变化' })))
    await expect(agentRequest('/proposals/p/approve', { method: 'POST' })).rejects.toThrow('版本已变化')
  })
  it('resumes the stream at its last event sequence', async () => {
    vi.stubGlobal('localStorage', { getItem: () => null })
    let calledUrl = ''
    vi.stubGlobal('fetch', async (url: string) => { calledUrl = url; return new Response('data: {"seq":8,"turn_id":"t","type":"status","payload":{"status":"running"}}\n\n', { headers: { 'Content-Type': 'text/event-stream' } }) })
    const events: unknown[] = []
    await streamTurn('t', 7, new AbortController().signal, event => events.push(event))
    expect(calledUrl).toMatch(/turns\/t\/events\?after=7$/)
    expect(events).toHaveLength(1)
  })
  it('rejects a JSON response accidentally returned by an SSE endpoint', async () => {
    vi.stubGlobal('localStorage', { getItem: () => null })
    vi.stubGlobal('fetch', async () => new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
    await expect(streamTurn('t', 0, new AbortController().signal, () => {})).rejects.toThrow('事件流')
  })
})
