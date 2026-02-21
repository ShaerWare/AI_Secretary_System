<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronLeft, Plus, RotateCcw, Loader2 } from 'lucide-vue-next'
import draggable from 'vuedraggable'
import type { KanbanTask } from '@/api'
import KanbanCard from './KanbanCard.vue'

const props = defineProps<{
  tasksByStatus: Record<string, KanbanTask[]>
  loading: boolean
  disabled: boolean
}>()

const emit = defineEmits<{
  reorder: [taskId: number, newStatus: string, newPosition: number]
  clickTask: [task: KanbanTask]
  createTask: []
}>()

const { t } = useI18n()

const STATUSES = ['draft', 'todo', 'in_progress', 'review', 'done'] as const

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-zinc-400',
  todo: 'bg-blue-500',
  in_progress: 'bg-amber-500',
  review: 'bg-purple-500',
  done: 'bg-emerald-500',
}

// ============== Local column data (deep copy for vuedraggable v-model) ==============

const columnTasks = ref<Record<string, KanbanTask[]>>({})

watch(
  () => props.tasksByStatus,
  (val) => {
    const copy: Record<string, KanbanTask[]> = {}
    for (const s of STATUSES) {
      copy[s] = val[s] ? val[s].map((t) => ({ ...t })) : []
    }
    columnTasks.value = copy
  },
  { immediate: true, deep: true }
)

// ============== Drag & drop ==============

function onColumnChange(
  targetStatus: string,
  evt: { added?: { element: KanbanTask; newIndex: number } }
) {
  if (!evt.added) return
  const task = evt.added.element
  const newPosition = evt.added.newIndex
  emit('reorder', task.id, targetStatus, newPosition)
}

// ============== Column widths (resizable + persisted) ==============

const STORAGE_KEY = 'kanban-column-widths'
const DEFAULT_WIDTH = 288
const MIN_WIDTH = 180
const MAX_WIDTH = 600

const columnWidths = ref<Record<string, number>>({})

function loadColumnWidths() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) columnWidths.value = JSON.parse(saved)
  } catch {
    /* ignore */
  }
}

function saveColumnWidths() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(columnWidths.value))
  } catch {
    /* ignore */
  }
}

function getColumnWidth(status: string): number {
  return columnWidths.value[status] || DEFAULT_WIDTH
}

function resetColumnWidths() {
  columnWidths.value = {}
  localStorage.removeItem(STORAGE_KEY)
}

const hasCustomWidths = ref(false)
watch(
  columnWidths,
  (val) => {
    hasCustomWidths.value = Object.keys(val).length > 0
  },
  { deep: true }
)

// Column resize drag
const resizingStatus = ref<string | null>(null)
const resizeStartX = ref(0)
const resizeStartWidth = ref(0)

function onResizeStart(e: MouseEvent, status: string) {
  e.preventDefault()
  resizingStatus.value = status
  resizeStartX.value = e.clientX
  resizeStartWidth.value = getColumnWidth(status)
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', onResizeEnd)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function onResizeMove(e: MouseEvent) {
  if (resizingStatus.value === null) return
  const delta = e.clientX - resizeStartX.value
  const newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, resizeStartWidth.value + delta))
  columnWidths.value = { ...columnWidths.value, [resizingStatus.value]: newWidth }
}

function onResizeEnd() {
  resizingStatus.value = null
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  saveColumnWidths()
}

// ============== Column collapse/expand (persisted) ==============

const COLLAPSED_STORAGE_KEY = 'kanban-collapsed'
const COLLAPSED_WIDTH = 48
const collapsedColumns = ref<Set<string>>(new Set())

function loadCollapsedState() {
  try {
    const saved = localStorage.getItem(COLLAPSED_STORAGE_KEY)
    if (saved) collapsedColumns.value = new Set(JSON.parse(saved))
  } catch {
    /* ignore */
  }
}

