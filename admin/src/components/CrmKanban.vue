<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { RefreshCw, ChevronDown, ChevronLeft, GripVertical, ExternalLink, User, RotateCcw, Loader2 } from 'lucide-vue-next'
import draggable from 'vuedraggable'
import { amocrmApi } from '@/api/amocrm'
import type { AmoCRMPipeline, AmoCRMPipelineStatus, AmoCRMLead } from '@/api/amocrm'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{
  subdomain: string
  currency?: string
}>()

const { t } = useI18n()
const queryClient = useQueryClient()
const toast = useToastStore()

const selectedPipelineId = ref<number | null>(null)
const showPipelineSelect = ref(false)

// ============== Progressive rendering ==============

const BATCH_SIZE = 30

// What vuedraggable renders (sliced from columnLeads)
const visibleColumnLeads = ref<Record<number, AmoCRMLead[]>>({})

// Display limits per column
const displayLimits = ref<Record<number, number>>({})

function syncVisible() {
  const result: Record<number, AmoCRMLead[]> = {}
  for (const sid of Object.keys(columnLeads.value)) {
    const statusId = Number(sid)
    const all = columnLeads.value[statusId] || []
    const limit = displayLimits.value[statusId] || BATCH_SIZE
    result[statusId] = all.slice(0, limit)
  }
  visibleColumnLeads.value = result
}

function loadMore(statusId: number) {
  const newLimit = (displayLimits.value[statusId] || BATCH_SIZE) + BATCH_SIZE
  displayLimits.value = { ...displayLimits.value, [statusId]: newLimit }
  const all = columnLeads.value[statusId] || []
  visibleColumnLeads.value = {
    ...visibleColumnLeads.value,
    [statusId]: all.slice(0, newLimit),
  }
}

function hiddenCount(statusId: number): number {
  return (columnLeads.value[statusId]?.length || 0) -
         (visibleColumnLeads.value[statusId]?.length || 0)
}

function totalCount(statusId: number): number {
  return columnLeads.value[statusId]?.length || 0
}

// IntersectionObserver per column sentinel
const sentinelObservers = new Map<number, IntersectionObserver>()

function observeSentinel(el: HTMLElement | null, statusId: number) {
  if (sentinelObservers.has(statusId)) {
    sentinelObservers.get(statusId)!.disconnect()
    sentinelObservers.delete(statusId)
  }
  if (!el) return

  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && hiddenCount(statusId) > 0) {
      loadMore(statusId)
    }
  }, { threshold: 0.1 })
  observer.observe(el)
  sentinelObservers.set(statusId, observer)
}

// ============== Column widths (resizable + persisted) ==============

const STORAGE_KEY = 'crm-kanban-column-widths'
const DEFAULT_WIDTH = 288 // 18rem = 288px
const MIN_WIDTH = 180
const MAX_WIDTH = 600

const columnWidths = ref<Record<number, number>>({})

function loadColumnWidths() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) columnWidths.value = JSON.parse(saved)
  } catch { /* ignore */ }
}

function saveColumnWidths() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(columnWidths.value))
  } catch { /* ignore */ }
}

function getColumnWidth(statusId: number): number {
  return columnWidths.value[statusId] || DEFAULT_WIDTH
}

function resetColumnWidths() {
  columnWidths.value = {}
  localStorage.removeItem(STORAGE_KEY)
}

// ============== Column collapse/expand (persisted) ==============

const COLLAPSED_STORAGE_KEY = 'crm-kanban-collapsed'
const COLLAPSED_WIDTH = 48
const collapsedColumns = ref<Set<number>>(new Set())

function loadCollapsedState() {
  try {
    const saved = localStorage.getItem(COLLAPSED_STORAGE_KEY)
    if (saved) collapsedColumns.value = new Set(JSON.parse(saved))
  } catch { /* ignore */ }
}

function saveCollapsedState() {
  try {
    localStorage.setItem(COLLAPSED_STORAGE_KEY, JSON.stringify([...collapsedColumns.value]))
  } catch { /* ignore */ }
}

function toggleColumnCollapse(statusId: number) {
  const next = new Set(collapsedColumns.value)
  if (next.has(statusId)) next.delete(statusId)
  else next.add(statusId)
  collapsedColumns.value = next
  saveCollapsedState()
}

function isCollapsed(statusId: number): boolean {
  return collapsedColumns.value.has(statusId)
}

function getEffectiveColumnWidth(statusId: number): number {
  return isCollapsed(statusId) ? COLLAPSED_WIDTH : getColumnWidth(statusId)
}

