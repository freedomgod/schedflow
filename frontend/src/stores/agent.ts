import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { agentApi, streamTurn } from '@/agent/api'
import { deduplicateOperationCards } from '@/agent/presentation'
import { applyAgentEvent, canApprove, createTurnState, isTurnActive } from '@/agent/protocol'
import type { TurnState } from '@/agent/protocol'
import type { AgentConfig, AgentMessage, AgentOperation, AgentProposal, AgentSession } from '@/agent/types'

export const useAgentStore = defineStore('agent', () => {
  const config = ref<AgentConfig | null>(null)
  const sessions = ref<AgentSession[]>([])
  const session = ref<AgentSession | null>(null)
  const activeTurn = ref<TurnState | null>(null)
  const proposals = ref<Record<string, AgentProposal>>({})
  const operations = ref<Record<string, AgentOperation>>({})
  const pendingActions = ref<Record<string, boolean>>({})
  const loading = ref(false); const sending = ref(false); const error = ref(''); const connection = ref<'connected' | 'reconnecting' | 'offline'>('connected')
  let streamController: AbortController | null = null
  let operationTimer: ReturnType<typeof setTimeout> | null = null
  let epoch = 0; let pollingEnabled = true
  const busy = computed(() => sending.value || !!(activeTurn.value && isTurnActive(activeTurn.value.status)))
  const messages = computed(() => {
    const result = [...(session.value?.messages || [])]
    for (const message of activeTurn.value?.messages || []) { const index = result.findIndex(item => item.message_id === message.message_id); if (index < 0) result.push(message); else result[index] = message }
    return deduplicateOperationCards(result)
  })
  function report(cause: unknown) { error.value = cause instanceof Error ? cause.message : String(cause) }
  function mergeSession(value: AgentSession) {
    session.value = { ...value, messages: value.messages || [], turns: value.turns || [], proposals: value.proposals || [] }
    for (const proposal of value.proposals || []) proposals.value[proposal.proposal_id] = proposal
    for (const message of value.messages || []) for (const block of message.blocks || []) {
      if (block.type === 'proposal' && !proposals.value[block.proposal_id]) void loadProposal(block.proposal_id)
      if ((block.type === 'operation_receipt' || block.type === 'execution') && !operations.value[block.operation_id]) void refreshOperation(block.operation_id)
    }
  }
  async function initialize() {
    pollingEnabled = true; scheduleOperations(); loading.value = true; error.value = ''
    try { config.value = await agentApi.config(); sessions.value = await agentApi.sessions(); const saved = localStorage.getItem('schedflow_agent_session'); const target = sessions.value.find(s => s.session_id === saved) || sessions.value[0]; if (target) await openSession(target.session_id) }
    catch (cause) { report(cause) } finally { loading.value = false }
  }
  async function openSession(sessionId: string) {
    const current = ++epoch; streamController?.abort(); activeTurn.value = null; error.value = ''; loading.value = true
    try {
      const value = await agentApi.session(sessionId); if (current !== epoch) return
      mergeSession(value); localStorage.setItem('schedflow_agent_session', sessionId)
      const active = value.turns?.find(turn => isTurnActive(turn.status))
      if (active) {
        const snapshot = await agentApi.turn(active.turn_id); if (current !== epoch) return
        if (isTurnActive(snapshot.status)) {
          activeTurn.value = { ...createTurnState(active.turn_id), status: snapshot.status, lastSeq: value.last_seq || 0, messages: structuredClone(value.messages?.filter(message => message.turn_id === active.turn_id && message.role === 'assistant') || []) }
          void connect(current)
        } else { const terminal = await agentApi.session(sessionId); if (current === epoch) mergeSession(terminal) }
      }
    } catch (cause) { if (current === epoch) report(cause) } finally { if (current === epoch) loading.value = false }
  }
  async function newSession() {
    if (sending.value) return
    try { const value = await agentApi.createSession(); sessions.value.unshift(value); await openSession(value.session_id) } catch (cause) { report(cause) }
  }
  async function removeSession(sessionId: string) {
    try { await agentApi.deleteSession(sessionId); sessions.value = sessions.value.filter(s => s.session_id !== sessionId); if (session.value?.session_id === sessionId) { ++epoch; streamController?.abort(); session.value = null; activeTurn.value = null; localStorage.removeItem('schedflow_agent_session'); if (sessions.value[0]) await openSession(sessions.value[0].session_id) } } catch (cause) { report(cause) }
  }
  async function send(text: string, jobId?: string) {
    if (busy.value || !text.trim() || !config.value?.enabled || !config.value.configured) return false
    sending.value = true; error.value = ''
    try {
      if (!session.value) { const value = await agentApi.createSession(); sessions.value.unshift(value); mergeSession(value); localStorage.setItem('schedflow_agent_session', value.session_id) }
      const sessionId = session.value!.session_id; const current = epoch
      const turn = await agentApi.send(sessionId, text.trim(), jobId)
      if (current !== epoch) return false
      const userMessage: AgentMessage = { message_id: `local-${turn.turn_id}`, turn_id: turn.turn_id, role: 'user', status: 'completed', blocks: [{ type: 'assistant_text', text: text.trim() }] }
      session.value!.messages.push(userMessage)
      activeTurn.value = { ...createTurnState(turn.turn_id), status: turn.status }; void connect(current); return true
    } catch (cause) { report(cause); return false } finally { sending.value = false }
  }
  async function connect(current: number) {
    streamController?.abort(); const controller = new AbortController(); streamController = controller
    let attempts = 0
    while (current === epoch && activeTurn.value && isTurnActive(activeTurn.value.status) && !controller.signal.aborted) {
      const turn = activeTurn.value
      try {
        await streamTurn(turn.turn_id, turn.lastSeq, controller.signal, event => {
          if (current !== epoch || !activeTurn.value || !applyAgentEvent(activeTurn.value, event)) return
          connection.value = 'connected'; attempts = 0
          for (const proposal of activeTurn.value.proposals) proposals.value[proposal.proposal_id] = proposal
          for (const message of activeTurn.value.messages) for (const block of message.blocks || []) {
            if (block.type === 'proposal' && !proposals.value[block.proposal_id]) void loadProposal(block.proposal_id)
            if ((block.type === 'operation_receipt' || block.type === 'execution') && !operations.value[block.operation_id]) void refreshOperation(block.operation_id)
          }
          if (activeTurn.value.error) error.value = activeTurn.value.error
        })
        if (current !== epoch || controller.signal.aborted) return
        const snapshot = await agentApi.turn(turn.turn_id)
        if (current !== epoch) return
        turn.status = snapshot.status
        if (!isTurnActive(turn.status)) break
      } catch (cause) { if (controller.signal.aborted || current !== epoch) return; connection.value = 'reconnecting'; if (++attempts >= 5) { connection.value = 'offline'; report(new Error('连接已中断。点击恢复回答，从已保存的事件继续。')); return } }
      if (isTurnActive(turn.status)) await new Promise<void>(resolve => { const timer = setTimeout(resolve, Math.min(1000 * (attempts + 1), 5000)); controller.signal.addEventListener('abort', () => { clearTimeout(timer); resolve() }, { once: true }) })
    }
    if (current === epoch && session.value && !controller.signal.aborted) {
      try { const value = await agentApi.session(session.value.session_id); if (current === epoch) { mergeSession(value); activeTurn.value = null; sessions.value = await agentApi.sessions() } } catch (cause) { report(cause) }
    }
  }
  function reconnect() { error.value = ''; if (activeTurn.value) void connect(epoch); else if (session.value) void openSession(session.value.session_id) }
  async function cancel() {
    if (!activeTurn.value) return
    const current = epoch; const turnId = activeTurn.value.turn_id; const sessionId = session.value?.session_id
    try {
      const turn = await agentApi.cancel(turnId)
      if (current !== epoch || activeTurn.value?.turn_id !== turnId) return
      activeTurn.value.status = turn.status
      if (!isTurnActive(turn.status)) {
        streamController?.abort()
        if (sessionId) { const snapshot = await agentApi.session(sessionId); if (current === epoch) { mergeSession(snapshot); if (activeTurn.value?.turn_id === turnId) activeTurn.value.messages = [] } }
      }
    } catch (cause) { if (current === epoch) report(cause) }
  }
  async function loadProposal(proposalId: string) { try { const proposal = await agentApi.proposal(proposalId); proposals.value[proposalId] = proposal; if (proposal.operation_id) void refreshOperation(proposal.operation_id) } catch (cause) { report(cause) } }
  async function approve(proposalId: string) {
    const proposal = proposals.value[proposalId]
    if (!proposal || pendingActions.value[proposalId] || !canApprove(proposal, proposal.version)) return
    pendingActions.value[proposalId] = true; error.value = ''
    const current = epoch; const sessionId = session.value?.session_id
    try {
      const operation = await agentApi.approve(proposal); operations.value[operation.operation_id] = operation
      await loadProposal(proposalId); scheduleOperations()
      if (sessionId && current === epoch && session.value?.session_id === sessionId) {
        const snapshot = await agentApi.session(sessionId)
        if (current === epoch && session.value?.session_id === sessionId) mergeSession(snapshot)
      }
    }
    catch (cause) { report(cause); await loadProposal(proposalId) } finally { pendingActions.value[proposalId] = false }
  }
  async function reject(proposalId: string) { if (pendingActions.value[proposalId]) return; pendingActions.value[proposalId] = true; try { await agentApi.reject(proposalId); await loadProposal(proposalId) } catch (cause) { report(cause) } finally { pendingActions.value[proposalId] = false } }
  async function revise(proposalId: string, enabled: boolean) { if (pendingActions.value[proposalId]) return; pendingActions.value[proposalId] = true; try { proposals.value[proposalId] = await agentApi.revise(proposalId, enabled) } catch (cause) { report(cause); await loadProposal(proposalId) } finally { pendingActions.value[proposalId] = false } }
  async function refreshOperation(operationId: string) { try { operations.value[operationId] = await agentApi.operation(operationId); scheduleOperations() } catch (cause) { report(cause) } }
  function scheduleOperations() {
    if (!pollingEnabled || operationTimer) return
    const pending = Object.values(operations.value).filter(o => ['prepared', 'committing', 'accepted', 'running'].includes(o.status))
    if (!pending.length) return
    operationTimer = setTimeout(async () => { operationTimer = null; await Promise.all(pending.map(async operation => { try { operations.value[operation.operation_id] = await agentApi.operation(operation.operation_id) } catch { /* Preserve last known receipt while reconnecting. */ } })); scheduleOperations() }, 2000)
  }
  function disconnect() { pollingEnabled = false; ++epoch; streamController?.abort(); if (operationTimer) clearTimeout(operationTimer); operationTimer = null }
  return { config, sessions, session, activeTurn, proposals, operations, pendingActions, loading, sending, busy, messages, error, connection, initialize, openSession, newSession, removeSession, send, reconnect, cancel, loadProposal, approve, reject, revise, refreshOperation, disconnect }
})
