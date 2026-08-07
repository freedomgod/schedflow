export interface SchedulerStatus {
  state: number
  state_name: string
  job_count: number
  failed_jobstores: Record<string, string>
  failed_executors: Record<string, string>
}

export interface RescheduleParams {
  trigger: string
  trigger_args?: Record<string, unknown>
}
