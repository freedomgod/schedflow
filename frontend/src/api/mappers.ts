/**
 * Mappers between the backend JSON contract and the view-layer types.
 *
 * Views stay untouched: all conversion between the view-layer shapes
 * (DagData with task_node, uppercase statuses, flat trigger fields) and the
 * API payloads happens in this module.
 */

import type { Job, JobCreateParams, JobUpdateParams } from '@/types'
import type { DagData, ExecutionLog, NodeExecutionRecord } from '@/types/workflow'

/** Map a backend trigger type name to the editor's canonical lowercase type. */
export function normalizeTriggerType(name: string | null | undefined): string {
  if (!name) return 'cron'
  const map: Record<string, string> = {
    CronTrigger: 'cron',
    DateTrigger: 'date',
    IntervalTrigger: 'interval',
    CalendarIntervalTrigger: 'calendarinterval',
    AndTrigger: 'and',
    OrTrigger: 'or',
  }
  return map[name] || name || 'cron'
}

function normalizeTask(task: unknown): Record<string, unknown> {
  if (typeof task === 'string') {
    return { type: 'python_callable', ref: task }
  }
  const normalized = { ...((task || {}) as Record<string, unknown>) }
  // Legacy plural spelling from the old flow models; the REST API uses the
  // singular "python_script" as the canonical type.
  if (normalized.type === 'python_scripts') {
    normalized.type = 'python_script'
  }
  return normalized
}

/** workflow JSON -> DagData used by the workflow editor views. */
export function workflowToDag(workflow: any): DagData {
  return {
    nodes: (workflow?.nodes || []).map((node: any) => ({
      node_id: node.node_id,
      task_node: {
        task_id: node.node_id,
        name: node.name,
        description: node.description,
        func: normalizeTask(node.task),
        done_callback: node.on_success ? { ...node.on_success } : null,
        stop_max_attempt_number: node.retries ?? undefined,
      },
    })),
    edges: (workflow?.edges || []).map((edge: any) => ({
      id: edge.id,
      name: edge.name,
      description: edge.description,
      source: edge.source,
      target: edge.target,
    })),
  }
}

/** DagData -> workflow JSON. */
export function dagToWorkflow(dag?: DagData | null): any {
  return {
    flow_id: dag?.flow_id,
    nodes: (dag?.nodes || []).map((node) => ({
      node_id: node.node_id,
      task: normalizeTask(node.task_node?.func),
      name: node.task_node?.name,
      description: node.task_node?.description,
      retries: node.task_node?.stop_max_attempt_number,
      on_success: node.task_node?.done_callback
        ? { ...node.task_node.done_callback }
        : undefined,
    })),
    edges: (dag?.edges || []).map((edge) => ({
      source: edge.source,
      target: edge.target,
      name: edge.name,
      description: edge.description,
    })),
  }
}

/** job JSON -> the Job shape consumed by the views. */
export function jobFromApi(job: any): Job {
  const dag = job.workflow ? workflowToDag(job.workflow) : null
  const firstTask = dag?.nodes?.[0]?.task_node?.func
  return {
    id: job.job_id,
    name: job.name,
    description: job.description,
    job_status: (job.status || 'running').toUpperCase(),
    executor: job.executor_alias,
    jobstore: job.jobstore_alias,
    misfire_grace_time: job.misfire_grace_time,
    coalesce: job.coalesce,
    max_instances: job.max_instances,
    next_run_time: job.next_run_time,
    func_ref: typeof firstTask?.ref === 'string' ? firstTask.ref : undefined,
    dag,
    trigger: job.trigger?.type ?? null,
    trigger_args: job.trigger?.args ?? null,
  }
}

/** JobCreateParams -> create payload. */
export function jobCreatePayload(params: JobCreateParams): any {
  let workflow: any
  if (params.dag) {
    workflow = dagToWorkflow(params.dag)
  } else if (params.func || params.func_ref || params.task_type) {
    // Single-task quick-create: wrap into a one-node workflow.
    workflow = {
      nodes: [
        {
          node_id: 'task_1',
          task: {
            type: params.task_type || 'python_callable',
            ref: params.func_ref || params.func,
            script_path: params.script_path,
            script: params.script,
            command: params.command,
            args: params.args,
            kwargs: params.kwargs,
          },
        },
      ],
      edges: [],
    }
  }
  return {
    workflow,
    trigger: params.trigger
      ? { type: params.trigger, args: params.trigger_args || {} }
      : undefined,
    job_id: params.id,
    name: params.name,
    description: params.description,
    executor_alias: params.executor,
    jobstore_alias: params.jobstore,
    misfire_grace_time: params.misfire_grace_time,
    coalesce: params.coalesce,
    max_instances: params.max_instances,
    replace: params.replace_existing,
  }
}

/** JobUpdateParams -> update payload. */
export function jobUpdatePayload(params: JobUpdateParams): any {
  const result: Record<string, unknown> = {
    name: params.name,
    description: params.description,
    executor_alias: params.executor,
    jobstore_alias: params.jobstore,
    misfire_grace_time: params.misfire_grace_time,
    coalesce: params.coalesce,
    max_instances: params.max_instances,
  }
  if (params.dag) {
    result.workflow = dagToWorkflow(params.dag)
  }
  if (params.trigger) {
    result.trigger = { type: params.trigger, args: params.trigger_args || {} }
  }
  return result
}

/** execution log JSON -> the ExecutionLog shape consumed by the views. */
export function logFromApi(log: any): ExecutionLog {
  const dag = log.dag_snapshot ? workflowToDag(log.dag_snapshot) : null
  const nodeNames = new Map(
    (dag?.nodes || []).map((node) => [node.node_id, node.task_node?.name]),
  )
  const records: Record<string, NodeExecutionRecord> = {}
  for (const [nodeId, record] of Object.entries(log.records || {})) {
    const rec = record as any
    records[nodeId] = {
      ...rec,
      status: rec.status ? rec.status.toUpperCase() : null,
      node_name: nodeNames.get(nodeId) ?? rec.node_name,
    }
  }
  return {
    flow_log_id: log.log_id,
    flow_id: log.flow_id,
    start_time: log.start_time,
    end_time: log.end_time,
    duration: log.duration,
    node_records: records,
    dag,
  }
}
