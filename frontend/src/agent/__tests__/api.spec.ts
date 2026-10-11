import { describe, expect, it, vi, afterEach } from 'vitest'
import { agentApi, agentRequest, streamTurn } from '../api'

afterEach(() => vi.unstubAllGlobals())
describe('Agent transport', () => {
  it('reads public provider profiles and full settings through human authenticated endpoints', async () => {
    vi.stubGlobal('localStorage', { getItem: () => 'token' })
    const calls: string[] = []
    vi.stubGlobal('fetch', async (url: string) => { calls.push(url); return new Response(JSON.stringify({ code: 0, data: { providers: [] } })) })
    await agentApi.providers(); await agentApi.settings()
    expect(calls[0]).toMatch(/\/agent\/providers$/); expect(calls[1]).toMatch(/\/agent\/config$/)
  })
  it('uses separate save, unsaved test, and immediate toggle endpoints', async () => {
    vi.stubGlobal('localStorage', { getItem: () => 'token' })
    const calls: { url: string; options: RequestInit }[] = []
    vi.stubGlobal('fetch', async (url: string, options: RequestInit) => { calls.push({ url, options }); return new Response(JSON.stringify({ code: 0, data: {} })) })
    const payload = { enabled: false, provider: 'openai', protocol: 'responses', base_url: 'https://api.openai.com/v1', model: 'test', api_key: 'secret', clear_api_key: false, max_steps: 8, timeout: 60, max_tokens: 4096, allow_code_generation: false, retention_days: 30 } as const
    await agentApi.saveSettings(payload); await agentApi.testSettings(payload); await agentApi.setEnabled(true)
    expect(calls.map(call => call.options.method)).toEqual(['PUT', 'POST', 'PUT'])
    expect(calls.map(call => call.url.split('/agent')[1])).toEqual(['/config', '/config/test', '/enabled'])
    expect(calls[0].options.body).toBe(JSON.stringify(payload)); expect(calls[1].options.body).toBe(JSON.stringify(payload))
    expect(calls[2].options.body).toBe('{"enabled":true}')
    expect(calls.every(call => !call.url.includes('secret'))).toBe(true)
  })
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
