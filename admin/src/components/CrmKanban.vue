<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { RefreshCw, ChevronDown, GripVertical, ExternalLink, User } from 'lucide-vue-next'
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

// Fetch pipelines
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

// Fetch leads for selected pipeline
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

// Group leads by status_id for kanban columns
const columnLeads = ref<Record<number, AmoCRMLead[]>>({})

// Rebuild columnLeads whenever allLeads changes
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

// Watch for data changes
import { watch } from 'vue'
watch([allLeads, statuses], rebuildColumns, { immediate: true })

// Auto-select first pipeline
watch(pipelines, (val) => {
  if (val.length && !selectedPipelineId.value) {
    selectedPipelineId.value = val.find(p => p.is_main)?.id || val[0].id
  }
}, { immediate: true })

// Update lead mutation (for drag & drop)
const updateLeadMutation = useMutation({
  mutationFn: ({ leadId, data }: { leadId: number; data: { status_id: number } }) =>
    amocrmApi.updateLead(leadId, data),
  onError: () => {
    toast.error(t('crm.kanban.moveFailed'))
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

// Auto-refresh
let refreshTimer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  refreshTimer = setInterval(() => refetchLeads(), 30000)
})
onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
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

      <div class="flex-1" />

      <span class="text-sm text-muted-foreground">
        {{ allLeads.length }} {{ t('crm.kanban.deals') }}
      </span>
    </div>

    <!-- Loading -->
    <div v-if="pipelinesLoading || leadsLoading" class="flex items-center justify-center py-12">
      <RefreshCw class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Kanban board -->
    <div v-else class="flex gap-4 overflow-x-auto pb-4" style="min-height: 400px;">
      <div
        v-for="status in statuses"
        :key="status.id"
        class="flex-shrink-0 w-72 flex flex-col"
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
                  :href="`https://${subdomain}.amocrm.ru/leads/detail/${lead.id}`"
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
    </div>

    <!-- Empty state -->
    <div
      v-if="!pipelinesLoading && !leadsLoading && allLeads.length === 0"
      class="text-center py-12 text-muted-foreground"
    >
      {{ t('crm.kanban.empty') }}
    </div>
  </div>
</template>
