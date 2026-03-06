<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { gsmApi, type GSMConfig, type GSMStatus, type CallInfo, type SMSMessage, type VoiceCallConfig, type VoiceCallStatus } from '@/api/gsm'
import { wikiRagApi, type KnowledgeCollection } from '@/api/wikiRag'
import { llmApi, type CloudProvider } from '@/api/llm'
import {
  Phone,
  PhoneCall,
  PhoneOff,
  PhoneIncoming,
  PhoneOutgoing,
  MessageSquare,
  Settings,
  Signal,
  SignalZero,
  Wifi,
  WifiOff,
  RefreshCw,
  Play,
  Send,
  Terminal,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Clock,
  User,
  Save,
  Usb,
  Download,
} from 'lucide-vue-next'
import { ref, computed, watch } from 'vue'
import { useToastStore } from '@/stores/toast'

const queryClient = useQueryClient()
const toast = useToastStore()

// ============== State ==============

const activeTab = ref<'status' | 'calls' | 'sms' | 'config' | 'debug'>('status')
const atCommand = ref('')
const atResponse = ref<string[]>([])
const smsNumber = ref('')
const smsText = ref('')
const dialNumber = ref('')

// ============== Queries ==============

const { data: statusData, isLoading: statusLoading, refetch: refetchStatus } = useQuery({
  queryKey: ['gsm-status'],
  queryFn: () => gsmApi.getStatus(),
  refetchInterval: 5000, // Auto-refresh every 5 seconds
})

const { data: configData, refetch: refetchConfig } = useQuery({
  queryKey: ['gsm-config'],
  queryFn: () => gsmApi.getConfig(),
})

const { data: callsData, refetch: refetchCalls } = useQuery({
  queryKey: ['gsm-calls'],
  queryFn: () => gsmApi.listCalls({ limit: 20 }),
})

const { data: smsData, refetch: refetchSMS } = useQuery({
  queryKey: ['gsm-sms'],
  queryFn: () => gsmApi.listSMS({ limit: 20 }),
})

const { data: portsData } = useQuery({
  queryKey: ['gsm-ports'],
  queryFn: () => gsmApi.listPorts(),
})

const { data: activeCallData, refetch: refetchActiveCall } = useQuery({
  queryKey: ['gsm-active-call'],
  queryFn: () => gsmApi.getActiveCall(),
  refetchInterval: 1000, // Check every second during calls
})

// Conversations
const selectedNumber = ref<string | null>(null)

const { data: conversationsData, refetch: refetchConversations } = useQuery({
  queryKey: ['gsm-conversations'],
  queryFn: () => gsmApi.listConversations({ limit: 50 }),
})

const { data: conversationDetail, refetch: refetchConversationDetail } = useQuery({
  queryKey: computed(() => ['gsm-conversation', selectedNumber.value]),
  queryFn: () => gsmApi.getConversation(selectedNumber.value!),
  enabled: computed(() => !!selectedNumber.value),
})

// Voice call queries
const { data: voiceCallConfig, refetch: refetchVoiceCallConfig } = useQuery({
  queryKey: ['gsm-voice-call-config'],
  queryFn: () => gsmApi.getVoiceCallConfig(),
})

const { data: voiceCallStatus } = useQuery({
  queryKey: ['gsm-voice-call-status'],
  queryFn: () => gsmApi.getVoiceCallStatus(),
  refetchInterval: 5000,
})

const { data: collectionsData } = useQuery({
  queryKey: ['knowledge-collections'],
  queryFn: async () => {
    const res = await wikiRagApi.getCollections()
    return res.collections
  },
})

const { data: providersData } = useQuery({
  queryKey: ['cloud-providers-enabled'],
  queryFn: async () => {
    const res = await llmApi.getProviders(true)
    return res.providers
  },
})

// Local config state
const localConfig = ref<Partial<GSMConfig>>({})
const localVoiceConfig = ref<Partial<VoiceCallConfig>>({})

watch(configData, (data) => {
  if (data) {
    localConfig.value = { ...data }
  }
}, { immediate: true })

watch(voiceCallConfig, (data) => {
  if (data) {
    localVoiceConfig.value = { ...data }
  }
}, { immediate: true })

// ============== Computed ==============

const status = computed(() => statusData.value)
const isConnected = computed(() => status.value?.state !== 'disconnected')
const signalBars = computed(() => {
  const strength = status.value?.signal_strength
  if (!strength || strength === 99) return 0
  if (strength >= 20) return 4
  if (strength >= 15) return 3
  if (strength >= 10) return 2
  if (strength >= 5) return 1
  return 0
})

const stateLabel = computed(() => {
  const state = status.value?.state
  const labels: Record<string, string> = {
    disconnected: 'Отключён',
    initializing: 'Инициализация...',
    ready: 'Готов',
    incoming_call: 'Входящий звонок',
    in_call: 'В разговоре',
    error: 'Ошибка',
  }
  return labels[state || 'disconnected'] || state
})

