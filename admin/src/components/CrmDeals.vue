<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  RefreshCw,
  Search,
  Filter,
  Plus,
  X,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  StickyNote,
  User,
} from 'lucide-vue-next'
import { amocrmApi } from '@/api/amocrm'
import type { AmoCRMPipeline, AmoCRMLead } from '@/api/amocrm'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{
  subdomain: string
  currency?: string
}>()

const { t } = useI18n()
const queryClient = useQueryClient()
const toast = useToastStore()

// Filters
const searchQuery = ref('')
const page = ref(1)
const limit = 50
const showFilters = ref(false)

// Detail modal
const selectedLead = ref<AmoCRMLead | null>(null)
const noteText = ref('')
const addingNote = ref(false)

// Create modal
const showCreateDialog = ref(false)
const newDeal = ref({ name: '', pipeline_id: 0, status_id: 0 })

// Pipelines for filter/create
const { data: pipelinesData } = useQuery({
  queryKey: ['crm-pipelines'],
  queryFn: () => amocrmApi.getPipelines(),
})

const pipelines = computed<AmoCRMPipeline[]>(() =>
  pipelinesData.value?._embedded?.pipelines || []
)

// Leads
const { data: leadsData, isLoading, refetch } = useQuery({
  queryKey: ['crm-deals', page, searchQuery],
  queryFn: () => amocrmApi.getLeads(page.value, limit, searchQuery.value || undefined),
})

const leads = computed<AmoCRMLead[]>(() =>
  leadsData.value?._embedded?.leads || []
)

const hasMore = computed(() => leads.value.length >= limit)

// Create lead
const createMutation = useMutation({
  mutationFn: (data: { name: string; pipeline_id?: number; status_id?: number }) =>
    amocrmApi.createLead(data),
  onSuccess: () => {
    toast.success(t('crm.deals.created'))
    showCreateDialog.value = false
    newDeal.value = { name: '', pipeline_id: 0, status_id: 0 }
    queryClient.invalidateQueries({ queryKey: ['crm-deals'] })
  },
  onError: () => toast.error(t('crm.deals.createFailed')),
})

// Add note
const addNoteMutation = useMutation({
  mutationFn: ({ leadId, text }: { leadId: number; text: string }) =>
    amocrmApi.addNoteToLead(leadId, text),
  onSuccess: () => {
    toast.success(t('crm.deals.noteAdded'))
    noteText.value = ''
    addingNote.value = false
  },
  onError: () => toast.error(t('crm.deals.noteFailed')),
})

function getPipelineName(pipelineId: number): string {
  return pipelines.value.find(p => p.id === pipelineId)?.name || ''
}

function getStatusName(pipelineId: number, statusId: number): string {
  const pipeline = pipelines.value.find(p => p.id === pipelineId)
  if (!pipeline) return ''
  return pipeline._embedded.statuses.find(s => s.id === statusId)?.name || ''
}

function getStatusColor(pipelineId: number, statusId: number): string {
  const pipeline = pipelines.value.find(p => p.id === pipelineId)
  if (!pipeline) return '#6b7280'
  const status = pipeline._embedded.statuses.find(s => s.id === statusId)
  const color = status?.color || '#6b7280'
  return color.startsWith('#') ? color : `#${color}`
}

function formatPrice(price: number): string {
  if (!price) return '-'
  const cur = props.currency || 'RUB'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(price)
}

function formatTs(ts: number | undefined): string {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleDateString()
}

function getContactName(lead: AmoCRMLead): string {
  const contacts = lead._embedded?.contacts
  if (contacts && contacts.length > 0) return contacts[0].name
  return '-'
}

function openDetail(lead: AmoCRMLead) {
  selectedLead.value = lead
  noteText.value = ''
  addingNote.value = false
}

function submitNote() {
  if (!selectedLead.value || !noteText.value.trim()) return
  addNoteMutation.mutate({ leadId: selectedLead.value.id, text: noteText.value.trim() })
}

function doSearch() {
  page.value = 1
  refetch()
}
</script>

