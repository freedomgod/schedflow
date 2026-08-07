<template>
  <div class="workflow-editor">
    <div v-if="!props.readonly" class="wf-toolbar">
      <el-button size="small" @click="addNode">添加节点</el-button>
      <el-button size="small" @click="lfInstance?.zoom(true)">放大</el-button>
      <el-button size="small" @click="lfInstance?.zoom(false)">缩小</el-button>
      <el-button size="small" @click="lfInstance?.resetZoom()">重置缩放</el-button>
      <span class="wf-hint">点击节点/边可编辑 | 从节点拖拽可创建连线 | 滚轮缩放</span>
    </div>

    <div class="wf-canvas-wrapper">
      <div ref="containerRef" class="lf-canvas"></div>

      <transition name="panel-slide">
        <div v-if="nodeDrawerVisible" class="wf-side-panel">
          <NodeConfigDrawer
            v-model:visible="nodeDrawerVisible"
            :node-data="selectedNodeData"
            @save="onNodeSave"
            @delete="onNodeDelete"
          />
        </div>
      </transition>
      <transition name="panel-slide">
        <div v-if="edgeDrawerVisible" class="wf-side-panel">
          <EdgeConfigDrawer
            v-model:visible="edgeDrawerVisible"
            :edge-data="selectedEdgeData"
            @save="onEdgeSave"
            @delete="onEdgeDelete"
          />
        </div>
      </transition>
    </div>

    <div
      v-if="contextMenuVisible"
      class="wf-context-menu"
      :style="{ left: contextMenuX + 'px', top: contextMenuY + 'px', position: 'fixed' }"
      @click.stop
    >
      <div class="wf-context-menu-item" @click="handleContextMenuCopy">复制节点</div>
      <div class="wf-context-menu-item" @click="handleContextMenuEdit">编辑节点</div>
      <div class="wf-context-menu-item wf-context-menu-item--danger" @click="handleContextMenuDelete">删除节点</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import LogicFlow, { RectNode, RectNodeModel, h } from '@logicflow/core'
import dagre, { graphlib } from 'dagre'
import NodeConfigDrawer from './NodeConfigDrawer.vue'
import EdgeConfigDrawer from './EdgeConfigDrawer.vue'
import type { DagData, EdgeProperties, TaskNodeProperties, KeyValuePair } from '@/types/workflow'
import type { JSX } from 'preact'

// ── Node type color config (fill + stroke, no emoji) ──
const NODE_TYPE_STYLES: Record<string, { fill: string; stroke: string }> = {
  python_callable: { fill: 'rgba(59, 130, 246, 0.12)', stroke: '#3B82F6' },
  python: { fill: 'rgba(59, 130, 246, 0.12)', stroke: '#3B82F6' },
  python_script: { fill: 'rgba(59, 130, 246, 0.12)', stroke: '#3B82F6' },
  bash: { fill: 'rgba(217, 119, 6, 0.10)', stroke: '#D97706' },
}

function getNodeStyle(nodeType: string) {
  return NODE_TYPE_STYLES[nodeType] || NODE_TYPE_STYLES['python_callable']
}

