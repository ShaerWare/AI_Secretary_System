<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { useResponsive } from '@/composables/useResponsive'
import {
  Code2,
  Globe,
  Palette,
  MessageSquare,
  Copy,
  Check,
  Plus,
  X,
  Power,
  ExternalLink,
  Terminal,
  BookOpen,
  RefreshCw,
  Loader2,
  Eye,
  EyeOff,
  Trash2,
  Edit3,
  ChevronRight,
  Cpu,
  Volume2,
  Settings2,
  Send,
  MessageCircle,
  RotateCcw
} from 'lucide-vue-next'
import { widgetInstancesApi, llmApi, type WidgetInstance, type CloudProvider } from '@/api'
import { chatApi, type ChatMessage } from '@/api/chat'
import { useToastStore } from '@/stores/toast'

const { t } = useI18n()
const queryClient = useQueryClient()
const toast = useToastStore()
const { isMobile } = useResponsive()

// Mobile master-detail: show list or detail
const showMobileList = ref(true)

// State
const selectedInstanceId = ref<string | null>(null)
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const activeTab = ref<'settings' | 'appearance' | 'domains' | 'ai' | 'code' | 'test'>('settings')
const copied = ref<string | null>(null)

// Form state for create/edit
const formData = ref<Partial<WidgetInstance>>({
  name: '',
  description: '',
  enabled: true,
  title: 'AI Ассистент',
  greeting: 'Здравствуйте! Чем могу помочь?',
  placeholder: 'Введите сообщение...',
  placeholder_color: '',
  placeholder_font: '',
  primary_color: '#c2410c',
  button_icon: 'chat',
  position: 'right',
  allowed_domains: [],
  tunnel_url: '',
  llm_backend: 'vllm',
  llm_persona: 'anna',
  system_prompt: '',
  tts_engine: 'xtts',
  tts_voice: 'anna',
  tts_preset: '',
  rate_limit_count: null,
  rate_limit_hours: null,
})

const newDomain = ref('')

const iconOptions = ['chat', 'headset', 'robot', 'comment', 'support', 'wave'] as const
const iconSvgs: Record<string, string> = {
  chat: '<svg viewBox="0 0 24 24" class="w-6 h-6"><path fill="currentColor" d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z"/></svg>',
  headset: '<svg viewBox="0 0 24 24" class="w-6 h-6"><path fill="currentColor" d="M12 1a9 9 0 0 0-9 9v7c0 1.66 1.34 3 3 3h3v-8H5v-2c0-3.87 3.13-7 7-7s7 3.13 7 7v2h-4v8h3c1.66 0 3-1.34 3-3v-7a9 9 0 0 0-9-9z"/></svg>',
  robot: '<svg viewBox="0 0 24 24" class="w-6 h-6"><path fill="currentColor" d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2zM7.5 13A2.5 2.5 0 0 0 5 15.5 2.5 2.5 0 0 0 7.5 18a2.5 2.5 0 0 0 2.5-2.5A2.5 2.5 0 0 0 7.5 13zm9 0a2.5 2.5 0 0 0-2.5 2.5 2.5 2.5 0 0 0 2.5 2.5 2.5 2.5 0 0 0 2.5-2.5 2.5 2.5 0 0 0-2.5-2.5z"/></svg>',
  comment: '<svg viewBox="0 0 24 24" class="w-6 h-6"><path fill="currentColor" d="M12 3C6.5 3 2 6.6 2 11c0 2.5 1.4 4.7 3.5 6.2-.3 1.6-1.2 3-2.4 4 2.2-.1 4.4-1 6-2.5.9.2 1.9.3 2.9.3 5.5 0 10-3.6 10-8s-4.5-8-10-8z"/></svg>',
  support: '<svg viewBox="0 0 24 24" class="w-6 h-6"><path fill="currentColor" d="M11.5 2C6.8 2 3 5.8 3 10.5c0 1.6.4 3.1 1.2 4.4L2 21l6.1-2.2c1.3.8 2.8 1.2 4.4 1.2h.5c4.2-.3 7.5-3.8 7.5-8 0-4.7-3.8-8.5-8.5-8.5h-.5zm5 11h-9c-.3 0-.5-.2-.5-.5s.2-.5.5-.5h9c.3 0 .5.2.5.5s-.2.5-.5.5zm0-3h-9c-.3 0-.5-.2-.5-.5s.2-.5.5-.5h9c.3 0 .5.2.5.5s-.2.5-.5.5z"/></svg>',
  wave: '<svg viewBox="0 0 24 24" class="w-6 h-6"><path fill="currentColor" d="M7.03 4.95c-.29-.29-.77-.29-1.06 0L4.89 6.03c-2.34 2.34-2.34 6.14 0 8.49l4.59 4.59c2.34 2.34 6.14 2.34 8.49 0l1.08-1.08c.29-.29.29-.77 0-1.06L7.03 4.95zm14.46 6.02c.39-.39.39-1.02 0-1.41L18.95 7.01c-.39-.39-1.02-.39-1.41 0-.39.39-.39 1.02 0 1.41l1.06 1.06-4.23 4.23 1.06 1.06 4.23-4.23 1.06 1.06c.39.39 1.02.39 1.41 0l.36-.37zM8.44 17.8c-.39.39-.39 1.02 0 1.41.39.39 1.02.39 1.41 0l4.23-4.23-1.06-1.06-4.58 3.88z"/></svg>',
}

