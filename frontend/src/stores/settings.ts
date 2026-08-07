import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getTheme, setTheme as apiSetTheme,
  getVariables, createVariable as apiCreateVariable,
  updateVariable as apiUpdateVariable, deleteVariable as apiDeleteVariable,
} from '@/api/settings'
import type { VariableItem } from '@/api/settings'

export const useSettingsStore = defineStore('settings', () => {
  const theme = ref<'light' | 'dark'>('light')
  const variables = ref<VariableItem[]>([])
  const themeLoaded = ref(false)

  async function fetchTheme() {
    if (!localStorage.getItem('schedflow_token')) {
      themeLoaded.value = true
      return
    }
    try {
      const res = await getTheme()
      theme.value = res.theme
    } catch {
      theme.value = 'light'
    } finally {
      themeLoaded.value = true
    }
  }

  async function switchTheme(newTheme: 'light' | 'dark') {
    theme.value = newTheme
    await apiSetTheme(newTheme).catch(() => {})
  }

  async function fetchVariables() {
    if (!localStorage.getItem('schedflow_token')) {
      return
    }
    try {
      variables.value = await getVariables()
    } catch {
      variables.value = []
    }
  }

  async function createVariable(data: { name: string; value: string; description?: string }) {
    const result = await apiCreateVariable(data)
    variables.value.push(result)
  }

  async function updateVariable(id: string, data: { name?: string; value?: string; description?: string }) {
    const result = await apiUpdateVariable(id, data)
    const idx = variables.value.findIndex(v => v.id === id)
    if (idx !== -1) variables.value[idx] = result
  }

  async function deleteVariable(id: string) {
    await apiDeleteVariable(id)
    variables.value = variables.value.filter(v => v.id !== id)
  }

  return {
    theme, variables, themeLoaded,
    fetchTheme, switchTheme, fetchVariables,
    createVariable, updateVariable, deleteVariable,
  }
})
