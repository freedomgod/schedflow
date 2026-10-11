/** A link to a pending execution must never select an unrelated latest log. */
export function requestedExecutionIndex(logs: Array<{ flow_log_id: string }>, executionId: unknown): number {
  return typeof executionId === 'string' && executionId ? logs.findIndex(log => log.flow_log_id === executionId) : logs.length ? 0 : -1
}