// Queries
const { data: instancesData, isLoading: instancesLoading, refetch: refetchInstances } = useQuery({
  queryKey: ['widget-instances'],
  queryFn: () => widgetInstancesApi.list(),
  refetchInterval: 5000,
})

const instances = computed(() => instancesData.value?.instances || [])

// Cloud providers for LLM backend dropdown
const { data: cloudProvidersData } = useQuery({
  queryKey: ['llm-providers'],
  queryFn: () => llmApi.getProviders(),
})
const cloudProviders = computed(() => (cloudProvidersData.value?.providers || []).filter((p: CloudProvider) => p.enabled))

const selectedInstance = computed(() =>
  instances.value.find(i => i.id === selectedInstanceId.value)
)

// Mutations
const createMutation = useMutation({
  mutationFn: (data: Partial<WidgetInstance>) => widgetInstancesApi.create(data),
  onSuccess: (data) => {
    queryClient.invalidateQueries({ queryKey: ['widget-instances'] })
    toast.success(t('widget.instanceCreated'))
    showCreateDialog.value = false
    selectedInstanceId.value = data.instance.id
  },
  onError: () => toast.error(t('widget.createFailed')),
})

const updateMutation = useMutation({
  mutationFn: ({ id, data }: { id: string; data: Partial<WidgetInstance> }) =>
    widgetInstancesApi.update(id, data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['widget-instances'] })
    toast.success(t('widget.saved'))
    showEditDialog.value = false
  },
  onError: () => toast.error(t('widget.saveFailed')),
})

const deleteMutation = useMutation({
  mutationFn: (id: string) => widgetInstancesApi.delete(id),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['widget-instances'] })
    toast.success(t('widget.instanceDeleted'))
    if (selectedInstanceId.value === deleteMutation.variables.value) {
      selectedInstanceId.value = null
    }
  },
  onError: () => toast.error(t('widget.deleteFailed')),
})

// Functions
function openCreateDialog() {
  formData.value = {
    name: '',
    description: '',
    enabled: true,
    title: 'AI Ассистент',
    greeting: 'Здравствуйте! Чем могу помочь?',
    placeholder: 'Введите сообщение...',
    placeholder_color: '',
    placeholder_font: '',
    primary_color: '#c2410c',
    button_icon: 'chat',
    position: 'right',
    allowed_domains: [],
    tunnel_url: '',
    llm_backend: 'vllm',
    llm_persona: 'anna',
    system_prompt: '',
    tts_engine: 'xtts',
    tts_voice: 'anna',
    tts_preset: '',
    rate_limit_count: null,
    rate_limit_hours: null,
  }
  showCreateDialog.value = true
}

async function openEditDialog(instance: WidgetInstance) {
  // Load instance for editing
  try {
    const response = await widgetInstancesApi.get(instance.id)
    formData.value = { ...response.instance }
  } catch {
    formData.value = { ...instance }
  }
  showEditDialog.value = true
}

function saveInstance() {
  if (showCreateDialog.value) {
    createMutation.mutate(formData.value)
  } else if (showEditDialog.value && selectedInstanceId.value) {
    updateMutation.mutate({ id: selectedInstanceId.value, data: formData.value })
  }
}

function confirmDelete(instance: WidgetInstance) {
  if (confirm(t('widget.confirmDelete', { name: instance.name }))) {
    deleteMutation.mutate(instance.id)
  }
}

function addDomain() {
  const domain = newDomain.value.trim().toLowerCase()
  if (domain && !formData.value.allowed_domains?.includes(domain)) {
    formData.value.allowed_domains = [...(formData.value.allowed_domains || []), domain]
    newDomain.value = ''
  }
}

function removeDomain(domain: string) {
  formData.value.allowed_domains = formData.value.allowed_domains?.filter(d => d !== domain) || []
}

// Copy to clipboard
async function copyToClipboard(text: string, key: string) {
  await navigator.clipboard.writeText(text)
  copied.value = key
  setTimeout(() => { copied.value = null }, 2000)
  toast.success(t('common.copied'))
}

// Generated code snippets
const apiUrl = computed(() => {
  if (selectedInstance.value?.tunnel_url) {
    return selectedInstance.value.tunnel_url
  }
  return window.location.origin
})

const scriptTag = computed(() => {
  const instanceParam = selectedInstance.value?.id && selectedInstance.value.id !== 'default'
    ? `?instance=${selectedInstance.value.id}`
    : ''
  return `<script src="${apiUrl.value}/widget.js${instanceParam}"></` + 'script>'
})

const fullSnippet = computed(() => {
  const instanceParam = selectedInstance.value?.id && selectedInstance.value.id !== 'default'
    ? `?instance=${selectedInstance.value.id}`
    : ''
  return `<!-- AI Chat Widget -->
<script src="${apiUrl.value}/widget.js${instanceParam}"></` + 'script>'
})

// Color presets
const colorPresets = [
  { name: 'Orange', value: '#c2410c' },
  { name: 'Indigo', value: '#6366f1' },
  { name: 'Blue', value: '#3b82f6' },
  { name: 'Green', value: '#22c55e' },
  { name: 'Purple', value: '#a855f7' },
  { name: 'Pink', value: '#ec4899' },
]