const stateColor = computed(() => {
  const state = status.value?.state
  const colors: Record<string, string> = {
    disconnected: 'text-muted-foreground',
    initializing: 'text-yellow-500',
    ready: 'text-green-500',
    incoming_call: 'text-blue-500 animate-pulse',
    in_call: 'text-green-500',
    error: 'text-red-500',
  }
  return colors[state || 'disconnected'] || 'text-muted-foreground'
})

// ============== Mutations ==============

const initializeMutation = useMutation({
  mutationFn: () => gsmApi.initialize(),
  onSuccess: (data) => {
    toast.success(data.message)
    refetchStatus()
  },
  onError: (error: Error) => {
    toast.error(`Ошибка инициализации: ${error.message}`)
  },
})

const updateConfigMutation = useMutation({
  mutationFn: (config: Partial<GSMConfig>) => gsmApi.updateConfig(config),
  onSuccess: () => {
    toast.success('Конфигурация сохранена')
    queryClient.invalidateQueries({ queryKey: ['gsm-config'] })
  },
  onError: (error: Error) => {
    toast.error(`Ошибка сохранения: ${error.message}`)
  },
})

const updateVoiceConfigMutation = useMutation({
  mutationFn: (config: Partial<VoiceCallConfig>) => gsmApi.updateVoiceCallConfig(config),
  onSuccess: () => {
    toast.success('Настройки голосового ассистента сохранены')
    refetchVoiceCallConfig()
  },
  onError: (error: Error) => {
    toast.error(`Ошибка сохранения: ${error.message}`)
  },
})

const answerMutation = useMutation({
  mutationFn: () => gsmApi.answerCall(),
  onSuccess: (data) => {
    toast.success(data.message)
    refetchStatus()
    refetchActiveCall()
  },
  onError: (error: Error) => {
    toast.error(`Ошибка: ${error.message}`)
  },
})

const hangupMutation = useMutation({
  mutationFn: () => gsmApi.hangupCall(),
  onSuccess: (data) => {
    toast.success(data.message)
    refetchStatus()
    refetchActiveCall()
    refetchCalls()
  },
  onError: (error: Error) => {
    toast.error(`Ошибка: ${error.message}`)
  },
})

const dialMutation = useMutation({
  mutationFn: (number: string) => gsmApi.dialNumber(number),
  onSuccess: (data) => {
    toast.success(data.message)
    dialNumber.value = ''
    refetchStatus()
  },
  onError: (error: Error) => {
    toast.error(`Ошибка: ${error.message}`)
  },
})

const sendSMSMutation = useMutation({
  mutationFn: () => gsmApi.sendSMS(smsNumber.value, smsText.value),
  onSuccess: (data) => {
    toast.success(data.message)
    smsText.value = ''
    refetchSMS()
    refetchConversations()
    if (selectedNumber.value) {
      refetchConversationDetail()
    }
  },
  onError: (error: Error) => {
    toast.error(`Ошибка: ${error.message}`)
  },
})

const executeATMutation = useMutation({
  mutationFn: (command: string) => gsmApi.executeAT(command),
  onSuccess: (data) => {
    atResponse.value = data.response
    if (!data.success && data.error) {
      toast.error(data.error)
    }
  },
  onError: (error: Error) => {
    toast.error(`Ошибка: ${error.message}`)
  },
})

const readModemSMSMutation = useMutation({
  mutationFn: () => gsmApi.readModemSMS(),
  onSuccess: (data) => {
    toast.success(`Прочитано SMS с SIM: ${data.count}`)
    refetchSMS()
  },
  onError: (error: Error) => {
    toast.error(`Ошибка чтения SIM: ${error.message}`)
  },
})

// ============== Computed: SMS ==============

const hasCyrillic = computed(() => /[а-яёА-ЯЁ]/.test(smsText.value))
const smsMaxChars = computed(() => hasCyrillic.value ? 70 : 160)

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const chronologicalItems = computed<any[]>(() => {
  if (!conversationDetail.value) return []
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const items: any[] = []
  for (const msg of conversationDetail.value.messages || []) {
    items.push({ type: 'sms', time: msg.sent_at, ...msg })
  }
  for (const call of conversationDetail.value.calls || []) {
    items.push({ type: 'call', time: call.started_at, ...call })
  }
  items.sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime())
  return items
})

function selectConversation(number: string) {
  selectedNumber.value = number
  smsNumber.value = number
}

// ============== Methods ==============

function saveConfig() {
  updateConfigMutation.mutate(localConfig.value as GSMConfig)
}

function saveVoiceConfig() {
  updateVoiceConfigMutation.mutate(localVoiceConfig.value)
}

function toggleCollection(id: number) {
  const ids = localVoiceConfig.value.knowledge_collection_ids || []
  const idx = ids.indexOf(id)
  if (idx >= 0) {
    ids.splice(idx, 1)
  } else {
    ids.push(id)
  }
  localVoiceConfig.value.knowledge_collection_ids = [...ids]
}

