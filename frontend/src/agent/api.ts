import { expireSession } from '../utils/session'
import { SseDecoder } from './protocol'
import type { AgentConfig, AgentEvent, AgentOperation, AgentProposal, AgentSession, AgentTurn } from './types'
const base = `${(import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')}/agent`
function authHeaders(): Headers { const headers = new Headers(); const token = localStorage.getItem('schedflow_token'); if (token) headers.set('Authorization', `Bearer ${token}`); return headers }
async function failure(response: Response): Promise<Error> {
  if ([401, 403].includes(response.status)) expireSession()
  try { const body = await response.json(); return new Error(body.message || body.detail || `请求失败 (${response.status})`) } catch { return new Error(`请求失败 (${response.status})`) }
}
export async function agentRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = authHeaders(); headers.set('Content-Type', 'application/json')
  const response = await fetch(`${base}${path}`, { ...options, headers })
  if (!response.ok) throw await failure(response)
  const body = await response.json()
  if (body.code !== 0) throw new Error(body.message || '请求失败')
  return body.data
}
export async function streamTurn(turnId: string, after: number, signal: AbortSignal, onEvent: (event: AgentEvent) => void): Promise<void> {
  const response = await fetch(`${base}/turns/${encodeURIComponent(turnId)}/events?after=${after}`, { headers: authHeaders(), signal })
  if (!response.ok) throw await failure(response)
  if (!response.headers.get('Content-Type')?.includes('text/event-stream') || !response.body) throw new Error('无法读取事件流')
  const reader = response.body.getReader(); const decoder = new SseDecoder()
  try { while (!signal.aborted) { const { value, done } = await reader.read(); if (done) { decoder.push(new Uint8Array(), true).forEach(onEvent); break }; decoder.push(value).forEach(onEvent) } }
  finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
}
const id = encodeURIComponent
export const agentApi = {
  config: () => agentRequest<AgentConfig>('/config-status'),
  sessions: async () => { const data = await agentRequest<AgentSession[] | { sessions: AgentSession[] }>('/sessions'); return Array.isArray(data) ? data : data.sessions },
  createSession: () => agentRequest<AgentSession>('/sessions', { method: 'POST', body: '{}' }),
  session: (sessionId: string) => agentRequest<AgentSession>(`/sessions/${id(sessionId)}`),
  deleteSession: (sessionId: string) => agentRequest<void>(`/sessions/${id(sessionId)}`, { method: 'DELETE' }),
  send: (sessionId: string, message: string, jobId?: string) => agentRequest<AgentTurn>(`/sessions/${id(sessionId)}/turns`, { method: 'POST', body: JSON.stringify({ message, job_id: jobId || undefined }) }),
  turn: (turnId: string) => agentRequest<AgentTurn>(`/turns/${id(turnId)}`),
  cancel: (turnId: string) => agentRequest<AgentTurn>(`/turns/${id(turnId)}/cancel`, { method: 'POST', body: '{}' }),
  proposal: (proposalId: string) => agentRequest<AgentProposal>(`/proposals/${id(proposalId)}`),
  approve: (proposal: AgentProposal) => agentRequest<AgentOperation>(`/proposals/${id(proposal.proposal_id)}/approve`, { method: 'POST', body: JSON.stringify({ proposal_version: proposal.version }) }),
  reject: (proposalId: string) => agentRequest<AgentProposal>(`/proposals/${id(proposalId)}/reject`, { method: 'POST', body: '{}' }),
  revise: (proposalId: string, enabled: boolean) => agentRequest<AgentProposal>(`/proposals/${id(proposalId)}/revise`, { method: 'POST', body: JSON.stringify({ enabled }) }),
  operation: (operationId: string) => agentRequest<AgentOperation>(`/operations/${id(operationId)}`),
}
