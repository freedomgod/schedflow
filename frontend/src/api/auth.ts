import client from './client'

export interface InitStatus {
  need_init: boolean
}

export interface AuthResult {
  user_id: string
  username: string
  token: string
}

export interface ApiKeyItem {
  id: string
  name: string
  key_prefix: string
  is_active: boolean
  last_used_at: string | null
  created_at: string
  expires_at: string | null
}

export interface ApiKeyCreateResult extends ApiKeyItem {
  plain_key: string
}

export function getInitStatus(): Promise<InitStatus> {
  return client.get('/auth/init-status')
}

export function initSetup(username: string, password: string): Promise<AuthResult> {
  return client.post('/auth/init-setup', { username, password })
}

export function login(username: string, password: string): Promise<AuthResult> {
  return client.post('/auth/login', { username, password })
}

export function getApiKeys(): Promise<ApiKeyItem[]> {
  return client.get('/auth/apikeys')
}

export function createApiKey(name: string): Promise<ApiKeyCreateResult> {
  return client.post('/auth/apikeys', { name })
}

export function updateApiKey(id: string, data: { name?: string; is_active?: boolean }): Promise<void> {
  return client.put(`/auth/apikeys/${id}`, data)
}

export function deleteApiKey(id: string): Promise<void> {
  return client.delete(`/auth/apikeys/${id}`)
}
