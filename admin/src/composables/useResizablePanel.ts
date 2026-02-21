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

  function applyDelta(clientX: number) {
    const delta = direction === 'right' ? clientX - startX : startX - clientX
    width.value = Math.max(minWidth, Math.min(maxWidth, startW + delta))
  }

  // Mouse handlers
  function onMouseMove(e: MouseEvent) {
    applyDelta(e.clientX)
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

  // Touch handlers
  function onTouchMove(e: TouchEvent) {
    if (e.touches.length === 1) {
      applyDelta(e.touches[0].clientX)
    }
  }

  function onTouchEnd() {
    document.removeEventListener('touchmove', onTouchMove)
    document.removeEventListener('touchend', onTouchEnd)
    document.removeEventListener('touchcancel', onTouchEnd)
    localStorage.setItem(storageKey, String(width.value))
  }

  function startTouchResize(e: TouchEvent) {
    if (e.touches.length !== 1) return
    e.preventDefault()
    startX = e.touches[0].clientX
    startW = width.value
    document.addEventListener('touchmove', onTouchMove, { passive: false })
    document.addEventListener('touchend', onTouchEnd)
    document.addEventListener('touchcancel', onTouchEnd)
  }

  onUnmounted(() => {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.removeEventListener('touchmove', onTouchMove)
    document.removeEventListener('touchend', onTouchEnd)
    document.removeEventListener('touchcancel', onTouchEnd)
  })

  return { width, startResize, startTouchResize }
}
