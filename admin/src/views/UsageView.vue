<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { usageApi, type UsageLog, type UsageQueryParams, type UsageLimit } from '@/api'
import {
  BarChart3,
  RefreshCw,
  Filter,
  ChevronLeft,
  ChevronRight,
  Trash2,
  Plus,
  Settings,
  X,
  AlertTriangle,
  Check,
  Activity,
  MessageSquare,
  Mic,
  Brain
} from 'lucide-vue-next'
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const queryClient = useQueryClient()

// Filters state
const filters = ref<UsageQueryParams>({
  service_type: undefined,
  action: undefined,
  source: undefined,
  from_date: undefined,
  to_date: undefined,
  limit: 50,
  offset: 0
})

const showFilters = ref(false)
const showLimitsModal = ref(false)
const editingLimit = ref<UsageLimit | null>(null)
const periodDays = ref(30)

// New limit form
const newLimit = ref({
  service_type: 'tts',
  limit_type: 'daily',
  limit_value: 10000,
  hard_limit: false,
  warning_threshold: 80
})

// Queries
const {
  data: logsData,
  isLoading,
  refetch
} = useQuery({
  queryKey: ['usage-logs', filters],
  queryFn: () => usageApi.getLogs(filters.value)
})

const { data: statsData, isLoading: statsLoading } = useQuery({
  queryKey: ['usage-stats', periodDays],
  queryFn: () => usageApi.getStats(undefined, periodDays.value)
})

const { data: limitsData, refetch: refetchLimits } = useQuery({
  queryKey: ['usage-limits'],
  queryFn: () => usageApi.getLimits(false)
})

const { data: summaryData } = useQuery({
  queryKey: ['usage-summary'],
  queryFn: () => usageApi.getSummary()
})

// Mutations
const setLimitMutation = useMutation({
  mutationFn: (limit: typeof newLimit.value) =>
    usageApi.setLimit(
      limit.service_type,
      limit.limit_type,
      limit.limit_value,
      limit.hard_limit,
      limit.warning_threshold
    ),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['usage-limits'] })
    queryClient.invalidateQueries({ queryKey: ['usage-summary'] })
    showLimitsModal.value = false
    resetNewLimit()
  }
})

const deleteLimitMutation = useMutation({
  mutationFn: (limit: UsageLimit) => usageApi.deleteLimit(limit.service_type, limit.limit_type),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['usage-limits'] })
    queryClient.invalidateQueries({ queryKey: ['usage-summary'] })
  }
})

const cleanupMutation = useMutation({
  mutationFn: (days: number) => usageApi.cleanup(days),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['usage-logs'] })
    queryClient.invalidateQueries({ queryKey: ['usage-stats'] })
  }
})

// Computed
const logs = computed(() => logsData.value?.logs || [])
const stats = computed(() => statsData.value?.stats)
const limits = computed(() => limitsData.value?.limits || [])
const summary = computed(() => summaryData.value?.summary)

const currentPage = computed(
  () => Math.floor((filters.value.offset || 0) / (filters.value.limit || 50)) + 1
)
const hasMore = computed(() => logs.value.length >= (filters.value.limit || 50))

const totalRequests = computed(() => {
  if (!stats.value?.by_service) return 0
  return Object.values(stats.value.by_service).reduce((sum, s) => sum + (s.requests || 0), 0)
})

const totalCost = computed(() => {
  if (!stats.value?.by_service) return 0
  return Object.values(stats.value.by_service).reduce((sum, s) => sum + (s.cost_usd || 0), 0)
})

// Methods
function applyFilters() {
  filters.value.offset = 0
  refetch()
}

function clearFilters() {
  filters.value = {
    service_type: undefined,
    action: undefined,
    source: undefined,
    from_date: undefined,
    to_date: undefined,
    limit: 50,
    offset: 0
  }
  refetch()
}

function nextPage() {
  filters.value.offset = (filters.value.offset || 0) + (filters.value.limit || 50)
  refetch()
}

function prevPage() {
  const newOffset = (filters.value.offset || 0) - (filters.value.limit || 50)
  filters.value.offset = Math.max(0, newOffset)
  refetch()
}

function resetNewLimit() {
  newLimit.value = {
    service_type: 'tts',
    limit_type: 'daily',
    limit_value: 10000,
    hard_limit: false,
    warning_threshold: 80
  }
  editingLimit.value = null
}

