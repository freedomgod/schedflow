import dagre from 'dagre'

import type { DagData, NodePosition } from '@/types/workflow'

/**
 * Compute top-to-bottom node positions with dagre.
 *
 * ``dagre`` 0.8 (pulled in by @logicflow/layout) exports ``{ graphlib, layout }``
 * rather than a ``Graph`` class or a callable default, so the layout entry
 * points are ``new dagre.graphlib.Graph()`` and ``dagre.layout(graph)``.
 * A layout failure must not blank the canvas, hence the grid fallback.
 */
export function computeDagreLayout(
  nodes: DagData['nodes'],
  edges: DagData['edges'],
): Map<string, NodePosition> {
  const positions = new Map<string, NodePosition>()
  if (nodes.length === 0) return positions

  const grid = () =>
    new Map<string, NodePosition>(
      nodes.map((node, index) => [
        node.node_id,
        { x: 120, y: 100 + index * 90 },
      ]),
    )

  try {
    const g = new dagre.graphlib.Graph()
    g.setGraph({
      rankdir: 'TB',
      nodesep: 60,
      ranksep: 80,
      marginx: 80,
      marginy: 80,
    })
    g.setDefaultEdgeLabel(() => ({}))
    for (const node of nodes) {
      g.setNode(node.node_id, { width: 150, height: 50 })
    }
    for (const edge of edges) {
      g.setEdge(edge.source, edge.target)
    }
    dagre.layout(g)
    for (const node of nodes) {
      const pos = g.node(node.node_id)
      if (pos) positions.set(node.node_id, { x: pos.x, y: pos.y })
    }
  } catch (error) {
    console.error('Dagre layout error, falling back to grid:', error)
    return grid()
  }
  return positions.size > 0 ? positions : grid()
}