function executeAT() {
  if (!atCommand.value.trim()) return
  executeATMutation.mutate(atCommand.value.trim())
}

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '—'
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function formatTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getCallStateLabel(state: string): string {
  const labels: Record<string, string> = {
    ringing: 'Звонит',
    active: 'Активен',
    completed: 'Завершён',
    missed: 'Пропущен',
    failed: 'Неудачный',
  }
  return labels[state] || state
}

function getCallStateColor(state: string): string {
  const colors: Record<string, string> = {
    ringing: 'bg-blue-500/20 text-blue-500',
    active: 'bg-green-500/20 text-green-500',
    completed: 'bg-secondary text-muted-foreground',
    missed: 'bg-red-500/20 text-red-500',
    failed: 'bg-red-500/20 text-red-500',
  }
  return colors[state] || 'bg-secondary'
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Phone class="w-7 h-7" />
          GSM Телефония
        </h1>
        <p class="text-muted-foreground">SIM7600E-H модуль — голосовые звонки и SMS</p>
      </div>

      <div class="flex items-center gap-2">
        <!-- Mock Mode Badge -->
        <span
          v-if="status?.mock_mode"
          class="px-2 py-1 bg-yellow-500/20 text-yellow-500 rounded text-xs font-medium"
        >
          MOCK
        </span>

        <!-- Status Badge -->
        <div class="flex items-center gap-2 px-3 py-1.5 bg-card rounded-lg border border-border">
          <span :class="['w-2 h-2 rounded-full', isConnected ? 'bg-green-500' : 'bg-red-500']" />
          <span :class="stateColor">{{ stateLabel }}</span>
        </div>

        <button
          class="p-2 hover:bg-secondary rounded"
          :disabled="statusLoading"
          @click="refetchStatus()"
        >
          <RefreshCw :class="['w-5 h-5', statusLoading && 'animate-spin']" />
        </button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 border-b border-border">
      <button
        v-for="tab in [
          { id: 'status', label: 'Статус', icon: Signal },
          { id: 'calls', label: 'Звонки', icon: PhoneCall },
          { id: 'sms', label: 'SMS', icon: MessageSquare },
          { id: 'config', label: 'Настройки', icon: Settings },
          { id: 'debug', label: 'Отладка', icon: Terminal },
        ]"
        :key="tab.id"
        :class="[
          'flex items-center gap-2 px-4 py-2 border-b-2 -mb-[2px] transition-colors',
          activeTab === tab.id
            ? 'border-primary text-primary'
            : 'border-transparent text-muted-foreground hover:text-foreground'
        ]"
        @click="activeTab = tab.id as typeof activeTab"
      >
        <component :is="tab.icon" class="w-4 h-4" />
        {{ tab.label }}
      </button>
    </div>

    <!-- Tab Content -->
    <div class="space-y-6">
      <!-- Status Tab -->
      <template v-if="activeTab === 'status'">
        <!-- Module Status Card -->
        <div class="bg-card rounded-lg border border-border p-6">
          <h2 class="text-lg font-semibold mb-4 flex items-center gap-2">
            <Usb class="w-5 h-5" />
            Статус модуля
          </h2>

          <div v-if="!isConnected" class="text-center py-8">
            <WifiOff class="w-16 h-16 mx-auto text-muted-foreground mb-4" />
            <p class="text-lg font-medium mb-2">Модуль не подключён</p>
            <p class="text-muted-foreground mb-4">
              {{ status?.last_error || 'Подключите SIM7600E-H через USB' }}
            </p>

            <!-- Available ports -->
            <div v-if="portsData && portsData.total > 0" class="mt-4 text-sm">
              <p class="text-muted-foreground mb-2">Обнаруженные порты:</p>
              <div class="flex flex-wrap justify-center gap-2">
                <span
                  v-for="port in [...portsData.usb_ports, ...portsData.acm_ports]"
                  :key="port"
                  class="px-2 py-1 bg-secondary rounded text-xs font-mono"
                >
                  {{ port }}
                </span>
              </div>
            </div>

            <button
              class="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90"
              :disabled="initializeMutation.isPending.value"
              @click="initializeMutation.mutate()"
            >
              <Loader2 v-if="initializeMutation.isPending.value" class="w-4 h-4 animate-spin inline mr-2" />
              Инициализировать
            </button>
          </div>

          <div v-else class="grid grid-cols-2 md:grid-cols-5 gap-4">
            <!-- Signal -->
            <div class="p-4 bg-secondary/50 rounded-lg">
              <div class="flex items-center gap-2 mb-2 text-muted-foreground">
                <Signal class="w-4 h-4" />
                <span class="text-sm">Сигнал</span>
              </div>
              <div class="flex items-center gap-1">
                <div
