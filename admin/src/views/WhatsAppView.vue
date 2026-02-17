<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { useResponsive } from '@/composables/useResponsive'
import {
  MessageCircle,
  Power,
  Play,
  Square,
  RefreshCw,
  Plus,
  X,
  Loader2,
  Trash2,
  Edit3,
  ChevronRight,
  Volume2,
  FileText,
  Shield,
  Phone,
} from 'lucide-vue-next'
import { whatsappInstancesApi, type WhatsAppInstance } from '@/api'
import { wikiRagApi } from '@/api/wikiRag'
import { useToastStore } from '@/stores/toast'

const { t } = useI18n()
const queryClient = useQueryClient()
const toast = useToastStore()
const { isMobile } = useResponsive()

// Mobile master-detail
const showMobileList = ref(true)

// State
const selectedInstanceId = ref<string | null>(null)
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showLogsDialog = ref(false)
const activeTab = ref<'settings' | 'ai' | 'access' | 'logs'>('settings')

// Form data
const formData = ref<Partial<WhatsAppInstance>>({
  name: '',
  description: '',
  phone_number_id: '',
  waba_id: '',
  access_token: '',
  verify_token: '',
  app_secret: '',
  webhook_port: 8003,
  llm_backend: 'vllm',
  system_prompt: '',
  rag_mode: 'all',
  knowledge_collection_id: null,
  tts_enabled: false,
  tts_engine: 'xtts',
  tts_voice: 'anna',
  allowed_phones: [],
  blocked_phones: [],
  rate_limit_count: null,
  rate_limit_hours: null,
})

// Phone input helpers
const allowedPhonesText = ref('')
const blockedPhonesText = ref('')

// ─── Queries ──────────────────────────────────────────────

const { data: instancesData, isLoading: instancesLoading } = useQuery({
  queryKey: ['whatsapp-instances'],
  queryFn: () => whatsappInstancesApi.list(),
  refetchInterval: 10000,
})

const instances = computed(() => instancesData.value?.instances || [])

const selectedInstance = computed(() =>
  instances.value.find(i => i.id === selectedInstanceId.value)
)

const { data: statusData } = useQuery({
  queryKey: ['whatsapp-status', selectedInstanceId],
  queryFn: () => selectedInstanceId.value ? whatsappInstancesApi.getStatus(selectedInstanceId.value) : null,
  refetchInterval: 5000,
  enabled: computed(() => !!selectedInstanceId.value),
})

const instanceStatus = computed(() => statusData.value?.status)

const { data: collectionsData } = useQuery({
  queryKey: ['knowledge-collections'],
  queryFn: () => wikiRagApi.getCollections(),
})
const knowledgeCollections = computed(() => collectionsData.value?.collections || [])

const { data: logsData, refetch: refetchLogs } = useQuery({
  queryKey: ['whatsapp-logs', selectedInstanceId],
  queryFn: () => selectedInstanceId.value ? whatsappInstancesApi.getLogs(selectedInstanceId.value, 200) : null,
  enabled: computed(() => !!selectedInstanceId.value && showLogsDialog.value),
})

// ─── Mutations ──────────────────────────────────────────────

const createMutation = useMutation({
  mutationFn: (data: Partial<WhatsAppInstance>) => whatsappInstancesApi.create(data),
  onSuccess: () => {
    toast.success(t('whatsapp.instanceCreated'))
    queryClient.invalidateQueries({ queryKey: ['whatsapp-instances'] })
    showCreateDialog.value = false
  },
  onError: () => toast.error(t('whatsapp.createFailed')),
})

const updateMutation = useMutation({
  mutationFn: ({ id, data }: { id: string; data: Partial<WhatsAppInstance> }) =>
    whatsappInstancesApi.update(id, data),
  onSuccess: () => {
    toast.success(t('whatsapp.saved'))
    queryClient.invalidateQueries({ queryKey: ['whatsapp-instances'] })
    showEditDialog.value = false
  },
  onError: () => toast.error(t('whatsapp.saveFailed')),
})