// ── Inline SVG icon renderers for Python / Bash ──
function renderIcon(nodeType: string, nodeHeight: number, nodeX: number, nodeY: number): JSX.Element {
  const iconY = nodeY + (nodeHeight - 20) / 2
  const iconX = nodeX + 10
  const isBash = nodeType === 'bash'

  const pythonPaths = [
    h('path', { d: 'M420.693333 85.333333C353.28 85.333333 298.666667 139.946667 298.666667 207.36v71.68h183.04c16.64 0 30.293333 24.32 30.293333 40.96H207.36C139.946667 320 85.333333 374.613333 85.333333 442.026667v161.322666c0 67.413333 54.613333 122.026667 122.026667 122.026667h50.346667v-114.346667c0-67.413333 54.186667-122.026667 121.6-122.026666h224c67.413333 0 122.026667-54.229333 122.026666-121.642667V207.36C725.333333 139.946667 670.72 85.333333 603.306667 85.333333z m-30.72 68.693334c17.066667 0 30.72 5.12 30.72 30.293333s-13.653333 38.016-30.72 38.016c-16.64 0-30.293333-12.8-30.293333-37.973333s13.653333-30.336 30.293333-30.336z', fill: '#3C78AA' }),
    h('path', { d: 'M766.250667 298.666667v114.346666a121.6 121.6 0 0 1-121.6 121.984H420.693333A121.6 121.6 0 0 0 298.666667 656.597333v160a122.026667 122.026667 0 0 0 122.026666 122.026667h182.613334A122.026667 122.026667 0 0 0 725.333333 816.64v-71.68h-183.082666c-16.64 0-30.250667-24.32-30.250667-40.96h304.64A122.026667 122.026667 0 0 0 938.666667 581.973333v-161.28a122.026667 122.026667 0 0 0-122.026667-122.026666zM354.986667 491.221333l-0.170667 0.170667c0.512-0.085333 1.066667-0.042667 1.621333-0.170667z m279.04 310.442667c16.64 0 30.293333 12.8 30.293333 37.973333a30.293333 30.293333 0 0 1-30.293333 30.293334c-17.066667 0-30.72-5.12-30.72-30.293334s13.653333-37.973333 30.72-37.973333z', fill: '#FDD835' }),
  ]

  const bashPaths = [
    h('path', { d: 'M917.333333 835.413333H106.666667V188.586667h810.666666zM186.666667 755.413333h650.666666V268.586667H186.666667z', fill: '#00C1DE' }),
    h('path', { d: 'M343.04 648.746667l-56.533333-56.533334 88.32-88.32-88.32-88.32 56.533333-56.746666 144.853333 145.066666-144.853333 144.853334zM507.093333 585.173333h230.4v80h-230.4z', fill: '#00C1DE' }),
  ]

  return h('g', { transform: `translate(${iconX}, ${iconY})` }, [
    h('svg', { width: '20', height: '20', viewBox: '0 0 1024 1024' },
      isBash ? bashPaths : pythonPaths
    ),
  ])
}

// ── Custom LogicFlow node with type-icon badge ──
// LogicFlow uses (x, y) as the node CENTER, so we offset rect drawing by -w/2, -h/2
class TaskNodeView extends RectNode {
  getShape() {
    const { model } = this.props
    const { width, height, x, y } = model
    const style = model.getNodeStyle()
    const properties = model.getProperties() as Partial<TaskNodeProperties>
    const nodeType = properties?.type || 'python_callable'
    const nodeStyle = getNodeStyle(nodeType)

    const rectX = Number(x) - Number(width) / 2
    const rectY = Number(y) - Number(height) / 2

    return h('g', {}, [
      h('rect', {
        ...style,
        x: String(rectX), y: String(rectY),
        width: String(width), height: String(height),
        fill: nodeStyle.fill,
        stroke: style.stroke || nodeStyle.stroke,
        strokeWidth: style.strokeWidth || 2,
        rx: style.rx || 8,
        ry: style.ry || 8,
      }),
      renderIcon(nodeType, Number(height), rectX, rectY),
    ])
  }
}
class TaskNodeModel extends RectNodeModel {
  setAttributes() {
    super.setAttributes()
    // Center the text label at the node center (x, y)
    this.text.x = this.x
    this.text.y = this.y
  }
}

const props = defineProps<{
  readonly?: boolean
  nodeStatusMap?: Record<string, string>
}>()

const emit = defineEmits<{
  'update:dagData': [data: DagData]
  'node-click': [nodeId: string, nodeData: TaskNodeProperties | null]
  'canvas-click': []
}>()

const containerRef = ref<HTMLElement | null>(null)
const lfInstance = ref<LogicFlow | null>(null)

