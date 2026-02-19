import { ref, watch } from 'vue'

export function useSidebarCollapse(storageKey: string) {
  const stored = localStorage.getItem(storageKey)
  const collapsed = ref(stored === null ? true : stored === 'true')
  watch(collapsed, (val) => localStorage.setItem(storageKey, String(val)))
  const toggle = () => { collapsed.value = !collapsed.value }
  return { collapsed, toggle }
}
