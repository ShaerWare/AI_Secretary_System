<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { monitorApi, type GpuFullInfo, type DockerContainer, type ProcessInfo, type DiskInfo, type NetworkInfo } from '@/api'
import {
  Activity,
  Cpu,
  HardDrive,
  Thermometer,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Trash2,
  Server,
  Database,
  Wifi,
  Box,
  Zap,
  Fan,
  Clock,
  Monitor,
  MemoryStick
} from 'lucide-vue-next'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

const queryClient = useQueryClient()

// State
const gpuHistory = ref<{ time: string; allocated: number }[]>([])
let gpuStreamHandle: { close: () => void } | null = null
const activeTab = ref<'overview' | 'gpus' | 'docker' | 'processes' | 'network' | 'disks'>('overview')

// Queries
const { data: systemData, isLoading: systemLoading, refetch: refetchSystem } = useQuery({
  queryKey: ['system-status'],
  queryFn: () => monitorApi.getSystemStatus(),
  refetchInterval: 5000,
})

const { data: healthData, isLoading: healthLoading, refetch: refetchHealth } = useQuery({
  queryKey: ['health'],
  queryFn: () => monitorApi.getHealth(),
  refetchInterval: 10000,
})

const { data: metricsData, refetch: refetchMetrics } = useQuery({
  queryKey: ['metrics'],
  queryFn: () => monitorApi.getMetrics(),
  refetchInterval: 5000,
})

const { data: errorsData, refetch: refetchErrors } = useQuery({
  queryKey: ['errors'],
  queryFn: () => monitorApi.getErrors(),
})

// Mutations
const resetMetricsMutation = useMutation({
  mutationFn: () => monitorApi.resetMetrics(),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['metrics'] })
  },
})

// Computed
const gpus = computed(() => systemData.value?.gpus || [])
const cpu = computed(() => systemData.value?.cpu)
const memory = computed(() => systemData.value?.memory)
const disks = computed(() => systemData.value?.disks || [])
const docker = computed(() => systemData.value?.docker || [])
const network = computed(() => systemData.value?.network || [])
const processes = computed(() => systemData.value?.processes || [])
const systemInfo = computed(() => systemData.value?.system)

const healthComponents = computed(() => healthData.value?.components || {})

const errors = computed(() => {
  if (!errorsData.value?.errors) return []
  return Object.entries(errorsData.value.errors).map(([service, error]) => ({
    service,
    error,
  }))
})

const runningContainers = computed(() => docker.value.filter(c => c.state === 'running'))
const stoppedContainers = computed(() => docker.value.filter(c => c.state !== 'running'))

// GPU streaming for history
function startGpuStream() {
  gpuStreamHandle = monitorApi.streamGpuStats((data) => {
    if (data.gpus?.[0]) {
      const now = new Date().toLocaleTimeString()
      gpuHistory.value.push({
        time: now,
        allocated: data.gpus[0].allocated_gb,
      })
      if (gpuHistory.value.length > 60) {
        gpuHistory.value = gpuHistory.value.slice(-60)
      }
    }
  })
}

function stopGpuStream() {
  if (gpuStreamHandle) {
    gpuStreamHandle.close()
    gpuStreamHandle = null
  }
}

function refreshAll() {
  refetchSystem()
  refetchHealth()
  refetchMetrics()
  refetchErrors()
}

function getStatusColor(status: string) {
  switch (status) {
    case 'healthy':
      return 'text-green-500'
    case 'unhealthy':
      return 'text-red-500'
    case 'unavailable':
    case 'stopped':
      return 'text-yellow-500'
    default:
      return 'text-muted-foreground'
  }
}

function getStatusIcon(status: string) {
  switch (status) {
    case 'healthy':
      return CheckCircle2
    case 'unhealthy':
      return XCircle
    default:
      return AlertTriangle
  }
}

function getTempColor(temp: number): string {
  if (temp > 85) return 'text-red-500'
  if (temp > 70) return 'text-orange-500'
  if (temp > 55) return 'text-yellow-500'
  return 'text-green-500'
}

