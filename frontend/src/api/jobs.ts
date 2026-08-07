import { schedulerClient } from './client'
import { jobCreatePayload, jobFromApi, jobUpdatePayload } from './mappers'
import type { Job, JobCreateParams, JobUpdateParams } from '@/types'

export function getJobs(): Promise<Job[]> {
  return (schedulerClient.get('/jobs') as Promise<any>).then((jobs: any[]) =>
    jobs.map(jobFromApi),
  )
}

export function getJob(id: string): Promise<Job> {
  return (schedulerClient.get(`/jobs/${id}`) as Promise<any>).then(jobFromApi)
}

export function createJob(params: JobCreateParams): Promise<Job> {
  return (schedulerClient.post('/jobs', jobCreatePayload(params)) as Promise<any>).then(
    jobFromApi,
  )
}

export function updateJob(id: string, params: JobUpdateParams): Promise<Job> {
  return (schedulerClient.put(`/jobs/${id}`, jobUpdatePayload(params)) as Promise<any>).then(
    jobFromApi,
  )
}

export function deleteJob(id: string): Promise<void> {
  return schedulerClient.delete(`/jobs/${id}`)
}

export function pauseJob(id: string): Promise<Job> {
  return (schedulerClient.post(`/jobs/${id}/pause`) as Promise<any>).then(jobFromApi)
}

export function resumeJob(id: string): Promise<Job> {
  return (schedulerClient.post(`/jobs/${id}/resume`) as Promise<any>).then(jobFromApi)
}

/**
 * EventSource cannot set Authorization headers, so the JWT is appended as a
 * query parameter for SSE endpoints (the backend accepts both forms).
 */
function sseAuthQuery(): string {
  const token = localStorage.getItem('schedflow_token')
  return token ? `?token=${encodeURIComponent(token)}` : ''
}

export function connectNextRunTimeSSE(
  jobId: string,
  onUpdate: (nextRunTime: string | null) => void,
  onError?: (error: string) => void,
): () => void {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  const url =
    `${baseUrl}/sse/jobs/${encodeURIComponent(jobId)}/next-run-time` +
    sseAuthQuery()
  const eventSource = new EventSource(url)

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if ('next_run_time' in data) {
        onUpdate(data.next_run_time ?? null)
      }
    } catch {
      // ignore parse errors
    }
  }

  // Do not close on error: EventSource reconnects automatically, which keeps
  // the next-run-time display live across transient network hiccups.
  eventSource.onerror = () => {
    onError?.('SSE connection error')
  }

  return () => {
    eventSource.close()
  }
}

export function connectAllJobsNextRunTimeSSE(
  onUpdate: (jobs: Record<string, string | null>) => void,
  onError?: (error: string) => void,
): () => void {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  const url = `${baseUrl}/sse/jobs/next-run-time${sseAuthQuery()}`
  const eventSource = new EventSource(url)

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.jobs && typeof data.jobs === 'object') {
        onUpdate(data.jobs as Record<string, string | null>)
      }
    } catch {
      // ignore parse errors
    }
  }

  eventSource.onerror = () => {
    onError?.('SSE connection error')
  }

  return () => {
    eventSource.close()
  }
}
