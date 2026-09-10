import { schedulerClient } from './client'
import { logFromApi } from './mappers'
import type { ExecutionLog } from '@/types/workflow'
import type { RunSummary } from '@/types'

export function getJobLogs(jobId: string): Promise<ExecutionLog[]> {
  return (schedulerClient.get(`/jobs/${jobId}/logs`) as Promise<any>).then(
    (logs: any[]) => logs.map(logFromApi),
  )
}

export function getFlowLogDetail(jobId: string, flowLogId: string): Promise<ExecutionLog> {
  return (schedulerClient.get(`/jobs/${jobId}/logs/${flowLogId}`) as Promise<any>).then(
    logFromApi,
  )
}

export function getRuns(jobId: string): Promise<RunSummary[]> {
  return schedulerClient.get(`/jobs/${jobId}/runs`) as Promise<RunSummary[]>
}

export function getRunDetail(jobId: string, executionId: string): Promise<unknown> {
  return schedulerClient.get(`/jobs/${jobId}/runs/${executionId}`)
}
