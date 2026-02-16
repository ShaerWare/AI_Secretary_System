import { ref, watch } from 'vue'

export function useSidebarCollapse(storageKey: string) {
  const collapsed = ref(localStorage.getItem(storageKey) === 'true')
  watch(collapsed, (val) => localStorage.setItem(storageKey, String(val)))
  const toggle = () => { collapsed.value = !collapsed.value }
  return { collapsed, toggle }
}
