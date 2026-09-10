import { describe, expect, it } from 'vitest'

import { computeDagreLayout } from '../dagreLayout'

const nodes = [
  { node_id: 'a', task_node: { name: 'a', func: { type: 'bash' } } },
  { node_id: 'b', task_node: { name: 'b', func: { type: 'python_script' } } },
] as any
const edges = [{ source: 'a', target: 'b' }] as any

describe('computeDagreLayout', () => {
  it('places every node for a two-node workflow', () => {
    const positions = computeDagreLayout(nodes, edges)

    expect(positions.size).toBe(2)
    for (const id of ['a', 'b']) {
      const pos = positions.get(id)!
      expect(Number.isFinite(pos.x)).toBe(true)
      expect(Number.isFinite(pos.y)).toBe(true)
    }
    expect(positions.get('b')!.y).toBeGreaterThan(positions.get('a')!.y)
  })

  it('returns an empty layout when there are no nodes', () => {
    expect(computeDagreLayout([], []).size).toBe(0)
  })
})
