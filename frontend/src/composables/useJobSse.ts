import { onBeforeUnmount } from 'vue'

export interface JobSseEvent {
  kind: string
  job_id?: string | null
  run_time?: string | null
  detail?: Record<string, unknown> | null
  record?: Record<string, unknown> | null
  log?: Record<string, unknown> | null
}

const EVENT_KINDS = [
  'job.started',
  'job.succeeded',
  'job.failed',
  'job.cancelled',
  'job.completed',
  'task.executed',
  'task.error',
  'task.skipped',
  'task.cancelled',
]

export function useJobSse(
  jobId: string,
  onEvent: (event: JobSseEvent) => void,
  onError?: (message: string) => void,
): () => void {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  const token = localStorage.getItem('schedflow_token')
  const query = token ? `?token=${encodeURIComponent(token)}` : ''
  const source = new EventSource(
    `${baseUrl}/sse/jobs/${encodeURIComponent(jobId)}/events${query}`,
  )

  const handler = (raw: MessageEvent) => {
    try {
      const payload = JSON.parse(raw.data) as JobSseEvent
      if (payload.kind) onEvent(payload)
    } catch {
      // ignore malformed event payloads
    }
  }

  source.onmessage = handler
  EVENT_KINDS.forEach((kind) => source.addEventListener(kind, handler as EventListener))
  source.onerror = () => onError?.('SSE connection error')

  const cleanup = () => {
    EVENT_KINDS.forEach((kind) =>
      source.removeEventListener(kind, handler as EventListener),
    )
    source.close()
  }
  onBeforeUnmount(cleanup)
  return cleanup
}
