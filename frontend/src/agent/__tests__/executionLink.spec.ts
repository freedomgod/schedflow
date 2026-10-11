import { describe, expect, it } from 'vitest'
import { requestedExecutionIndex } from '../../utils/executionLink'
describe('execution log navigation', () => {
  it('opens the requested execution rather than the latest unrelated log', () => {
    expect(requestedExecutionIndex([{ flow_log_id: 'latest' }, { flow_log_id: 'requested' }], 'requested')).toBe(1)
  })
  it('does not substitute another execution if the requested result is still pending', () => {
    expect(requestedExecutionIndex([{ flow_log_id: 'latest' }], 'missing')).toBe(-1)
    expect(requestedExecutionIndex([{ flow_log_id: 'latest' }], undefined)).toBe(0)
  })
})