const deleteMutation = useMutation({
  mutationFn: (id: string) => whatsappInstancesApi.delete(id),
  onSuccess: () => {
    toast.success(t('whatsapp.instanceDeleted'))
    queryClient.invalidateQueries({ queryKey: ['whatsapp-instances'] })
    if (selectedInstanceId.value) selectedInstanceId.value = null
  },
  onError: () => toast.error(t('whatsapp.deleteFailed')),
})

const startMutation = useMutation({
  mutationFn: (id: string) => whatsappInstancesApi.start(id),
  onSuccess: () => {
    toast.success(t('whatsapp.started'))
    queryClient.invalidateQueries({ queryKey: ['whatsapp-status'] })
  },
  onError: () => toast.error(t('whatsapp.startFailed')),
})

const stopMutation = useMutation({
  mutationFn: (id: string) => whatsappInstancesApi.stop(id),
  onSuccess: () => {
    toast.success(t('whatsapp.stopped'))
    queryClient.invalidateQueries({ queryKey: ['whatsapp-status'] })
  },
  onError: () => toast.error(t('whatsapp.stopFailed')),
})

const restartMutation = useMutation({
  mutationFn: (id: string) => whatsappInstancesApi.restart(id),
  onSuccess: () => {
    toast.success(t('whatsapp.restarted'))
    queryClient.invalidateQueries({ queryKey: ['whatsapp-status'] })
  },
  onError: () => toast.error(t('whatsapp.restartFailed')),
})

// ─── Actions ──────────────────────────────────────────────

function selectInstance(id: string) {
  selectedInstanceId.value = id
  activeTab.value = 'settings'
  if (isMobile.value) showMobileList.value = false
}

function openCreate() {
  formData.value = {
    name: '',
    description: '',
    phone_number_id: '',
    waba_id: '',
    access_token: '',
    verify_token: '',
    app_secret: '',
    webhook_port: 8003,
    llm_backend: 'vllm',
    system_prompt: '',
    rag_mode: 'all',
    knowledge_collection_id: null,
    tts_enabled: false,
    tts_engine: 'xtts',
    tts_voice: 'anna',
    allowed_phones: [],
    blocked_phones: [],
    rate_limit_count: null,
    rate_limit_hours: null,
  }
  allowedPhonesText.value = ''
  blockedPhonesText.value = ''
  showCreateDialog.value = true
}

function openEdit() {
  if (!selectedInstance.value) return
  const inst = selectedInstance.value
  formData.value = { ...inst }
  allowedPhonesText.value = (inst.allowed_phones || []).join('\n')
  blockedPhonesText.value = (inst.blocked_phones || []).join('\n')
  showEditDialog.value = true
}

function submitCreate() {
  const data = { ...formData.value }
  data.allowed_phones = parsePhoneList(allowedPhonesText.value)
  data.blocked_phones = parsePhoneList(blockedPhonesText.value)
  createMutation.mutate(data)
}

function submitEdit() {
  if (!selectedInstanceId.value) return
  const data = { ...formData.value }
  data.allowed_phones = parsePhoneList(allowedPhonesText.value)
  data.blocked_phones = parsePhoneList(blockedPhonesText.value)
  updateMutation.mutate({ id: selectedInstanceId.value, data })
}

function confirmDelete() {
  if (!selectedInstance.value) return
  if (confirm(t('whatsapp.confirmDelete', { name: selectedInstance.value.name }))) {
    deleteMutation.mutate(selectedInstance.value.id)
  }
}

function parsePhoneList(text: string): string[] {
  return text.split(/[\n,;]+/).map(s => s.trim()).filter(s => s.length > 0)
}

// Auto-select first instance
watch(instances, (val) => {
  if (val.length > 0 && !selectedInstanceId.value) {
    selectedInstanceId.value = val[0].id
  }
}, { immediate: true })
</script>

