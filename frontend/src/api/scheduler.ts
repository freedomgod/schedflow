import { schedulerClient } from './client'
import type { SchedulerStatus } from '@/types'

export function getSchedulerStatus(): Promise<SchedulerStatus> {
  return (schedulerClient.get('/scheduler/status') as Promise<any>).then((data: any) => ({
    ...data,
    failed_jobstores: data.failed_jobstores || {},
    failed_executors: data.failed_executors || {},
  }))
}

export function pauseScheduler(): Promise<void> {
  return schedulerClient.post('/scheduler/pause')
}

export function resumeScheduler(): Promise<void> {
  return schedulerClient.post('/scheduler/resume')
}

export function startScheduler(): Promise<void> {
  return schedulerClient.post('/scheduler/start')
}

export function shutdownScheduler(): Promise<void> {
  return schedulerClient.post('/scheduler/shutdown')
}