function editLimit(limit: UsageLimit) {
  newLimit.value = {
    service_type: limit.service_type,
    limit_type: limit.limit_type,
    limit_value: limit.limit_value,
    hard_limit: limit.hard_limit,
    warning_threshold: limit.warning_threshold
  }
  editingLimit.value = limit
  showLimitsModal.value = true
}

function saveLimit() {
  setLimitMutation.mutate(newLimit.value)
}

function deleteLimit(limit: UsageLimit) {
  if (confirm(t('usage.confirmDeleteLimit'))) {
    deleteLimitMutation.mutate(limit)
  }
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString()
}

function getServiceIcon(service: string) {
  switch (service) {
    case 'tts':
      return Mic
    case 'stt':
      return MessageSquare
    case 'llm':
      return Brain
    default:
      return Activity
  }
}

function getServiceColor(service: string) {
  switch (service) {
    case 'tts':
      return 'bg-purple-500/20 text-purple-400'
    case 'stt':
      return 'bg-blue-500/20 text-blue-400'
    case 'llm':
      return 'bg-green-500/20 text-green-400'
    default:
      return 'bg-gray-500/20 text-gray-400'
  }
}

function getUsagePercent(service: string, period: string) {
  if (!summary.value?.[service]) return 0
  const data = period === 'daily' ? summary.value[service].daily : summary.value[service].monthly
  return data.percent || 0
}

