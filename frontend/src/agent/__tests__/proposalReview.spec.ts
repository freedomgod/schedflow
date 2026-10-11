import { describe, expect, it } from 'vitest'
import { runTimeoutView } from '../proposalReview'
describe('run proposal timeout review', () => {
  it('shows an explicit run override instead of the workflow default', () => {
    expect(runTimeoutView({ run_timeout: 15, after: { workflow_timeout: 90 } })).toEqual({ seconds: 15, inherited: false })
  })
  it('falls back to the configured workflow timeout when no run override exists', () => {
    expect(runTimeoutView({ run_timeout: null, after: { workflow_timeout: 90 } })).toEqual({ seconds: 90, inherited: true })
  })
  it('does not invent a timeout when both settings are absent', () => {
    expect(runTimeoutView({ after: {} })).toEqual({ seconds: null, inherited: true })
  })
})