const nodeDrawerVisible = ref(false)
const edgeDrawerVisible = ref(false)
const selectedNodeData = ref<TaskNodeProperties | null>(null)
const selectedEdgeData = ref<EdgeProperties | null>(null)
const activeNodeId = ref('')
const activeEdgeId = ref('')

const contextMenuVisible = ref(false)
const contextMenuX = ref(0)
const contextMenuY = ref(0)
const contextMenuNodeId = ref('')

const selectedNodeId = ref('')
const nodeStatusColors = ref<Map<string, string>>(new Map())
let isLoadingDag = false

function selectNode(nodeId: string) {
  if (selectedNodeId.value && lfInstance.value) {
    const prevNode = lfInstance.value.getNodeModelById(selectedNodeId.value)
    if (prevNode) {
      const prevColor = nodeStatusColors.value.get(selectedNodeId.value) || 'rgba(255,255,255,0.25)'
      prevNode.setStyles({ strokeWidth: 1, stroke: prevColor })
    }
  }
  if (lfInstance.value) {
    const node = lfInstance.value.getNodeModelById(nodeId)
    if (node) {
      node.setStyles({ strokeWidth: 2, stroke: '#3B82F6' })
    }
  }
  selectedNodeId.value = nodeId
}

function hideContextMenu() {
  contextMenuVisible.value = false
  contextMenuNodeId.value = ''
}

function applyAutoLayout() {
  if (!lfInstance.value) return

  const graphData = lfInstance.value.getGraphData()
  const rawNodes = (graphData.nodes || []) as Array<{ id: string }>
  const rawEdges = (graphData.edges || []) as Array<{ id: string; sourceNodeId: string; targetNodeId: string }>

  if (rawNodes.length === 0) return

  const g = new graphlib.Graph()
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 80, marginx: 80, marginy: 80 })
  g.setDefaultEdgeLabel(() => ({}))

  rawNodes.forEach((node) => {
    g.setNode(node.id, { width: 150, height: 50 })
  })
  rawEdges.forEach((edge) => {
    g.setEdge(edge.sourceNodeId, edge.targetNodeId)
  })

  try {
    dagre.layout(g)
  } catch (e) {
    console.error('Dagre layout error:', e)
    return
  }

  rawNodes.forEach((node) => {
    const pos = g.node(node.id)
    if (pos) {
      const nodeModel = lfInstance.value!.getNodeModelById(node.id)
      if (nodeModel) {
        nodeModel.moveTo(pos.x, pos.y)
        if (props.readonly) {
          nodeModel.draggable = false
        }
      }
    }
  })
}

function syncReadonlyState() {
  if (!lfInstance.value) return
  const lf = lfInstance.value
  const ro = props.readonly

  lf.updateEditConfig({
    textEdit: !ro,
    nodeTextEdit: !ro,
    edgeTextEdit: !ro,
    nodeTextMode: 'text',
    stopMoveGraph: false,
    stopZoomGraph: false,
  })

  const graphData = lf.getGraphData()
  const allNodes = (graphData.nodes || []) as Array<{ id: string }>
  for (const node of allNodes) {
    const nodeModel = lf.getNodeModelById(node.id)
    if (nodeModel) {
      nodeModel.draggable = !ro
      if (ro) {
        nodeModel.setTextMode('label' as any)
      }
    }
  }
}

watch(() => props.readonly, (isReadonly) => {
  syncReadonlyState()
  if (isReadonly) {
    nodeDrawerVisible.value = false
    edgeDrawerVisible.value = false
    activeNodeId.value = ''
    activeEdgeId.value = ''
  }
})

