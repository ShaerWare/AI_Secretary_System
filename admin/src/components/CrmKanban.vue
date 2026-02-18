<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { RefreshCw, ChevronDown, GripVertical, ExternalLink, User, RotateCcw } from 'lucide-vue-next'
import draggable from 'vuedraggable'
import { amocrmApi } from '@/api/amocrm'
import type { AmoCRMPipeline, AmoCRMPipelineStatus, AmoCRMLead } from '@/api/amocrm'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{
  subdomain: string
}>()

const { t } = useI18n()
const queryClient = useQueryClient()
const toast = useToastStore()

const selectedPipelineId = ref<number | null>(null)
const showPipelineSelect = ref(false)

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

// ============== Scroll sync (sticky horizontal scrollbar) ==============

const boardContainer = ref<HTMLElement | null>(null)
const scrollProxy = ref<HTMLElement | null>(null)
const scrollProxyInner = ref<HTMLElement | null>(null)
const syncingScroll = ref(false)

function onBoardScroll() {
  if (syncingScroll.value) return
  syncingScroll.value = true
  if (scrollProxy.value && boardContainer.value) {
    scrollProxy.value.scrollLeft = boardContainer.value.scrollLeft
  }
  nextTick(() => { syncingScroll.value = false })
}

function onProxyScroll() {
  if (syncingScroll.value) return
  syncingScroll.value = true
  if (boardContainer.value && scrollProxy.value) {
    boardContainer.value.scrollLeft = scrollProxy.value.scrollLeft
  }
  nextTick(() => { syncingScroll.value = false })
}

function syncProxyWidth() {
  if (boardContainer.value && scrollProxyInner.value) {
    scrollProxyInner.value.style.width = boardContainer.value.scrollWidth + 'px'
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

const allLeads = computed<AmoCRMLead[]>(() =>
  leadsData.value?._embedded?.leads || []
)

const columnLeads = ref<Record<number, AmoCRMLead[]>>({})

function rebuildColumns() {
  const grouped: Record<number, AmoCRMLead[]> = {}
  for (const status of statuses.value) {
    grouped[status.id] = []
  }
  for (const lead of allLeads.value) {
    if (grouped[lead.status_id]) {
      grouped[lead.status_id].push(lead)
    }
  }
  columnLeads.value = grouped
}

watch([allLeads, statuses], rebuildColumns, { immediate: true })

watch(pipelines, (val) => {
  if (val.length && !selectedPipelineId.value) {
    selectedPipelineId.value = val.find(p => p.is_main)?.id || val[0].id
  }
}, { immediate: true })

// Sync proxy width when columns/widths change
watch([statuses, columnWidths], () => {
  nextTick(syncProxyWidth)
}, { deep: true })

// ============== Lead drag & drop ==============

const updateLeadMutation = useMutation({
  mutationFn: ({ leadId, data }: { leadId: number; data: { status_id: number } }) =>
    amocrmApi.updateLead(leadId, data),
  onError: () => {
    toast.error(t('crm.kanban.updateFailed'))
    refetchLeads()
  },
})

function onDragEnd(statusId: number) {
  const leads = columnLeads.value[statusId] || []
  for (const lead of leads) {
    if (lead.status_id !== statusId) {
      lead.status_id = statusId
      updateLeadMutation.mutate({ leadId: lead.id, data: { status_id: statusId } })
    }
  }
}

function formatPrice(price: number): string {
  if (!price) return ''
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(price)
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
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  loadColumnWidths()
  refreshTimer = setInterval(() => refetchLeads(), 30000)
  // Watch board content size for scroll proxy
  if (boardContainer.value) {
    resizeObserver = new ResizeObserver(syncProxyWidth)
    resizeObserver.observe(boardContainer.value)
  }
  nextTick(syncProxyWidth)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (resizeObserver) resizeObserver.disconnect()
  // Cleanup resize listeners in case component unmounts during resize
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
})
</script>

<template>
  <div class="space-y-4">
    <!-- Toolbar -->
    <div class="flex items-center gap-3 flex-wrap">
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
      <!-- Sticky horizontal scrollbar (top) -->
      <div
        ref="scrollProxy"
        class="overflow-x-auto overflow-y-hidden sticky top-0 z-10"
        style="height: 12px;"
        @scroll="onProxyScroll"
      >
        <div ref="scrollProxyInner" style="height: 1px;" />
      </div>

      <!-- Kanban board -->
      <div
        ref="boardContainer"
        class="flex overflow-x-auto pb-4 kanban-board"
        style="min-height: 400px;"
        @scroll="onBoardScroll"
      >
        <template v-for="(status, idx) in statuses" :key="status.id">
          <div
            class="flex-shrink-0 flex flex-col"
            :style="{ width: getColumnWidth(status.id) + 'px' }"
          >
            <!-- Column header -->
            <div class="flex items-center gap-2 mb-3 px-2">
              <span
                class="w-3 h-3 rounded-full flex-shrink-0"
                :style="{ backgroundColor: getStatusColor(status.color) }"
              />
              <span class="font-medium text-sm truncate">{{ status.name }}</span>
              <span class="text-xs text-muted-foreground ml-auto">
                {{ (columnLeads[status.id] || []).length }}
              </span>
            </div>

            <!-- Draggable column -->
            <draggable
              v-model="columnLeads[status.id]"
              group="kanban"
              item-key="id"
              class="flex-1 space-y-2 p-2 rounded-lg bg-secondary/30 min-h-[100px]"
              ghost-class="opacity-50"
              @end="onDragEnd(status.id)"
            >
              <template #item="{ element: lead }">
                <div class="bg-card border border-border rounded-lg p-3 cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow">
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
            </draggable>
          </div>

          <!-- Resize handle between columns -->
          <div
            v-if="idx < statuses.length - 1"
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

/* Hide native scrollbar on main board (proxy handles it) */
.kanban-board {
  scrollbar-width: thin;
}
</style>