// Column resize drag
const resizingStatusId = ref<number | null>(null)
const resizeStartX = ref(0)
const resizeStartWidth = ref(0)

function onResizeStart(e: MouseEvent, statusId: number) {
  e.preventDefault()
  resizingStatusId.value = statusId
  resizeStartX.value = e.clientX
  resizeStartWidth.value = getColumnWidth(statusId)
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', onResizeEnd)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function onResizeMove(e: MouseEvent) {
  if (resizingStatusId.value === null) return
  const delta = e.clientX - resizeStartX.value
  const newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, resizeStartWidth.value + delta))
  columnWidths.value = { ...columnWidths.value, [resizingStatusId.value]: newWidth }
}

function onResizeEnd() {
  resizingStatusId.value = null
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  saveColumnWidths()
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

// ============== Data fetching ==============

const { data: pipelinesData, isLoading: pipelinesLoading } = useQuery({
  queryKey: ['crm-pipelines'],
  queryFn: () => amocrmApi.getPipelines(),
})

const pipelines = computed<AmoCRMPipeline[]>(() =>
  pipelinesData.value?._embedded?.pipelines || []
)

const selectedPipeline = computed(() =>
  pipelines.value.find(p => p.id === selectedPipelineId.value) || pipelines.value[0]
)

const statuses = computed<AmoCRMPipelineStatus[]>(() => {
  if (!selectedPipeline.value) return []
  return [...selectedPipeline.value._embedded.statuses].sort((a, b) => a.sort - b.sort)
})

const { data: leadsData, isLoading: leadsLoading, refetch: refetchLeads } = useQuery({
  queryKey: ['crm-kanban-leads', selectedPipelineId],
  queryFn: () => {
    const pid = selectedPipelineId.value || selectedPipeline.value?.id
    if (!pid) return Promise.resolve({ _embedded: { leads: [] } })
    return amocrmApi.getLeadsByPipeline(pid)
  },
  enabled: computed(() => !!selectedPipeline.value),
})

// Unsorted leads (separate amoCRM API — they have no pipeline)
const { data: unsortedData, refetch: refetchUnsorted } = useQuery({
  queryKey: ['crm-kanban-unsorted'],
  queryFn: () => amocrmApi.getUnsortedLeads(1, 250),
  enabled: computed(() => !!selectedPipeline.value),
})

const unsortedHasNext = computed(() => unsortedData.value?.has_next || false)

const allLeads = computed<AmoCRMLead[]>(() =>
  leadsData.value?._embedded?.leads || []
)

const unsortedLeads = computed<AmoCRMLead[]>(() =>
  unsortedData.value?._embedded?.leads || []
)

const columnLeads = ref<Record<number, AmoCRMLead[]>>({})

// Find the "Неразобранное" status (sort === 10, first in pipeline)
const unsortedStatusId = computed(() => {
  const first = statuses.value[0]
  return first && first.sort <= 10 ? first.id : null
})

function rebuildColumns() {
  const grouped: Record<number, AmoCRMLead[]> = {}
  const newLimits: Record<number, number> = {}
  for (const status of statuses.value) {
    grouped[status.id] = []
    newLimits[status.id] = BATCH_SIZE
  }
  for (const lead of allLeads.value) {
    if (grouped[lead.status_id]) {
      grouped[lead.status_id].push(lead)
    }
  }
  // Merge unsorted leads into "Неразобранное" column (assign status_id)
  const usId = unsortedStatusId.value
  if (usId && grouped[usId]) {
    for (const lead of unsortedLeads.value) {
      grouped[usId].push({ ...lead, status_id: usId })
    }
  }
  columnLeads.value = grouped
  displayLimits.value = newLimits
  syncVisible()
}

watch([allLeads, unsortedLeads, statuses], rebuildColumns, { immediate: true })

watch(pipelines, (val) => {
  if (val.length && !selectedPipelineId.value) {
    selectedPipelineId.value = val.find(p => p.is_main)?.id || val[0].id
  }
}, { immediate: true })


// ============== Lead drag & drop ==============

const updateLeadMutation = useMutation({
  mutationFn: ({ leadId, data }: { leadId: number; data: { status_id: number } }) =>
    amocrmApi.updateLead(leadId, data),
  onError: () => {
    toast.error(t('crm.kanban.updateFailed'))
    refetchLeads()
  },
})

function onColumnChange(targetStatusId: number, evt: { added?: { element: AmoCRMLead; newIndex: number }; removed?: { element: AmoCRMLead; oldIndex: number } }) {
  if (!evt.added) return
  const lead = evt.added.element
  const oldStatusId = lead.status_id
  if (oldStatusId === targetStatusId) return

  // Remove from source column's full list
  const srcAll = columnLeads.value[oldStatusId]
  if (srcAll) {
    const idx = srcAll.findIndex(l => l.id === lead.id)
    if (idx !== -1) srcAll.splice(idx, 1)
  }

  // Add to target column's full list
  const targetAll = columnLeads.value[targetStatusId]
  if (targetAll && !targetAll.some(l => l.id === lead.id)) {
    targetAll.push(lead)
  }

  lead.status_id = targetStatusId
  updateLeadMutation.mutate({ leadId: lead.id, data: { status_id: targetStatusId } })

  // Refill source column's visible list
  const srcLimit = displayLimits.value[oldStatusId] || BATCH_SIZE
  const srcAllNow = columnLeads.value[oldStatusId] || []
  visibleColumnLeads.value = {
    ...visibleColumnLeads.value,
    [oldStatusId]: srcAllNow.slice(0, srcLimit),
  }
}

function formatPrice(price: number): string {
  if (!price) return ''
  const cur = props.currency || 'RUB'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(price)
}

function getContactName(lead: AmoCRMLead): string {
  const contacts = lead._embedded?.contacts
  if (contacts && contacts.length > 0) {
    return contacts[0].name
  }
  return ''
}

function getStatusColor(color: string): string {
  if (!color) return '#6b7280'
  return color.startsWith('#') ? color : `#${color}`
}

// ============== Lifecycle ==============

let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  loadColumnWidths()
  loadCollapsedState()
  refreshTimer = setInterval(() => { refetchLeads(); refetchUnsorted() }, 30000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
  for (const obs of sentinelObservers.values()) obs.disconnect()
})
</script>