onMounted(() => {
  if (!containerRef.value) return

  const lf = new LogicFlow({
    container: containerRef.value,
    grid: !props.readonly ? {
      size: 20,
      type: 'dot',
      config: { color: 'rgba(128,128,128,0.15)' },
    } : false,
    isSilentMode: false,
    keyboard: { enabled: !props.readonly },
    stopScrollGraph: true,
    style: {
      rect: { rx: 8, ry: 8, strokeWidth: 1.5 },
    },
  })

  lf.on('node:click', ({ data }) => {
    const nodeId = (data as { id: string }).id
    selectNode(nodeId)
    hideContextMenu()
    if (props.readonly) {
      const nodeModel = lf.getNodeModelById(nodeId)
      const properties = (nodeModel?.getProperties() as TaskNodeProperties) || null
      emit('node-click', nodeId, properties)
    } else {
      activeNodeId.value = nodeId
      selectedNodeData.value =
        ((data as { properties?: TaskNodeProperties }).properties as TaskNodeProperties) || null
      nodeDrawerVisible.value = true
    }
  })

  lf.on('node:dbclick', ({ e }) => {
    if (props.readonly) {
      ;(e as MouseEvent).preventDefault()
      ;(e as MouseEvent).stopPropagation()
    }
  })

  lf.on('node:contextmenu', ({ data, e }) => {
    if (props.readonly) return
    const nodeId = (data as { id: string }).id
    selectNode(nodeId)
    contextMenuNodeId.value = nodeId
    contextMenuX.value = (e as MouseEvent).clientX
    contextMenuY.value = (e as MouseEvent).clientY
    contextMenuVisible.value = true
  })

  lf.on('edge:click', ({ data }) => {
    if (props.readonly) return
    activeEdgeId.value = (data as { id: string }).id
    selectedEdgeData.value =
      ((data as { properties?: EdgeProperties }).properties as EdgeProperties) || null
    edgeDrawerVisible.value = true
    hideContextMenu()
  })

  lf.on('edge:add', ({ data }) => {
    if (props.readonly && !isLoadingDag) {
      const edgeId = (data as { id: string }).id
      nextTick(() => {
        lf.deleteEdge(edgeId)
      })
    }
  })

  lf.on('blank:click', () => {
    if (selectedNodeId.value && lfInstance.value) {
      const prevNode = lfInstance.value.getNodeModelById(selectedNodeId.value)
      if (prevNode) {
        const prevColor = nodeStatusColors.value.get(selectedNodeId.value) || 'rgba(255,255,255,0.25)'
        prevNode.setStyles({ strokeWidth: 1, stroke: prevColor })
      }
    }
    selectedNodeId.value = ''
    hideContextMenu()
    if (props.readonly) {
      emit('canvas-click')
    }
  })

  lf.register({ type: 'task-node', view: TaskNodeView, model: TaskNodeModel })
  // Apply dark-mode-optimized text theme
  lf.setTheme({
    nodeText: { color: 'rgba(255,255,255,0.90)', fontSize: 12, fontWeight: 500 },
    edgeText: { color: 'rgba(255,255,255,0.60)', fontSize: 11 },
  })
  lf.render({})

  if (props.readonly) {
    lf.updateEditConfig({ textEdit: false, nodeTextEdit: false, edgeTextEdit: false })
  }

  containerRef.value.addEventListener('wheel', (e) => {
    e.preventDefault()
    if (e.deltaY < 0) {
      lf.zoom(true)
    } else {
      lf.zoom(false)
    }
  }, { passive: false })

  document.addEventListener('click', hideContextMenu)
  lfInstance.value = lf
})

onBeforeUnmount(() => {
  document.removeEventListener('click', hideContextMenu)
  if (lfInstance.value) {
    lfInstance.value.destroy()
    lfInstance.value = null
  }
})

function emitDagUpdate() {
  emit('update:dagData', getDagData())
}

