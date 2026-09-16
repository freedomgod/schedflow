import client from './client'

export interface ThemeInfo {
  theme: 'light' | 'dark'
}

export interface VariableItem {
  id: string
  name: string
  value: string
  description: string | null
  created_at: string
  updated_at: string
}

export function getTheme(): Promise<ThemeInfo> {
  return client.get('/settings/theme')
}

export function setTheme(theme: string): Promise<void> {
  return client.put('/settings/theme', { theme })
}

export function getVariables(): Promise<VariableItem[]> {
  return client.get('/settings/variables')
}

export function createVariable(data: { name: string; value: string; description?: string }): Promise<VariableItem> {
  return client.post('/settings/variables', data)
}

export function updateVariable(id: string, data: { name?: string; value?: string; description?: string }): Promise<VariableItem> {
  return client.put(`/settings/variables/${id}`, data)
}

export function deleteVariable(id: string): Promise<void> {
  return client.delete(`/settings/variables/${id}`)
}

export interface WebhookConfig {
  url: string
  events: string[]
  secret?: string | null
}

export interface RateLimitConfig {
  enabled: boolean
  rpm: number
}

export interface TimezoneInfo {
  /** Effective default timezone for newly scheduled work. */
  timezone: string
  /** Whether the operator picked one, or it follows the system zone. */
  configured: boolean
  /** Zone the backend process runs in (container TZ / /etc/localtime). */
  system_timezone: string
  /** IANA names known to the server (empty when the image lacks tzdata). */
  available: string[]
}

let timezoneInfo: TimezoneInfo | null = null

export async function getTimezone(force = false): Promise<TimezoneInfo> {
  if (!timezoneInfo || force) {
    const info: TimezoneInfo = await client.get('/settings/timezone')
    timezoneInfo = info
  }
  return timezoneInfo
}

export function setTimezone(timezone: string | null): Promise<TimezoneInfo> {
  const request: Promise<TimezoneInfo> = client.put('/settings/timezone', { timezone })
  return request.then((info) => {
    timezoneInfo = info
    return info
  })
}

/** IANA zones the current browser knows about; a superset is fine client-side. */
export function browserTimezones(): string[] {
  const supported = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] })
    .supportedValuesOf
  if (typeof supported === 'function') {
    try {
      return supported('timeZone')
    } catch {
      /* fall through to the single local zone */
    }
  }
  const local = Intl.DateTimeFormat().resolvedOptions().timeZone
  return local ? [local] : []
}

export function getWebhooks(): Promise<WebhookConfig[]> {
  return client.get('/settings/webhooks')
}

export function setWebhooks(webhooks: WebhookConfig[]): Promise<WebhookConfig[]> {
  return client.put('/settings/webhooks', { webhooks })
}

export function getRateLimit(): Promise<RateLimitConfig> {
  return client.get('/settings/rate-limit')
}

export function setRateLimit(config: RateLimitConfig): Promise<RateLimitConfig> {
  return client.put('/settings/rate-limit', config)
}

export interface WebhookTestResult {
  ok: boolean
  status_code: number | null
  error: string | null
  duration_ms: number
}

export function testWebhookDelivery(params: {
  url: string
  events?: string[]
  secret?: string
}): Promise<WebhookTestResult> {
  return client.post('/settings/webhooks/test', params)
}
