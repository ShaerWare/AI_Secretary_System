<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { servicesApi, logsApi, type ServiceStatus } from '@/api'
import {
  Play,
  Square,
  RotateCw,
  RefreshCw,
  Terminal,
  CheckCircle2,
  XCircle,
  Loader2,
  Search,
  X
} from 'lucide-vue-next'
import { ref, computed, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'

const queryClient = useQueryClient()
const authStore = useAuthStore()

// State
const selectedLog = ref<string | null>(null)
const logSearch = ref('')
const logLines = ref<string[]>([])
const logLoading = ref(false)

// Queries
const { data: servicesData, isLoading } = useQuery({
  queryKey: ['services-status'],
  queryFn: () => servicesApi.getStatus(),
  refetchInterval: 5000,
})

const { data: logsData } = useQuery({
  queryKey: ['logs-list'],
  queryFn: () => logsApi.list(),
})

// Mutations
const startMutation = useMutation({
  mutationFn: (name: string) => servicesApi.startService(name),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['services-status'] }),
})

const stopMutation = useMutation({
  mutationFn: (name: string) => servicesApi.stopService(name),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['services-status'] }),
})

const restartMutation = useMutation({
  mutationFn: (name: string) => servicesApi.restartService(name),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['services-status'] }),
})

const startAllMutation = useMutation({
  mutationFn: () => servicesApi.startAll(),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['services-status'] }),
})

const stopAllMutation = useMutation({
  mutationFn: () => servicesApi.stopAll(),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['services-status'] }),
})

// Computed
const services = computed(() => {
  if (!servicesData.value) return []
  return Object.entries(servicesData.value.services).map(([key, value]) => ({
    id: key,
    ...value,
  }))
})

const externalServices = computed(() =>
  services.value.filter(s => !s.internal)
)

const internalServices = computed(() =>
  services.value.filter(s => s.internal)
)

// Methods
async function loadLog(logfile: string) {
  selectedLog.value = logfile
  logLoading.value = true
  try {
    const response = await logsApi.read(logfile, 200, 0, logSearch.value || undefined)
    logLines.value = response.lines
  } catch (e) {
    console.error('Failed to load log:', e)
    logLines.value = ['Error loading log']
  } finally {
    logLoading.value = false
  }
}

async function refreshLog() {
  if (selectedLog.value) {
    await loadLog(selectedLog.value)
  }
}

function closeLog() {
  selectedLog.value = null
  logLines.value = []
}

function getLogLineClass(line: string): string {
  const lower = line.toLowerCase()
  if (lower.includes('error') || lower.includes('❌')) return 'log-line error'
  if (lower.includes('warning') || lower.includes('⚠️')) return 'log-line warning'
  if (lower.includes('info') || lower.includes('✅')) return 'log-line info'
  return 'log-line'
}

// Watch search changes
watch(logSearch, async () => {
  if (selectedLog.value) {
    await loadLog(selectedLog.value)
  }
})
</script>

<template>
  <div class="space-y-6">
    <!-- Toolbar -->
    <div class="flex items-center gap-4">
      <button
        v-if="authStore.canManage('system')"
        :disabled="startAllMutation.isPending.value"
        class="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
        @click="startAllMutation.mutate()"
      >
        <Play class="w-4 h-4" />
        Start All
      </button>
      <button
        v-if="authStore.canManage('system')"
        :disabled="stopAllMutation.isPending.value"
        class="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
        @click="stopAllMutation.mutate()"
      >
        <Square class="w-4 h-4" />
        Stop All
      </button>
      <button
        class="flex items-center gap-2 px-4 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
        @click="queryClient.invalidateQueries({ queryKey: ['services-status'] })"
      >
        <RefreshCw class="w-4 h-4" />
        Refresh
      </button>
    </div>

    <!-- External Services -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border">
        <h2 class="text-lg font-semibold">External Services</h2>
        <p class="text-sm text-muted-foreground">Managed by ServiceManager (can be started/stopped)</p>
      </div>

      <div class="divide-y divide-border">
        <div
          v-for="service in externalServices"
          :key="service.id"
          class="flex items-center justify-between p-4"
        >
          <div class="flex items-center gap-4">
            <div
