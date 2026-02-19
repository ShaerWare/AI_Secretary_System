import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useSettingsStore = defineStore('settings', () => {
  // UI Settings (persisted to localStorage)
  const sidebarCollapsed = ref(true)
  const autoRefreshInterval = ref(5000) // ms
  const theme = ref<'dark' | 'light'>('dark')

  // Load from localStorage
  const savedSettings = localStorage.getItem('admin-settings')
  if (savedSettings) {
    try {
      const parsed = JSON.parse(savedSettings)
      sidebarCollapsed.value = parsed.sidebarCollapsed ?? true
      autoRefreshInterval.value = parsed.autoRefreshInterval ?? 5000
      theme.value = parsed.theme ?? 'dark'
    } catch {
      // Ignore parse errors
    }
  }

  // Persist to localStorage on change
  watch(
    [sidebarCollapsed, autoRefreshInterval, theme],
    () => {
      localStorage.setItem(
        'admin-settings',
        JSON.stringify({
          sidebarCollapsed: sidebarCollapsed.value,
          autoRefreshInterval: autoRefreshInterval.value,
          theme: theme.value,
        })
      )
    },
    { deep: true }
  )

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setAutoRefreshInterval(interval: number) {
    autoRefreshInterval.value = interval
  }

  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    document.documentElement.classList.toggle('dark', theme.value === 'dark')
  }

  return {
    sidebarCollapsed,
    autoRefreshInterval,
    theme,
    toggleSidebar,
    setAutoRefreshInterval,
    toggleTheme,
  }
})