// Auto-select first instance
watch(instances, (newInstances) => {
  if (!selectedInstanceId.value && newInstances.length > 0) {
    selectedInstanceId.value = newInstances[0].id
  }
}, { immediate: true })

// === Test Chat ===
interface TestMessage {
  role: 'user' | 'assistant'
  content: string
}

const testSessionMap = ref<Map<string, string>>(new Map())
const testMessages = ref<TestMessage[]>([])
const testInput = ref('')
const testStreaming = ref(false)
const testChatContainer = ref<HTMLElement | null>(null)
let currentAbort: (() => void) | null = null

const testSessionId = computed(() =>
  selectedInstanceId.value ? testSessionMap.value.get(selectedInstanceId.value) ?? null : null
)

// Reset messages when switching instances
watch(selectedInstanceId, () => {
  testMessages.value = []
  testInput.value = ''
  if (testStreaming.value && currentAbort) {
    currentAbort()
    testStreaming.value = false
    currentAbort = null
  }
})

function scrollTestChat() {
  nextTick(() => {
    if (testChatContainer.value) {
      testChatContainer.value.scrollTop = testChatContainer.value.scrollHeight
    }
  })
}

async function sendTestMessage() {
  const content = testInput.value.trim()
  if (!content || testStreaming.value || !selectedInstance.value) return

  const instanceId = selectedInstance.value.id
  testInput.value = ''

  // Add user message
  testMessages.value.push({ role: 'user', content })
  scrollTestChat()

  // Create session if needed
  let sessionId = testSessionMap.value.get(instanceId)
  if (!sessionId) {
    try {
      const res = await chatApi.createSession(
        `Widget test: ${selectedInstance.value.name}`,
        undefined,
        'widget',
        instanceId
      )
      sessionId = res.session.id
      testSessionMap.value.set(instanceId, sessionId)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to create session'
      testMessages.value.push({ role: 'assistant', content: `Error: ${msg}` })
      scrollTestChat()
      return
    }
  }

  // Add empty assistant message for streaming
  testMessages.value.push({ role: 'assistant', content: '' })
  testStreaming.value = true
  scrollTestChat()

  const assistantIdx = testMessages.value.length - 1

  const { abort } = chatApi.streamMessage(
    sessionId,
    content,
    (data) => {
      if (data.type === 'chunk' && data.content) {
        testMessages.value[assistantIdx].content += data.content
        scrollTestChat()
      } else if (data.type === 'done') {
        testStreaming.value = false
        currentAbort = null
      } else if (data.type === 'error') {
        testMessages.value[assistantIdx].content += `\n[Error: ${data.content}]`
        testStreaming.value = false
        currentAbort = null
        scrollTestChat()
      }
    },
    undefined,
    instanceId
  )

  currentAbort = abort
}

function clearTestChat() {
  if (testStreaming.value && currentAbort) {
    currentAbort()
    testStreaming.value = false
    currentAbort = null
  }
  testMessages.value = []
  if (selectedInstanceId.value) {
    const sessionId = testSessionMap.value.get(selectedInstanceId.value)
    if (sessionId) {
      chatApi.deleteSession(sessionId).catch(() => {})
      testSessionMap.value.delete(selectedInstanceId.value)
    }
  }
}

function handleTestKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendTestMessage()
  }
}
</script>

<template>
  <div class="flex h-full gap-6 animate-fade-in">
    <!-- Sidebar: Instance List -->
    <div
      v-show="!isMobile || showMobileList"
      :class="[
        'flex-shrink-0 flex flex-col bg-card rounded-xl border border-border overflow-hidden',
        isMobile ? 'w-full' : 'w-80'
      ]"
    >
      <!-- Header -->
      <div class="p-4 border-b border-border">
        <div class="flex items-center justify-between mb-2">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <Code2 class="w-5 h-5 text-indigo-400" />
            {{ t('widget.widgets') }}
          </h2>
          <button
            class="p-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
            :title="t('widget.createWidget')"
            @click="openCreateDialog"
          >
            <Plus class="w-4 h-4" />
          </button>
        </div>
        <p class="text-xs text-muted-foreground">{{ t('widget.instancesDesc') }}</p>
      </div>

      <!-- Instance List -->
      <div class="flex-1 overflow-y-auto p-2">
        <div v-if="instancesLoading" class="flex items-center justify-center p-8">
          <Loader2 class="w-6 h-6 animate-spin text-primary" />
        </div>

        <div v-else-if="instances.length === 0" class="text-center p-8 text-muted-foreground">
          <Globe class="w-12 h-12 mx-auto mb-2 opacity-50" />
          <p>{{ t('widget.noInstances') }}</p>
        </div>

        <div v-else class="space-y-1">
          <button
            v-for="instance in instances"
            :key="instance.id"
            :class="[
              'w-full p-3 rounded-lg text-left transition-colors',
              selectedInstanceId === instance.id
                ? 'bg-primary/10 border border-primary/30'
                : 'hover:bg-secondary'
            ]"
            @click="selectedInstanceId = instance.id; showMobileList = false"
          >
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span
:class="[
                  'w-2 h-2 rounded-full',
                  instance.enabled ? 'bg-green-400' : 'bg-gray-400'
                ]" />
                <span class="font-medium truncate">{{ instance.name }}</span>
              </div>
              <ChevronRight class="w-4 h-4 text-muted-foreground" />
            </div>
            <p v-if="instance.description" class="text-xs text-muted-foreground mt-1 truncate">
              {{ instance.description }}
            </p>
          </button>
        </div>
      </div>
    </div>

    <!-- Main Content -->
    <div v-show="!isMobile || !showMobileList" class="flex-1 flex flex-col min-w-0">
      <!-- No selection -->
      <div v-if="!selectedInstance" class="flex-1 flex items-center justify-center">
        <div class="text-center">
          <Globe class="w-16 h-16 mx-auto mb-4 text-muted-foreground/50" />
          <p class="text-muted-foreground">{{ t('widget.selectInstance') }}</p>
        </div>
      </div>

      <!-- Instance Detail -->
      <template v-else>
        <!-- Mobile back button -->
        <button
          v-if="isMobile"
          class="flex items-center gap-2 text-sm text-primary mb-4 hover:underline"
          @click="showMobileList = true"
        >
          <ChevronRight class="w-4 h-4 rotate-180" />
          {{ t('widget.widgets') }}
        </button>

        <!-- Instance Header -->
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            <h1 class="text-2xl font-bold flex items-center gap-2">
              {{ selectedInstance.name }}
              <span