function saveCollapsedState() {
  try {
    localStorage.setItem(COLLAPSED_STORAGE_KEY, JSON.stringify([...collapsedColumns.value]))
  } catch {
    /* ignore */
  }
}

function toggleColumnCollapse(status: string) {
  const next = new Set(collapsedColumns.value)
  if (next.has(status)) next.delete(status)
  else next.add(status)
  collapsedColumns.value = next
  saveCollapsedState()
}

function isCollapsed(status: string): boolean {
  return collapsedColumns.value.has(status)
}

function columnCount(status: string): number {
  return columnTasks.value[status]?.length || 0
}

// ============== Drag-to-scroll ==============

const boardContainer = ref<HTMLElement | null>(null)
const isDragScrolling = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const dragScrollLeft = ref(0)
const dragScrollTop = ref(0)
const dragMoved = ref(false)

function isCardElement(el: HTMLElement | null): boolean {
  while (el) {
    if (el.classList?.contains('kanban-card')) return true
    if (el.classList?.contains('kanban-resize-handle')) return true
    if (el === boardContainer.value) return false
    el = el.parentElement
  }
  return false
}

function onBoardPointerDown(e: PointerEvent) {
  if (isCardElement(e.target as HTMLElement)) return
  const board = boardContainer.value
  if (!board) return
  isDragScrolling.value = true
  dragMoved.value = false
  dragStartX.value = e.clientX
  dragStartY.value = e.clientY
  dragScrollLeft.value = board.scrollLeft
  dragScrollTop.value = board.scrollTop
  board.setPointerCapture(e.pointerId)
  board.classList.add('is-grabbing')
}

function onBoardPointerMove(e: PointerEvent) {
  if (!isDragScrolling.value) return
  const board = boardContainer.value
  if (!board) return
  const dx = e.clientX - dragStartX.value
  const dy = e.clientY - dragStartY.value
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragMoved.value = true
  board.scrollLeft = dragScrollLeft.value - dx
  board.scrollTop = dragScrollTop.value - dy
}

function onBoardPointerUp(e: PointerEvent) {
  if (!isDragScrolling.value) return
  isDragScrolling.value = false
  const board = boardContainer.value
  if (board) {
    board.releasePointerCapture(e.pointerId)
    board.classList.remove('is-grabbing')
  }
}

// ============== Lifecycle ==============

onMounted(() => {
  loadColumnWidths()
  loadCollapsedState()
})

onUnmounted(() => {
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
})
</script>

