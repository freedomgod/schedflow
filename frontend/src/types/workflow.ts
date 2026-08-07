/** Task type union */
export type TaskType = 'python_callable' | 'python' | 'python_script' | 'bash'

/** 函数引用模型 — 对应后端 CallableModel */
export interface FuncRef {
  type?: TaskType
  ref?: string
  script_path?: string
  script?: string
  command?: string
  kwargs?: Record<string, unknown>
}

/** 任务节点属性 — LogicFlow 节点 properties 存储 */
export interface TaskNodeProperties {
  name: string
  description?: string
  type?: TaskType
  func_ref?: string
  script_path?: string
  script?: string
  command?: string
  kwargs: KeyValuePair[]
  done_callback_ref?: string
  stop_max_attempt_number?: number
}

/** 键值对 (kwargs 编辑器用) */
export interface KeyValuePair {
  key: string
  value: string
  type: 'string' | 'number' | 'boolean'
}

/** 任务节点模型 — 对应后端 TaskNodeModel (JSON 序列化) */
export interface TaskNodeData {
  task_id: string
  name?: string
  description?: string
  func: FuncRef
  done_callback?: FuncRef | null
  stop_max_attempt_number?: number
}

/** DAG 节点 — 对应后端 nodes 数组元素 */
export interface DagNode {
  node_id: string
  task_node: TaskNodeData
}

/** 边模型 — 对应后端 EdgeModel (JSON 序列化) */
export interface DagEdge {
  id?: string
  name?: string
  description?: string
  source: string
  target: string
}

/** 完整的 DAG 数据 — 对应后端 dag 字段 */
export interface DagData {
  flow_id?: string
  nodes: DagNode[]
  edges: DagEdge[]
}

/** 边属性 — 用于 EdgeConfigDrawer */
export interface EdgeProperties {
  name?: string
  description?: string
}

/** 节点执行记录 — 对应后端 node_records 中的条目 */
export interface NodeExecutionRecord {
  node_id: string
  task_id?: string
  node_name?: string
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'SKIPPED' | null
  start_time?: string | null
  end_time?: string | null
  duration?: number | null
  result?: string | null
  error?: string | null
  exit_code?: number | null
  stdout?: string | null
  stderr?: string | null
  skip_reason?: string | null
}

/** 执行日志 — 对应后端 WorkflowExecutionLog.to_dict() 返回 */
export interface ExecutionLog {
  flow_log_id: string
  flow_id?: string | null
  start_time?: string | null
  end_time?: string | null
  duration?: number | null
  node_records: Record<string, NodeExecutionRecord> | null
  dag?: DagData | null
}