function getUsageBarColor(percent: number) {
  if (percent >= 100) return 'bg-red-500'
  if (percent >= 80) return 'bg-yellow-500'
  return 'bg-green-500'
}
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h1 class="text-3xl font-bold flex items-center gap-2">
        <BarChart3 class="w-8 h-8" />
        {{ t('nav.usage') }}
      </h1>
      <div class="flex gap-2">
        <button :disabled="isLoading" class="btn btn-sm btn-outline" @click="refetch()">
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoading }" />
        </button>
        <button class="btn btn-sm btn-primary" @click="showLimitsModal = true">
          <Settings class="w-4 h-4" />
          {{ t('usage.configureLimits') }}
        </button>
      </div>
    </div>

    <!-- Usage Summary Cards -->
    <div v-if="summary" class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div
        v-for="service in ['tts', 'stt', 'llm']"
        :key="service"
        class="card bg-base-100 shadow-md"
      >
        <div class="card-body">
          <div class="flex items-center justify-between">
            <h3 class="card-title text-lg uppercase">{{ service }}</h3>
            <component :is="getServiceIcon(service)" class="w-5 h-5 opacity-50" />
          </div>

          <!-- Daily Usage -->
          <div class="space-y-1">
            <div class="flex justify-between text-sm">
              <span>{{ t('usage.daily') }}</span>
              <span>
                {{ summary[service]?.daily.used || 0 }}
                <span v-if="summary[service]?.daily.limit">
                  / {{ summary[service]?.daily.limit }}
                </span>
              </span>
            </div>
            <div class="w-full bg-base-300 rounded-full h-2">
              <div
                class="h-2 rounded-full transition-all"
                :class="getUsageBarColor(getUsagePercent(service, 'daily'))"
                :style="{ width: `${Math.min(100, getUsagePercent(service, 'daily'))}%` }"
              ></div>
            </div>
          </div>

          <!-- Monthly Usage -->
          <div class="space-y-1">
            <div class="flex justify-between text-sm">
              <span>{{ t('usage.monthly') }}</span>
              <span>
                {{ summary[service]?.monthly.used || 0 }}
                <span v-if="summary[service]?.monthly.limit">
                  / {{ summary[service]?.monthly.limit }}
                </span>
              </span>
            </div>
            <div class="w-full bg-base-300 rounded-full h-2">
              <div
                class="h-2 rounded-full transition-all"
                :class="getUsageBarColor(getUsagePercent(service, 'monthly'))"
                :style="{ width: `${Math.min(100, getUsagePercent(service, 'monthly'))}%` }"
              ></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Stats Overview -->
    <div v-if="stats && !statsLoading" class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="card bg-base-100 shadow-md">
        <div class="card-body">
          <h3 class="card-title text-lg">{{ t('usage.totalRequests') }}</h3>
          <p class="text-3xl font-bold text-primary">{{ totalRequests }}</p>
          <p class="text-sm opacity-70">{{ t('usage.lastNDays', { n: periodDays }) }}</p>
        </div>
      </div>
      <div class="card bg-base-100 shadow-md">
        <div class="card-body">
          <h3 class="card-title text-lg">{{ t('usage.totalCost') }}</h3>
          <p class="text-3xl font-bold text-success">${{ totalCost.toFixed(2) }}</p>
          <p class="text-sm opacity-70">{{ t('usage.lastNDays', { n: periodDays }) }}</p>
        </div>
      </div>
      <div class="card bg-base-100 shadow-md">
        <div class="card-body">
          <h3 class="card-title text-lg">{{ t('usage.activeLimits') }}</h3>
          <p class="text-3xl font-bold">{{ limits.filter((l) => l.enabled).length }}</p>
          <p class="text-sm opacity-70">{{ t('usage.limitsConfigured') }}</p>
        </div>
      </div>
    </div>

    <!-- Usage by Service -->
    <div v-if="stats" class="card bg-base-100 shadow-md">
      <div class="card-body">
        <h2 class="card-title">{{ t('usage.byService') }}</h2>
        <div class="space-y-3">
          <div
            v-for="(data, service) in stats.by_service"
            :key="service"
            class="flex justify-between items-center p-3 bg-base-200 rounded"
          >
            <div class="flex items-center gap-2">
              <component :is="getServiceIcon(service as string)" class="w-5 h-5" />
              <span class="font-semibold uppercase">{{ service }}</span>
            </div>
            <div class="space-x-4 text-right">
              <span class="badge badge-ghost">{{ data.requests }} {{ t('usage.requests') }}</span>
              <span class="badge badge-ghost">{{ data.units }} {{ t('usage.units') }}</span>
              <span class="badge badge-success">${{ data.cost_usd?.toFixed(2) || '0.00' }}</span>
            </div>
          </div>
          <div
            v-if="Object.keys(stats.by_service || {}).length === 0"
            class="text-center py-4 opacity-50"
          >
            {{ t('usage.noData') }}
          </div>
        </div>
      </div>
    </div>

    <!-- Filters Toggle -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('usage.logs') }}</h2>
      <button class="btn btn-sm btn-outline" @click="showFilters = !showFilters">
        <Filter class="w-4 h-4" />
        {{ showFilters ? t('common.hideFilters') : t('common.showFilters') }}
      </button>
    </div>

    <!-- Filters -->
    <div v-if="showFilters" class="card bg-base-100 shadow-md">
      <div class="card-body">
        <h2 class="card-title">{{ t('common.filters') }}</h2>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <select v-model="filters.service_type" class="select select-bordered">
            <option :value="undefined">{{ t('usage.allServices') }}</option>
            <option value="tts">TTS</option>
            <option value="stt">STT</option>
            <option value="llm">LLM</option>
          </select>
          <select v-model="filters.source" class="select select-bordered">
            <option :value="undefined">{{ t('usage.allSources') }}</option>
            <option value="admin">Admin</option>
            <option value="telegram">Telegram</option>
            <option value="widget">Widget</option>
          </select>
          <input
            v-model="filters.from_date"
            type="datetime-local"
            class="input input-bordered"
            :placeholder="t('common.fromDate')"
          />
          <input
            v-model="filters.to_date"
            type="datetime-local"
            class="input input-bordered"
            :placeholder="t('common.toDate')"
          />
        </div>
        <div class="flex gap-2 mt-4">
          <button class="btn btn-primary" @click="applyFilters">{{ t('common.apply') }}</button>
          <button class="btn btn-outline" @click="clearFilters">{{ t('common.clear') }}</button>
        </div>
      </div>
    </div>

    <!-- Logs Table -->
    <div class="card bg-base-100 shadow-md">
      <div class="card-body">
        <div class="overflow-x-auto">
          <table class="table">
            <thead>
              <tr>
                <th>{{ t('common.timestamp') }}</th>
                <th>{{ t('usage.service') }}</th>
                <th>{{ t('usage.action') }}</th>
                <th>{{ t('usage.source') }}</th>
                <th>{{ t('usage.units') }}</th>
                <th>{{ t('usage.cost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="log in logs" :key="log.id" class="hover">
                <td class="text-sm">{{ formatDate(log.timestamp) }}</td>
                <td>
                  <span class="badge" :class="getServiceColor(log.service_type)">
                    {{ log.service_type.toUpperCase() }}
                  </span>
                </td>
                <td>{{ log.action }}</td>
                <td>{{ log.source || '-' }}</td>
                <td>{{ log.units_consumed }}</td>
                <td>${{ log.cost_usd?.toFixed(4) || '0.0000' }}</td>
              </tr>
              <tr v-if="logs.length === 0">
                <td colspan="6" class="text-center py-8 opacity-50">
                  {{ t('usage.noLogs') }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div class="flex justify-between items-center mt-4">
          <span class="text-sm opacity-70">{{ t('common.page') }} {{ currentPage }}</span>
          <div class="flex gap-2">
            <button :disabled="currentPage === 1" class="btn btn-sm btn-outline" @click="prevPage">
              <ChevronLeft class="w-4 h-4" />
              {{ t('common.prev') }}
            </button>
            <button :disabled="!hasMore" class="btn btn-sm btn-outline" @click="nextPage">
              {{ t('common.next') }}
              <ChevronRight class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Limits Modal -->
    <dialog :class="{ modal: true, 'modal-open': showLimitsModal }">
      <div class="modal-box max-w-2xl">
        <h3 class="font-bold text-lg flex items-center gap-2">
          <Settings class="w-5 h-5" />
          {{ t('usage.configureLimits') }}
        </h3>

        <!-- Existing Limits -->
        <div class="mt-4">
          <h4 class="font-semibold mb-2">{{ t('usage.currentLimits') }}</h4>
          <div v-if="limits.length > 0" class="space-y-2">
            <div
              v-for="limit in limits"
              :key="`${limit.service_type}-${limit.limit_type}`"
              class="flex justify-between items-center p-3 bg-base-200 rounded"
            >
              <div>
                <span class="font-semibold uppercase">{{ limit.service_type }}</span>
                <span class="mx-2">-</span>
                <span>{{ limit.limit_type }}</span>
                <span class="badge badge-sm ml-2" :class="limit.hard_limit ? 'badge-error' : 'badge-warning'">
                  {{ limit.hard_limit ? t('usage.hardLimit') : t('usage.softLimit') }}
                </span>
              </div>
              <div class="flex items-center gap-2">
                <span class="font-mono">{{ limit.limit_value.toLocaleString() }}</span>
                <button class="btn btn-xs btn-ghost" @click="editLimit(limit)">
                  <Settings class="w-3 h-3" />
                </button>
                <button class="btn btn-xs btn-ghost text-error" @click="deleteLimit(limit)">
                  <Trash2 class="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>
          <div v-else class="text-center py-4 opacity-50">
            {{ t('usage.noLimitsConfigured') }}
          </div>
        </div>

        <!-- Add/Edit Limit Form -->
        <div class="divider">{{ editingLimit ? t('usage.editLimit') : t('usage.addLimit') }}</div>

        <div class="grid grid-cols-2 gap-4">
          <div class="form-control">
            <label class="label">
              <span class="label-text">{{ t('usage.service') }}</span>
            </label>
            <select v-model="newLimit.service_type" class="select select-bordered">
              <option value="tts">TTS</option>
              <option value="stt">STT</option>
              <option value="llm">LLM</option>
            </select>
          </div>
          <div class="form-control">
            <label class="label">
              <span class="label-text">{{ t('usage.limitType') }}</span>
            </label>
            <select v-model="newLimit.limit_type" class="select select-bordered">
              <option value="daily">{{ t('usage.daily') }}</option>
              <option value="monthly">{{ t('usage.monthly') }}</option>
            </select>
          </div>
          <div class="form-control">
            <label class="label">
              <span class="label-text">{{ t('usage.limitValue') }}</span>
            </label>
            <input
              v-model.number="newLimit.limit_value"
              type="number"
              min="1"
              class="input input-bordered"
            />
          </div>
          <div class="form-control">
            <label class="label">
              <span class="label-text">{{ t('usage.warningThreshold') }} (%)</span>
            </label>
            <input
              v-model.number="newLimit.warning_threshold"
              type="number"
              min="0"
              max="100"
              class="input input-bordered"
            />
          </div>
          <div class="form-control col-span-2">
            <label class="label cursor-pointer justify-start gap-2">
              <input v-model="newLimit.hard_limit" type="checkbox" class="checkbox" />
              <span class="label-text">
                {{ t('usage.hardLimitDescription') }}
              </span>
            </label>
          </div>
        </div>

        <div class="modal-action">
          <button
            class="btn"
            @click="
              showLimitsModal = false;
              resetNewLimit()
            "
          >
            {{ t('common.cancel') }}
          </button>
          <button
            :disabled="setLimitMutation.isPending.value"
            class="btn btn-primary"
            @click="saveLimit"
          >
            <Plus v-if="!editingLimit" class="w-4 h-4" />
            <Check v-else class="w-4 h-4" />
            {{ editingLimit ? t('common.save') : t('usage.addLimit') }}
          </button>
        </div>
      </div>
      <form method="dialog" class="modal-backdrop">
        <button @click="resetNewLimit">close</button>
      </form>
    </dialog>
  </div>
</template>
