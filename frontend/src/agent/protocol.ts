import type { AgentBlock, AgentEvent, AgentMessage, AgentProposal, MessageStatus, TurnStatus, WorkflowSummary } from './types'
const eventTypes = new Set(['message.delta', 'message.completed', 'status', 'proposal.created', 'turn.completed', 'turn.failed'])
const turnStatuses = new Set(['pending', 'queued', 'running', 'streaming', 'thinking', 'tool_running', 'cancelling', 'cancelled', 'completed', 'failed', 'interrupted'])
function record(value: unknown): value is Record<string, unknown> { return !!value && typeof value === 'object' && !Array.isArray(value) }
function isEvent(value: unknown): value is AgentEvent { return record(value) && Number.isSafeInteger(value.seq) && Number(value.seq) > 0 && typeof value.turn_id === 'string' && typeof value.type === 'string' && eventTypes.has(value.type) && record(value.payload) }
function messageFromUnknown(value: unknown): AgentMessage | null {
  if (!record(value) || typeof value.message_id !== 'string' || !['user', 'assistant'].includes(String(value.role)) || !Array.isArray(value.blocks)) return null
  const blocks: AgentBlock[] = []
  for (const block of value.blocks) {
    if (!record(block)) continue
    if (block.type === 'assistant_text' && typeof block.text === 'string') blocks.push({ type: block.type, text: block.text })
    else if (block.type === 'error' && typeof block.message === 'string') blocks.push({ type: block.type, message: block.message })
    else if ((block.type === 'operation_receipt' || block.type === 'execution') && typeof block.operation_id === 'string') blocks.push({ type: block.type, operation_id: block.operation_id })
    else if (block.type === 'proposal' && typeof block.proposal_id === 'string' && Number.isSafeInteger(block.version)) blocks.push({ type: block.type, proposal_id: block.proposal_id, version: Number(block.version) })
    else if (block.type === 'clarification' && typeof block.text === 'string') blocks.push({ type: block.type, text: block.text, options: Array.isArray(block.options) ? block.options.filter((option): option is { label: string; value: string } => record(option) && typeof option.label === 'string' && typeof option.value === 'string') : [] })
    else if (block.type === 'workflow_results' && Array.isArray(block.jobs)) blocks.push({ type: block.type, jobs: block.jobs.filter((job): job is WorkflowSummary => record(job) && typeof job.job_id === 'string') })
  }
  const status = ['pending', 'streaming', 'completed', 'cancelled', 'failed', 'interrupted'].includes(String(value.status)) ? value.status as MessageStatus : 'completed'
  return { message_id: value.message_id, turn_id: typeof value.turn_id === 'string' ? value.turn_id : undefined, role: value.role as 'user' | 'assistant', status, blocks }
}
function proposalFromUnknown(value: unknown): AgentProposal | null {
  if (!record(value) || typeof value.proposal_id !== 'string' || !Number.isSafeInteger(value.version) || !['create', 'update', 'run'].includes(String(value.action)) || !['pending', 'awaiting_confirmation', 'committing', 'committed', 'approved', 'rejected', 'expired', 'stale', 'superseded'].includes(String(value.status)) || !record(value.payload) || !Array.isArray(value.diff)) return null
  return value as unknown as AgentProposal
}
/** Stateful UTF-8 / SSE framing; a network chunk is not a text or event boundary. */
export class SseDecoder {
  private decoder = new TextDecoder()
  private buffer = ''
  push(bytes: Uint8Array, final = false): AgentEvent[] {
    this.buffer += this.decoder.decode(bytes, { stream: !final })
    const events: AgentEvent[] = []
    let match: RegExpExecArray | null
    while ((match = /\r?\n\r?\n/.exec(this.buffer))) {
      const frame = this.buffer.slice(0, match.index)
      this.buffer = this.buffer.slice(match.index + match[0].length)
      const data = frame.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).replace(/^ /, '')).join('\n')
      if (!data) continue
      try { const event: unknown = JSON.parse(data); if (isEvent(event)) events.push(event) } catch { /* Malformed data never becomes an executable UI instruction. */ }
    }
    return events
  }
}
export interface TurnState { turn_id: string; status: TurnStatus; lastSeq: number; messages: AgentMessage[]; proposals: AgentProposal[]; error: string | null }
export function createTurnState(turnId: string): TurnState { return { turn_id: turnId, status: 'pending', lastSeq: 0, messages: [], proposals: [], error: null } }
export function applyAgentEvent(state: TurnState, input: unknown): boolean {
  if (!isEvent(input) || input.turn_id !== state.turn_id || input.seq <= state.lastSeq) return false
  const event = input; state.lastSeq = event.seq; const payload = event.payload
  if (event.type === 'message.delta' && typeof payload.message_id === 'string' && typeof payload.text === 'string') {
    let message = state.messages.find(message => message.message_id === payload.message_id)
    if (!message) { message = { message_id: payload.message_id, turn_id: event.turn_id, role: 'assistant', status: 'streaming', blocks: [{ type: 'assistant_text', text: '' }] }; state.messages.push(message) }
    let text = message.blocks.find(block => block.type === 'assistant_text')
    if (!text) { text = { type: 'assistant_text', text: '' }; message.blocks.push(text) }
    if (text.type === 'assistant_text') text.text += payload.text
  } else if (event.type === 'message.completed') {
    const message = messageFromUnknown(payload.message); if (!message) return true
    const index = state.messages.findIndex(item => item.message_id === message.message_id)
    if (index < 0) state.messages.push(message); else state.messages[index] = message
  } else if (event.type === 'status' || event.type === 'turn.completed') { if (typeof payload.status === 'string' && turnStatuses.has(payload.status)) state.status = payload.status as TurnStatus }
  else if (event.type === 'turn.failed') { state.status = 'failed'; state.error = typeof payload.message === 'string' ? payload.message : '回答失败' }
  else if (event.type === 'proposal.created') {
    const proposal = proposalFromUnknown(payload.proposal); if (!proposal) return true
    const index = state.proposals.findIndex(item => item.proposal_id === proposal.proposal_id)
    if (index < 0) state.proposals.push(proposal); else state.proposals[index] = proposal
  }
  return true
}
export function isTurnActive(status: string): boolean { return ['pending', 'queued', 'running', 'streaming', 'thinking', 'tool_running', 'cancelling'].includes(status) }
export function canApprove(proposal: { status: string; version: number; expires_at?: string }, version: number, now = new Date()): boolean { return ['pending', 'awaiting_confirmation'].includes(proposal.status) && proposal.version === version && (!proposal.expires_at || Date.parse(proposal.expires_at) > now.getTime()) }
export function operationLabel(status: string): string { return ({ prepared: '等待确认', committing: '正在提交', accepted: '调度器已接收', running: '正在执行', succeeded: '执行成功', failed: '执行失败', unknown: '结果待核实' } as Record<string, string>)[status] || status }
export function shouldSend(event: { key: string; isComposing: boolean; shiftKey: boolean; keyCode?: number }): boolean { return event.key === 'Enter' && !event.isComposing && event.keyCode !== 229 && !event.shiftKey }