<template>
  <div class="flex h-full">
    <!-- Instance List Sidebar -->
    <div
      v-show="!isMobile || showMobileList"
      :class="[
        'flex flex-col border-r border-border bg-card',
        isMobile ? 'w-full' : 'w-72 shrink-0'
      ]"
    >
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b border-border">
        <div>
          <h2 class="font-semibold">{{ t('whatsapp.title') }}</h2>
          <p class="text-xs text-muted-foreground">{{ t('whatsapp.instancesDesc') }}</p>
        </div>
        <button
          class="p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90"
          @click="openCreate"
        >
          <Plus class="w-4 h-4" />
        </button>
      </div>

      <!-- Instance list -->
      <div class="flex-1 overflow-y-auto p-2 space-y-1">
        <div v-if="instancesLoading" class="flex items-center justify-center p-8">
          <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
        <div v-else-if="instances.length === 0" class="p-8 text-center text-muted-foreground text-sm">
          {{ t('whatsapp.noInstances') }}
        </div>
        <button
          v-for="inst in instances"
          :key="inst.id"
          :class="[
            'w-full text-left p-3 rounded-lg transition-colors',
            selectedInstanceId === inst.id
              ? 'bg-secondary text-foreground'
              : 'hover:bg-secondary/50 text-muted-foreground'
          ]"
          @click="selectInstance(inst.id)"
        >
          <div class="flex items-center gap-2">
            <MessageCircle class="w-4 h-4 shrink-0" />
            <span class="font-medium truncate text-sm">{{ inst.name }}</span>
            <span
              :class="[
                'w-2 h-2 rounded-full ml-auto shrink-0',
                inst.running ? 'bg-green-500' : 'bg-gray-400'
              ]"
            />
          </div>
          <p v-if="inst.description" class="text-xs text-muted-foreground mt-1 truncate pl-6">
            {{ inst.description }}
          </p>
        </button>
      </div>
    </div>

    <!-- Main Content -->
    <div
      v-show="!isMobile || !showMobileList"
      class="flex-1 flex flex-col overflow-hidden"
    >
      <!-- No selection -->
      <div v-if="!selectedInstance" class="flex items-center justify-center h-full text-muted-foreground">
        <div class="text-center">
          <MessageCircle class="w-12 h-12 mx-auto mb-4 opacity-30" />
          <p>{{ t('whatsapp.selectInstance') }}</p>
        </div>
      </div>

      <!-- Instance detail -->
      <template v-else>
        <!-- Instance Header -->
        <div class="flex items-center gap-3 p-4 border-b border-border">
          <button
            v-if="isMobile"
            class="p-1 rounded hover:bg-secondary"
            @click="showMobileList = true"
          >
            <ChevronRight class="w-5 h-5 rotate-180" />
          </button>

          <MessageCircle class="w-6 h-6 text-green-600" />
          <div class="flex-1 min-w-0">
            <h2 class="font-semibold truncate">{{ selectedInstance.name }}</h2>
            <p class="text-xs text-muted-foreground">{{ selectedInstance.phone_number_id || t('whatsapp.noPhoneId') }}</p>
          </div>

          <!-- Status badge -->
          <span
            :class="[
              'px-2 py-0.5 rounded-full text-xs font-medium',
              instanceStatus?.running
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
            ]"
          >
            {{ instanceStatus?.running ? t('whatsapp.running') : t('whatsapp.stopped') }}
          </span>

          <!-- Control buttons -->
          <div class="flex items-center gap-1">
            <button
              v-if="!instanceStatus?.running"
              class="p-2 rounded-lg text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20"
              :disabled="startMutation.isPending.value"
              :title="t('whatsapp.start')"
              @click="startMutation.mutate(selectedInstance!.id)"
            >
              <Play class="w-4 h-4" />
            </button>
            <button
              v-if="instanceStatus?.running"
              class="p-2 rounded-lg text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
              :disabled="stopMutation.isPending.value"
              :title="t('whatsapp.stop')"
              @click="stopMutation.mutate(selectedInstance!.id)"
            >
              <Square class="w-4 h-4" />
            </button>
            <button
              class="p-2 rounded-lg text-muted-foreground hover:bg-secondary"
              :disabled="restartMutation.isPending.value"
              :title="t('whatsapp.restart')"
              @click="restartMutation.mutate(selectedInstance!.id)"
            >
              <RefreshCw class="w-4 h-4" />
            </button>
            <button
              class="p-2 rounded-lg text-muted-foreground hover:bg-secondary"
              :title="t('whatsapp.editBot')"
              @click="openEdit"
            >
              <Edit3 class="w-4 h-4" />
            </button>
            <button
              class="p-2 rounded-lg text-muted-foreground hover:bg-secondary"
              :title="t('whatsapp.viewLogs')"
              @click="showLogsDialog = true; refetchLogs()"
            >
              <FileText class="w-4 h-4" />
            </button>
            <button
              class="p-2 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
              :title="t('common.delete')"
              @click="confirmDelete"
            >
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Status Cards -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4">
          <div class="bg-card rounded-xl border border-border p-3">
            <div class="text-xs text-muted-foreground">{{ t('whatsapp.status') }}</div>
            <div class="font-semibold mt-1">
              {{ instanceStatus?.running ? t('whatsapp.online') : t('whatsapp.offline') }}
            </div>
          </div>
          <div class="bg-card rounded-xl border border-border p-3">
            <div class="text-xs text-muted-foreground">{{ t('whatsapp.aiBackend') }}</div>
            <div class="font-semibold mt-1 truncate">{{ selectedInstance.llm_backend }}</div>
          </div>
          <div class="bg-card rounded-xl border border-border p-3">
            <div class="text-xs text-muted-foreground">{{ t('whatsapp.webhookPort') }}</div>
            <div class="font-semibold mt-1">{{ selectedInstance.webhook_port }}</div>
          </div>
          <div class="bg-card rounded-xl border border-border p-3">
            <div class="text-xs text-muted-foreground">{{ t('whatsapp.tts') }}</div>
            <div class="font-semibold mt-1">{{ selectedInstance.tts_enabled ? selectedInstance.tts_engine : t('common.disabled') }}</div>
          </div>
        </div>

        <!-- Tabs -->
        <div class="flex border-b border-border px-4 gap-1">
          <button
            v-for="tab in (['settings', 'ai', 'access', 'logs'] as const)"
            :key="tab"
            :class="[
              'px-3 py-2 text-sm font-medium border-b-2 transition-colors -mb-px',
              activeTab === tab
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            ]"
            @click="activeTab = tab"
          >
            {{ t(`whatsapp.tabs.${tab}`) }}
          </button>
        </div>

        <!-- Tab Content -->
        <div class="flex-1 overflow-y-auto p-4">

          <!-- Settings Tab -->
          <div v-if="activeTab === 'settings'" class="space-y-4 max-w-2xl">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.phoneNumberId') }}</label>
              <div class="text-sm text-muted-foreground font-mono bg-secondary/50 px-3 py-2 rounded-lg">
                {{ selectedInstance.phone_number_id || '—' }}
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.wabaId') }}</label>
              <div class="text-sm text-muted-foreground font-mono bg-secondary/50 px-3 py-2 rounded-lg">
                {{ selectedInstance.waba_id || '—' }}
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.accessToken') }}</label>
              <div class="text-sm text-muted-foreground font-mono bg-secondary/50 px-3 py-2 rounded-lg">
                {{ selectedInstance.access_token_masked || '—' }}
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.verifyToken') }}</label>
              <div class="text-sm text-muted-foreground font-mono bg-secondary/50 px-3 py-2 rounded-lg">
                {{ selectedInstance.verify_token || '—' }}
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.webhookPort') }}</label>
              <div class="text-sm text-muted-foreground font-mono bg-secondary/50 px-3 py-2 rounded-lg">
                {{ selectedInstance.webhook_port }}
              </div>
            </div>
            <div class="flex items-center gap-2 text-sm">
              <Power class="w-4 h-4" />
              <span>{{ t('whatsapp.autoStart') }}:</span>
              <span :class="selectedInstance.auto_start ? 'text-green-600' : 'text-muted-foreground'">
                {{ selectedInstance.auto_start ? t('common.enabled') : t('common.disabled') }}
              </span>
            </div>
          </div>

          <!-- AI Tab -->
          <div v-if="activeTab === 'ai'" class="space-y-4 max-w-2xl">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.llmBackend') }}</label>
              <div class="text-sm bg-secondary/50 px-3 py-2 rounded-lg">{{ selectedInstance.llm_backend }}</div>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.ragMode') }}</label>
              <div class="text-sm bg-secondary/50 px-3 py-2 rounded-lg">
                {{ selectedInstance.rag_mode === 'none' ? t('whatsapp.ragModeNone') : selectedInstance.rag_mode === 'collection' ? t('whatsapp.ragModeCollection') : t('whatsapp.ragModeAll') }}
                <span v-if="selectedInstance.rag_mode === 'collection' && selectedInstance.knowledge_collection_id">
                  ({{ knowledgeCollections.find(c => c.id === selectedInstance?.knowledge_collection_id)?.name || `#${selectedInstance?.knowledge_collection_id}` }})
                </span>
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.systemPrompt') }}</label>
              <div class="text-sm bg-secondary/50 px-3 py-2 rounded-lg whitespace-pre-wrap min-h-[60px]">
                {{ selectedInstance.system_prompt || t('whatsapp.systemPromptDefault') }}
              </div>
            </div>
            <div class="border-t border-border pt-4">
              <h3 class="font-medium mb-3 flex items-center gap-2">
                <Volume2 class="w-4 h-4" />
                {{ t('whatsapp.tts') }}
              </h3>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.ttsEnabled') }}</label>
                  <div class="text-sm">{{ selectedInstance.tts_enabled ? t('common.enabled') : t('common.disabled') }}</div>
                </div>
                <div v-if="selectedInstance.tts_enabled">
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.ttsEngine') }}</label>
                  <div class="text-sm">{{ selectedInstance.tts_engine }} / {{ selectedInstance.tts_voice }}</div>
                </div>
              </div>
            </div>
            <div class="border-t border-border pt-4">
              <h3 class="font-medium mb-3">{{ t('whatsapp.rateLimit') }}</h3>
              <p class="text-xs text-muted-foreground mb-2">{{ t('whatsapp.rateLimitHint') }}</p>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.rateLimitCount') }}</label>
                  <div class="text-sm">{{ selectedInstance.rate_limit_count ?? '—' }}</div>
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.rateLimitHours') }}</label>
                  <div class="text-sm">{{ selectedInstance.rate_limit_hours ?? '—' }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Access Tab -->
          <div v-if="activeTab === 'access'" class="space-y-4 max-w-2xl">
            <div>
              <h3 class="font-medium mb-2 flex items-center gap-2">
                <Shield class="w-4 h-4" />
                {{ t('whatsapp.allowedPhones') }}
              </h3>
              <p class="text-xs text-muted-foreground mb-2">{{ t('whatsapp.allowedPhonesHint') }}</p>
              <div v-if="selectedInstance.allowed_phones?.length" class="space-y-1">
                <div
                  v-for="phone in selectedInstance.allowed_phones"
                  :key="phone"
                  class="text-sm font-mono bg-secondary/50 px-3 py-1.5 rounded-lg flex items-center gap-2"
                >
                  <Phone class="w-3 h-3 text-muted-foreground" />
                  {{ phone }}
                </div>
              </div>
              <div v-else class="text-sm text-muted-foreground">{{ t('whatsapp.allPhones') }}</div>
            </div>
            <div class="border-t border-border pt-4">
              <h3 class="font-medium mb-2 flex items-center gap-2">
                <Shield class="w-4 h-4 text-red-500" />
                {{ t('whatsapp.blockedPhones') }}
              </h3>
              <div v-if="selectedInstance.blocked_phones?.length" class="space-y-1">
                <div
                  v-for="phone in selectedInstance.blocked_phones"
                  :key="phone"
                  class="text-sm font-mono bg-red-50 dark:bg-red-900/10 px-3 py-1.5 rounded-lg"
                >
                  {{ phone }}
                </div>
              </div>
              <div v-else class="text-sm text-muted-foreground">{{ t('whatsapp.noBlockedPhones') }}</div>
            </div>
          </div>

          <!-- Logs Tab -->
          <div v-if="activeTab === 'logs'" class="space-y-2">
            <div class="flex items-center justify-between">
              <h3 class="font-medium">{{ t('whatsapp.logs') }}</h3>
              <button
                class="text-xs px-2 py-1 rounded bg-secondary hover:bg-secondary/80"
                @click="refetchLogs()"
              >
                <RefreshCw class="w-3 h-3 inline mr-1" />
                {{ t('common.refresh') }}
              </button>
            </div>
            <pre class="bg-secondary/50 rounded-lg p-3 text-xs font-mono overflow-auto max-h-[500px] whitespace-pre-wrap">{{ logsData?.logs || t('whatsapp.noLogs') }}</pre>
          </div>
        </div>
      </template>
    </div>

    <!-- Create Dialog -->
    <Teleport to="body">
      <div v-if="showCreateDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showCreateDialog = false">
        <div class="bg-card rounded-2xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
          <div class="flex items-center justify-between p-4 border-b border-border">
            <h3 class="font-semibold">{{ t('whatsapp.createBot') }}</h3>
            <button class="p-1 rounded hover:bg-secondary" @click="showCreateDialog = false"><X class="w-4 h-4" /></button>
          </div>
          <div class="p-4 space-y-3">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.botName') }} *</label>
              <input v-model="formData.name" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" :placeholder="t('whatsapp.botNamePlaceholder')" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.botDescription') }}</label>
              <input v-model="formData.description" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" />
            </div>
            <div class="border-t border-border pt-3">
              <h4 class="text-sm font-medium mb-2">WhatsApp Cloud API</h4>
              <div class="space-y-2">
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.phoneNumberId') }}</label>
                  <input v-model="formData.phone_number_id" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" placeholder="123456789012345" />
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.wabaId') }}</label>
                  <input v-model="formData.waba_id" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" />
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.accessToken') }}</label>
                  <input v-model="formData.access_token" type="password" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" />
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.verifyToken') }}</label>
                  <input v-model="formData.verify_token" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" />
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.appSecret') }}</label>
                  <input v-model="formData.app_secret" type="password" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" />
                </div>
              </div>
            </div>
            <div class="border-t border-border pt-3">
              <h4 class="text-sm font-medium mb-2">{{ t('whatsapp.tabs.ai') }}</h4>
              <div>
                <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.llmBackend') }}</label>
                <input v-model="formData.llm_backend" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" placeholder="vllm" />
              </div>
              <!-- RAG config -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.ragMode') }}</label>
                  <select v-model="formData.rag_mode" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm">
                    <option value="all">{{ t('whatsapp.ragModeAll') }}</option>
                    <option value="collection">{{ t('whatsapp.ragModeCollection') }}</option>
                    <option value="none">{{ t('whatsapp.ragModeNone') }}</option>
                  </select>
                </div>
                <div v-if="formData.rag_mode === 'collection'">
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.ragCollection') }}</label>
                  <select v-model="formData.knowledge_collection_id" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm">
                    <option :value="null">—</option>
                    <option v-for="col in knowledgeCollections" :key="col.id" :value="col.id">{{ col.name }}</option>
                  </select>
                </div>
              </div>
              <div class="mt-2">
                <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.systemPrompt') }}</label>
                <textarea v-model="formData.system_prompt" rows="3" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" :placeholder="t('whatsapp.systemPromptPlaceholder')" />
              </div>
            </div>
          </div>
          <div class="flex justify-end gap-2 p-4 border-t border-border">
            <button class="px-4 py-2 rounded-lg text-sm hover:bg-secondary" @click="showCreateDialog = false">{{ t('common.cancel') }}</button>
            <button
              class="px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              :disabled="!formData.name || createMutation.isPending.value"
              @click="submitCreate"
            >
              <Loader2 v-if="createMutation.isPending.value" class="w-4 h-4 animate-spin inline mr-1" />
              {{ t('common.create') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Edit Dialog -->
    <Teleport to="body">
      <div v-if="showEditDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showEditDialog = false">
        <div class="bg-card rounded-2xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
          <div class="flex items-center justify-between p-4 border-b border-border">
            <h3 class="font-semibold">{{ t('whatsapp.editBot') }}</h3>
            <button class="p-1 rounded hover:bg-secondary" @click="showEditDialog = false"><X class="w-4 h-4" /></button>
          </div>
          <div class="p-4 space-y-3">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.botName') }} *</label>
              <input v-model="formData.name" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('whatsapp.botDescription') }}</label>
              <input v-model="formData.description" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" />
            </div>
            <div class="border-t border-border pt-3">
              <h4 class="text-sm font-medium mb-2">WhatsApp Cloud API</h4>
              <div class="space-y-2">
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.phoneNumberId') }}</label>
                  <input v-model="formData.phone_number_id" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" />
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.wabaId') }}</label>
                  <input v-model="formData.waba_id" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" />
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.accessToken') }}</label>
                  <input v-model="formData.access_token" type="password" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" placeholder="(unchanged)" />
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.verifyToken') }}</label>
                  <input v-model="formData.verify_token" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" />
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.appSecret') }}</label>
                  <input v-model="formData.app_secret" type="password" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" placeholder="(unchanged)" />
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.webhookPort') }}</label>
                  <input v-model.number="formData.webhook_port" type="number" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" />
                </div>
              </div>
            </div>
            <div class="border-t border-border pt-3">
              <h4 class="text-sm font-medium mb-2">{{ t('whatsapp.tabs.ai') }}</h4>
              <div>
                <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.llmBackend') }}</label>
                <input v-model="formData.llm_backend" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" />
              </div>
              <div class="mt-2">
                <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.systemPrompt') }}</label>
                <textarea v-model="formData.system_prompt" rows="3" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" />
              </div>
              <div class="mt-3 flex items-center gap-2">
                <input id="tts-enabled" v-model="formData.tts_enabled" type="checkbox" class="rounded" />
                <label for="tts-enabled" class="text-sm">{{ t('whatsapp.ttsEnabled') }}</label>
              </div>
            </div>
            <div class="border-t border-border pt-3">
              <h4 class="text-sm font-medium mb-2">{{ t('whatsapp.tabs.access') }}</h4>
              <div>
                <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.allowedPhones') }}</label>
                <textarea v-model="allowedPhonesText" rows="3" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" :placeholder="t('whatsapp.phonesPlaceholder')" />
              </div>
              <div class="mt-2">
                <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.blockedPhones') }}</label>
                <textarea v-model="blockedPhonesText" rows="2" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono" :placeholder="t('whatsapp.phonesPlaceholder')" />
              </div>
            </div>
            <div class="border-t border-border pt-3">
              <h4 class="text-sm font-medium mb-2">{{ t('whatsapp.rateLimit') }}</h4>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.rateLimitCount') }}</label>
                  <input v-model.number="formData.rate_limit_count" type="number" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" />
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('whatsapp.rateLimitHours') }}</label>
                  <input v-model.number="formData.rate_limit_hours" type="number" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" />
                </div>
              </div>
            </div>
            <div class="flex items-center gap-2 border-t border-border pt-3">
              <input id="auto-start" v-model="formData.auto_start" type="checkbox" class="rounded" />
              <label for="auto-start" class="text-sm">{{ t('whatsapp.autoStart') }}</label>
            </div>
          </div>
          <div class="flex justify-end gap-2 p-4 border-t border-border">
            <button class="px-4 py-2 rounded-lg text-sm hover:bg-secondary" @click="showEditDialog = false">{{ t('common.cancel') }}</button>
            <button
              class="px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              :disabled="!formData.name || updateMutation.isPending.value"
              @click="submitEdit"
            >
              <Loader2 v-if="updateMutation.isPending.value" class="w-4 h-4 animate-spin inline mr-1" />
              {{ t('common.save') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Logs Dialog -->
    <Teleport to="body">
      <div v-if="showLogsDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showLogsDialog = false">
        <div class="bg-card rounded-2xl shadow-xl w-full max-w-3xl mx-4 max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between p-4 border-b border-border">
            <h3 class="font-semibold">{{ t('whatsapp.logs') }} — {{ selectedInstance?.name }}</h3>
            <div class="flex items-center gap-2">
              <button class="text-xs px-2 py-1 rounded bg-secondary hover:bg-secondary/80" @click="refetchLogs()">
                <RefreshCw class="w-3 h-3 inline mr-1" />{{ t('common.refresh') }}
              </button>
              <button class="p-1 rounded hover:bg-secondary" @click="showLogsDialog = false"><X class="w-4 h-4" /></button>
            </div>
          </div>
          <pre class="flex-1 overflow-auto p-4 text-xs font-mono whitespace-pre-wrap">{{ logsData?.logs || t('whatsapp.noLogs') }}</pre>
        </div>
      </div>
    </Teleport>
  </div>
</template>
