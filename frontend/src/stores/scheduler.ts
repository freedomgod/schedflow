import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSchedulerStatus, pauseScheduler, resumeScheduler, startScheduler } from '@/api/scheduler'
import type { SchedulerStatus } from '@/types'

export const useSchedulerStore = defineStore('scheduler', () => {
  const status = ref<SchedulerStatus | null>(null)
  const loading = ref(false)
  const busy = ref(false)

  const isRunning = computed(() => status.value?.state_name === 'RUNNING')
  const isPaused = computed(() => status.value?.state_name === 'PAUSED')
  const isStopped = computed(() => status.value?.state_name === 'STOPPED')

  async function fetchStatus(quiet = false) {
    if (!localStorage.getItem('schedflow_token')) return
    if (!quiet) loading.value = true
    try {
      status.value = await getSchedulerStatus()
    } finally {
      if (!quiet) loading.value = false
    }
  }

  /** Apply a state transition with an optimistic flip so the UI responds instantly. */
  async function runTransition(call: () => Promise<void>, nextState: string) {
    if (busy.value) return
    busy.value = true
    const previous = status.value
    if (status.value) {
      status.value = { ...status.value, state_name: nextState }
    }
    try {
      await call()
      await fetchStatus(true)
    } catch (error) {
      status.value = previous
      await fetchStatus(true).catch(() => {})
      throw error
    } finally {
      busy.value = false
    }
  }

  async function pause() {
    await runTransition(() => pauseScheduler(), 'PAUSED')
  }

  async function resume() {
    await runTransition(() => resumeScheduler(), 'RUNNING')
  }

  async function start() {
    await runTransition(() => startScheduler(), 'RUNNING')
  }

  /** Toggle between RUNNING / PAUSED / STOPPED based on the current state. */
  async function toggle() {
    if (busy.value) return
    if (isRunning.value) return pause()
    if (isPaused.value) return resume()
    return start()
  }

  return {
    status,
    loading,
    busy,
    isRunning,
    isPaused,
    isStopped,
    fetchStatus,
    pause,
    resume,
    start,
    toggle,
  }
})