function addNode() {
  if (!lfInstance.value) return

  const nodeId = `node_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
  const x = 100 + Math.random() * 300
  const y = 100 + Math.random() * 200

  const properties: TaskNodeProperties = {
    name: '新节点',
    type: 'python_callable',
    func_ref: '',
    script_path: '',
    script: '',
    command: '',
    kwargs: [],
    done_callback_ref: '',
    stop_max_attempt_number: undefined,
  }

  const nodeStyle = getNodeStyle('python_callable')
  const nodeModel = lfInstance.value.addNode({
    type: 'task-node',
    x,
    y,
    id: nodeId,
    properties,
    text: '新节点',
  })
  nodeModel.setStyles({
    fill: nodeStyle.fill,
    stroke: nodeStyle.stroke,
    strokeWidth: 2,
  })

  nextTick(() => {
    applyAutoLayout()
    nextTick(() => {
      lfInstance.value?.resetZoom()
    })
  })

  emitDagUpdate()
}

function handleContextMenuCopy() {
  if (!lfInstance.value || !contextMenuNodeId.value) return
  const nodeModel = lfInstance.value.getNodeModelById(contextMenuNodeId.value)
  if (!nodeModel) return

  const copiedProps = { ...(nodeModel.getProperties() as TaskNodeProperties) }
  const newNodeId = `node_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
  const pos = nodeModel.getData() as { x: number; y: number }

  const nodeStyle = getNodeStyle(copiedProps.type || 'python_callable')
  const copiedModel = lfInstance.value.addNode({
    type: 'task-node',
    x: pos.x + 50,
    y: pos.y + 50,
    id: newNodeId,
    properties: copiedProps,
    text: copiedProps.name || '新节点',
  })
  copiedModel.setStyles({
    fill: nodeStyle.fill,
    stroke: nodeStyle.stroke,
    strokeWidth: 2,
  })

  hideContextMenu()
  emitDagUpdate()
}

function handleContextMenuEdit() {
  if (!lfInstance.value || !contextMenuNodeId.value) return
  const nodeModel = lfInstance.value.getNodeModelById(contextMenuNodeId.value)
  if (!nodeModel) return

  activeNodeId.value = contextMenuNodeId.value
  selectedNodeData.value = (nodeModel.getProperties() as TaskNodeProperties) || null
  nodeDrawerVisible.value = true
  hideContextMenu()
}

function handleContextMenuDelete() {
  if (!lfInstance.value || !contextMenuNodeId.value) return
  lfInstance.value.deleteNode(contextMenuNodeId.value)
  if (selectedNodeId.value === contextMenuNodeId.value) {
    selectedNodeId.value = ''
  }
  hideContextMenu()
  emitDagUpdate()
}

function onNodeSave(data: TaskNodeProperties) {
  if (!lfInstance.value || !activeNodeId.value) return
  const nodeModel = lfInstance.value.getNodeModelById(activeNodeId.value)
  if (nodeModel) {
    const nodeStyle = getNodeStyle(data.type || 'python_callable')
    nodeModel.setProperties(data)
    nodeModel.updateText(data.name || '未命名')
    nodeModel.setStyles({
      fill: nodeStyle.fill,
      stroke: nodeStyle.stroke,
      strokeWidth: 2,
    })
  }
  nodeDrawerVisible.value = false
  activeNodeId.value = ''
  emitDagUpdate()
}

function onNodeDelete() {
  if (!lfInstance.value || !activeNodeId.value) return
  lfInstance.value.deleteNode(activeNodeId.value)
  nodeDrawerVisible.value = false
  activeNodeId.value = ''
  emitDagUpdate()
}

function onEdgeSave(data: EdgeProperties) {
  if (!lfInstance.value || !activeEdgeId.value) return
  lfInstance.value.setProperties(activeEdgeId.value, {
    name: data.name ?? '',
    description: data.description ?? '',
  })
  const edgeModel = lfInstance.value.getEdgeModelById(activeEdgeId.value)
  if (edgeModel && data.name) {
    lfInstance.value.updateText(activeEdgeId.value, data.name)
  }
  edgeDrawerVisible.value = false
  activeEdgeId.value = ''
  emitDagUpdate()
}

function onEdgeDelete() {
  if (!lfInstance.value || !activeEdgeId.value) return
  lfInstance.value.deleteEdge(activeEdgeId.value)
  edgeDrawerVisible.value = false
  activeEdgeId.value = ''
  emitDagUpdate()
}

