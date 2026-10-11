export type TurnStatus = 'pending' | 'queued' | 'running' | 'streaming' | 'thinking' | 'tool_running' | 'cancelling' | 'cancelled' | 'completed' | 'failed' | 'interrupted'
export type ProposalStatus = 'pending' | 'awaiting_confirmation' | 'committing' | 'committed' | 'approved' | 'rejected' | 'expired' | 'stale' | 'superseded'
export type OperationStatus = 'prepared' | 'committing' | 'accepted' | 'running' | 'succeeded' | 'failed' | 'unknown'
export type MessageStatus = 'pending' | 'streaming' | 'completed' | 'cancelled' | 'failed' | 'interrupted'
export interface WorkflowSummary { job_id: string; name?: string; status?: string; trigger?: unknown; next_run_time?: string | null }
export type AgentBlock =
  | { type: 'assistant_text'; text: string }
  | { type: 'workflow_results'; jobs: WorkflowSummary[] }
  | { type: 'clarification'; text: string; options?: { label: string; value: string }[] }
  | { type: 'proposal'; proposal_id: string; version: number }
  | { type: 'operation_receipt' | 'execution'; operation_id: string }
  | { type: 'error'; message: string }
export interface AgentMessage { message_id: string; turn_id?: string; role: 'user' | 'assistant'; status: MessageStatus; blocks: AgentBlock[] }
export interface AgentTurn { turn_id: string; status: TurnStatus; last_seq?: number }
export interface AgentSession { last_seq?: number; session_id: string; title: string; created_at?: string; messages: AgentMessage[]; turns: AgentTurn[]; proposals: AgentProposal[] }
export interface CoreJob { workflow_timeout?: number | null; job_id?: string; name?: string; description?: string; enabled?: boolean; status?: string; workflow?: { nodes: Array<{ node_id: string; name?: string; retries?: number; timeout?: number; task: Record<string, unknown> }>; edges: Array<{ source: string; target: string; condition?: unknown }> }; trigger?: { type?: string; args?: Record<string, unknown> }; [key: string]: unknown }
export interface AgentProposal { run_timeout?: number | null; proposal_id: string; version: number; status: ProposalStatus; action: 'create' | 'update' | 'run'; job_id?: string; name?: string; before: CoreJob | null; after: CoreJob | null; payload: CoreJob; diff: Array<{ path: string; before: unknown; after: unknown }>; expires_at?: string; operation_id?: string }
export interface AgentOperation { operation_id: string; status: OperationStatus; action: string; job_id?: string; execution_id?: string; result?: unknown; error?: string }
export interface AgentConfig { enabled: boolean; configured: boolean; model: string; base_url?: string; reason?: string }
export type EventType = 'message.delta' | 'message.completed' | 'status' | 'proposal.created' | 'turn.completed' | 'turn.failed'
export interface AgentEvent { seq: number; turn_id: string; type: EventType; payload: Record<string, unknown> }
