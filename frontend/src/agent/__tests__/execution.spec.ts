import { describe, expect, it } from 'vitest'
import { executionView } from '../execution'
describe('execution receipt projection', () => {
  it('projects actual node outcomes, duration and error from core execution logs', () => {
    const view = executionView({ log_id: 'log', duration: 2.5, succeeded: false, records: { a: { status: 'succeeded', duration: .4, stdout: 'hello' }, b: { status: 'failed', duration: 2.1, error: 'Process exited 1', stderr: 'bad' }, c: { status: 'skipped', skip_reason: 'upstream failed' } } })
    expect(view?.counts).toEqual({ total: 3, succeeded: 1, failed: 1, skipped: 1, running: 0, pending: 0 })
    expect(view?.duration).toBe(2.5); expect(view?.nodes[1].error).toBe('Process exited 1')
    expect(view?.nodes[2].skipReason).toBe('upstream failed')
  })
  it('never interprets a created job configuration as an execution log', () => {
    expect(executionView({ job_id: 'a', workflow: { nodes: [] } })).toBeNull()
  })
  it('bounds output display and preserves exact known statuses', () => {
    const view = executionView({ records: { a: { status: 'running', stdout: 'x'.repeat(10000) } } })
    expect(view?.nodes[0].status).toBe('running')
    expect(view?.nodes[0].stdout.length).toBeLessThan(8200)
    expect(view?.counts.succeeded).toBe(0)
  })
})
