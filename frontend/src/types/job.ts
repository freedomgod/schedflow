import type { DagData } from './workflow'

export interface Job {
  id: string
  name: string
  description?: string
  job_status: string
  executor: string
  jobstore: string
  misfire_grace_time?: number
  coalesce?: boolean
  max_instances?: number
  next_run_time?: string
  func_ref?: string
  dag?: DagData | null
  trigger?: string | null
  trigger_args?: Record<string, unknown> | null
}

export interface JobCreateParams {
  func?: string
  func_ref?: string
  args?: unknown[]
  kwargs?: Record<string, unknown>
  task_type?: 'python_callable' | 'python' | 'python_script' | 'bash'
  script_path?: string
  script?: string
  command?: string
  dag?: DagData
  id?: string
  name?: string
  description?: string
  trigger?: string
  trigger_args?: Record<string, unknown>
  executor?: string
  jobstore?: string
  misfire_grace_time?: number
  coalesce?: boolean
  max_instances?: number
  next_run_time?: string
  replace_existing?: boolean
}

export interface JobUpdateParams {
  name?: string
  description?: string
  job_status?: string
  misfire_grace_time?: number
  coalesce?: boolean
  max_instances?: number
  next_run_time?: string
  executor?: string
  jobstore?: string
  dag?: DagData
  trigger?: string
  trigger_args?: Record<string, unknown>
}