v-for="i in 4" :key="i" :class="[
                  'w-2 h-4 rounded-sm',
                  i <= signalBars ? 'bg-green-500' : 'bg-muted'
                ]" />
                <span class="ml-2 font-mono">{{ status?.signal_percent ?? '—' }}%</span>
              </div>
            </div>

            <!-- SIM -->
            <div class="p-4 bg-secondary/50 rounded-lg">
              <div class="flex items-center gap-2 mb-2 text-muted-foreground">
                <Wifi class="w-4 h-4" />
                <span class="text-sm">SIM</span>
              </div>
              <div class="font-medium">{{ status?.sim_status ?? '—' }}</div>
            </div>

            <!-- Network -->
            <div class="p-4 bg-secondary/50 rounded-lg">
              <div class="flex items-center gap-2 mb-2 text-muted-foreground">
                <Wifi class="w-4 h-4" />
                <span class="text-sm">Сеть</span>
              </div>
              <div class="font-medium">{{ status?.network_name ?? '—' }}</div>
              <div v-if="status?.network_mode" class="text-xs text-muted-foreground mt-1">
                {{ status.network_mode }}
              </div>
            </div>

            <!-- Phone Number -->
            <div class="p-4 bg-secondary/50 rounded-lg">
              <div class="flex items-center gap-2 mb-2 text-muted-foreground">
                <Phone class="w-4 h-4" />
                <span class="text-sm">Номер</span>
              </div>
              <div class="font-medium font-mono">{{ status?.phone_number ?? '—' }}</div>
            </div>

            <!-- AT Port -->
            <div class="p-4 bg-secondary/50 rounded-lg">
              <div class="flex items-center gap-2 mb-2 text-muted-foreground">
                <Usb class="w-4 h-4" />
                <span class="text-sm">Порт</span>
              </div>
              <div class="font-medium font-mono text-sm">{{ status?.at_port ?? '—' }}</div>
            </div>
          </div>
        </div>

        <!-- Active Call Card -->
        <div v-if="activeCallData" class="bg-card rounded-lg border border-primary p-6">
          <h2 class="text-lg font-semibold mb-4 flex items-center gap-2 text-primary">
            <PhoneCall class="w-5 h-5 animate-pulse" />
            Активный звонок
          </h2>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-2xl font-mono mb-1">{{ activeCallData.caller_number }}</div>
              <div class="text-muted-foreground flex items-center gap-2">
                <Clock class="w-4 h-4" />
                {{ formatDuration(activeCallData.duration_seconds) }}
              </div>
            </div>

            <button
              class="px-6 py-3 bg-red-500 text-white rounded-full hover:bg-red-600 flex items-center gap-2"
              @click="hangupMutation.mutate()"
            >
              <PhoneOff class="w-5 h-5" />
              Завершить
            </button>
          </div>
        </div>

        <!-- Quick Actions -->
        <div class="bg-card rounded-lg border border-border p-6">
          <h2 class="text-lg font-semibold mb-4">Быстрые действия</h2>

          <div class="flex flex-wrap gap-4">
            <!-- Dial -->
            <div class="flex-1 min-w-[200px]">
              <label class="text-sm text-muted-foreground mb-1 block">Позвонить</label>
              <div class="flex gap-2">
                <input
                  v-model="dialNumber"
                  type="tel"
                  placeholder="+7900..."
                  class="flex-1 px-3 py-2 bg-background border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <button
                  class="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 disabled:opacity-50"
                  :disabled="!dialNumber || dialMutation.isPending.value"
                  @click="dialMutation.mutate(dialNumber)"
                >
                  <PhoneOutgoing class="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Calls Tab -->
      <template v-if="activeTab === 'calls'">
        <div class="bg-card rounded-lg border border-border">
          <div class="p-4 border-b border-border flex items-center justify-between">
            <h2 class="text-lg font-semibold">История звонков</h2>
            <button class="p-2 hover:bg-secondary rounded" @click="refetchCalls()">
              <RefreshCw class="w-4 h-4" />
            </button>
          </div>

          <div v-if="!callsData?.calls?.length" class="p-8 text-center text-muted-foreground">
            <PhoneCall class="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p>Нет звонков</p>
          </div>

          <div v-else class="divide-y divide-border">
            <div
              v-for="call in callsData.calls"
              :key="call.id"
              class="p-4 flex items-center gap-4 hover:bg-secondary/50"
            >
              <div