<template>
  <div class="kanban-wrapper">
    <!-- Toolbar -->
    <div class="flex items-center gap-3 flex-wrap mb-4">
      <!-- Pipeline selector -->
      <div class="relative">
        <button
          class="btn btn-secondary flex items-center gap-2"
          @click="showPipelineSelect = !showPipelineSelect"
        >
          {{ selectedPipeline?.name || t('crm.kanban.selectPipeline') }}
          <ChevronDown class="w-4 h-4" />
        </button>
        <div
          v-if="showPipelineSelect"
          class="absolute top-full left-0 mt-1 bg-card border border-border rounded-lg shadow-lg z-10 min-w-[200px]"
        >
          <button
            v-for="pipeline in pipelines"
            :key="pipeline.id"
            class="w-full text-left px-4 py-2 hover:bg-secondary/50 first:rounded-t-lg last:rounded-b-lg text-sm"
            @click="selectedPipelineId = pipeline.id; showPipelineSelect = false"
          >
            {{ pipeline.name }}
            <span v-if="pipeline.is_main" class="text-xs text-muted-foreground ml-1">({{ t('crm.kanban.main') }})</span>
          </button>
        </div>
      </div>

      <button class="btn btn-ghost" :disabled="leadsLoading" @click="refetchLeads()">
        <RefreshCw :class="['w-4 h-4', leadsLoading && 'animate-spin']" />
      </button>

      <button
        v-if="Object.keys(columnWidths).length > 0"
        class="btn btn-ghost text-xs gap-1"
        :title="t('crm.kanban.resetWidths')"
        @click="resetColumnWidths"
      >
        <RotateCcw class="w-3.5 h-3.5" />
      </button>

      <div class="flex-1" />

      <span class="text-sm text-muted-foreground">
        {{ allLeads.length }} {{ t('crm.kanban.deals') }}
      </span>
    </div>

    <!-- Loading -->
    <div v-if="pipelinesLoading || leadsLoading" class="flex items-center justify-center py-12">
      <RefreshCw class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <template v-else>
      <!-- Kanban board (drag-to-scroll) -->
      <div
        ref="boardContainer"
        class="flex kanban-board"
        @pointerdown="onBoardPointerDown"
        @pointermove="onBoardPointerMove"
        @pointerup="onBoardPointerUp"
        @pointercancel="onBoardPointerUp"
      >
        <template v-for="(status, idx) in statuses" :key="status.id">
          <!-- Collapsed column -->
          <div
            v-if="isCollapsed(status.id)"
            class="flex-shrink-0 flex flex-col items-center cursor-pointer rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors py-3"
            :style="{ width: COLLAPSED_WIDTH + 'px' }"
            :title="t('crm.kanban.expandColumn')"
            @click="toggleColumnCollapse(status.id)"
          >
            <span
              class="w-3 h-3 rounded-full flex-shrink-0 mb-2"
              :style="{ backgroundColor: getStatusColor(status.color) }"
            />
            <span class="text-xs text-muted-foreground mb-2">
              {{ totalCount(status.id) }}
            </span>
            <span class="kanban-vertical-text text-xs font-medium text-muted-foreground">
              {{ status.name }}
            </span>
          </div>

          <!-- Expanded column -->
          <div
            v-else
            class="kanban-column flex-shrink-0 flex flex-col"
            :style="{ width: getColumnWidth(status.id) + 'px' }"
          >
            <!-- Column header -->
            <div class="flex items-center gap-2 mb-3 px-2 flex-shrink-0">
              <span
                class="w-3 h-3 rounded-full flex-shrink-0"
                :style="{ backgroundColor: getStatusColor(status.color) }"
              />
              <span class="font-medium text-sm truncate">{{ status.name }}</span>
              <span class="text-xs text-muted-foreground ml-auto">
                {{ totalCount(status.id) }}{{ status.id === unsortedStatusId && unsortedHasNext ? '+' : '' }}
              </span>
              <button
                class="p-0.5 rounded hover:bg-secondary text-muted-foreground"
                :title="t('crm.kanban.collapseColumn')"
                @click="toggleColumnCollapse(status.id)"
              >
                <ChevronLeft class="w-3.5 h-3.5" />
              </button>
            </div>

            <!-- Scrollable column body -->
            <div class="kanban-column-body flex-1 rounded-lg bg-secondary/30 overflow-y-auto">
              <draggable
                v-model="visibleColumnLeads[status.id]"
                group="kanban"
                item-key="id"
                class="space-y-2 p-2 min-h-[80px]"
                ghost-class="opacity-50"
                @change="onColumnChange(status.id, $event)"
              >
                <template #item="{ element: lead }">
                  <div class="kanban-card bg-card border border-border rounded-lg p-3 cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow">
                    <div class="flex items-start gap-2">
                      <GripVertical class="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
                      <div class="flex-1 min-w-0">
                        <div class="font-medium text-sm truncate">{{ lead.name }}</div>
                        <div v-if="lead.price" class="text-sm text-green-400 mt-1">
                          {{ formatPrice(lead.price) }}
                        </div>
                        <div v-if="getContactName(lead)" class="flex items-center gap-1 text-xs text-muted-foreground mt-1">
                          <User class="w-3 h-3" />
                          {{ getContactName(lead) }}
                        </div>
                      </div>
                      <a
                        :href="`https://${props.subdomain}.amocrm.ru/leads/detail/${lead.id}`"
                        target="_blank"
                        class="text-muted-foreground hover:text-primary"
                        @click.stop
                      >
                        <ExternalLink class="w-3.5 h-3.5" />
                      </a>
                    </div>
                  </div>
                </template>

                <template #footer>
                  <div
                    v-if="hiddenCount(status.id) > 0"
                    :ref="(el: any) => observeSentinel(el as HTMLElement, status.id)"
                    class="flex items-center justify-center gap-2 py-3 text-xs text-muted-foreground"
                  >
                    <Loader2 class="w-3.5 h-3.5 animate-spin" />
                    <span>{{ t('crm.kanban.moreDeals', { count: hiddenCount(status.id) }) }}</span>
                  </div>
                </template>
              </draggable>
            </div>
          </div>

          <!-- Resize handle between columns (hidden if either adjacent column is collapsed) -->
          <div
            v-if="idx < statuses.length - 1 && !isCollapsed(status.id) && !isCollapsed(statuses[idx + 1].id)"
            class="kanban-resize-handle flex-shrink-0"
            @mousedown="onResizeStart($event, status.id)"
          >
            <div class="kanban-resize-line" />
          </div>
        </template>
      </div>
    </template>

    <!-- Empty state -->
    <div
      v-if="!pipelinesLoading && !leadsLoading && allLeads.length === 0"
      class="text-center py-12 text-muted-foreground"
    >
      {{ t('crm.kanban.emptyColumn') }}
    </div>
  </div>
</template>

<style scoped>
.kanban-wrapper {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 10rem);
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

.kanban-card {
  cursor: grab;
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