:class="[
                'px-2 py-0.5 text-xs rounded-full',
                selectedInstance.enabled
                  ? 'bg-green-500/20 text-green-400'
                  : 'bg-gray-500/20 text-gray-400'
              ]">
                {{ selectedInstance.enabled ? t('widget.enabled') : t('widget.disabled') }}
              </span>
            </h1>
            <p v-if="selectedInstance.description" class="text-muted-foreground mt-1">
              {{ selectedInstance.description }}
            </p>
          </div>
          <div class="flex items-center gap-2 flex-wrap">
            <a
              :href="`${apiUrl}/widget.js${selectedInstance.id !== 'default' ? '?instance=' + selectedInstance.id : ''}`"
              target="_blank"
              class="flex items-center gap-2 px-3 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
              :title="t('widget.testWidget')"
            >
              <ExternalLink class="w-4 h-4" />
              {{ t('widget.testWidget') }}
            </a>
            <button
              class="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
              @click="openEditDialog(selectedInstance)"
            >
              <Edit3 class="w-4 h-4" />
              {{ t('common.edit') }}
            </button>
            <button
              class="p-2 text-red-400 hover:bg-red-500/20 rounded-lg transition-colors"
              :title="t('common.delete')"
              @click="confirmDelete(selectedInstance)"
            >
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Status Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div class="bg-card rounded-xl border border-border p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <Globe class="w-4 h-4" />
              <span class="text-sm">{{ t('widget.status') }}</span>
            </div>
            <p :class="['text-lg font-semibold', selectedInstance.enabled ? 'text-green-400' : 'text-gray-400']">
              {{ selectedInstance.enabled ? t('widget.enabled') : t('widget.disabled') }}
            </p>
          </div>
          <div class="bg-card rounded-xl border border-border p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <Palette class="w-4 h-4" />
              <span class="text-sm">{{ t('widget.primaryColor') }}</span>
            </div>
            <div class="flex items-center gap-2">
              <div
                class="w-6 h-6 rounded-full border border-border"
                :style="{ backgroundColor: selectedInstance.primary_color }"
              />
              <span class="text-sm font-mono">{{ selectedInstance.primary_color }}</span>
            </div>
          </div>
          <div class="bg-card rounded-xl border border-border p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <Globe class="w-4 h-4" />
              <span class="text-sm">{{ t('widget.allowedDomains') }}</span>
            </div>
            <p class="text-lg font-semibold">
              {{ selectedInstance.allowed_domains?.length || t('widget.allDomains') }}
            </p>
          </div>
          <div class="bg-card rounded-xl border border-border p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <Cpu class="w-4 h-4" />
              <span class="text-sm">{{ t('widget.aiBackend') }}</span>
            </div>
            <p class="text-lg font-semibold">{{ selectedInstance.llm_backend }}</p>
          </div>
        </div>

        <!-- Tabs -->
        <div class="flex gap-1 bg-secondary/50 p-1 rounded-lg w-fit mb-6 tab-bar-scroll max-w-full whitespace-nowrap">
          <button
            v-for="tab in ['settings', 'appearance', 'domains', 'ai', 'code', 'test'] as const"
            :key="tab"
            :class="[
              'px-4 py-2 text-sm rounded-md transition-colors',
              activeTab === tab
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            ]"
            @click="activeTab = tab"
          >
            <span class="flex items-center gap-2">
              <Settings2 v-if="tab === 'settings'" class="w-4 h-4" />
              <Palette v-else-if="tab === 'appearance'" class="w-4 h-4" />
              <Globe v-else-if="tab === 'domains'" class="w-4 h-4" />
              <Cpu v-else-if="tab === 'ai'" class="w-4 h-4" />
              <Code2 v-else-if="tab === 'code'" class="w-4 h-4" />
              <MessageCircle v-else class="w-4 h-4" />
              {{ t(`widget.tabs.${tab}`) }}
            </span>
          </button>
        </div>

        <!-- Tab Content -->
        <div class="flex-1 overflow-y-auto space-y-4">
          <!-- Settings Tab -->
          <template v-if="activeTab === 'settings'">
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('widget.tunnelUrl') }}</h3>
              <p class="text-sm text-muted-foreground mb-2">{{ t('widget.tunnelUrlDesc') }}</p>
              <code class="block px-3 py-2 bg-secondary rounded-lg font-mono text-sm">
                {{ selectedInstance.tunnel_url || t('widget.noTunnel') }}
              </code>
            </div>
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('widget.widgetTitle') }}</h3>
              <p class="text-sm bg-secondary rounded-lg p-3">{{ selectedInstance.title }}</p>
            </div>
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('widget.greeting') }}</h3>
              <p class="text-sm bg-secondary rounded-lg p-3">{{ selectedInstance.greeting }}</p>
            </div>
          </template>

          <!-- Appearance Tab -->
          <template v-if="activeTab === 'appearance'">
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('widget.primaryColor') }}</h3>
              <div class="flex items-center gap-3">
                <div
                  class="w-10 h-10 rounded-full border border-border"
                  :style="{ backgroundColor: selectedInstance.primary_color }"
                />
                <span class="font-mono">{{ selectedInstance.primary_color }}</span>
              </div>
            </div>
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('widget.position') }}</h3>
              <p class="text-lg font-semibold capitalize">{{ t(`widget.positions.${selectedInstance.position}`) }}</p>
            </div>
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('widget.placeholder') }}</h3>
              <p class="text-sm bg-secondary rounded-lg p-3">{{ selectedInstance.placeholder }}</p>
            </div>
            <div v-if="selectedInstance.placeholder_color" class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('widget.placeholderColor') }}</h3>
              <div class="flex items-center gap-3">
                <div
                  class="w-10 h-10 rounded-full border border-border"
                  :style="{ backgroundColor: selectedInstance.placeholder_color }"
                />
                <span class="font-mono">{{ selectedInstance.placeholder_color }}</span>
              </div>
            </div>
            <div v-if="selectedInstance.placeholder_font" class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('widget.placeholderFont') }}</h3>
              <p class="text-sm">{{ selectedInstance.placeholder_font }}</p>
            </div>
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('widget.buttonIcon') }}</h3>
              <div class="flex items-center gap-3">
                <div
                  class="w-10 h-10 rounded-full flex items-center justify-center"
                  :style="{ backgroundColor: selectedInstance.primary_color, color: 'white' }"
                  v-html="iconSvgs[selectedInstance.button_icon || 'chat']"
                />
                <span class="capitalize">{{ t(`widget.buttonIcons.${selectedInstance.button_icon || 'chat'}`) }}</span>
              </div>
            </div>
          </template>

          <!-- Domains Tab -->
          <template v-if="activeTab === 'domains'">
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('widget.allowedDomainsList') }}</h3>
              <p class="text-sm text-muted-foreground mb-3">{{ t('widget.allowedDomainsDesc') }}</p>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="domain in selectedInstance.allowed_domains"
                  :key="domain"
                  class="flex items-center gap-2 px-3 py-1.5 bg-secondary rounded-full text-sm"
                >
                  <Globe class="w-3 h-3 text-muted-foreground" />
                  {{ domain }}
                </span>
                <span v-if="!selectedInstance.allowed_domains?.length" class="text-sm text-muted-foreground">
                  {{ t('widget.allDomainsAllowed') }}
                </span>
              </div>
            </div>
          </template>

          <!-- AI Tab -->
          <template v-if="activeTab === 'ai'">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="bg-card rounded-xl border border-border p-4">
                <h3 class="font-medium mb-2">{{ t('widget.llmBackend') }}</h3>
                <p class="text-lg font-semibold">{{ selectedInstance.llm_backend }}</p>
              </div>
              <div class="bg-card rounded-xl border border-border p-4">
                <h3 class="font-medium mb-2">{{ t('widget.llmPersona') }}</h3>
                <p class="text-lg font-semibold">{{ selectedInstance.llm_persona }}</p>
              </div>
              <div class="bg-card rounded-xl border border-border p-4">
                <h3 class="font-medium mb-2">{{ t('widget.ttsEngine') }}</h3>
                <p class="text-lg font-semibold">{{ selectedInstance.tts_engine }}</p>
              </div>
              <div class="bg-card rounded-xl border border-border p-4">
                <h3 class="font-medium mb-2">{{ t('widget.ttsVoice') }}</h3>
                <p class="text-lg font-semibold">{{ selectedInstance.tts_voice }}</p>
              </div>
            </div>
            <div v-if="selectedInstance.system_prompt" class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('widget.systemPrompt') }}</h3>
              <p class="text-sm bg-secondary rounded-lg p-3 whitespace-pre-wrap">{{ selectedInstance.system_prompt }}</p>
            </div>
          </template>

          <!-- Code Tab -->
          <template v-if="activeTab === 'code'">
            <div class="bg-card rounded-xl border border-border p-4">
              <div class="flex items-center justify-between mb-3">
                <h3 class="font-medium flex items-center gap-2">
                  <Code2 class="w-5 h-5 text-green-400" />
                  {{ t('widget.simpleCode') }}
                </h3>
                <button
                  class="flex items-center gap-2 px-3 py-1.5 text-sm bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
                  @click="copyToClipboard(fullSnippet, 'simple')"
                >
                  <Check v-if="copied === 'simple'" class="w-4 h-4 text-green-400" />
                  <Copy v-else class="w-4 h-4" />
                  {{ t('common.copy') }}
                </button>
              </div>
              <pre class="bg-secondary/50 p-4 rounded-lg text-sm overflow-x-auto font-mono">{{ fullSnippet }}</pre>
              <p class="text-xs text-muted-foreground mt-2">
                {{ t('widget.simpleCodeDesc') }}
              </p>
            </div>

            <!-- Test URL -->
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium flex items-center gap-2 mb-3">
                <ExternalLink class="w-5 h-5 text-blue-400" />
                {{ t('widget.testWidget') }}
              </h3>
              <div class="flex items-center gap-2">
                <code class="flex-1 px-4 py-2 bg-secondary rounded-lg text-sm font-mono truncate">
                  {{ apiUrl }}/widget.js{{ selectedInstance.id !== 'default' ? '?instance=' + selectedInstance.id : '' }}
                </code>
                <a
                  :href="`${apiUrl}/widget.js${selectedInstance.id !== 'default' ? '?instance=' + selectedInstance.id : ''}`"
                  target="_blank"
                  class="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
                >
                  <ExternalLink class="w-4 h-4" />
                </a>
              </div>
            </div>

            <!-- Instructions -->
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-semibold flex items-center gap-2 mb-3">
                <BookOpen class="w-5 h-5 text-purple-400" />
                {{ t('widget.instructions') }}
              </h3>
              <div class="space-y-3 text-sm text-muted-foreground">
                <p>1. {{ t('widget.step1Desc') }}</p>
                <div class="bg-secondary/50 p-3 rounded-lg font-mono text-xs">
                  cloudflared tunnel --url http://localhost:8002
                </div>
                <p>2. {{ t('widget.step2Desc') }}</p>
                <p>3. {{ t('widget.step3Desc') }}</p>
                <p>4. {{ t('widget.step4Desc') }}</p>
              </div>
            </div>
          </template>

          <!-- Test Chat Tab -->
          <template v-if="activeTab === 'test'">
            <div class="bg-card rounded-xl border border-border flex flex-col" style="height: calc(100vh - 380px); min-height: 400px;">
              <!-- Chat Header -->
              <div class="p-4 border-b border-border flex items-center justify-between flex-shrink-0">
                <div class="flex items-center gap-3">
                  <MessageCircle class="w-5 h-5" :style="{ color: selectedInstance.primary_color }" />
                  <div>
                    <h3 class="font-medium">{{ t('widget.testChat') }}</h3>
                    <p class="text-xs text-muted-foreground">{{ t('widget.testChatDesc') }}</p>
                  </div>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-xs px-2 py-1 bg-secondary rounded-full text-muted-foreground">
                    {{ selectedInstance.llm_backend }}
                  </span>
                  <button
                    class="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
                    :title="t('widget.testClearChat')"
                    @click="clearTestChat"
                  >
                    <RotateCcw class="w-3.5 h-3.5" />
                    {{ t('widget.testClearChat') }}
                  </button>
                </div>
              </div>

              <!-- Messages -->
              <div ref="testChatContainer" class="flex-1 overflow-y-auto p-4 space-y-3">
                <!-- Greeting -->
                <div v-if="selectedInstance.greeting && testMessages.length === 0" class="flex justify-start">
                  <div
                    class="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-bl-sm text-sm"
                    :style="{ backgroundColor: selectedInstance.primary_color + '20', color: 'var(--foreground)' }"
                  >
                    {{ selectedInstance.greeting }}
                  </div>
                </div>

                <!-- Empty state -->
                <div v-if="testMessages.length === 0 && !selectedInstance.greeting" class="flex-1 flex items-center justify-center h-full">
                  <div class="text-center text-muted-foreground">
                    <MessageCircle class="w-10 h-10 mx-auto mb-2 opacity-40" />
                    <p class="text-sm">{{ t('widget.testNoMessages') }}</p>
                  </div>
                </div>

                <!-- Messages -->
                <template v-for="(msg, idx) in testMessages" :key="idx">
                  <!-- User message -->
                  <div v-if="msg.role === 'user'" class="flex justify-end">
                    <div
                      class="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-br-sm text-sm text-white"
                      :style="{ backgroundColor: selectedInstance.primary_color }"
                    >
                      {{ msg.content }}
                    </div>
                  </div>
                  <!-- Assistant message -->
                  <div v-else class="flex justify-start">
                    <div
                      class="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-bl-sm text-sm whitespace-pre-wrap"
                      :style="{ backgroundColor: selectedInstance.primary_color + '20', color: 'var(--foreground)' }"
                    >
                      <template v-if="msg.content">{{ msg.content }}</template>
                      <span v-else class="inline-flex gap-1">
                        <span class="w-1.5 h-1.5 rounded-full animate-bounce" :style="{ backgroundColor: selectedInstance.primary_color, animationDelay: '0ms' }" />
                        <span class="w-1.5 h-1.5 rounded-full animate-bounce" :style="{ backgroundColor: selectedInstance.primary_color, animationDelay: '150ms' }" />
                        <span class="w-1.5 h-1.5 rounded-full animate-bounce" :style="{ backgroundColor: selectedInstance.primary_color, animationDelay: '300ms' }" />
                      </span>
                    </div>
                  </div>
                </template>
              </div>

              <!-- Input -->
              <div class="p-4 border-t border-border flex-shrink-0">
                <div class="flex gap-2">
                  <textarea
                    v-model="testInput"
                    :placeholder="t('widget.testPlaceholder')"
                    class="flex-1 px-4 py-2.5 bg-secondary rounded-xl focus:outline-none focus:ring-2 focus:ring-primary resize-none text-sm"
                    rows="1"
                    :disabled="testStreaming"
                    @keydown="handleTestKeydown"
                  />
                  <button
                    class="px-4 py-2.5 rounded-xl text-white transition-colors disabled:opacity-50"
                    :style="{ backgroundColor: testInput.trim() && !testStreaming ? selectedInstance.primary_color : undefined }"
                    :class="{ 'bg-gray-500': !testInput.trim() || testStreaming }"
                    :disabled="!testInput.trim() || testStreaming"
                    @click="sendTestMessage"
                  >
                    <Loader2 v-if="testStreaming" class="w-5 h-5 animate-spin" />
                    <Send v-else class="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>
          </template>
        </div>
      </template>
    </div>

    <!-- Create/Edit Dialog -->
    <Teleport to="body">
      <div
        v-if="showCreateDialog || showEditDialog"
        class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        @click.self="showCreateDialog = false; showEditDialog = false"
      >
        <div class="bg-card rounded-xl border border-border w-full max-w-2xl max-h-[90vh] overflow-hidden">
          <div class="p-4 border-b border-border flex items-center justify-between">
            <h2 class="text-lg font-semibold">
              {{ showCreateDialog ? t('widget.createWidget') : t('widget.editWidget') }}
            </h2>
            <button
              class="p-1 hover:bg-secondary rounded"
              @click="showCreateDialog = false; showEditDialog = false"
            >
              <X class="w-5 h-5" />
            </button>
          </div>

          <div class="p-4 overflow-y-auto max-h-[calc(90vh-120px)] space-y-4">
            <!-- Basic Info -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.widgetName') }} *</label>
                <input
                  v-model="formData.name"
                  type="text"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                  :placeholder="t('widget.widgetNamePlaceholder')"
                />
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.widgetDescription') }}</label>
                <input
                  v-model="formData.description"
                  type="text"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>

            <!-- Tunnel URL -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('widget.tunnelUrl') }}</label>
              <input
                v-model="formData.tunnel_url"
                type="text"
                class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                :placeholder="t('widget.tunnelUrlPlaceholder')"
              />
              <p class="text-xs text-muted-foreground mt-1">{{ t('widget.tunnelUrlHint') }}</p>
            </div>

            <!-- Enabled -->
            <div class="flex items-center justify-between p-3 bg-secondary rounded-lg">
              <div>
                <h4 class="font-medium">{{ t('widget.enableWidget') }}</h4>
                <p class="text-sm text-muted-foreground">{{ t('widget.enableWidgetDesc') }}</p>
              </div>
              <button
                :class="[
                  'relative w-11 h-6 rounded-full transition-colors',
                  formData.enabled ? 'bg-green-500' : 'bg-gray-500'
                ]"
                @click="formData.enabled = !formData.enabled"
              >
                <span