:class="[
                'p-2 rounded-full',
                call.direction === 'incoming' ? 'bg-blue-500/20' : 'bg-green-500/20'
              ]">
                <PhoneIncoming v-if="call.direction === 'incoming'" class="w-5 h-5 text-blue-500" />
                <PhoneOutgoing v-else class="w-5 h-5 text-green-500" />
              </div>

              <div class="flex-1">
                <div class="font-medium font-mono">{{ call.caller_number }}</div>
                <div class="text-sm text-muted-foreground">{{ formatTime(call.started_at) }}</div>
              </div>

              <div class="text-right">
                <span :class="['px-2 py-1 rounded text-xs', getCallStateColor(call.state)]">
                  {{ getCallStateLabel(call.state) }}
                </span>
                <div class="text-sm text-muted-foreground mt-1">
                  {{ formatDuration(call.duration_seconds) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- SMS Tab -->
      <template v-if="activeTab === 'sms'">
        <div class="flex gap-4" style="height: calc(100vh - 280px); min-height: 500px;">
          <!-- Left Panel: Conversation List -->
          <div class="w-80 shrink-0 bg-card rounded-lg border border-border flex flex-col">
            <div class="p-3 border-b border-border flex items-center justify-between">
              <h2 class="font-semibold text-sm">Переписки</h2>
              <div class="flex gap-1">
                <button
                  class="p-1.5 hover:bg-secondary rounded disabled:opacity-50"
                  :disabled="readModemSMSMutation.isPending.value"
                  title="Прочитать SMS с SIM"
                  @click="readModemSMSMutation.mutate()"
                >
                  <Loader2 v-if="readModemSMSMutation.isPending.value" class="w-3.5 h-3.5 animate-spin" />
                  <Download v-else class="w-3.5 h-3.5" />
                </button>
                <button class="p-1.5 hover:bg-secondary rounded" @click="refetchConversations()">
                  <RefreshCw class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <!-- New message button -->
            <button
              :class="[
                'p-3 text-left text-sm border-b border-border hover:bg-secondary/50 transition-colors',
                selectedNumber === null && 'bg-primary/10'
              ]"
              @click="selectedNumber = null; smsNumber = ''; smsText = ''"
            >
              <span class="text-primary font-medium">+ Новое сообщение</span>
            </button>

            <!-- Conversation list -->
            <div class="flex-1 overflow-y-auto">
              <div v-if="!conversationsData?.conversations?.length" class="p-4 text-center text-muted-foreground text-sm">
                Нет переписок
              </div>
              <button
                v-for="conv in conversationsData?.conversations"
                :key="conv.number"
                :class="[
                  'w-full p-3 text-left border-b border-border hover:bg-secondary/50 transition-colors',
                  selectedNumber === conv.number && 'bg-primary/10'
                ]"
                @click="selectConversation(conv.number)"
              >
                <div class="flex items-center justify-between mb-1">
                  <span class="font-mono text-sm font-medium">{{ conv.number }}</span>
                  <span class="text-xs text-muted-foreground">{{ formatTime(conv.last_time) }}</span>
                </div>
                <div class="text-sm text-muted-foreground truncate">
                  <span v-if="conv.last_direction === 'outgoing'" class="text-green-500">← </span>
                  {{ conv.last_message || '...' }}
                </div>
                <div class="flex gap-2 mt-1">
                  <span v-if="conv.message_count" class="text-xs text-muted-foreground">
                    <MessageSquare class="w-3 h-3 inline" /> {{ conv.message_count }}
                  </span>
                  <span v-if="conv.call_count" class="text-xs text-muted-foreground">
                    <Phone class="w-3 h-3 inline" /> {{ conv.call_count }}
                  </span>
                </div>
              </button>
            </div>
          </div>

          <!-- Right Panel: Chat / New Message -->
          <div class="flex-1 bg-card rounded-lg border border-border flex flex-col">
            <!-- No conversation selected: New message form -->
            <template v-if="selectedNumber === null">
              <div class="p-4 border-b border-border">
                <h2 class="font-semibold">Новое сообщение</h2>
              </div>
              <div class="p-4 space-y-4">
                <div>
                  <label class="text-sm text-muted-foreground mb-1 block">Номер</label>
                  <input
                    v-model="smsNumber"
                    type="tel"
                    placeholder="+79001234567"
                    class="w-full px-3 py-2 bg-background border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div>
                  <label class="text-sm text-muted-foreground mb-1 block">Сообщение</label>
                  <textarea
                    v-model="smsText"
                    rows="4"
                    placeholder="Текст сообщения..."
                    class="w-full px-3 py-2 bg-background border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                  />
                  <div class="flex justify-between text-xs text-muted-foreground mt-1">
                    <span v-if="hasCyrillic" class="text-yellow-500">Кириллица: UCS2</span>
                    <span v-else>&nbsp;</span>
                    <span :class="smsText.length > smsMaxChars ? 'text-red-500' : ''">
                      {{ smsText.length }} / {{ smsMaxChars }}
                    </span>
                  </div>
                </div>
                <button
                  class="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                  :disabled="!smsNumber || !smsText || sendSMSMutation.isPending.value"
                  @click="sendSMSMutation.mutate()"
                >
                  <Loader2 v-if="sendSMSMutation.isPending.value" class="w-4 h-4 animate-spin" />
                  <Send v-else class="w-4 h-4" />
                  Отправить
                </button>
              </div>
            </template>

            <!-- Conversation selected: Chat view -->
            <template v-else>
              <!-- Chat header -->
              <div class="p-3 border-b border-border flex items-center justify-between">
                <div>
                  <span class="font-mono font-medium">{{ selectedNumber }}</span>
                </div>
                <button class="p-1.5 hover:bg-secondary rounded" @click="refetchConversationDetail()">
                  <RefreshCw class="w-4 h-4" />
                </button>
              </div>

              <!-- Messages area -->
              <div class="flex-1 overflow-y-auto p-4 space-y-3">
                <div v-if="!chronologicalItems.length" class="flex-1 flex items-center justify-center text-muted-foreground">
                  <div class="text-center">
                    <MessageSquare class="w-10 h-10 mx-auto mb-2 opacity-50" />
                    <p class="text-sm">Нет сообщений</p>
                  </div>
                </div>

                <template v-for="(item, idx) in chronologicalItems" :key="idx">
                  <!-- SMS bubble -->
                  <div
                    v-if="item.type === 'sms'"
                    :class="['flex', item.direction === 'outgoing' ? 'justify-end' : 'justify-start']"
                  >
                    <div
                      :class="[
                        'max-w-[70%] rounded-xl px-3 py-2',
                        item.direction === 'outgoing'
                          ? 'bg-green-500/20 rounded-br-sm'
                          : 'bg-secondary rounded-bl-sm'
                      ]"
                    >
                      <p class="text-sm whitespace-pre-wrap">{{ item.text }}</p>
                      <div class="text-[10px] text-muted-foreground mt-1 text-right">
                        {{ formatTime(item.time) }}
                      </div>
                    </div>
                  </div>

                  <!-- Call system message -->
                  <div v-else-if="item.type === 'call'" class="flex justify-center">
                    <div class="flex items-center gap-1.5 px-3 py-1 bg-secondary/50 rounded-full text-xs text-muted-foreground">
                      <PhoneIncoming v-if="item.direction === 'incoming'" class="w-3 h-3" />
                      <PhoneOutgoing v-else class="w-3 h-3" />
                      {{ item.direction === 'incoming' ? 'Входящий' : 'Исходящий' }}
                      {{ getCallStateLabel(item.state) }}
                      {{ formatDuration(item.duration_seconds) }}
                      <span class="opacity-60">{{ formatTime(item.time) }}</span>
                    </div>
                  </div>
                </template>
              </div>

              <!-- Reply form -->
              <div class="p-3 border-t border-border">
                <div class="flex gap-2 items-end">
                  <div class="flex-1">
                    <textarea
                      v-model="smsText"
                      rows="1"
                      placeholder="Сообщение..."
                      class="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                      @keydown.enter.ctrl="sendSMSMutation.mutate()"
                    />
                    <div v-if="smsText" class="flex justify-between text-[10px] text-muted-foreground mt-0.5">
                      <span v-if="hasCyrillic" class="text-yellow-500">UCS2</span>
                      <span v-else>&nbsp;</span>
                      <span :class="smsText.length > smsMaxChars ? 'text-red-500' : ''">
                        {{ smsText.length }} / {{ smsMaxChars }}
                      </span>
                    </div>
                  </div>
                  <button
                    class="p-2.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 shrink-0"
                    :disabled="!smsText || sendSMSMutation.isPending.value"
                    @click="sendSMSMutation.mutate()"
                  >
                    <Loader2 v-if="sendSMSMutation.isPending.value" class="w-4 h-4 animate-spin" />
                    <Send v-else class="w-4 h-4" />
                  </button>
                </div>
              </div>
            </template>
          </div>
        </div>
      </template>

      <!-- Config Tab -->
      <template v-if="activeTab === 'config'">
        <div class="bg-card rounded-lg border border-border p-6 space-y-6">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">Голосовой ассистент</h2>
            <button
              class="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90 flex items-center gap-2"
              :disabled="updateVoiceConfigMutation.isPending.value"
              @click="saveVoiceConfig"
            >
              <Loader2 v-if="updateVoiceConfigMutation.isPending.value" class="w-4 h-4 animate-spin" />
              <Save v-else class="w-4 h-4" />
              Сохранить
            </button>
          </div>

          <!-- Service status -->
          <div v-if="voiceCallStatus" class="flex items-center gap-2 text-sm">
            <div
              class="w-2 h-2 rounded-full"
              :class="voiceCallStatus.available ? 'bg-green-500' : 'bg-red-500'"
            />
            <span v-if="voiceCallStatus.available" class="text-green-600">
              Сервис активен
              <span v-if="voiceCallStatus.active" class="text-blue-500 ml-2">| В разговоре</span>
            </span>
            <span v-else class="text-muted-foreground">
              Сервис недоступен{{ voiceCallStatus.reason ? `: ${voiceCallStatus.reason}` : '' }}
            </span>
          </div>

          <!-- Capabilities -->
          <div v-if="voiceCallStatus?.available" class="flex gap-3 text-xs">
            <span class="px-2 py-1 rounded" :class="voiceCallStatus.stt_available ? 'bg-green-500/10 text-green-600' : 'bg-red-500/10 text-red-500'">
              STT {{ voiceCallStatus.stt_available ? 'OK' : 'N/A' }}
            </span>
            <span class="px-2 py-1 rounded" :class="voiceCallStatus.tts_xtts_available ? 'bg-green-500/10 text-green-600' : 'bg-yellow-500/10 text-yellow-600'">
              XTTS {{ voiceCallStatus.tts_xtts_available ? 'OK' : 'N/A' }}
            </span>
            <span class="px-2 py-1 rounded" :class="voiceCallStatus.tts_piper_available ? 'bg-green-500/10 text-green-600' : 'bg-yellow-500/10 text-yellow-600'">
              Piper {{ voiceCallStatus.tts_piper_available ? 'OK' : 'N/A' }}
            </span>
            <span class="px-2 py-1 rounded" :class="voiceCallStatus.pcm_connected ? 'bg-green-500/10 text-green-600' : 'bg-muted text-muted-foreground'">
              PCM {{ voiceCallStatus.pcm_connected ? 'OK' : 'N/A' }}
            </span>
          </div>

          <!-- LLM Provider -->
          <div>
            <h3 class="font-medium mb-3">LLM провайдер</h3>
            <select
              v-model="localVoiceConfig.llm_backend"
              class="w-full px-3 py-2 bg-background border border-border rounded"
            >
              <option :value="null">По умолчанию (системный)</option>
              <option value="">По умолчанию (системный)</option>
              <option value="vllm">vLLM (локальный)</option>
              <option v-for="p in providersData" :key="p.id" :value="`cloud:${p.id}`">
                {{ p.name }} ({{ p.provider_type }}: {{ p.model_name }})
              </option>
            </select>
            <p class="text-xs text-muted-foreground mt-1">Какой LLM использовать для генерации ответов при звонках</p>
          </div>

          <!-- TTS Voice -->
          <div>
            <h3 class="font-medium mb-3">Голос</h3>
            <div class="space-y-3">
              <div>
                <label class="text-sm text-muted-foreground mb-1 block">Движок TTS</label>
                <select
                  v-model="localVoiceConfig.tts_voice"
                  class="w-full px-3 py-2 bg-background border border-border rounded"
                >
                  <option value="xtts">XTTS v2 (клонирование голоса, GPU)</option>
                  <option value="piper">Piper (готовые голоса, CPU)</option>
                </select>
              </div>
              <div v-if="localVoiceConfig.tts_voice === 'piper'">
                <label class="text-sm text-muted-foreground mb-1 block">Голос Piper</label>
                <select
                  v-model="localVoiceConfig.piper_voice"
                  class="w-full px-3 py-2 bg-background border border-border rounded"
                >
                  <option value="irina">Ирина (женский)</option>
                  <option value="dmitri">Дмитрий (мужской)</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Auto-answer -->
          <div>
            <h3 class="font-medium mb-3">Автоответ</h3>
            <div class="space-y-3">
              <label class="flex items-center gap-3">
                <input
                  v-model="localVoiceConfig.auto_answer"
                  type="checkbox"
                  class="w-4 h-4"
                />
                <span>Автоматически отвечать на звонки</span>
              </label>
              <div v-if="localVoiceConfig.auto_answer" class="ml-7">
                <label class="text-sm text-muted-foreground mb-1 block">Гудков до ответа</label>
                <input
                  v-model.number="localVoiceConfig.auto_answer_rings"
                  type="number"
                  min="1"
                  max="10"
                  class="w-20 px-3 py-2 bg-background border border-border rounded"
                />
              </div>
            </div>
          </div>

          <!-- SMS auto-reply -->
          <div>
            <h3 class="font-medium mb-3">SMS</h3>
            <label class="flex items-center gap-3">
              <input
                v-model="localVoiceConfig.sms_auto_reply"
                type="checkbox"
                class="w-4 h-4"
              />
              <span>Автоответ на входящие SMS</span>
            </label>
            <p class="text-xs text-muted-foreground mt-1 ml-7">Ассистент получает SMS, генерирует ответ через LLM и отправляет SMS обратно</p>
          </div>

          <!-- Greeting -->
          <div>
            <h3 class="font-medium mb-3">Приветствие</h3>
            <textarea
              v-model="localVoiceConfig.greeting"
              rows="2"
              placeholder="Здравствуйте! Чем могу помочь?"
              class="w-full px-3 py-2 bg-background border border-border rounded resize-none"
            />
            <p class="text-xs text-muted-foreground mt-1">Первая фраза ассистента при ответе на звонок</p>
          </div>

          <!-- System Prompt -->
          <div>
            <h3 class="font-medium mb-3">Системный промпт</h3>
            <textarea
              v-model="localVoiceConfig.system_prompt"
              rows="4"
              placeholder="Ты — виртуальный секретарь компании..."
              class="w-full px-3 py-2 bg-background border border-border rounded resize-y font-mono text-sm"
            />
            <p class="text-xs text-muted-foreground mt-1">Инструкция для LLM: роль, стиль ответов, ограничения</p>
          </div>

          <!-- RAG -->
          <div>
            <h3 class="font-medium mb-3">База знаний (RAG)</h3>
            <div class="space-y-3">
              <div>
                <label class="text-sm text-muted-foreground mb-1 block">Режим RAG</label>
                <select
                  v-model="localVoiceConfig.rag_mode"
                  class="w-full px-3 py-2 bg-background border border-border rounded"
                >
                  <option value="none">Отключён</option>
                  <option value="all">Все коллекции</option>
                  <option value="selected">Выбранные коллекции</option>
                </select>
              </div>
              <div v-if="localVoiceConfig.rag_mode === 'selected' && collectionsData?.length" class="space-y-1">
                <label class="text-sm text-muted-foreground mb-1 block">Коллекции</label>
                <label
                  v-for="col in collectionsData"
                  :key="col.id"
                  class="flex items-center gap-2 px-3 py-2 rounded hover:bg-muted/50 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    :checked="localVoiceConfig.knowledge_collection_ids?.includes(col.id)"
                    class="w-4 h-4"
                    @change="toggleCollection(col.id)"
                  />
                  <span class="text-sm">{{ col.name }}</span>
                  <span class="text-xs text-muted-foreground ml-auto">{{ col.document_count }} док.</span>
                </label>
              </div>
              <p v-if="localVoiceConfig.rag_mode === 'selected' && !collectionsData?.length" class="text-sm text-muted-foreground">
                Нет доступных коллекций. Создайте их в разделе "База знаний".
              </p>
            </div>
          </div>
        </div>
      </template>

      <!-- Debug Tab -->
      <template v-if="activeTab === 'debug'">
        <!-- AT Console -->
        <div class="bg-card rounded-lg border border-border p-6">
          <h2 class="text-lg font-semibold mb-4 flex items-center gap-2">
            <Terminal class="w-5 h-5" />
            AT Консоль
          </h2>

          <div class="space-y-4">
            <div class="flex gap-2">
              <input
                v-model="atCommand"
                type="text"
                placeholder="AT"
                class="flex-1 px-3 py-2 bg-background border border-border rounded font-mono focus:outline-none focus:ring-2 focus:ring-primary"
                @keyup.enter="executeAT"
              />
              <button
                class="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
                :disabled="!atCommand || executeATMutation.isPending.value"
                @click="executeAT"
              >
                <Loader2 v-if="executeATMutation.isPending.value" class="w-4 h-4 animate-spin" />
                <Play v-else class="w-4 h-4" />
              </button>
            </div>

            <!-- Quick Commands -->
            <div class="flex flex-wrap gap-2">
              <button
                v-for="cmd in ['AT', 'AT+CPIN?', 'AT+CSQ', 'AT+CREG?', 'AT+COPS?', 'ATI']"
                :key="cmd"
                class="px-2 py-1 bg-secondary rounded text-xs font-mono hover:bg-secondary/80"
                @click="atCommand = cmd; executeAT()"
              >
                {{ cmd }}
              </button>
            </div>

            <!-- Response -->
            <div class="bg-background border border-border rounded p-4 font-mono text-sm min-h-[200px]">
              <div v-if="atResponse.length === 0" class="text-muted-foreground">
                Ответ появится здесь...
              </div>
              <div v-else>
                <div v-for="(line, i) in atResponse" :key="i" class="whitespace-pre-wrap">
                  {{ line }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Ports Info -->
        <div class="bg-card rounded-lg border border-border p-6">
          <h2 class="text-lg font-semibold mb-4 flex items-center gap-2">
            <Usb class="w-5 h-5" />
            Serial порты
          </h2>

          <div v-if="portsData" class="space-y-4">
            <div>
              <h3 class="text-sm text-muted-foreground mb-2">USB (/dev/ttyUSB*)</h3>
              <div v-if="portsData.usb_ports.length" class="flex flex-wrap gap-2">
                <span
                  v-for="port in portsData.usb_ports"
                  :key="port"
                  class="px-3 py-1 bg-secondary rounded font-mono text-sm"
                >
                  {{ port }}
                </span>
              </div>
              <p v-else class="text-muted-foreground text-sm">Не найдены</p>
            </div>

            <div>
              <h3 class="text-sm text-muted-foreground mb-2">ACM (/dev/ttyACM*)</h3>
              <div v-if="portsData.acm_ports.length" class="flex flex-wrap gap-2">
                <span
                  v-for="port in portsData.acm_ports"
                  :key="port"
                  class="px-3 py-1 bg-secondary rounded font-mono text-sm"
                >
                  {{ port }}
                </span>
              </div>
              <p v-else class="text-muted-foreground text-sm">Не найдены</p>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
