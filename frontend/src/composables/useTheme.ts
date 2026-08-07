import { watch } from 'vue'
import { useSettingsStore } from '@/stores/settings'

export function useTheme() {
  const settingsStore = useSettingsStore()

  watch(
    () => settingsStore.theme,
    (val) => {
      document.documentElement.classList.toggle('dark', val === 'dark')
    },
    { immediate: true }
  )
}
