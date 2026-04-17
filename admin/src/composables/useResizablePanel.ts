import { ref, onUnmounted } from 'vue'

type MaxWidth = number | (() => number)

interface Options {
  /** Emitted when user keeps dragging the handle past minWidth — request parent to close the panel. */
  onCollapse?: () => void
  /** How many px below minWidth before onCollapse fires (default 40). */
  collapseThreshold?: number
}

export function useResizablePanel(
  storageKey: string,
  defaultWidth: number,
  minWidth: number,
  maxWidth: MaxWidth,
  direction: 'right' | 'left' = 'right',
  options: Options = {}
) {
  const { onCollapse, collapseThreshold = 40 } = options

  function resolveMax(): number {
    const m = typeof maxWidth === 'function' ? maxWidth() : maxWidth
    return Math.max(minWidth, m)
  }

  const saved = localStorage.getItem(storageKey)
  const width = ref(saved ? Math.max(minWidth, Math.min(resolveMax(), Number(saved))) : defaultWidth)

  let startX = 0
  let startW = 0
  let collapsedMidDrag = false

  function applyDelta(clientX: number) {
    const delta = direction === 'right' ? clientX - startX : startX - clientX
    const raw = startW + delta
    const max = resolveMax()
    // If user drags well below the minimum, request close instead of clamping.
    if (onCollapse && raw < minWidth - collapseThreshold && !collapsedMidDrag) {
      collapsedMidDrag = true
      onCollapse()
      return
    }
    width.value = Math.max(minWidth, Math.min(max, raw))
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
    collapsedMidDrag = false
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
    collapsedMidDrag = false
    document.addEventListener('touchmove', onTouchMove, { passive: false })
    document.addEventListener('touchend', onTouchEnd)
    document.addEventListener('touchcancel', onTouchEnd)
  }

  /** Re-clamp the stored width against the current max (e.g. on window resize). */
  function clampToBounds() {
    const max = resolveMax()
    if (width.value > max) width.value = max
    if (width.value < minWidth) width.value = minWidth
  }

  // Listen to window resize so maxWidth functions update live
  function onWindowResize() {
    clampToBounds()
  }
  window.addEventListener('resize', onWindowResize)

  onUnmounted(() => {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.removeEventListener('touchmove', onTouchMove)
    document.removeEventListener('touchend', onTouchEnd)
    document.removeEventListener('touchcancel', onTouchEnd)
    window.removeEventListener('resize', onWindowResize)
  })

  return { width, startResize, startTouchResize, clampToBounds }
}
