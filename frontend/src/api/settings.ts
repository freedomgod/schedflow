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
