import type { CoreJob } from './types'
/** A per-run timeout overrides the stored workflow timeout only for this execution. */
export function runTimeoutView(proposal: { run_timeout?: number | null; after?: CoreJob | null; before?: CoreJob | null }): { seconds: number | null; inherited: boolean } {
  if (typeof proposal.run_timeout === 'number') return { seconds: proposal.run_timeout, inherited: false }
  const candidate = proposal.after || proposal.before
  return { seconds: typeof candidate?.workflow_timeout === 'number' ? candidate.workflow_timeout : null, inherited: true }
}