function convertKwargs(kwargs: KeyValuePair[]): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const kv of kwargs) {
    if (!kv.key.trim()) continue
    switch (kv.type) {
      case 'number': {
        const num = parseFloat(kv.value)
        result[kv.key] = Number.isNaN(num) ? kv.value : num
        break
      }
      case 'boolean':
        result[kv.key] = kv.value === 'true'
        break
      default:
        result[kv.key] = kv.value
    }
  }
  return result
}

function getDagData(): DagData {
  if (!lfInstance.value) {
    return { nodes: [], edges: [] }
  }

  const graphData = lfInstance.value.getGraphData() as LogicFlow.GraphData
  const rawNodes = graphData.nodes as Array<{
    id: string
    properties?: TaskNodeProperties
  }>
  const rawEdges = graphData.edges as Array<{
    id: string
    properties?: { name?: string; description?: string }
    sourceNodeId: string
    targetNodeId: string
  }>

  return {
    nodes: rawNodes.map((node) => ({
      node_id: node.id,
      task_node: {
        task_id: node.id,
        name: node.properties?.name || '',
        description: node.properties?.description || '',
        func: {
          type: node.properties?.type || 'python_callable',
          ref: node.properties?.func_ref || undefined,
          script_path: node.properties?.script_path || undefined,
          script: node.properties?.script || undefined,
          command: node.properties?.command || undefined,
          kwargs: convertKwargs(node.properties?.kwargs || []),
        },
        done_callback: node.properties?.done_callback_ref
          ? { ref: node.properties.done_callback_ref }
          : null,
        stop_max_attempt_number:
          node.properties?.stop_max_attempt_number ?? undefined,
      },
    })),
    edges: rawEdges.map((edge) => ({
      id: edge.id,
      name: edge.properties?.name || '',
      description: edge.properties?.description || '',
      source: edge.sourceNodeId,
      target: edge.targetNodeId,
    })),
  }
}

function inferType(value: unknown): KeyValuePair['type'] {
  if (value === null || value === undefined) return 'string'
  const t = typeof value
  if (t === 'number') return 'number'
  if (t === 'boolean') return 'boolean'
  return 'string'
}

function computeDagreLayout(data: DagData): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()

  if (data.nodes.length === 0) return positions

  const g = new graphlib.Graph()
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 80, marginx: 80, marginy: 80 })
  g.setDefaultEdgeLabel(() => ({}))

  for (const node of data.nodes) {
    g.setNode(node.node_id, { width: 150, height: 50 })
  }
  for (const edge of data.edges) {
    g.setEdge(edge.source, edge.target)
  }

  try {
    dagre.layout(g)
  } catch (e) {
    console.error('Dagre layout error:', e)
    return positions
  }

  for (const node of data.nodes) {
    const pos = g.node(node.node_id)
    if (pos) {
      positions.set(node.node_id, { x: pos.x, y: pos.y })
    }
  }

  return positions
}