function getUsageColor(percent: number): string {
  if (percent > 90) return 'bg-red-500'
  if (percent > 75) return 'bg-orange-500'
  if (percent > 50) return 'bg-yellow-500'
  return 'bg-green-500'
}

function formatBytes(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`
  return `${mb.toFixed(0)} MB`
}

function shortenGpuName(name: string): string {
  // "NVIDIA GeForce RTX 3060" → "RTX 3060"
  // "NVIDIA GeForce GTX 1080 Ti" → "GTX 1080 Ti"
  // "NVIDIA A100-SXM4-40GB" → "A100-SXM4"
  if (!name) return 'GPU'
  return name
    .replace(/^NVIDIA\s*/i, '')
    .replace(/^GeForce\s*/i, '')
    .replace(/-\d+GB$/i, '') // Remove memory suffix like -40GB
    .trim()
}

onMounted(() => {
  startGpuStream()
})

onUnmounted(() => {
  stopGpuStream()
})
</script>

<template>
  <div class="space-y-6">
    <!-- System Info Header -->
    <div v-if="systemInfo" class="bg-card rounded-lg border border-border p-4">
      <div class="flex items-center justify-between flex-wrap gap-4">
        <div class="flex items-center gap-4">
          <div class="p-3 rounded-lg bg-primary/20">
            <Server class="w-6 h-6 text-primary" />
          </div>
          <div>
            <h1 class="text-xl font-bold">{{ systemInfo.hostname }}</h1>
            <p class="text-sm text-muted-foreground">{{ systemInfo.os }}</p>
          </div>
        </div>
        <div class="flex items-center gap-6 text-sm">
          <div class="flex items-center gap-2">
            <Clock class="w-4 h-4 text-muted-foreground" />
            <span>Uptime: {{ systemInfo.uptime }}</span>
          </div>
          <span
:class="[
            'px-3 py-1 rounded-full text-sm font-medium',
            healthData?.overall === 'healthy' ? 'bg-green-500/20 text-green-500' : 'bg-yellow-500/20 text-yellow-500'
          ]">
            {{ healthData?.overall || 'unknown' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Toolbar -->
    <div class="flex items-center gap-4 flex-wrap">
      <div class="flex gap-2">
        <button
          v-for="tab in ['overview', 'gpus', 'docker', 'processes', 'network', 'disks'] as const"
          :key="tab"
          :class="[
            'px-4 py-2 rounded-lg transition-colors capitalize',
            activeTab === tab ? 'bg-primary text-primary-foreground' : 'bg-secondary hover:bg-secondary/80'
          ]"
          @click="activeTab = tab"
        >
          {{ tab }}
        </button>
      </div>
      <div class="flex-1" />
      <button
        class="flex items-center gap-2 px-4 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
        @click="refreshAll"
      >
        <RefreshCw class="w-4 h-4" />
        Refresh
      </button>
      <button
        :disabled="resetMetricsMutation.isPending.value"
        class="flex items-center gap-2 px-4 py-2 bg-secondary rounded-lg hover:bg-secondary/80 disabled:opacity-50 transition-colors"
        @click="resetMetricsMutation.mutate()"
      >
        <Trash2 class="w-4 h-4" />
        Reset Cache
      </button>
    </div>

    <!-- Overview Tab -->
    <template v-if="activeTab === 'overview'">
      <!-- Quick Stats Grid -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <!-- CPU -->
        <div class="bg-card rounded-lg border border-border p-4">
          <div class="flex items-center gap-3 mb-3">
            <div class="p-2 rounded-lg bg-blue-500/20">
              <Cpu class="w-5 h-5 text-blue-500" />
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-sm text-muted-foreground truncate">CPU</p>
              <p class="text-2xl font-bold">{{ cpu?.usage_percent?.toFixed(0) || 0 }}%</p>
            </div>
          </div>
          <div class="h-2 bg-secondary rounded-full overflow-hidden">
            <div
              :class="['h-full transition-all', getUsageColor(cpu?.usage_percent || 0)]"
              :style="{ width: `${cpu?.usage_percent || 0}%` }"
            />
          </div>
          <p v-if="cpu?.temperature_c" :class="['text-xs mt-2', getTempColor(cpu.temperature_c)]">
            {{ cpu.temperature_c.toFixed(0) }}°C
          </p>
        </div>

        <!-- RAM -->
        <div class="bg-card rounded-lg border border-border p-4">
          <div class="flex items-center gap-3 mb-3">
            <div class="p-2 rounded-lg bg-orange-500/20">
              <MemoryStick class="w-5 h-5 text-orange-500" />
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-sm text-muted-foreground">RAM</p>
              <p class="text-2xl font-bold">{{ memory?.percent_used?.toFixed(0) || 0 }}%</p>
            </div>
          </div>
          <div class="h-2 bg-secondary rounded-full overflow-hidden">
            <div
              :class="['h-full transition-all', getUsageColor(memory?.percent_used || 0)]"
              :style="{ width: `${memory?.percent_used || 0}%` }"
            />
          </div>
          <p class="text-xs text-muted-foreground mt-2">
            {{ memory?.used_gb?.toFixed(1) }} / {{ memory?.total_gb?.toFixed(1) }} GB
          </p>
        </div>

        <!-- GPU (first) -->
        <div class="bg-card rounded-lg border border-border p-4">
          <div class="flex items-center gap-3 mb-3">
            <div class="p-2 rounded-lg bg-purple-500/20">
              <Activity class="w-5 h-5 text-purple-500" />
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-sm text-muted-foreground truncate" :title="gpus[0]?.name">
                {{ gpus[0] ? shortenGpuName(gpus[0].name) : 'GPU' }}
                <span v-if="gpus[0]" class="text-xs opacity-75">{{ formatBytes(gpus[0].memory_total_mb) }}</span>
              </p>
              <p class="text-2xl font-bold">
                {{ gpus[0] ? Math.round((gpus[0].memory_used_mb / gpus[0].memory_total_mb) * 100) : 0 }}%
              </p>
            </div>
          </div>
          <div class="h-2 bg-secondary rounded-full overflow-hidden">
            <div
              class="h-full bg-purple-500 transition-all"
              :style="{ width: gpus[0] ? `${(gpus[0].memory_used_mb / gpus[0].memory_total_mb) * 100}%` : '0%' }"
            />
          </div>
          <p v-if="gpus[0]" class="text-xs text-muted-foreground mt-2">
            {{ formatBytes(gpus[0].memory_used_mb) }} / {{ formatBytes(gpus[0].memory_total_mb) }}
            <span :class="['ml-2', getTempColor(gpus[0].temperature_c)]">{{ gpus[0].temperature_c }}°C</span>
          </p>
        </div>

        <!-- Docker -->
        <div class="bg-card rounded-lg border border-border p-4">
          <div class="flex items-center gap-3 mb-3">
            <div class="p-2 rounded-lg bg-cyan-500/20">
              <Box class="w-5 h-5 text-cyan-500" />
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-sm text-muted-foreground">Docker</p>
              <p class="text-2xl font-bold">{{ runningContainers.length }}</p>
            </div>
          </div>
          <p class="text-xs text-muted-foreground">
            {{ runningContainers.length }} running, {{ stoppedContainers.length }} stopped
          </p>
        </div>
      </div>

      <!-- Health Status -->
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border">
          <h2 class="text-lg font-semibold">Services Health</h2>
        </div>
        <div v-if="healthLoading" class="p-8 text-center text-muted-foreground">Loading...</div>
        <div v-else class="grid grid-cols-2 md:grid-cols-4 gap-4 p-4">
          <div
            v-for="(component, name) in healthComponents"
            :key="name"
            class="flex items-center gap-3 p-3 rounded-lg bg-secondary/50"
          >
            <component
              :is="getStatusIcon(component.status)"
              :class="['w-5 h-5', getStatusColor(component.status)]"
            />
            <div class="min-w-0">
              <p class="font-medium capitalize truncate">{{ (name as string).replace(/_/g, ' ') }}</p>
              <p class="text-xs text-muted-foreground">{{ component.status }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Errors -->
      <div v-if="errors.length" class="bg-card rounded-lg border border-red-500/50">
        <div class="p-4 border-b border-border">
          <h2 class="text-lg font-semibold text-red-500">Recent Errors</h2>
        </div>
        <div class="divide-y divide-border">
          <div v-for="error in errors" :key="error.service" class="p-4">
            <p class="font-medium text-red-400">{{ error.service }}</p>
            <p class="text-sm text-muted-foreground mt-1">{{ error.error }}</p>
          </div>
        </div>
      </div>
    </template>

    <!-- GPUs Tab -->
    <template v-if="activeTab === 'gpus'">
      <div v-if="gpus.length === 0" class="bg-card rounded-lg border border-border p-8 text-center text-muted-foreground">
        No GPUs detected
      </div>
      <div v-else class="space-y-4">
        <div
          v-for="gpu in gpus"
          :key="gpu.index"
          class="bg-card rounded-lg border border-border"
        >
          <div class="p-4 border-b border-border flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="p-2 rounded-lg bg-purple-500/20">
                <Monitor class="w-5 h-5 text-purple-500" />
              </div>
              <div>
                <h3 class="font-semibold">
                  {{ shortenGpuName(gpu.name) }}
                  <span class="text-muted-foreground font-normal ml-2">{{ formatBytes(gpu.memory_total_mb) }}</span>
                </h3>
                <p class="text-sm text-muted-foreground">Driver: {{ gpu.driver_version }} | CC: {{ gpu.compute_capability }}</p>
              </div>
            </div>
            <div class="flex items-center gap-4">
              <div :class="['flex items-center gap-1', getTempColor(gpu.temperature_c)]">
                <Thermometer class="w-4 h-4" />
                <span class="font-medium">{{ gpu.temperature_c }}°C</span>
              </div>
              <div v-if="gpu.fan_speed_percent > 0" class="flex items-center gap-1 text-muted-foreground">
                <Fan class="w-4 h-4" />
                <span>{{ gpu.fan_speed_percent }}%</span>
              </div>
            </div>
          </div>

          <div class="p-4 grid grid-cols-2 md:grid-cols-4 gap-6">
            <!-- Memory -->
            <div>
              <p class="text-sm text-muted-foreground mb-2">VRAM Usage</p>
              <div class="h-3 bg-secondary rounded-full overflow-hidden mb-2">
                <div
                  class="h-full bg-purple-500 transition-all"
                  :style="{ width: `${(gpu.memory_used_mb / gpu.memory_total_mb) * 100}%` }"
                />
              </div>
              <p class="text-sm">
                {{ formatBytes(gpu.memory_used_mb) }} / {{ formatBytes(gpu.memory_total_mb) }}
                <span class="text-muted-foreground">({{ Math.round((gpu.memory_used_mb / gpu.memory_total_mb) * 100) }}%)</span>
              </p>
            </div>

            <!-- Utilization -->
            <div>
              <p class="text-sm text-muted-foreground mb-2">GPU Utilization</p>
              <div class="h-3 bg-secondary rounded-full overflow-hidden mb-2">
                <div
                  :class="['h-full transition-all', getUsageColor(gpu.utilization_percent)]"
                  :style="{ width: `${gpu.utilization_percent}%` }"
                />
              </div>
              <p class="text-sm">{{ gpu.utilization_percent }}%</p>
            </div>

            <!-- Power -->
            <div>
              <p class="text-sm text-muted-foreground mb-2">Power Draw</p>
              <div class="flex items-center gap-2">
                <Zap class="w-4 h-4 text-yellow-500" />
                <span class="text-lg font-medium">{{ gpu.power_draw_w?.toFixed(0) || 0 }}W</span>
                <span class="text-sm text-muted-foreground">/ {{ gpu.power_limit_w?.toFixed(0) || 0 }}W</span>
              </div>
            </div>

            <!-- PCIe -->
            <div>
              <p class="text-sm text-muted-foreground mb-2">PCIe Link</p>
              <p class="text-lg font-medium">Gen{{ gpu.pcie_gen }} x{{ gpu.pcie_width }}</p>
            </div>
          </div>
        </div>

        <!-- GPU Memory History Chart -->
        <div v-if="gpuHistory.length > 5" class="bg-card rounded-lg border border-border">
          <div class="p-4 border-b border-border">
            <h3 class="font-semibold">GPU #0 Memory History</h3>
          </div>
          <div class="p-4">
            <div class="h-32 flex items-end gap-1">
              <div
                v-for="(entry, i) in gpuHistory.slice(-30)"
                :key="i"
                class="flex-1 bg-purple-500 rounded-t transition-all"
                :style="{
                  height: `${(entry.allocated / (gpus[0]?.memory_total_mb / 1024 || 12)) * 100}%`,
                  minHeight: '4px'
                }"
                :title="`${entry.time}: ${entry.allocated.toFixed(2)} GB`"
              />
            </div>
            <div class="flex justify-between text-xs text-muted-foreground mt-2">
              <span>{{ gpuHistory[0]?.time }}</span>
              <span>{{ gpuHistory[gpuHistory.length - 1]?.time }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Docker Tab -->
    <template v-if="activeTab === 'docker'">
      <div v-if="docker.length === 0" class="bg-card rounded-lg border border-border p-8 text-center text-muted-foreground">
        No Docker containers found
      </div>
      <div v-else class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border">
          <h2 class="text-lg font-semibold">Docker Containers ({{ docker.length }})</h2>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-secondary/50">
              <tr>
                <th class="text-left p-3 font-medium">Name</th>
                <th class="text-left p-3 font-medium">Image</th>
                <th class="text-left p-3 font-medium">Status</th>
                <th class="text-left p-3 font-medium">CPU</th>
                <th class="text-left p-3 font-medium">Memory</th>
                <th class="text-left p-3 font-medium">Ports</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border">
              <tr v-for="container in docker" :key="container.id" class="hover:bg-secondary/30">
                <td class="p-3">
                  <div class="flex items-center gap-2">
                    <div
:class="[
                      'w-2 h-2 rounded-full',
                      container.state === 'running' ? 'bg-green-500' : 'bg-gray-500'
                    ]" />
                    <span class="font-medium">{{ container.name }}</span>
                  </div>
                </td>
                <td class="p-3 text-sm text-muted-foreground max-w-[200px] truncate">{{ container.image }}</td>
                <td class="p-3">
                  <span
:class="[
                    'px-2 py-1 rounded text-xs',
                    container.state === 'running' ? 'bg-green-500/20 text-green-500' :
                    container.state === 'exited' ? 'bg-gray-500/20 text-gray-500' :
                    'bg-yellow-500/20 text-yellow-500'
                  ]">
                    {{ container.status }}
                  </span>
                </td>
                <td class="p-3">{{ container.cpu_percent?.toFixed(1) || 0 }}%</td>
                <td class="p-3">
                  <span v-if="container.memory_mb">{{ formatBytes(container.memory_mb) }}</span>
                  <span v-else>-</span>
                </td>
                <td class="p-3 text-sm text-muted-foreground max-w-[200px] truncate">{{ container.ports || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- Processes Tab -->
    <template v-if="activeTab === 'processes'">
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border">
          <h2 class="text-lg font-semibold">Top Processes (by CPU + Memory)</h2>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-secondary/50">
              <tr>
                <th class="text-left p-3 font-medium">PID</th>
                <th class="text-left p-3 font-medium">Name</th>
                <th class="text-left p-3 font-medium">CPU %</th>
                <th class="text-left p-3 font-medium">Memory %</th>
                <th class="text-left p-3 font-medium">Memory</th>
                <th class="text-left p-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border">
              <tr v-for="proc in processes" :key="proc.pid" class="hover:bg-secondary/30">
                <td class="p-3 font-mono text-sm">{{ proc.pid }}</td>
                <td class="p-3">
                  <p class="font-medium">{{ proc.name }}</p>
                  <p class="text-xs text-muted-foreground truncate max-w-[300px]">{{ proc.cmdline }}</p>
                </td>
                <td class="p-3">
                  <div class="flex items-center gap-2">
                    <div class="w-16 h-2 bg-secondary rounded-full overflow-hidden">
                      <div
                        :class="['h-full', getUsageColor(proc.cpu_percent)]"
                        :style="{ width: `${Math.min(proc.cpu_percent, 100)}%` }"
                      />
                    </div>
                    <span class="text-sm">{{ proc.cpu_percent?.toFixed(1) }}%</span>
                  </div>
                </td>
                <td class="p-3">
                  <div class="flex items-center gap-2">
                    <div class="w-16 h-2 bg-secondary rounded-full overflow-hidden">
                      <div
                        :class="['h-full', getUsageColor(proc.memory_percent)]"
                        :style="{ width: `${proc.memory_percent}%` }"
                      />
                    </div>
                    <span class="text-sm">{{ proc.memory_percent?.toFixed(1) }}%</span>
                  </div>
                </td>
                <td class="p-3">{{ formatBytes(proc.memory_mb) }}</td>
                <td class="p-3">
                  <span
:class="[
                    'px-2 py-1 rounded text-xs',
                    proc.status === 'running' ? 'bg-green-500/20 text-green-500' :
                    proc.status === 'sleeping' ? 'bg-blue-500/20 text-blue-500' :
                    'bg-gray-500/20 text-gray-500'
                  ]">
                    {{ proc.status }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- Network Tab -->
    <template v-if="activeTab === 'network'">
      <div v-if="network.length === 0" class="bg-card rounded-lg border border-border p-8 text-center text-muted-foreground">
        No network interfaces found
      </div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div
          v-for="iface in network"
          :key="iface.interface"
          class="bg-card rounded-lg border border-border p-4"
        >
          <div class="flex items-center gap-3 mb-4">
            <div
:class="[
              'p-2 rounded-lg',
              iface.is_up ? 'bg-green-500/20' : 'bg-gray-500/20'
            ]">
              <Wifi :class="['w-5 h-5', iface.is_up ? 'text-green-500' : 'text-gray-500']" />
            </div>
            <div>
              <h3 class="font-semibold">{{ iface.interface }}</h3>
              <p class="text-sm text-muted-foreground">{{ iface.ip_address }}</p>
            </div>
            <div class="ml-auto">
              <span
:class="[
                'px-2 py-1 rounded text-xs',
                iface.is_up ? 'bg-green-500/20 text-green-500' : 'bg-gray-500/20 text-gray-500'
              ]">
                {{ iface.is_up ? 'UP' : 'DOWN' }}
              </span>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p class="text-muted-foreground">MAC</p>
              <p class="font-mono">{{ iface.mac_address || '-' }}</p>
            </div>
            <div>
              <p class="text-muted-foreground">Traffic</p>
              <p>
                <span class="text-green-500">↑</span> {{ iface.bytes_sent_mb?.toFixed(1) }} MB
                <span class="text-blue-500 ml-2">↓</span> {{ iface.bytes_recv_mb?.toFixed(1) }} MB
              </p>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Disks Tab -->
    <template v-if="activeTab === 'disks'">
      <div v-if="disks.length === 0" class="bg-card rounded-lg border border-border p-8 text-center text-muted-foreground">
        No disks found
      </div>
      <div v-else class="space-y-4">
        <div
          v-for="disk in disks"
          :key="disk.mountpoint"
          class="bg-card rounded-lg border border-border p-4"
        >
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-3">
              <div class="p-2 rounded-lg bg-blue-500/20">
                <HardDrive class="w-5 h-5 text-blue-500" />
              </div>
              <div>
                <h3 class="font-semibold">{{ disk.mountpoint }}</h3>
                <p class="text-sm text-muted-foreground">{{ disk.device }} ({{ disk.fstype }})</p>
              </div>
            </div>
            <span
:class="[
              'text-lg font-bold',
              disk.percent_used > 90 ? 'text-red-500' :
              disk.percent_used > 75 ? 'text-orange-500' : ''
            ]">
              {{ disk.percent_used?.toFixed(0) }}%
            </span>
          </div>
          <div class="h-3 bg-secondary rounded-full overflow-hidden mb-2">
            <div
              :class="['h-full transition-all', getUsageColor(disk.percent_used)]"
              :style="{ width: `${disk.percent_used}%` }"
            />
          </div>
          <div class="flex justify-between text-sm text-muted-foreground">
            <span>Used: {{ disk.used_gb?.toFixed(1) }} GB</span>
            <span>Free: {{ disk.free_gb?.toFixed(1) }} GB</span>
            <span>Total: {{ disk.total_gb?.toFixed(1) }} GB</span>
          </div>
        </div>
      </div>
    </template>

    <!-- CPU Details (shown on Overview) -->
    <template v-if="activeTab === 'overview' && cpu">
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border">
          <h2 class="text-lg font-semibold">CPU Details</h2>
        </div>
        <div class="p-4">
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div>
              <p class="text-sm text-muted-foreground">Model</p>
              <p class="font-medium truncate" :title="cpu.model">{{ cpu.model }}</p>
            </div>
            <div>
              <p class="text-sm text-muted-foreground">Cores</p>
              <p class="font-medium">{{ cpu.cores_physical }} / {{ cpu.cores_logical }} (P/L)</p>
            </div>
            <div>
              <p class="text-sm text-muted-foreground">Frequency</p>
              <p class="font-medium">{{ (cpu.frequency_mhz / 1000).toFixed(2) }} GHz</p>
            </div>
            <div>
              <p class="text-sm text-muted-foreground">Load Average</p>
              <p class="font-medium">{{ cpu.load_avg_1m }} / {{ cpu.load_avg_5m }} / {{ cpu.load_avg_15m }}</p>
            </div>
          </div>

          <!-- Per-core usage -->
          <div v-if="cpu.usage_per_core && cpu.usage_per_core.length > 0">
            <p class="text-sm text-muted-foreground mb-2">Per-Core Usage</p>
            <div class="grid grid-cols-4 md:grid-cols-8 lg:grid-cols-12 gap-2">
              <div
                v-for="(usage, i) in cpu.usage_per_core"
                :key="i"
                class="text-center"
              >
                <div class="h-8 bg-secondary rounded overflow-hidden flex flex-col-reverse">
                  <div
                    :class="['transition-all', getUsageColor(usage)]"
                    :style="{ height: `${usage}%` }"
                  />
                </div>
                <p class="text-xs text-muted-foreground mt-1">{{ i }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- TTS Cache & LLM Stats (on Overview) -->
    <template v-if="activeTab === 'overview'">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- TTS Cache Stats -->
        <div v-if="metricsData?.streaming_tts" class="bg-card rounded-lg border border-border">
          <div class="p-4 border-b border-border">
            <h2 class="text-lg font-semibold">TTS Streaming Cache</h2>
          </div>
          <div class="p-4 grid grid-cols-3 gap-4">
            <div>
              <p class="text-sm text-muted-foreground">Cache Size</p>
              <p class="text-xl font-bold">{{ metricsData.streaming_tts.cache_size }}</p>
            </div>
            <div>
              <p class="text-sm text-muted-foreground">Max Size</p>
              <p class="text-xl font-bold">{{ metricsData.streaming_tts.max_cache_size }}</p>
            </div>
            <div>
              <p class="text-sm text-muted-foreground">Active Sessions</p>
              <p class="text-xl font-bold">{{ metricsData.streaming_tts.active_sessions }}</p>
            </div>
          </div>
        </div>

        <!-- LLM Stats -->
        <div v-if="metricsData?.llm" class="bg-card rounded-lg border border-border">
          <div class="p-4 border-b border-border">
            <h2 class="text-lg font-semibold">LLM Stats</h2>
          </div>
          <div class="p-4 grid grid-cols-2 gap-4">
            <div>
              <p class="text-sm text-muted-foreground">History Length</p>
              <p class="text-xl font-bold">{{ metricsData.llm.history_length }} messages</p>
            </div>
            <div>
              <p class="text-sm text-muted-foreground">FAQ Entries</p>
              <p class="text-xl font-bold">{{ metricsData.llm.faq_count }}</p>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