:class="[
                  'absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform',
                  formData.enabled ? 'translate-x-5' : 'translate-x-0'
                ]" />
              </button>
            </div>

            <!-- Appearance -->
            <div class="space-y-4 p-4 bg-secondary/30 rounded-lg">
              <h4 class="font-medium">{{ t('widget.appearance') }}</h4>

              <!-- Title -->
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.widgetTitle') }}</label>
                <input
                  v-model="formData.title"
                  type="text"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <!-- Greeting -->
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.greeting') }}</label>
                <textarea
                  v-model="formData.greeting"
                  rows="2"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                />
              </div>

              <!-- Placeholder -->
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.placeholder') }}</label>
                <input
                  v-model="formData.placeholder"
                  type="text"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <!-- Placeholder Color -->
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.placeholderColor') }}</label>
                <div class="flex items-center gap-3">
                  <input
                    v-model="formData.placeholder_color"
                    type="color"
                    class="w-10 h-10 rounded cursor-pointer"
                  />
                  <input
                    v-model="formData.placeholder_color"
                    type="text"
                    class="w-32 px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
                    placeholder="#9ca3af"
                  />
                </div>
              </div>

              <!-- Placeholder Font -->
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.placeholderFont') }}</label>
                <input
                  v-model="formData.placeholder_font"
                  type="text"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="Arial, Roboto, ..."
                />
              </div>

              <!-- Color -->
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.primaryColor') }}</label>
                <div class="flex items-center gap-3">
                  <div class="flex gap-2">
                    <button
                      v-for="preset in colorPresets"
                      :key="preset.value"
                      :class="[
                        'w-8 h-8 rounded-full border-2 transition-all',
                        formData.primary_color === preset.value
                          ? 'border-foreground scale-110'
                          : 'border-transparent hover:scale-105'
                      ]"
                      :style="{ backgroundColor: preset.value }"
                      :title="preset.name"
                      @click="formData.primary_color = preset.value"
                    />
                  </div>
                  <input
                    v-model="formData.primary_color"
                    type="color"
                    class="w-10 h-10 rounded cursor-pointer"
                  />
                  <input
                    v-model="formData.primary_color"
                    type="text"
                    class="w-28 px-3 py-2 bg-secondary rounded-lg text-sm font-mono"
                  />
                </div>
              </div>

              <!-- Button Icon -->
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.buttonIcon') }}</label>
                <div class="flex gap-2 flex-wrap">
                  <button
                    v-for="icon in iconOptions"
                    :key="icon"
                    :class="[
                      'w-12 h-12 rounded-lg border-2 transition-all flex items-center justify-center',
                      formData.button_icon === icon
                        ? 'border-primary bg-primary/10 scale-110'
                        : 'border-border bg-secondary hover:bg-secondary/80 hover:scale-105'
                    ]"
                    :title="t(`widget.buttonIcons.${icon}`)"
                    @click="formData.button_icon = icon"
                    v-html="iconSvgs[icon]"
                  />
                </div>
              </div>

              <!-- Position -->
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.position') }}</label>
                <div class="flex gap-2">
                  <button
                    v-for="pos in ['left', 'right'] as const"
                    :key="pos"
                    :class="[
                      'px-4 py-2 rounded-lg transition-colors capitalize',
                      formData.position === pos
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-secondary hover:bg-secondary/80'
                    ]"
                    @click="formData.position = pos"
                  >
                    {{ t(`widget.positions.${pos}`) }}
                  </button>
                </div>
              </div>
            </div>

            <!-- Allowed Domains -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('widget.allowedDomainsList') }}</label>
              <div class="flex gap-2 mb-2">
                <input
                  v-model="newDomain"
                  type="text"
                  class="flex-1 px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                  :placeholder="t('widget.domainPlaceholder')"
                  @keydown.enter="addDomain"
                />
                <button
                  class="px-3 py-2 bg-primary text-primary-foreground rounded-lg"
                  @click="addDomain"
                >
                  <Plus class="w-4 h-4" />
                </button>
              </div>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="domain in formData.allowed_domains"
                  :key="domain"
                  class="flex items-center gap-1 px-2 py-1 bg-secondary rounded text-sm"
                >
                  {{ domain }}
                  <button class="text-muted-foreground hover:text-red-400" @click="removeDomain(domain)">
                    <X class="w-3 h-3" />
                  </button>
                </span>
                <span v-if="!formData.allowed_domains?.length" class="text-sm text-muted-foreground">
                  {{ t('widget.allDomainsAllowed') }}
                </span>
              </div>
            </div>

            <!-- AI Config -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.llmBackend') }}</label>
                <select
                  v-model="formData.llm_backend"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="vllm">vLLM</option>
                  <option
                    v-for="cp in cloudProviders"
                    :key="cp.id"
                    :value="`cloud:${cp.id}`"
                  >{{ cp.name }} ({{ cp.model_name }})</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.llmPersona') }}</label>
                <select
                  v-model="formData.llm_persona"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="anna">Анна</option>
                  <option value="marina">Марина</option>
                </select>
              </div>
            </div>

            <!-- TTS Config -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.ttsEngine') }}</label>
                <select
                  v-model="formData.tts_engine"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="xtts">XTTS v2</option>
                  <option value="piper">Piper</option>
                  <option value="openvoice">OpenVoice</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('widget.ttsVoice') }}</label>
                <select
                  v-model="formData.tts_voice"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="anna">Анна</option>
                  <option value="marina">Марина</option>
                </select>
              </div>
            </div>

            <!-- System Prompt -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('widget.systemPrompt') }}</label>
              <textarea
                v-model="formData.system_prompt"
                rows="3"
                class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                :placeholder="t('widget.systemPromptPlaceholder')"
              />
            </div>

            <!-- Rate Limiting -->
            <div class="space-y-3 p-4 bg-secondary/30 rounded-lg">
              <h4 class="font-medium text-sm">{{ t('widget.rateLimit') }}</h4>
              <p class="text-xs text-muted-foreground">{{ t('widget.rateLimitHint') }}</p>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('widget.rateLimitCount') }}</label>
                  <input
                    v-model.number="formData.rate_limit_count"
                    type="number"
                    min="0"
                    class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="5"
                  />
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('widget.rateLimitHours') }}</label>
                  <input
                    v-model.number="formData.rate_limit_hours"
                    type="number"
                    min="0"
                    class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="5"
                  />
                </div>
              </div>
            </div>
          </div>

          <div class="p-4 border-t border-border flex justify-end gap-2">
            <button
              class="px-4 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
              @click="showCreateDialog = false; showEditDialog = false"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              :disabled="createMutation.isPending.value || updateMutation.isPending.value || !formData.name"
              class="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
              @click="saveInstance"
            >
              <Loader2 v-if="createMutation.isPending.value || updateMutation.isPending.value" class="w-4 h-4 animate-spin" />
              <Check v-else class="w-4 h-4" />
              {{ t('common.save') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
