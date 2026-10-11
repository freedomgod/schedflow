export type NodeStatus = 'succeeded' | 'failed' | 'skipped' | 'running' | 'pending' | 'unknown'
export interface ExecutionNodeView { id: string; status: NodeStatus; duration?: number; error: string; stdout: string; stderr: string; skipReason: string }
export interface ExecutionView { logId?: string; duration?: number; counts: Record<Exclude<NodeStatus, 'unknown'> | 'total', number>; nodes: ExecutionNodeView[] }
function record(value: unknown): value is Record<string, unknown> { return !!value && typeof value === 'object' && !Array.isArray(value) }
function output(value: unknown): string { if (value === null || value === undefined) return ''; const text = typeof value === 'string' ? value : JSON.stringify(value); return text.length > 8000 ? `${text.slice(0, 8000)}\n…输出已截断，请查看完整执行日志。` : text }
export function executionView(result: unknown): ExecutionView | null {
  if (!record(result) || !record(result.records)) return null
  const counts = { total: 0, succeeded: 0, failed: 0, skipped: 0, running: 0, pending: 0 }
  const nodes: ExecutionNodeView[] = []
  for (const [id, node] of Object.entries(result.records)) {
    if (!record(node)) continue
    const rawStatus = String(node.status || '').toLowerCase()
    const status: NodeStatus = ['succeeded', 'failed', 'skipped', 'running', 'pending'].includes(rawStatus) ? rawStatus as NodeStatus : 'unknown'
    counts.total++; if (status !== 'unknown') counts[status]++
    nodes.push({ id, status, duration: typeof node.duration === 'number' ? node.duration : undefined, error: output(node.error), stdout: output(node.stdout), stderr: output(node.stderr), skipReason: output(node.skip_reason) })
  }
  return { logId: typeof result.log_id === 'string' ? result.log_id : undefined, duration: typeof result.duration === 'number' ? result.duration : undefined, counts, nodes }
}
export function nodeStatusLabel(status: NodeStatus): string { return { succeeded: '成功', failed: '失败', skipped: '跳过', running: '运行中', pending: '等待中', unknown: '状态待查询' }[status] }
