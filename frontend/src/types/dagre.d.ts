declare module 'dagre' {
  export interface GraphLabel {
    rankdir?: string
    align?: string
    nodesep?: number
    edgesep?: number
    ranksep?: number
    marginx?: number
    marginy?: number
    [key: string]: unknown
  }

  export class Graph {
    constructor()
    setGraph(label: GraphLabel): void
    setDefaultEdgeLabel(callback: () => Record<string, unknown>): void
    setNode(id: string, label: { width: number; height: number }): void
    setEdge(source: string, target: string, label?: Record<string, unknown>): void
    node(id: string): { x: number; y: number; width: number; height: number } | undefined
  }

  export function layout(graph: Graph): void
  export { Graph as graphlib }
  export default layout
}