<template>
  <div class="kanban-wrapper">
    <!-- Reset widths button -->
    <div v-if="hasCustomWidths" class="flex justify-end mb-2">
      <button
        class="flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground hover:text-foreground rounded hover:bg-muted transition-colors"
        :title="t('kanban.resetWidths')"
        @click="resetColumnWidths"
      >
        <RotateCcw class="w-3 h-3" />
        {{ t('kanban.resetWidths') }}
      </button>
    </div>

    <!-- Loading overlay -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
    </div>

    <!-- Kanban board -->
    <div
      v-else
      ref="boardContainer"
      class="flex kanban-board"
      @pointerdown="onBoardPointerDown"
      @pointermove="onBoardPointerMove"
      @pointerup="onBoardPointerUp"
      @pointercancel="onBoardPointerUp"
    >
      <template v-for="(status, idx) in STATUSES" :key="status">
        <!-- Collapsed column -->
        <div
          v-if="isCollapsed(status)"
          class="flex-shrink-0 flex flex-col items-center cursor-pointer rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors py-3"
          :style="{ width: COLLAPSED_WIDTH + 'px' }"
          :title="t('kanban.expandColumn')"
          @click="toggleColumnCollapse(status)"
        >
          <span class="w-3 h-3 rounded-full flex-shrink-0 mb-2" :class="STATUS_COLORS[status]" />
          <span class="text-xs text-muted-foreground mb-2">{{ columnCount(status) }}</span>
          <span class="kanban-vertical-text text-xs font-medium text-muted-foreground">
            {{ t(`kanban.status.${status}`) }}
          </span>
        </div>

        <!-- Expanded column -->
        <div
          v-else
          class="kanban-column flex-shrink-0 flex flex-col"
          :style="{ width: getColumnWidth(status) + 'px' }"
        >
          <!-- Column header -->
          <div class="flex items-center gap-2 mb-3 px-2 flex-shrink-0">
            <span class="w-3 h-3 rounded-full flex-shrink-0" :class="STATUS_COLORS[status]" />
            <span class="font-medium text-sm truncate">{{ t(`kanban.status.${status}`) }}</span>
            <span class="text-xs text-muted-foreground ml-auto">{{ columnCount(status) }}</span>
            <button
              class="p-0.5 rounded hover:bg-secondary text-muted-foreground"
              :title="t('kanban.collapseColumn')"
              @click="toggleColumnCollapse(status)"
            >
              <ChevronLeft class="w-3.5 h-3.5" />
            </button>
          </div>

          <!-- Scrollable column body -->
          <div class="kanban-column-body flex-1 rounded-lg bg-secondary/30 overflow-y-auto">
            <draggable
              v-model="columnTasks[status]"
              group="kanban-tasks"
              item-key="id"
              class="space-y-2 p-2 min-h-[80px]"
              ghost-class="opacity-50"
              :disabled="props.disabled"
              @change="onColumnChange(status, $event)"
            >
              <template #item="{ element: task }">
                <KanbanCard
                  :task="task"
                  :disabled="props.disabled"
                  @click="emit('clickTask', task)"
                />
              </template>

              <template #footer>
                <!-- Empty column message -->
                <div
                  v-if="columnCount(status) === 0"
                  class="text-center py-6 text-xs text-muted-foreground"
                >
                  {{ t('kanban.emptyColumn') }}
                </div>
                <!-- New task button in draft column -->
                <button
                  v-if="status === 'draft' && !props.disabled"
                  class="w-full flex items-center justify-center gap-1.5 py-2 mt-1 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary/50 rounded-lg transition-colors"
                  @click="emit('createTask')"
                >
                  <Plus class="w-4 h-4" />
                  {{ t('kanban.newTask') }}
                </button>
              </template>
            </draggable>
          </div>
        </div>

        <!-- Resize handle between columns -->
        <div
          v-if="idx < STATUSES.length - 1 && !isCollapsed(status) && !isCollapsed(STATUSES[idx + 1])"
          class="kanban-resize-handle flex-shrink-0"
          @mousedown="onResizeStart($event, status)"
        >
          <div class="kanban-resize-line" />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.kanban-wrapper {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 12rem);
  overflow: hidden;
}

.kanban-board {
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
  cursor: grab;
  padding-bottom: 1rem;
}
.kanban-board::-webkit-scrollbar {
  display: none;
}
.kanban-board.is-grabbing {
  cursor: grabbing;
  user-select: none;
}

.kanban-column {
  height: 100%;
}

.kanban-column-body {
  scrollbar-width: thin;
  scrollbar-color: hsl(var(--border)) transparent;
}
.kanban-column-body::-webkit-scrollbar {
  width: 4px;
}
.kanban-column-body::-webkit-scrollbar-thumb {
  background-color: hsl(var(--border));
  border-radius: 2px;
}

.kanban-resize-handle {
  width: 16px;
  cursor: col-resize;
  display: flex;
  align-items: stretch;
  justify-content: center;
  position: relative;
  z-index: 5;
}

.kanban-resize-handle:hover .kanban-resize-line,
.kanban-resize-handle:active .kanban-resize-line {
  background-color: hsl(var(--primary));
  opacity: 1;
}

.kanban-resize-line {
  width: 3px;
  border-radius: 2px;
  background-color: hsl(var(--border));
  opacity: 0.5;
  transition: background-color 0.15s, opacity 0.15s;
}

.kanban-vertical-text {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-height: 200px;
}
</style>