<template>
  <div class="space-y-4">
    <!-- Toolbar -->
    <div class="flex items-center gap-3 flex-wrap">
      <div class="relative flex-1 max-w-sm">
        <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          v-model="searchQuery"
          type="text"
          :placeholder="t('crm.deals.search')"
          class="input w-full pl-10"
          @keydown.enter="doSearch"
        />
      </div>

      <button class="btn btn-ghost" :disabled="isLoading" @click="refetch()">
        <RefreshCw :class="['w-4 h-4', isLoading && 'animate-spin']" />
      </button>

      <div class="flex-1" />

      <div class="flex items-center gap-2">
        <button class="btn btn-ghost btn-sm" :disabled="page <= 1" @click="page--">
          <ChevronLeft class="w-4 h-4" />
        </button>
        <span class="text-sm text-muted-foreground">
          {{ t('crm.deals.page') }} {{ page }}
        </span>
        <button class="btn btn-ghost btn-sm" :disabled="!hasMore" @click="page++">
          <ChevronRight class="w-4 h-4" />
        </button>
      </div>

      <button class="btn btn-primary" @click="showCreateDialog = true">
        <Plus class="w-4 h-4 mr-2" />
        {{ t('crm.deals.create') }}
      </button>
    </div>

    <!-- Table -->
    <div class="bg-card border border-border rounded-xl overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-secondary/50">
            <tr>
              <th class="px-4 py-3 text-left text-sm font-medium">{{ t('crm.deals.name') }}</th>
              <th class="px-4 py-3 text-left text-sm font-medium">{{ t('crm.deals.price') }}</th>
              <th class="px-4 py-3 text-left text-sm font-medium">{{ t('crm.deals.pipeline') }}</th>
              <th class="px-4 py-3 text-left text-sm font-medium">{{ t('crm.deals.status') }}</th>
              <th class="px-4 py-3 text-left text-sm font-medium">{{ t('crm.deals.contact') }}</th>
              <th class="px-4 py-3 text-left text-sm font-medium">{{ t('crm.deals.created') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            <tr
              v-for="lead in leads"
              :key="lead.id"
              class="hover:bg-secondary/30 cursor-pointer transition-colors"
              @click="openDetail(lead)"
            >
              <td class="px-4 py-3 text-sm font-medium">{{ lead.name }}</td>
              <td class="px-4 py-3 text-sm text-green-400">{{ formatPrice(lead.price) }}</td>
              <td class="px-4 py-3 text-sm text-muted-foreground">{{ getPipelineName(lead.pipeline_id) }}</td>
              <td class="px-4 py-3 text-sm">
                <span
                  class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs"
                  :style="{ backgroundColor: getStatusColor(lead.pipeline_id, lead.status_id) + '30', color: getStatusColor(lead.pipeline_id, lead.status_id) }"
                >
                  <span class="w-1.5 h-1.5 rounded-full" :style="{ backgroundColor: getStatusColor(lead.pipeline_id, lead.status_id) }" />
                  {{ getStatusName(lead.pipeline_id, lead.status_id) }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-muted-foreground">{{ getContactName(lead) }}</td>
              <td class="px-4 py-3 text-sm text-muted-foreground">{{ formatTs(lead.created_at) }}</td>
            </tr>

            <tr v-if="isLoading">
              <td colspan="6" class="px-4 py-8 text-center text-muted-foreground">
                <RefreshCw class="w-5 h-5 animate-spin mx-auto" />
              </td>
            </tr>
            <tr v-if="!isLoading && leads.length === 0">
              <td colspan="6" class="px-4 py-8 text-center text-muted-foreground">
                {{ t('crm.deals.empty') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

    </div>

    <!-- Detail Modal -->
    <div v-if="selectedLead" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" @click.self="selectedLead = null">
      <div class="bg-card border border-border rounded-xl w-full max-w-lg max-h-[80vh] overflow-y-auto">
        <div class="flex items-center justify-between p-4 border-b border-border">
          <h3 class="font-semibold text-lg">{{ selectedLead.name }}</h3>
          <div class="flex items-center gap-2">
            <a
              :href="`https://${subdomain}.amocrm.ru/leads/detail/${selectedLead.id}`"
              target="_blank"
              class="btn btn-ghost btn-sm"
            >
              <ExternalLink class="w-4 h-4" />
            </a>
            <button class="btn btn-ghost btn-sm" @click="selectedLead = null">
              <X class="w-4 h-4" />
            </button>
          </div>
        </div>

        <div class="p-4 space-y-4">
          <!-- Lead info -->
          <div class="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span class="text-muted-foreground">{{ t('crm.deals.price') }}</span>
              <div class="font-medium text-green-400">{{ formatPrice(selectedLead.price) }}</div>
            </div>
            <div>
              <span class="text-muted-foreground">{{ t('crm.deals.pipeline') }}</span>
              <div class="font-medium">{{ getPipelineName(selectedLead.pipeline_id) }}</div>
            </div>
            <div>
              <span class="text-muted-foreground">{{ t('crm.deals.status') }}</span>
              <div>
                <span
                  class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs"
                  :style="{ backgroundColor: getStatusColor(selectedLead.pipeline_id, selectedLead.status_id) + '30', color: getStatusColor(selectedLead.pipeline_id, selectedLead.status_id) }"
                >
                  {{ getStatusName(selectedLead.pipeline_id, selectedLead.status_id) }}
                </span>
              </div>
            </div>
            <div>
              <span class="text-muted-foreground">{{ t('crm.deals.created') }}</span>
              <div class="font-medium">{{ formatTs(selectedLead.created_at) }}</div>
            </div>
          </div>

          <!-- Contacts -->
          <div v-if="selectedLead._embedded?.contacts?.length">
            <h4 class="text-sm font-medium mb-2 flex items-center gap-1">
              <User class="w-4 h-4" />
              {{ t('crm.deals.contacts') }}
            </h4>
            <div class="space-y-1">
              <div
                v-for="contact in selectedLead._embedded.contacts"
                :key="contact.id"
                class="text-sm p-2 rounded bg-secondary/30"
              >
                {{ contact.name }}
              </div>
            </div>
          </div>

          <!-- Add note -->
          <div>
            <h4 class="text-sm font-medium mb-2 flex items-center gap-1">
              <StickyNote class="w-4 h-4" />
              {{ t('crm.deals.addNote') }}
            </h4>
            <textarea
              v-model="noteText"
              :placeholder="t('crm.deals.notePlaceholder')"
              rows="3"
              class="input w-full resize-none"
            />
            <button
              class="btn btn-primary btn-sm mt-2"
              :disabled="!noteText.trim() || addNoteMutation.isPending.value"
              @click="submitNote"
            >
              {{ t('crm.deals.sendNote') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Dialog -->
    <div v-if="showCreateDialog" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" @click.self="showCreateDialog = false">
      <div class="bg-card border border-border rounded-xl w-full max-w-md">
        <div class="flex items-center justify-between p-4 border-b border-border">
          <h3 class="font-semibold">{{ t('crm.deals.create') }}</h3>
          <button class="btn btn-ghost btn-sm" @click="showCreateDialog = false">
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="p-4 space-y-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">{{ t('crm.deals.name') }}</label>
            <input v-model="newDeal.name" type="text" class="input w-full" :placeholder="t('crm.deals.namePlaceholder')" />
          </div>

          <div>
            <label class="block text-sm font-medium mb-1.5">{{ t('crm.deals.pipeline') }}</label>
            <select v-model="newDeal.pipeline_id" class="input w-full">
              <option :value="0" disabled>{{ t('crm.deals.selectPipeline') }}</option>
              <option v-for="p in pipelines" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>

          <div class="flex justify-end gap-2">
            <button class="btn btn-secondary" @click="showCreateDialog = false">
              {{ t('crm.deals.cancel') }}
            </button>
            <button
              class="btn btn-primary"
              :disabled="!newDeal.name.trim() || createMutation.isPending.value"
              @click="createMutation.mutate({ name: newDeal.name, pipeline_id: newDeal.pipeline_id || undefined })"
            >
              {{ t('crm.deals.create') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
