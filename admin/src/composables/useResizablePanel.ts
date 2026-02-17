import { ref, onUnmounted } from 'vue'

export function useResizablePanel(
  storageKey: string,
  defaultWidth: number,
  minWidth: number,
  maxWidth: number,
  direction: 'right' | 'left' = 'right'
) {
  const saved = localStorage.getItem(storageKey)
  const width = ref(saved ? Math.max(minWidth, Math.min(maxWidth, Number(saved))) : defaultWidth)

  let startX = 0
  let startW = 0

  function onMouseMove(e: MouseEvent) {
    const delta = direction === 'right' ? e.clientX - startX : startX - e.clientX
    width.value = Math.max(minWidth, Math.min(maxWidth, startW + delta))
  }

  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    localStorage.setItem(storageKey, String(width.value))
  }

  function startResize(e: MouseEvent) {
    e.preventDefault()
    startX = e.clientX
    startW = width.value
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }

  onUnmounted(() => {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  })

  return { width, startResize }
}
