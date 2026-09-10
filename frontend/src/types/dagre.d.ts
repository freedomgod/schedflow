/**
 * Minimal typings for dagre 0.8.
 *
 * The package ships CommonJS (`module.exports = { graphlib, layout, ... }`) and
 * has no bundled types; `@types/dagre` describes an ESM shape that does not
 * match this runtime, so the surface the DAG editor uses is declared here.
 */
declare module 'dagre' {
  export interface DagreGraph {
    setGraph(label: Record<string, unknown>): DagreGraph
    setDefaultEdgeLabel(callback: () => Record<string, unknown>): DagreGraph
    setNode(id: string, label?: Record<string, unknown>): DagreGraph
    setEdge(source: string, target: string): DagreGraph
    node(id: string): { x: number; y: number } | undefined
  }

  export const graphlib: {
    Graph: new () => DagreGraph
  }

  export function layout(graph: DagreGraph): void

  const dagre: {
    graphlib: typeof graphlib
    layout: typeof layout
  }

  export default dagre
}