:class="[
              'p-2 rounded-lg',
              service.is_running ? 'bg-green-500/20' : 'bg-red-500/20'
            ]">
              <CheckCircle2 v-if="service.is_running" class="w-5 h-5 text-green-500" />
              <XCircle v-else class="w-5 h-5 text-red-500" />
            </div>
            <div>
              <p class="font-medium">{{ service.display_name }}</p>
              <p class="text-sm text-muted-foreground">
                <template v-if="service.is_running">
                  PID: {{ service.pid }} | Memory: {{ service.memory_mb?.toFixed(0) }} MB
                  <span v-if="service.port"> | Port: {{ service.port }}</span>
                </template>
                <template v-else>
                  Not running
                  <span v-if="service.last_error" class="text-red-400"> - {{ service.last_error }}</span>
                </template>
              </p>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <button
              v-if="service.log_file"
              class="p-2 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors"
              title="View Logs"
              @click="loadLog(service.id)"
            >
              <Terminal class="w-4 h-4" />
            </button>
            <button
              v-if="!service.is_running && authStore.canManage('system')"
              :disabled="startMutation.isPending.value"
              class="p-2 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
              title="Start"
              @click="startMutation.mutate(service.id)"
            >
              <Loader2 v-if="startMutation.isPending.value" class="w-4 h-4 animate-spin" />
              <Play v-else class="w-4 h-4" />
            </button>
            <button
              v-if="service.is_running && authStore.canManage('system')"
              :disabled="stopMutation.isPending.value"
              class="p-2 rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
              title="Stop"
              @click="stopMutation.mutate(service.id)"
            >
              <Loader2 v-if="stopMutation.isPending.value" class="w-4 h-4 animate-spin" />
              <Square v-else class="w-4 h-4" />
            </button>
            <button
              v-if="authStore.canManage('system')"
              :disabled="restartMutation.isPending.value"
              class="p-2 rounded-lg bg-secondary hover:bg-secondary/80 disabled:opacity-50 transition-colors"
              title="Restart"
              @click="restartMutation.mutate(service.id)"
            >
              <Loader2 v-if="restartMutation.isPending.value" class="w-4 h-4 animate-spin" />
              <RotateCw v-else class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Internal Services -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border">
        <h2 class="text-lg font-semibold">Internal Services</h2>
        <p class="text-sm text-muted-foreground">Managed by Orchestrator (restart orchestrator to change)</p>
      </div>

      <div class="divide-y divide-border">
        <div
          v-for="service in internalServices"
          :key="service.id"
          class="flex items-center justify-between p-4"
        >
          <div class="flex items-center gap-4">
            <div
:class="[
              'p-2 rounded-lg',
              service.is_running ? 'bg-green-500/20' : 'bg-gray-500/20'
            ]">
              <CheckCircle2 v-if="service.is_running" class="w-5 h-5 text-green-500" />
              <XCircle v-else class="w-5 h-5 text-gray-500" />
            </div>
            <div>
              <p class="font-medium">{{ service.display_name }}</p>
              <p class="text-sm text-muted-foreground">
                <span v-if="service.gpu_required" class="text-purple-400">GPU Required</span>
                <span v-else-if="service.cpu_only" class="text-blue-400">CPU Only</span>
              </p>
            </div>
          </div>
          <span
:class="[
            'text-sm px-2 py-1 rounded',
            service.is_running ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'
          ]">
            {{ service.is_running ? 'Loaded' : 'Not loaded' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Log Viewer Modal -->
    <div
      v-if="selectedLog"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="closeLog"
    >
      <div class="bg-card border border-border rounded-lg w-full max-w-4xl max-h-[80vh] flex flex-col">
        <div class="flex items-center justify-between p-4 border-b border-border">
          <h3 class="text-lg font-semibold">Logs: {{ selectedLog }}</h3>
          <div class="flex items-center gap-2">
            <div class="relative">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                v-model="logSearch"
                type="text"
                placeholder="Search..."
                class="pl-9 pr-3 py-1.5 bg-secondary rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <button
              class="p-2 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors"
              @click="refreshLog"
            >
              <RefreshCw class="w-4 h-4" />
            </button>
            <button
              class="p-2 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors"
              @click="closeLog"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
        </div>

        <div class="flex-1 overflow-auto p-4 log-viewer bg-background">
          <div v-if="logLoading" class="text-center text-muted-foreground">
            Loading...
          </div>
          <div v-else-if="logLines.length === 0" class="text-center text-muted-foreground">
            No log entries
          </div>
          <div v-else>
            <div
              v-for="(line, i) in logLines"
              :key="i"
              :class="getLogLineClass(line)"
            >
              {{ line }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