function loadDag(data: DagData) {
  if (!lfInstance.value) return

  const isReadonly = props.readonly
  const lf = lfInstance.value

  isLoadingDag = true
  nodeStatusColors.value.clear()
  lf.clearData()

  const positions = computeDagreLayout(data)

  for (const dagNode of data.nodes) {
    const pos = positions.get(dagNode.node_id)

    const nodeProps: TaskNodeProperties = {
      name: dagNode.task_node.name || '',
      description: dagNode.task_node.description || '',
      type: dagNode.task_node.func?.type || 'python_callable',
      func_ref: dagNode.task_node.func?.ref || '',
      script_path: dagNode.task_node.func?.script_path || '',
      script: dagNode.task_node.func?.script || '',
      command: dagNode.task_node.func?.command || '',
      kwargs: Object.entries(dagNode.task_node.func?.kwargs || {}).map(
        ([key, value]) => ({
          key,
          value: String(value),
          type: inferType(value),
        }),
      ),
      done_callback_ref: dagNode.task_node.done_callback?.ref || '',
      stop_max_attempt_number: dagNode.task_node.stop_max_attempt_number,
    }

    const nodeType = dagNode.task_node.func?.type || 'python_callable'
    const nodeStyle = getNodeStyle(nodeType)
    const nodeModel = lf.addNode({
      type: 'task-node',
      id: dagNode.node_id,
      x: pos ? pos.x : 100,
      y: pos ? pos.y : 100,
      properties: nodeProps,
      text: dagNode.task_node.name || '未命名',
    })
    nodeModel.setStyles({
      fill: nodeStyle.fill,
      stroke: nodeStyle.stroke,
      strokeWidth: 2,
    })

    if (isReadonly) {
      nodeModel.setTextMode('label' as any)
    }

    const status = props.nodeStatusMap?.[dagNode.node_id]
    if (status) {
      const colorMap: Record<string, string> = {
        'SUCCEEDED': '#22C55E',
        'FAILED': '#EF4444',
        'SKIPPED': '#F59E0B',
        'RUNNING': '#3B82F6',
        'PENDING': 'rgba(255,255,255,0.25)',
      }
      const strokeColor = colorMap[status] || 'rgba(255,255,255,0.25)'
      nodeStatusColors.value.set(dagNode.node_id, strokeColor)
      nodeModel.setStyles({ fill: nodeStyle.fill, stroke: strokeColor, strokeWidth: 2.5 })
    }
  }

  for (const dagEdge of data.edges) {
    lf.addEdge({
      type: 'polyline',
      id: dagEdge.id,
      sourceNodeId: dagEdge.source,
      targetNodeId: dagEdge.target,
      properties: {
        name: dagEdge.name || '',
        description: dagEdge.description || '',
      },
    })
  }

  nextTick(() => {
    const graphData = lf.getGraphData()
    const allNodes = (graphData.nodes || []) as Array<{ id: string }>

    for (const node of allNodes) {
      const nodeModel = lf.getNodeModelById(node.id)
      if (nodeModel) {
        if (isReadonly) {
          nodeModel.draggable = false
          nodeModel.setTextMode('label' as any)
        } else {
          nodeModel.draggable = true
        }
      }
    }

    if (isReadonly) {
      lf.updateEditConfig({ textEdit: false, nodeTextEdit: false, edgeTextEdit: false })
    }

    nextTick(() => {
      lf.resetZoom()
      isLoadingDag = false
    })
  })
}

defineExpose({
  getDagData,
  loadDag,
  addNode,
})
</script>

<style scoped>
.workflow-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.wf-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  flex-shrink: 0;
  background: var(--glass-bg);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--glass-border);
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
}

.wf-toolbar :deep(.el-button) {
  font-size: 12px;
}

.wf-hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
}

.wf-canvas-wrapper {
  flex: 1;
  position: relative;
  overflow: hidden;
  min-height: 400px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--bg-deep);
}

.lf-canvas {
  width: 100%;
  height: 100%;
}

/* Canvas theme: dark dot-grid background */
.lf-canvas :deep(svg:not([class])) {
  background: var(--bg-deep) !important;
}
.lf-canvas :deep(.lf-graph) {
  background: var(--bg-deep) !important;
}
.lf-canvas :deep(.lf-background) {
  fill: var(--bg-deep) !important;
}

/* Glass side panel */
.wf-side-panel {
  position: absolute;
  top: 0;
  right: 0;
  width: 480px;
  height: 100%;
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-left: 1px solid var(--glass-border);
  box-shadow: var(--shadow-lg);
  z-index: 100;
  overflow-y: auto;
}

/* Glass context menu */
.wf-context-menu {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  padding: 4px 0;
  z-index: 1000;
  min-width: 120px;
}

.wf-context-menu-item {
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary);
  transition: background var(--transition-fast);
}

.wf-context-menu-item:hover {
  background: var(--bg-surface-hover);
}

.wf-context-menu-item--danger {
  color: var(--color-danger);
}

.wf-context-menu-item--danger:hover {
  background: var(--color-danger-soft);
}
</style>
