<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { useResponsive } from '@/composables/useResponsive'
import {
  Send,
  Bot,
  Power,
  Play,
  Square,
  RefreshCw,
  Users,
  Shield,
  MessageSquare,
  Settings2,
  Copy,
  Check,
  Plus,
  X,
  Loader2,
  ExternalLink,
  Eye,
  EyeOff,
  Trash2,
  BookOpen,
  Edit3,
  ChevronRight,
  Cpu,
  Volume2,
  MoreVertical,
  FileText,
  Zap,
  GripVertical,
  CreditCard,
  Star,
  TrendingUp,
  BarChart3,
  GitBranch,
  Wallet,
} from 'lucide-vue-next'
import { botInstancesApi, botSalesApi, llmApi, type BotInstance, type BotInstanceSession, type ActionButton, type PaymentProduct } from '@/api'
import type { AgentPrompt, QuizQuestion, Segment, FollowupRule, Testimonial, HardwareSpec, GithubConfig, FunnelData } from '@/api/bot-sales'
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
const showLogsDialog = ref(false)
const activeTab = ref<'settings' | 'users' | 'messages' | 'ai' | 'sessions' | 'buttons' | 'sales'>('settings')

// Button editing state
const showButtonEditDialog = ref(false)
const editingButtonIndex = ref(-1)
const editingButton = ref<Partial<ActionButton>>({
  id: '',
  label: '',
  icon: '',
  enabled: true,
  order: 0,
  llm_backend: '',
  system_prompt: '',
})

// Sales bot state
const salesSection = ref<'prompts' | 'quiz' | 'segments' | 'followups' | 'testimonials' | 'hardware' | 'abtests' | 'subscribers' | 'funnel' | 'github' | 'users'>('prompts')
const salesPrompts = ref<AgentPrompt[]>([])
const salesQuiz = ref<QuizQuestion[]>([])
const salesSegments = ref<Segment[]>([])
const salesFollowups = ref<FollowupRule[]>([])
const salesTestimonials = ref<Testimonial[]>([])
const salesHardware = ref<HardwareSpec[]>([])
const salesFunnel = ref<FunnelData>({})
const salesSubscriberCount = ref(0)
const salesGithub = ref<GithubConfig | null>(null)
const salesLoading = ref(false)

// Sales CRUD dialog state
const showSalesDialog = ref(false)
const salesDialogMode = ref<'create' | 'edit'>('create')
const salesDialogType = ref<'prompt' | 'quiz' | 'segment' | 'followup' | 'testimonial'>('prompt')
const salesEditingId = ref<number | null>(null)

// Sales form data
const salesForm = ref<Record<string, any>>({})

function openSalesCreate(type: 'prompt' | 'quiz' | 'segment' | 'followup' | 'testimonial') {
  salesDialogType.value = type
  salesDialogMode.value = 'create'
  salesEditingId.value = null
  if (type === 'prompt') {
    salesForm.value = { prompt_key: '', name: '', description: '', system_prompt: '', temperature: 0.7, max_tokens: 1024, enabled: true, order: 0 }
  } else if (type === 'quiz') {
    salesForm.value = { question_key: '', text: '', order: 1, enabled: true, options: [{ label: '', value: '', icon: '' }] }
  } else if (type === 'segment') {
    salesForm.value = { segment_key: '', name: '', description: '', path: 'custom', match_rules: '{}', priority: 0, agent_prompt_key: '', enabled: true }
  } else if (type === 'followup') {
    salesForm.value = { name: '', trigger: '', delay_hours: 24, segment_filter: '', message_template: '', max_sends: 2, enabled: true, order: 0 }
  } else if (type === 'testimonial') {
    salesForm.value = { text: '', author: '', rating: 5, enabled: true, order: 0 }
  }
  showSalesDialog.value = true
}

function openSalesEdit(type: 'prompt' | 'quiz' | 'segment' | 'followup' | 'testimonial', item: any) {
  salesDialogType.value = type
  salesDialogMode.value = 'edit'
  salesEditingId.value = item.id
  if (type === 'prompt') {
    salesForm.value = { prompt_key: item.prompt_key, name: item.name, description: item.description || '', system_prompt: item.system_prompt, temperature: item.temperature, max_tokens: item.max_tokens, enabled: item.enabled, order: item.order }
  } else if (type === 'quiz') {
    salesForm.value = { question_key: item.question_key, text: item.text, order: item.order, enabled: item.enabled, options: Array.isArray(item.options) ? [...item.options] : [] }
  } else if (type === 'segment') {
    salesForm.value = { segment_key: item.segment_key, name: item.name, description: item.description || '', path: item.path, match_rules: typeof item.match_rules === 'string' ? item.match_rules : JSON.stringify(item.match_rules || {}), priority: item.priority, agent_prompt_key: item.agent_prompt_key || '', enabled: item.enabled }
  } else if (type === 'followup') {
    salesForm.value = { name: item.name, trigger: item.trigger, delay_hours: item.delay_hours, segment_filter: item.segment_filter || '', message_template: item.message_template, max_sends: item.max_sends, enabled: item.enabled, order: item.order }
  } else if (type === 'testimonial') {
    salesForm.value = { text: item.text, author: item.author, rating: item.rating, enabled: item.enabled, order: item.order }
  }
  showSalesDialog.value = true
}

async function saveSalesItem() {
  if (!selectedInstanceId.value) return
  const id = selectedInstanceId.value
  const type = salesDialogType.value
  const data = { ...salesForm.value }

  // Parse match_rules from string to object for segments
  if (type === 'segment' && typeof data.match_rules === 'string') {
    try { data.match_rules = JSON.parse(data.match_rules) } catch { data.match_rules = {} }
  }

  try {
    if (salesDialogMode.value === 'create') {
      if (type === 'prompt') await botSalesApi.createPrompt(id, data)
      else if (type === 'quiz') await botSalesApi.createQuiz(id, data)
      else if (type === 'segment') await botSalesApi.createSegment(id, data)
      else if (type === 'followup') await botSalesApi.createFollowup(id, data)
      else if (type === 'testimonial') await botSalesApi.createTestimonial(id, data)
    } else {
      const eid = salesEditingId.value!
      if (type === 'prompt') await botSalesApi.updatePrompt(id, eid, data)
      else if (type === 'quiz') await botSalesApi.updateQuiz(id, eid, data)
      else if (type === 'segment') await botSalesApi.updateSegment(id, eid, data)
      else if (type === 'followup') await botSalesApi.updateFollowup(id, eid, data)
      else if (type === 'testimonial') await botSalesApi.updateTestimonial(id, eid, data)
    }
    toast.success(salesDialogMode.value === 'create' ? t('common.created') : t('common.saved'))
    showSalesDialog.value = false
    await loadSalesData()
  } catch (e) {
    toast.error(String(e))
  }
}

function addQuizOption() {
  if (!salesForm.value.options) salesForm.value.options = []
  salesForm.value.options.push({ label: '', value: '', icon: '' })
}

function removeQuizOption(index: number) {
  salesForm.value.options?.splice(index, 1)
}

async function loadSalesData(section?: string) {
  if (!selectedInstanceId.value) return
  const id = selectedInstanceId.value
  salesLoading.value = true
  try {
    const s = section || salesSection.value
    if (s === 'prompts') {
      const data = await botSalesApi.listPrompts(id)
      salesPrompts.value = data.prompts || []
    } else if (s === 'quiz') {
      const data = await botSalesApi.listQuiz(id)
      salesQuiz.value = data.questions || []
    } else if (s === 'segments') {
      const data = await botSalesApi.listSegments(id)
      salesSegments.value = data.segments || []
    } else if (s === 'followups') {
      const data = await botSalesApi.listFollowups(id)
      salesFollowups.value = data.rules || []
    } else if (s === 'testimonials') {
      const data = await botSalesApi.listTestimonials(id)
      salesTestimonials.value = data.testimonials || []
    } else if (s === 'hardware') {
      const data = await botSalesApi.listHardware(id)
      salesHardware.value = data.specs || []
    } else if (s === 'funnel') {
      const data = await botSalesApi.getFunnel(id)
      salesFunnel.value = data.funnel || {}
      const stats = await botSalesApi.getSubscriberStats(id)
      salesSubscriberCount.value = stats.stats?.total_active || 0
    } else if (s === 'subscribers') {
      const stats = await botSalesApi.getSubscriberStats(id)
      salesSubscriberCount.value = stats.stats?.total_active || 0
    } else if (s === 'github') {
      const data = await botSalesApi.getGithubConfig(id)
      salesGithub.value = data.config || null
    }
  } catch (e) {
    console.error('Failed to load sales data:', e)
  } finally {
    salesLoading.value = false
  }
}

async function deleteSalesItem(type: string, id: number) {
  if (!selectedInstanceId.value) return
  const iid = selectedInstanceId.value
  try {
    if (type === 'prompt') await botSalesApi.deletePrompt(iid, id)
    else if (type === 'quiz') await botSalesApi.deleteQuiz(iid, id)
    else if (type === 'segment') await botSalesApi.deleteSegment(iid, id)
    else if (type === 'followup') await botSalesApi.deleteFollowup(iid, id)
    else if (type === 'testimonial') await botSalesApi.deleteTestimonial(iid, id)
    else if (type === 'hardware') await botSalesApi.deleteHardware(iid, id)
    toast.success(t('common.deleted'))
    await loadSalesData()
  } catch (e) {
    toast.error(String(e))
  }
}

watch(salesSection, () => { loadSalesData() })

// Form state for create/edit
const formData = ref<Partial<BotInstance>>({
  name: '',
  description: '',
  enabled: true,
  bot_token: '',
  api_url: '',
  allowed_users: [],
  admin_users: [],
  welcome_message: 'Здравствуйте! Я AI-ассистент. Чем могу помочь?',
  unauthorized_message: 'Извините, у вас нет доступа к этому боту.',
  error_message: 'Произошла ошибка. Попробуйте позже.',
  typing_enabled: true,
  llm_backend: 'vllm',
  llm_persona: 'anna',
  system_prompt: '',
  tts_engine: 'xtts',
  tts_voice: 'anna',
  tts_preset: '',
  action_buttons: [],
  payment_enabled: false,
  yookassa_provider_token: '',
  stars_enabled: false,
  payment_products: [],
  payment_success_message: 'Спасибо за оплату! Ваш платёж успешно обработан.',
  yoomoney_client_id: '',
  yoomoney_client_secret: '',
  yoomoney_redirect_uri: '',
  yoomoney_configured: false,
  yoomoney_wallet_id: '',
  rate_limit_count: null,
  rate_limit_hours: null,
})

const newAllowedUser = ref('')
const newAdminUser = ref('')
const showToken = ref(false)
const showYookassaToken = ref(false)

// Queries
const { data: instancesData, isLoading: instancesLoading, refetch: refetchInstances } = useQuery({
  queryKey: ['bot-instances'],
  queryFn: () => botInstancesApi.list(),
  refetchInterval: 5000,
})

const instances = computed(() => instancesData.value?.instances || [])

const selectedInstance = computed(() =>
  instances.value.find(i => i.id === selectedInstanceId.value)
)

// Sessions query for selected instance
const { data: sessionsData, refetch: refetchSessions } = useQuery({
  queryKey: ['bot-instance-sessions', selectedInstanceId],
  queryFn: () => selectedInstanceId.value ? botInstancesApi.getSessions(selectedInstanceId.value) : Promise.resolve({ sessions: [] }),
  enabled: computed(() => !!selectedInstanceId.value),
})

// Cloud LLM providers query
const { data: llmProvidersData } = useQuery({
  queryKey: ['llm-providers-enabled'],
  queryFn: () => llmApi.getProviders(true),
})

// Available LLM options for dropdown
interface LlmOption {
  value: string
  label: string
  type: 'vllm' | 'cloud'
}

const availableLlmOptions = computed<LlmOption[]>(() => {
  const options: LlmOption[] = []

  // Add vLLM option (local)
  options.push({
    value: 'vllm',
    label: 'vLLM (Local)',
    type: 'vllm'
  })

  // Add enabled cloud providers
  const providers = llmProvidersData.value?.providers || []
  for (const provider of providers) {
    if (provider.enabled) {
      options.push({
        value: `cloud:${provider.id}`,
        label: `${provider.name} (${provider.model_name})`,
        type: 'cloud'
      })
    }
  }

  return options
})

const sessions = computed<BotInstanceSession[]>(() => sessionsData.value?.sessions || [])

// Logs query
const { data: logsData, refetch: refetchLogs } = useQuery({
  queryKey: ['bot-instance-logs', selectedInstanceId],
  queryFn: () => selectedInstanceId.value ? botInstancesApi.getLogs(selectedInstanceId.value, 200) : Promise.resolve({ logs: '' }),
  enabled: computed(() => showLogsDialog.value && !!selectedInstanceId.value),
})

// Mutations
const createMutation = useMutation({
  mutationFn: (data: Partial<BotInstance>) => botInstancesApi.create(data),
  onSuccess: (data) => {
    queryClient.invalidateQueries({ queryKey: ['bot-instances'] })
    toast.success(t('telegram.instanceCreated'))
    showCreateDialog.value = false
    selectedInstanceId.value = data.instance.id
  },
  onError: () => toast.error(t('telegram.createFailed')),
})

const updateMutation = useMutation({
  mutationFn: ({ id, data }: { id: string; data: Partial<BotInstance> }) =>
    botInstancesApi.update(id, data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['bot-instances'] })
    toast.success(t('telegram.saved'))
    showEditDialog.value = false
  },
  onError: () => toast.error(t('telegram.saveFailed')),
})

const deleteMutation = useMutation({
  mutationFn: (id: string) => botInstancesApi.delete(id),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['bot-instances'] })
    toast.success(t('telegram.instanceDeleted'))
    if (selectedInstanceId.value === deleteMutation.variables.value) {
      selectedInstanceId.value = null
    }
  },
  onError: () => toast.error(t('telegram.deleteFailed')),
})

const startMutation = useMutation({
  mutationFn: (id: string) => botInstancesApi.start(id),
  onSuccess: (data) => {
    refetchInstances()
    if (data.status === 'already_running') {
      toast.info(t('telegram.alreadyRunning'))
    } else {
      toast.success(t('telegram.started'))
    }
  },
  onError: (error: any) => toast.error(error?.response?.data?.detail || t('telegram.startFailed')),
})

const stopMutation = useMutation({
  mutationFn: (id: string) => botInstancesApi.stop(id),
  onSuccess: () => {
    refetchInstances()
    toast.success(t('telegram.stopped'))
  },
  onError: () => toast.error(t('telegram.stopFailed')),
})

const restartMutation = useMutation({
  mutationFn: (id: string) => botInstancesApi.restart(id),
  onSuccess: () => {
    refetchInstances()
    toast.success(t('telegram.restarted'))
  },
  onError: () => toast.error(t('telegram.restartFailed')),
})

const clearSessionsMutation = useMutation({
  mutationFn: (id: string) => botInstancesApi.clearSessions(id),
  onSuccess: () => {
    refetchSessions()
    toast.success(t('telegram.sessionsCleared'))
  },
})

// Functions
function openCreateDialog() {
  formData.value = {
    name: '',
    description: '',
    enabled: true,
    bot_token: '',
    api_url: '',
    allowed_users: [],
    admin_users: [],
    welcome_message: 'Здравствуйте! Я AI-ассистент. Чем могу помочь?',
    unauthorized_message: 'Извините, у вас нет доступа к этому боту.',
    error_message: 'Произошла ошибка. Попробуйте позже.',
    typing_enabled: true,
    llm_backend: 'vllm',
    llm_persona: 'anna',
    system_prompt: '',
    tts_engine: 'xtts',
    tts_voice: 'anna',
    tts_preset: '',
    action_buttons: [],
    payment_enabled: false,
    yookassa_provider_token: '',
    stars_enabled: false,
    payment_products: [],
    payment_success_message: 'Спасибо за оплату! Ваш платёж успешно обработан.',
    yoomoney_client_id: '',
    yoomoney_client_secret: '',
    yoomoney_redirect_uri: '',
    yoomoney_configured: false,
    yoomoney_wallet_id: '',
    rate_limit_count: null,
    rate_limit_hours: null,
  }
  showCreateDialog.value = true
}

async function openEditDialog(instance: BotInstance) {
  // Load instance with token for editing
  try {
    const response = await botInstancesApi.get(instance.id, true) // includeToken=true
    formData.value = { ...response.instance }
  } catch {
    // Fallback to instance without token
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

function confirmDelete(instance: BotInstance) {
  if (confirm(t('telegram.confirmDelete', { name: instance.name }))) {
    deleteMutation.mutate(instance.id)
  }
}

function addAllowedUser() {
  const userId = parseInt(newAllowedUser.value.trim())
  if (userId && !isNaN(userId) && !formData.value.allowed_users?.includes(userId)) {
    formData.value.allowed_users = [...(formData.value.allowed_users || []), userId]
    newAllowedUser.value = ''
  }
}

function removeAllowedUser(userId: number) {
  formData.value.allowed_users = formData.value.allowed_users?.filter(id => id !== userId) || []
}

function addAdminUser() {
  const userId = parseInt(newAdminUser.value.trim())
  if (userId && !isNaN(userId) && !formData.value.admin_users?.includes(userId)) {
    formData.value.admin_users = [...(formData.value.admin_users || []), userId]
    newAdminUser.value = ''
  }
}

function removeAdminUser(userId: number) {
  formData.value.admin_users = formData.value.admin_users?.filter(id => id !== userId) || []
}

function openLogs() {
  showLogsDialog.value = true
  refetchLogs()
}

// Button management functions
function openAddButtonDialog() {
  editingButtonIndex.value = -1
  const maxOrder = Math.max(0, ...(formData.value.action_buttons || []).map(b => b.order))
  editingButton.value = {
    id: `button-${Date.now()}`,
    label: '',
    icon: '',
    enabled: true,
    order: maxOrder + 1,
    llm_backend: '',
    system_prompt: '',
  }
  showButtonEditDialog.value = true
}

function openEditButtonDialog(index: number) {
  const button = formData.value.action_buttons?.[index]
  if (button) {
    editingButtonIndex.value = index
    editingButton.value = { ...button }
    showButtonEditDialog.value = true
  }
}

function saveButton() {
  if (!editingButton.value.label) return

  const buttons = [...(formData.value.action_buttons || [])]
  const buttonToSave: ActionButton = {
    id: editingButton.value.id || `button-${Date.now()}`,
    label: editingButton.value.label || '',
    icon: editingButton.value.icon || '',
    enabled: editingButton.value.enabled ?? true,
    order: editingButton.value.order ?? 0,
    llm_backend: editingButton.value.llm_backend || undefined,
    system_prompt: editingButton.value.system_prompt || undefined,
  }

  if (editingButtonIndex.value >= 0) {
    buttons[editingButtonIndex.value] = buttonToSave
  } else {
    buttons.push(buttonToSave)
  }

  // Sort by order
  buttons.sort((a, b) => a.order - b.order)
  formData.value.action_buttons = buttons
  showButtonEditDialog.value = false
  toast.success(t('telegram.buttonSaved'))
}

function deleteButton(index: number) {
  const button = formData.value.action_buttons?.[index]
  if (button && confirm(t('telegram.confirmDeleteButton', { label: button.label }))) {
    const buttons = [...(formData.value.action_buttons || [])]
    buttons.splice(index, 1)
    formData.value.action_buttons = buttons
    toast.success(t('telegram.buttonDeleted'))
  }
}

function addPaymentProduct() {
  const products = [...(formData.value.payment_products || [])]
  const id = `product_${Date.now()}`
  products.push({
    id,
    title: '',
    description: '',
    price_rub: 50000,
    price_stars: 100,
  })
  formData.value.payment_products = products
}

async function authorizeYoomoney() {
  const instanceId = formData.value.id
  if (!instanceId) return
  try {
    // First save the current form to persist client_id/secret/redirect_uri
    await saveInstance()
    const resp = await fetch(`/admin/telegram/instances/${instanceId}/yoomoney/auth-url`, {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('jwt_token') || ''}` },
    })
    const data = await resp.json()
    if (data.auth_url) {
      window.open(data.auth_url, 'yoomoney_auth', 'width=600,height=700')
      // Listen for callback message
      window.addEventListener('message', function handler(e: MessageEvent) {
        if (e.data?.type === 'yoomoney_connected') {
          formData.value.yoomoney_configured = true
          formData.value.yoomoney_wallet_id = e.data.wallet_id
          toast.success('YooMoney подключён!')
          refetchInstances()
          window.removeEventListener('message', handler)
        }
      })
    } else {
      toast.error(data.detail || 'Не удалось получить URL авторизации')
    }
  } catch (e) {
    toast.error('Ошибка авторизации YooMoney')
  }
}

async function disconnectYoomoney() {
  const instanceId = formData.value.id
  if (!instanceId) return
  if (!confirm('Отключить YooMoney?')) return
  try {
    await fetch(`/admin/telegram/instances/${instanceId}/yoomoney/disconnect`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${localStorage.getItem('jwt_token') || ''}` },
    })
    formData.value.yoomoney_configured = false
    formData.value.yoomoney_wallet_id = ''
    toast.success('YooMoney отключён')
    refetchInstances()
  } catch {
    toast.error('Ошибка отключения YooMoney')
  }
}

function toggleButtonEnabled(index: number) {
  const buttons = [...(formData.value.action_buttons || [])]
  if (buttons[index]) {
    buttons[index] = { ...buttons[index], enabled: !buttons[index].enabled }
    formData.value.action_buttons = buttons
  }
}

function moveButton(index: number, direction: 'up' | 'down') {
  const buttons = [...(formData.value.action_buttons || [])]
  const newIndex = direction === 'up' ? index - 1 : index + 1
  if (newIndex < 0 || newIndex >= buttons.length) return

  // Swap orders
  const tempOrder = buttons[index].order
  buttons[index] = { ...buttons[index], order: buttons[newIndex].order }
  buttons[newIndex] = { ...buttons[newIndex], order: tempOrder }

  // Sort by order
  buttons.sort((a, b) => a.order - b.order)
  formData.value.action_buttons = buttons
}

// Auto-select first instance
watch(instances, (newInstances) => {
  if (!selectedInstanceId.value && newInstances.length > 0) {
    selectedInstanceId.value = newInstances[0].id
  }
}, { immediate: true })
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
            <Send class="w-5 h-5 text-[#0088cc]" />
            {{ t('telegram.bots') }}
          </h2>
          <button
            class="p-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
            :title="t('telegram.createBot')"
            @click="openCreateDialog"
          >
            <Plus class="w-4 h-4" />
          </button>
        </div>
        <p class="text-xs text-muted-foreground">{{ t('telegram.instancesDesc') }}</p>
      </div>

      <!-- Instance List -->
      <div class="flex-1 overflow-y-auto p-2">
        <div v-if="instancesLoading" class="flex items-center justify-center p-8">
          <Loader2 class="w-6 h-6 animate-spin text-primary" />
        </div>

        <div v-else-if="instances.length === 0" class="text-center p-8 text-muted-foreground">
          <Bot class="w-12 h-12 mx-auto mb-2 opacity-50" />
          <p>{{ t('telegram.noInstances') }}</p>
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
                  instance.running ? 'bg-green-400 animate-pulse' : 'bg-gray-400'
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
          <Bot class="w-16 h-16 mx-auto mb-4 text-muted-foreground/50" />
          <p class="text-muted-foreground">{{ t('telegram.selectInstance') }}</p>
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
          {{ t('telegram.bots') }}
        </button>

        <!-- Instance Header -->
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            <h1 class="text-2xl font-bold flex items-center gap-2">
              {{ selectedInstance.name }}
              <span
:class="[
                'px-2 py-0.5 text-xs rounded-full',
                selectedInstance.running
                  ? 'bg-green-500/20 text-green-400'
                  : 'bg-gray-500/20 text-gray-400'
              ]">
                {{ selectedInstance.running ? t('telegram.running') : t('telegram.stopped') }}
              </span>
            </h1>
            <p v-if="selectedInstance.description" class="text-muted-foreground mt-1">
              {{ selectedInstance.description }}
            </p>
          </div>
          <div class="flex items-center gap-2 flex-wrap">
            <!-- Control buttons -->
            <button
              v-if="!selectedInstance.running"
              :disabled="startMutation.isPending.value || !selectedInstance.bot_token_masked || !selectedInstance.enabled"
              class="flex items-center gap-2 px-3 py-2 bg-green-500/20 text-green-400 rounded-lg hover:bg-green-500/30 disabled:opacity-50 transition-colors"
              @click="startMutation.mutate(selectedInstance.id)"
            >
              <Loader2 v-if="startMutation.isPending.value" class="w-4 h-4 animate-spin" />
              <Play v-else class="w-4 h-4" />
              {{ t('telegram.start') }}
            </button>
            <button
              v-else
              :disabled="stopMutation.isPending.value"
              class="flex items-center gap-2 px-3 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 disabled:opacity-50 transition-colors"
              @click="stopMutation.mutate(selectedInstance.id)"
            >
              <Loader2 v-if="stopMutation.isPending.value" class="w-4 h-4 animate-spin" />
              <Square v-else class="w-4 h-4" />
              {{ t('telegram.stop') }}
            </button>
            <button
              :disabled="restartMutation.isPending.value || !selectedInstance.running"
              class="p-2 bg-secondary rounded-lg hover:bg-secondary/80 disabled:opacity-50 transition-colors"
              :title="t('telegram.restart')"
              @click="restartMutation.mutate(selectedInstance.id)"
            >
              <Loader2 v-if="restartMutation.isPending.value" class="w-4 h-4 animate-spin" />
              <RefreshCw v-else class="w-4 h-4" />
            </button>
            <button
              class="p-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
              :title="t('telegram.viewLogs')"
              @click="openLogs"
            >
              <FileText class="w-4 h-4" />
            </button>
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
              <Bot class="w-4 h-4" />
              <span class="text-sm">{{ t('telegram.status') }}</span>
            </div>
            <p :class="['text-lg font-semibold', selectedInstance.running ? 'text-green-400' : 'text-gray-400']">
              {{ selectedInstance.running ? t('telegram.online') : t('telegram.offline') }}
            </p>
          </div>
          <div class="bg-card rounded-xl border border-border p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <MessageSquare class="w-4 h-4" />
              <span class="text-sm">{{ t('telegram.sessions') }}</span>
            </div>
            <p class="text-lg font-semibold">{{ sessions.length }}</p>
          </div>
          <div class="bg-card rounded-xl border border-border p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <Users class="w-4 h-4" />
              <span class="text-sm">{{ t('telegram.allowedUsers') }}</span>
            </div>
            <p class="text-lg font-semibold">
              {{ selectedInstance.allowed_users?.length || t('telegram.allUsers') }}
            </p>
          </div>
          <div class="bg-card rounded-xl border border-border p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <Cpu class="w-4 h-4" />
              <span class="text-sm">{{ t('telegram.aiBackend') }}</span>
            </div>
            <p class="text-lg font-semibold">{{ selectedInstance.llm_backend }}</p>
          </div>
        </div>

        <!-- Tabs -->
        <div class="flex gap-1 bg-secondary/50 p-1 rounded-lg w-fit mb-6 tab-bar-scroll max-w-full whitespace-nowrap">
          <button
            v-for="tab in ['settings', 'users', 'messages', 'ai', 'buttons', 'sessions', 'sales'] as const"
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
              <Users v-else-if="tab === 'users'" class="w-4 h-4" />
              <MessageSquare v-else-if="tab === 'messages'" class="w-4 h-4" />
              <Cpu v-else-if="tab === 'ai'" class="w-4 h-4" />
              <Zap v-else-if="tab === 'buttons'" class="w-4 h-4" />
              <TrendingUp v-else-if="tab === 'sales'" class="w-4 h-4" />
              <BookOpen v-else class="w-4 h-4" />
              {{ t(`telegram.tabs.${tab}`) }}
            </span>
          </button>
        </div>

        <!-- Tab Content -->
        <div class="flex-1 overflow-y-auto space-y-4">
          <!-- Settings Tab -->
          <template v-if="activeTab === 'settings'">
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('telegram.botToken') }}</h3>
              <p class="text-sm text-muted-foreground mb-2">{{ t('telegram.botTokenDesc') }}</p>
              <code class="block px-3 py-2 bg-secondary rounded-lg font-mono text-sm">
                {{ selectedInstance.bot_token_masked || t('telegram.noToken') }}
              </code>
            </div>
            <div class="bg-card rounded-xl border border-border p-4">
              <div class="flex items-center justify-between">
                <div>
                  <h3 class="font-medium">{{ t('telegram.typingIndicator') }}</h3>
                  <p class="text-sm text-muted-foreground">{{ t('telegram.typingIndicatorDesc') }}</p>
                </div>
                <span :class="['px-2 py-1 rounded-full text-sm', selectedInstance.typing_enabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400']">
                  {{ selectedInstance.typing_enabled ? t('common.enabled') : t('common.disabled') }}
                </span>
              </div>
            </div>
          </template>

          <!-- Users Tab -->
          <template v-if="activeTab === 'users'">
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('telegram.allowedUsersList') }}</h3>
              <p class="text-sm text-muted-foreground mb-3">{{ t('telegram.allowedUsersDesc') }}</p>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="userId in selectedInstance.allowed_users"
                  :key="userId"
                  class="px-3 py-1.5 bg-secondary rounded-full text-sm font-mono"
                >
                  {{ userId }}
                </span>
                <span v-if="!selectedInstance.allowed_users?.length" class="text-sm text-muted-foreground">
                  {{ t('telegram.allUsersAllowed') }}
                </span>
              </div>
            </div>
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('telegram.adminUsersList') }}</h3>
              <p class="text-sm text-muted-foreground mb-3">{{ t('telegram.adminUsersDesc') }}</p>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="userId in selectedInstance.admin_users"
                  :key="userId"
                  class="flex items-center gap-1 px-3 py-1.5 bg-orange-500/20 text-orange-400 rounded-full text-sm font-mono"
                >
                  <Shield class="w-3 h-3" />
                  {{ userId }}
                </span>
                <span v-if="!selectedInstance.admin_users?.length" class="text-sm text-muted-foreground">
                  {{ t('telegram.noAdmins') }}
                </span>
              </div>
            </div>
          </template>

          <!-- Messages Tab -->
          <template v-if="activeTab === 'messages'">
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('telegram.welcomeMessage') }}</h3>
              <p class="text-sm bg-secondary rounded-lg p-3">{{ selectedInstance.welcome_message }}</p>
            </div>
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('telegram.unauthorizedMessage') }}</h3>
              <p class="text-sm bg-secondary rounded-lg p-3">{{ selectedInstance.unauthorized_message }}</p>
            </div>
            <div class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('telegram.errorMessage') }}</h3>
              <p class="text-sm bg-secondary rounded-lg p-3">{{ selectedInstance.error_message }}</p>
            </div>
          </template>

          <!-- AI Tab -->
          <template v-if="activeTab === 'ai'">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="bg-card rounded-xl border border-border p-4">
                <h3 class="font-medium mb-2">{{ t('telegram.llmBackend') }}</h3>
                <p class="text-lg font-semibold">{{ selectedInstance.llm_backend }}</p>
              </div>
              <div class="bg-card rounded-xl border border-border p-4">
                <h3 class="font-medium mb-2">{{ t('telegram.llmPersona') }}</h3>
                <p class="text-lg font-semibold">{{ selectedInstance.llm_persona }}</p>
              </div>
              <div class="bg-card rounded-xl border border-border p-4">
                <h3 class="font-medium mb-2">{{ t('telegram.ttsEngine') }}</h3>
                <p class="text-lg font-semibold">{{ selectedInstance.tts_engine }}</p>
              </div>
              <div class="bg-card rounded-xl border border-border p-4">
                <h3 class="font-medium mb-2">{{ t('telegram.ttsVoice') }}</h3>
                <p class="text-lg font-semibold">{{ selectedInstance.tts_voice }}</p>
              </div>
            </div>
            <div v-if="selectedInstance.system_prompt" class="bg-card rounded-xl border border-border p-4">
              <h3 class="font-medium mb-2">{{ t('telegram.systemPrompt') }}</h3>
              <p class="text-sm bg-secondary rounded-lg p-3 whitespace-pre-wrap">{{ selectedInstance.system_prompt }}</p>
            </div>
          </template>

          <!-- Buttons Tab -->
          <template v-if="activeTab === 'buttons'">
            <div class="bg-card rounded-xl border border-border p-4">
              <div class="flex items-center justify-between mb-4">
                <div>
                  <h3 class="font-medium">{{ t('telegram.actionButtons') }}</h3>
                  <p class="text-sm text-muted-foreground">{{ t('telegram.actionButtonsDesc') }}</p>
                </div>
              </div>

              <div v-if="!selectedInstance.action_buttons?.length" class="text-center py-8 text-muted-foreground">
                <Zap class="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>{{ t('telegram.noButtons') }}</p>
              </div>

              <div v-else class="space-y-2">
                <div
                  v-for="(button, index) in selectedInstance.action_buttons"
                  :key="button.id"
                  class="flex items-center gap-3 p-3 bg-secondary rounded-lg"
                >
                  <span class="text-xl w-8 text-center">{{ button.icon || '🔘' }}</span>
                  <div class="flex-1 min-w-0">
                    <p class="font-medium truncate">{{ button.label }}</p>
                    <p class="text-xs text-muted-foreground truncate">
                      {{ button.llm_backend || t('telegram.useDefaultBackend') }}
                    </p>
                  </div>
                  <span
:class="[
                    'px-2 py-0.5 text-xs rounded-full',
                    button.enabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'
                  ]">
                    {{ button.enabled ? t('common.enabled') : t('common.disabled') }}
                  </span>
                </div>
              </div>
            </div>
          </template>

          <!-- Sessions Tab -->
          <template v-if="activeTab === 'sessions'">
            <div class="bg-card rounded-xl border border-border p-4">
              <div class="flex items-center justify-between mb-4">
                <h3 class="font-medium">{{ t('telegram.activeSessions') }} ({{ sessions.length }})</h3>
                <button
                  :disabled="clearSessionsMutation.isPending.value || sessions.length === 0"
                  class="flex items-center gap-2 px-3 py-1.5 text-sm bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 disabled:opacity-50 transition-colors"
                  @click="clearSessionsMutation.mutate(selectedInstance.id)"
                >
                  <Trash2 class="w-4 h-4" />
                  {{ t('telegram.clearSessions') }}
                </button>
              </div>
              <div v-if="sessions.length === 0" class="text-center py-8 text-muted-foreground">
                {{ t('telegram.noSessions') }}
              </div>
              <div v-else class="space-y-2">
                <div
                  v-for="session in sessions"
                  :key="session.user_id"
                  class="flex items-center justify-between p-3 bg-secondary rounded-lg"
                >
                  <div>
                    <p class="font-medium">
                      {{ session.first_name || session.username || `User ${session.user_id}` }}
                    </p>
                    <p class="text-sm text-muted-foreground">
                      ID: {{ session.user_id }}
                      <span v-if="session.username">• @{{ session.username }}</span>
                    </p>
                  </div>
                  <p class="text-xs text-muted-foreground">{{ session.chat_session_id }}</p>
                </div>
              </div>
            </div>
          </template>

          <!-- Sales Funnel Tab -->
          <template v-if="activeTab === 'sales'">
            <!-- Sub-navigation -->
            <div class="flex flex-wrap gap-1 mb-4">
              <button
                v-for="sec in ['prompts','quiz','segments','followups','testimonials','hardware','funnel','subscribers','github'] as const"
                :key="sec"
                :class="[
                  'px-3 py-1 text-xs rounded-md transition-colors',
                  salesSection === sec
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary text-muted-foreground hover:text-foreground'
                ]"
                @click="salesSection = sec; loadSalesData(sec)"
              >
                {{ t(`telegram.sales.${sec}`) }}
              </button>
            </div>

            <div v-if="salesLoading" class="flex items-center justify-center py-8">
              <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
            </div>

            <!-- Prompts Section -->
            <template v-else-if="salesSection === 'prompts'">
              <div class="bg-card rounded-xl border border-border p-4">
                <div class="flex items-center justify-between mb-4">
                  <div>
                    <h3 class="font-medium">{{ t('telegram.sales.prompts') }}</h3>
                    <p class="text-xs text-muted-foreground">{{ t('telegram.sales.promptsDesc') }}</p>
                  </div>
                  <button class="flex items-center gap-1 px-2 py-1 text-xs bg-primary text-primary-foreground rounded-lg hover:bg-primary/90" @click="openSalesCreate('prompt')">
                    <Plus class="w-3 h-3" />
                    {{ t('common.create') }}
                  </button>
                </div>
                <div v-if="salesPrompts.length === 0" class="text-center py-6 text-muted-foreground text-sm">
                  {{ t('telegram.sales.noData') }}
                </div>
                <div v-else class="space-y-2">
                  <div
v-for="p in salesPrompts" :key="p.id"
                    class="flex items-center justify-between p-3 bg-secondary rounded-lg">
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center gap-2">
                        <span class="font-medium text-sm">{{ p.name }}</span>
                        <span class="text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary">{{ p.prompt_key }}</span>
                        <span v-if="!p.enabled" class="text-xs px-1.5 py-0.5 rounded bg-red-500/10 text-red-400">OFF</span>
                      </div>
                      <p class="text-xs text-muted-foreground mt-1 truncate">{{ p.system_prompt?.slice(0, 120) }}...</p>
                      <div class="flex gap-3 mt-1 text-xs text-muted-foreground">
                        <span>T={{ p.temperature }}</span>
                        <span>max={{ p.max_tokens }}</span>
                      </div>
                    </div>
                    <button class="p-1 text-muted-foreground hover:text-foreground hover:bg-secondary rounded transition-colors" @click="openSalesEdit('prompt', p)">
                      <Edit3 class="w-4 h-4" />
                    </button>
                    <button
class="p-1 text-red-400 hover:bg-red-500/20 rounded transition-colors"
                      @click="deleteSalesItem('prompt', p.id)">
                      <Trash2 class="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            </template>

            <!-- Quiz Section -->
            <template v-else-if="salesSection === 'quiz'">
              <div class="bg-card rounded-xl border border-border p-4">
                <div class="flex items-center justify-between mb-4">
                  <div>
                    <h3 class="font-medium">{{ t('telegram.sales.quiz') }}</h3>
                    <p class="text-xs text-muted-foreground">{{ t('telegram.sales.quizDesc') }}</p>
                  </div>
                  <button class="flex items-center gap-1 px-2 py-1 text-xs bg-primary text-primary-foreground rounded-lg hover:bg-primary/90" @click="openSalesCreate('quiz')">
                    <Plus class="w-3 h-3" />
                    {{ t('common.create') }}
                  </button>
                </div>
                <div v-if="salesQuiz.length === 0" class="text-center py-6 text-muted-foreground text-sm">
                  {{ t('telegram.sales.noData') }}
                </div>
                <div v-else class="space-y-3">
                  <div
v-for="q in salesQuiz" :key="q.id"
                    class="p-3 bg-secondary rounded-lg">
                    <div class="flex items-center justify-between">
                      <div class="flex items-center gap-2">
                        <span class="text-xs font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary">#{{ q.order }}</span>
                        <span class="font-medium text-sm">{{ q.question_key }}</span>
                        <span v-if="!q.enabled" class="text-xs text-red-400">OFF</span>
                      </div>
                      <button class="p-1 text-muted-foreground hover:text-foreground hover:bg-secondary rounded transition-colors" @click="openSalesEdit('quiz', q)">
                        <Edit3 class="w-4 h-4" />
                      </button>
                      <button
class="p-1 text-red-400 hover:bg-red-500/20 rounded transition-colors"
                        @click="deleteSalesItem('quiz', q.id)">
                        <Trash2 class="w-4 h-4" />
                      </button>
                    </div>
                    <p class="text-sm mt-2 whitespace-pre-line">{{ q.text }}</p>
                    <div class="flex flex-wrap gap-1 mt-2">
                      <span
v-for="(opt, i) in (Array.isArray(q.options) ? q.options : [])" :key="i"
                        class="text-xs px-2 py-0.5 rounded-full bg-background border border-border">
                        {{ opt.icon || '' }} {{ opt.label }} ({{ opt.value }})
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <!-- Segments Section -->
            <template v-else-if="salesSection === 'segments'">
              <div class="bg-card rounded-xl border border-border p-4">
                <div class="flex items-center justify-between mb-4">
                  <div>
                    <h3 class="font-medium">{{ t('telegram.sales.segments') }}</h3>
                    <p class="text-xs text-muted-foreground">{{ t('telegram.sales.segmentsDesc') }}</p>
                  </div>
                  <button class="flex items-center gap-1 px-2 py-1 text-xs bg-primary text-primary-foreground rounded-lg hover:bg-primary/90" @click="openSalesCreate('segment')">
                    <Plus class="w-3 h-3" />
                    {{ t('common.create') }}
                  </button>
                </div>
                <div v-if="salesSegments.length === 0" class="text-center py-6 text-muted-foreground text-sm">
                  {{ t('telegram.sales.noData') }}
                </div>
                <div v-else class="space-y-2">
                  <div
v-for="s in salesSegments" :key="s.id"
                    class="flex items-center justify-between p-3 bg-secondary rounded-lg">
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center gap-2">
                        <span class="font-medium text-sm">{{ s.name }}</span>
                        <span
class="text-xs px-1.5 py-0.5 rounded"
                          :class="s.path === 'diy' ? 'bg-green-500/10 text-green-400' : s.path === 'basic' ? 'bg-blue-500/10 text-blue-400' : 'bg-purple-500/10 text-purple-400'">
                          {{ s.path }}
                        </span>
                        <span class="text-xs text-muted-foreground">P{{ s.priority }}</span>
                      </div>
                      <p class="text-xs text-muted-foreground mt-1">
                        Rules: {{ JSON.stringify(s.match_rules) }}
                        <span v-if="s.agent_prompt_key"> | Prompt: {{ s.agent_prompt_key }}</span>
                      </p>
                    </div>
                    <button class="p-1 text-muted-foreground hover:text-foreground hover:bg-secondary rounded transition-colors" @click="openSalesEdit('segment', s)">
                      <Edit3 class="w-4 h-4" />
                    </button>
                    <button
class="p-1 text-red-400 hover:bg-red-500/20 rounded transition-colors"
                      @click="deleteSalesItem('segment', s.id)">
                      <Trash2 class="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            </template>

            <!-- Followups Section -->
            <template v-else-if="salesSection === 'followups'">
              <div class="bg-card rounded-xl border border-border p-4">
                <div class="flex items-center justify-between mb-4">
                  <div>
                    <h3 class="font-medium">{{ t('telegram.sales.followups') }}</h3>
                    <p class="text-xs text-muted-foreground">{{ t('telegram.sales.followupsDesc') }}</p>
                  </div>
                  <button class="flex items-center gap-1 px-2 py-1 text-xs bg-primary text-primary-foreground rounded-lg hover:bg-primary/90" @click="openSalesCreate('followup')">
                    <Plus class="w-3 h-3" />
                    {{ t('common.create') }}
                  </button>
                </div>
                <div v-if="salesFollowups.length === 0" class="text-center py-6 text-muted-foreground text-sm">
                  {{ t('telegram.sales.noData') }}
                </div>
                <div v-else class="space-y-2">
                  <div
v-for="r in salesFollowups" :key="r.id"
                    class="p-3 bg-secondary rounded-lg">
                    <div class="flex items-center justify-between">
                      <div class="flex items-center gap-2">
                        <span class="font-medium text-sm">{{ r.name }}</span>
                        <span class="text-xs px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-400">{{ r.trigger }}</span>
                        <span class="text-xs text-muted-foreground">{{ r.delay_hours }}h</span>
                      </div>
                      <button class="p-1 text-muted-foreground hover:text-foreground hover:bg-secondary rounded transition-colors" @click="openSalesEdit('followup', r)">
                        <Edit3 class="w-4 h-4" />
                      </button>
                      <button
class="p-1 text-red-400 hover:bg-red-500/20 rounded transition-colors"
                        @click="deleteSalesItem('followup', r.id)">
                        <Trash2 class="w-4 h-4" />
                      </button>
                    </div>
                    <p class="text-xs text-muted-foreground mt-2 whitespace-pre-line">{{ r.message_template }}</p>
                  </div>
                </div>
              </div>
            </template>

            <!-- Testimonials Section -->
            <template v-else-if="salesSection === 'testimonials'">
              <div class="bg-card rounded-xl border border-border p-4">
                <div class="flex items-center justify-between mb-4">
                  <div>
                    <h3 class="font-medium">{{ t('telegram.sales.testimonials') }}</h3>
                    <p class="text-xs text-muted-foreground">{{ t('telegram.sales.testimonialsDesc') }}</p>
                  </div>
                  <button class="flex items-center gap-1 px-2 py-1 text-xs bg-primary text-primary-foreground rounded-lg hover:bg-primary/90" @click="openSalesCreate('testimonial')">
                    <Plus class="w-3 h-3" />
                    {{ t('common.create') }}
                  </button>
                </div>
                <div v-if="salesTestimonials.length === 0" class="text-center py-6 text-muted-foreground text-sm">
                  {{ t('telegram.sales.noData') }}
                </div>
                <div v-else class="space-y-2">
                  <div
v-for="t2 in salesTestimonials" :key="t2.id"
                    class="p-3 bg-secondary rounded-lg">
                    <div class="flex items-center justify-between">
                      <div class="flex items-center gap-1">
                        <Star v-for="n in t2.rating" :key="n" class="w-3 h-3 text-yellow-400 fill-yellow-400" />
                      </div>
                      <button class="p-1 text-muted-foreground hover:text-foreground hover:bg-secondary rounded transition-colors" @click="openSalesEdit('testimonial', t2)">
                        <Edit3 class="w-4 h-4" />
                      </button>
                      <button
class="p-1 text-red-400 hover:bg-red-500/20 rounded transition-colors"
                        @click="deleteSalesItem('testimonial', t2.id)">
                        <Trash2 class="w-4 h-4" />
                      </button>
                    </div>
                    <p class="text-sm mt-2 italic">"{{ t2.text }}"</p>
                    <p class="text-xs text-muted-foreground mt-1">— {{ t2.author }}</p>
                  </div>
                </div>
              </div>
            </template>

            <!-- Hardware Section -->
            <template v-else-if="salesSection === 'hardware'">
              <div class="bg-card rounded-xl border border-border p-4">
                <div class="flex items-center justify-between mb-4">
                  <div>
                    <h3 class="font-medium">{{ t('telegram.sales.hardware') }}</h3>
                    <p class="text-xs text-muted-foreground">{{ t('telegram.sales.hardwareDesc') }}</p>
                  </div>
                </div>
                <div v-if="salesHardware.length === 0" class="text-center py-6 text-muted-foreground text-sm">
                  {{ t('telegram.sales.noData') }}
                </div>
                <div v-else class="overflow-x-auto">
                  <table class="w-full text-sm">
                    <thead>
                      <tr class="text-xs text-muted-foreground border-b border-border">
                        <th class="text-left p-2">GPU</th>
                        <th class="text-center p-2">VRAM</th>
                        <th class="text-left p-2">LLM</th>
                        <th class="text-left p-2">TTS</th>
                        <th class="text-center p-2">Quality</th>
                        <th class="text-left p-2">Speed</th>
                        <th class="p-2"></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="h in salesHardware" :key="h.id" class="border-b border-border/50">
                        <td class="p-2 font-medium">{{ h.gpu_name }}</td>
                        <td class="p-2 text-center">{{ h.gpu_vram_gb }}GB</td>
                        <td class="p-2">{{ h.recommended_llm }}</td>
                        <td class="p-2">{{ h.recommended_tts }}</td>
                        <td class="p-2 text-center">
                          <span v-for="n in h.quality_stars" :key="n" class="text-yellow-400">*</span>
                        </td>
                        <td class="p-2 text-muted-foreground">{{ h.speed_note || '-' }}</td>
                        <td class="p-2">
                          <button
class="p-1 text-red-400 hover:bg-red-500/20 rounded transition-colors"
                            @click="deleteSalesItem('hardware', h.id)">
                            <Trash2 class="w-3 h-3" />
                          </button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </template>

            <!-- Funnel Section -->
            <template v-else-if="salesSection === 'funnel'">
              <div class="bg-card rounded-xl border border-border p-4">
                <div class="flex items-center justify-between mb-4">
                  <div>
                    <h3 class="font-medium flex items-center gap-2">
                      <BarChart3 class="w-4 h-4" />
                      {{ t('telegram.sales.funnel') }}
                    </h3>
                    <p class="text-xs text-muted-foreground">{{ t('telegram.sales.funnelDesc') }}</p>
                  </div>
                  <span class="text-xs text-muted-foreground">30 days</span>
                </div>
                <div v-if="Object.keys(salesFunnel).length === 0" class="text-center py-6 text-muted-foreground text-sm">
                  {{ t('telegram.sales.noData') }}
                </div>
                <div v-else class="space-y-2">
                  <div
v-for="(count, stage) in salesFunnel" :key="stage"
                    class="flex items-center gap-3 p-2">
                    <span class="text-xs font-mono w-32 text-muted-foreground">{{ stage }}</span>
                    <div class="flex-1 bg-secondary rounded-full h-5 overflow-hidden">
                      <div
class="bg-primary h-full rounded-full transition-all"
                        :style="{ width: `${Math.min(100, (Number(count) / Math.max(1, Number(Object.values(salesFunnel)[0]))) * 100)}%` }">
                      </div>
                    </div>
                    <span class="text-sm font-medium w-12 text-right">{{ count }}</span>
                  </div>
                </div>
                <div class="mt-4 pt-4 border-t border-border flex items-center gap-4 text-sm">
                  <span class="text-muted-foreground">Subscribers:</span>
                  <span class="font-medium">{{ salesSubscriberCount }}</span>
                </div>
              </div>
            </template>

            <!-- Subscribers Section -->
            <template v-else-if="salesSection === 'subscribers'">
              <div class="bg-card rounded-xl border border-border p-4">
                <h3 class="font-medium mb-4">{{ t('telegram.sales.subscribers') }}</h3>
                <div class="text-center py-8">
                  <p class="text-3xl font-bold">{{ salesSubscriberCount }}</p>
                  <p class="text-sm text-muted-foreground mt-1">{{ t('telegram.sales.subscribersDesc') }}</p>
                </div>
              </div>
            </template>

            <!-- GitHub Config Section -->
            <template v-else-if="salesSection === 'github'">
              <div class="bg-card rounded-xl border border-border p-4">
                <div class="flex items-center gap-2 mb-4">
                  <GitBranch class="w-4 h-4" />
                  <h3 class="font-medium">{{ t('telegram.sales.github') }}</h3>
                </div>
                <p class="text-xs text-muted-foreground mb-4">{{ t('telegram.sales.githubDesc') }}</p>
                <div v-if="!salesGithub" class="text-center py-6 text-muted-foreground text-sm">
                  GitHub webhook not configured
                </div>
                <div v-else class="space-y-3 text-sm">
                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label class="text-xs text-muted-foreground">Repo Owner</label>
                      <p class="font-medium">{{ salesGithub.repo_owner }}</p>
                    </div>
                    <div>
                      <label class="text-xs text-muted-foreground">Repo Name</label>
                      <p class="font-medium">{{ salesGithub.repo_name }}</p>
                    </div>
                  </div>
                  <div class="flex gap-4">
                    <div class="flex items-center gap-2">
                      <div :class="salesGithub.comment_enabled ? 'bg-green-500' : 'bg-gray-500'" class="w-2 h-2 rounded-full"></div>
                      <span>PR Comments</span>
                    </div>
                    <div class="flex items-center gap-2">
                      <div :class="salesGithub.broadcast_enabled ? 'bg-green-500' : 'bg-gray-500'" class="w-2 h-2 rounded-full"></div>
                      <span>Broadcast</span>
                    </div>
                  </div>
                  <div>
                    <label class="text-xs text-muted-foreground">Events</label>
                    <div class="flex gap-1 mt-1">
                      <span
v-for="ev in (salesGithub.events || [])" :key="ev"
                        class="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">{{ ev }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
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
              {{ showCreateDialog ? t('telegram.createBot') : t('telegram.editBot') }}
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
                <label class="block text-sm font-medium mb-1">{{ t('telegram.botName') }} *</label>
                <input
                  v-model="formData.name"
                  type="text"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                  :placeholder="t('telegram.botNamePlaceholder')"
                />
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.botDescription') }}</label>
                <input
                  v-model="formData.description"
                  type="text"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>

            <!-- Token -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('telegram.botToken') }}</label>
              <div class="relative">
                <input
                  v-model="formData.bot_token"
                  :type="showToken ? 'text' : 'password'"
                  class="w-full px-3 py-2 pr-10 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
                  :placeholder="t('telegram.tokenPlaceholder')"
                />
                <button
                  class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
                  @click="showToken = !showToken"
                >
                  <EyeOff v-if="showToken" class="w-4 h-4" />
                  <Eye v-else class="w-4 h-4" />
                </button>
              </div>
            </div>

            <!-- API URL -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('telegram.apiUrl') }}</label>
              <input
                v-model="formData.api_url"
                type="text"
                class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                :placeholder="t('telegram.apiUrlPlaceholder')"
              />
              <p class="text-xs text-muted-foreground mt-1">{{ t('telegram.apiUrlDesc') }}</p>
            </div>

            <!-- Enabled -->
            <div class="flex items-center justify-between p-3 bg-secondary rounded-lg">
              <div>
                <h4 class="font-medium">{{ t('telegram.enableBot') }}</h4>
                <p class="text-sm text-muted-foreground">{{ t('telegram.enableBotDesc') }}</p>
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

            <!-- Allowed Users -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('telegram.allowedUsersList') }}</label>
              <div class="flex gap-2 mb-2">
                <input
                  v-model="newAllowedUser"
                  type="number"
                  class="flex-1 px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                  :placeholder="t('telegram.userIdPlaceholder')"
                  @keydown.enter="addAllowedUser"
                />
                <button
                  class="px-3 py-2 bg-primary text-primary-foreground rounded-lg"
                  @click="addAllowedUser"
                >
                  <Plus class="w-4 h-4" />
                </button>
              </div>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="userId in formData.allowed_users"
                  :key="userId"
                  class="flex items-center gap-1 px-2 py-1 bg-secondary rounded text-sm font-mono"
                >
                  {{ userId }}
                  <button class="text-muted-foreground hover:text-red-400" @click="removeAllowedUser(userId)">
                    <X class="w-3 h-3" />
                  </button>
                </span>
                <span v-if="!formData.allowed_users?.length" class="text-sm text-muted-foreground">
                  {{ t('telegram.allUsersAllowed') }}
                </span>
              </div>
            </div>

            <!-- Admin Users -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('telegram.adminUsersList') }}</label>
              <div class="flex gap-2 mb-2">
                <input
                  v-model="newAdminUser"
                  type="number"
                  class="flex-1 px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                  :placeholder="t('telegram.userIdPlaceholder')"
                  @keydown.enter="addAdminUser"
                />
                <button
                  class="px-3 py-2 bg-primary text-primary-foreground rounded-lg"
                  @click="addAdminUser"
                >
                  <Plus class="w-4 h-4" />
                </button>
              </div>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="userId in formData.admin_users"
                  :key="userId"
                  class="flex items-center gap-1 px-2 py-1 bg-orange-500/20 text-orange-400 rounded text-sm font-mono"
                >
                  {{ userId }}
                  <button class="hover:text-red-400" @click="removeAdminUser(userId)">
                    <X class="w-3 h-3" />
                  </button>
                </span>
              </div>
            </div>

            <!-- Messages -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('telegram.welcomeMessage') }}</label>
              <textarea
                v-model="formData.welcome_message"
                rows="2"
                class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
              />
            </div>

            <!-- AI Config -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.llmBackend') }}</label>
                <select
                  v-model="formData.llm_backend"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option v-for="option in availableLlmOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.llmPersona') }}</label>
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
                <label class="block text-sm font-medium mb-1">{{ t('telegram.ttsEngine') }}</label>
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
                <label class="block text-sm font-medium mb-1">{{ t('telegram.ttsVoice') }}</label>
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
              <label class="block text-sm font-medium mb-1">{{ t('telegram.systemPrompt') }}</label>
              <textarea
                v-model="formData.system_prompt"
                rows="3"
                class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                :placeholder="t('telegram.systemPromptPlaceholder')"
              />
            </div>

            <!-- Rate Limiting -->
            <div class="space-y-3 p-4 bg-secondary/30 rounded-lg">
              <h4 class="font-medium text-sm">{{ t('telegram.rateLimit') }}</h4>
              <p class="text-xs text-muted-foreground">{{ t('telegram.rateLimitHint') }}</p>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.rateLimitCount') }}</label>
                  <input
                    v-model.number="formData.rate_limit_count"
                    type="number"
                    min="0"
                    class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="5"
                  />
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.rateLimitHours') }}</label>
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

            <!-- Action Buttons -->
            <div class="border-t border-border pt-4">
              <div class="flex items-center justify-between mb-3">
                <div>
                  <h3 class="font-medium">{{ t('telegram.actionButtons') }}</h3>
                  <p class="text-sm text-muted-foreground">{{ t('telegram.actionButtonsDesc') }}</p>
                </div>
                <button
                  class="flex items-center gap-1 px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90"
                  @click="openAddButtonDialog"
                >
                  <Plus class="w-4 h-4" />
                  {{ t('telegram.addButton') }}
                </button>
              </div>

              <div v-if="!formData.action_buttons?.length" class="text-center py-6 text-muted-foreground bg-secondary rounded-lg">
                {{ t('telegram.noButtons') }}
              </div>

              <div v-else class="space-y-2">
                <div
                  v-for="(button, index) in formData.action_buttons"
                  :key="button.id"
                  class="flex items-center gap-2 p-3 bg-secondary rounded-lg"
                >
                  <GripVertical class="w-4 h-4 text-muted-foreground cursor-move" />
                  <span class="text-xl w-8 text-center">{{ button.icon || '🔘' }}</span>
                  <div class="flex-1 min-w-0">
                    <p class="font-medium truncate">{{ button.label }}</p>
                    <p class="text-xs text-muted-foreground truncate">
                      {{ button.llm_backend || t('telegram.useDefaultBackend') }}
                    </p>
                  </div>
                  <button
                    :class="[
                      'relative w-10 h-5 rounded-full transition-colors',
                      button.enabled ? 'bg-green-500' : 'bg-gray-500'
                    ]"
                    @click="toggleButtonEnabled(index)"
                  >
                    <span
:class="[
                      'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform',
                      button.enabled ? 'translate-x-5' : 'translate-x-0'
                    ]" />
                  </button>
                  <button
                    class="p-1.5 text-muted-foreground hover:text-foreground hover:bg-background rounded"
                    @click="openEditButtonDialog(index)"
                  >
                    <Edit3 class="w-4 h-4" />
                  </button>
                  <button
                    class="p-1.5 text-muted-foreground hover:text-red-400 hover:bg-red-500/20 rounded"
                    @click="deleteButton(index)"
                  >
                    <Trash2 class="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            <!-- Payment Configuration -->
            <div class="border-t border-border pt-4">
              <div class="flex items-center gap-2 mb-3">
                <CreditCard class="w-5 h-5 text-muted-foreground" />
                <h3 class="font-medium">{{ t('telegram.payments') }}</h3>
              </div>

              <!-- Enable Payments -->
              <div class="flex items-center justify-between p-3 bg-secondary rounded-lg mb-3">
                <div>
                  <p class="font-medium text-sm">{{ t('telegram.paymentEnabled') }}</p>
                  <p class="text-xs text-muted-foreground">{{ t('telegram.paymentEnabledDesc') }}</p>
                </div>
                <button
                  :class="[
                    'relative w-10 h-5 rounded-full transition-colors',
                    formData.payment_enabled ? 'bg-green-500' : 'bg-gray-500'
                  ]"
                  @click="formData.payment_enabled = !formData.payment_enabled"
                >
                  <span
:class="[
                    'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform',
                    formData.payment_enabled ? 'translate-x-5' : 'translate-x-0'
                  ]" />
                </button>
              </div>

              <div v-if="formData.payment_enabled" class="space-y-3">
                <!-- Telegram Stars -->
                <div class="flex items-center justify-between p-3 bg-secondary rounded-lg">
                  <div class="flex items-center gap-2">
                    <Star class="w-4 h-4 text-yellow-400" />
                    <div>
                      <p class="font-medium text-sm">Telegram Stars</p>
                      <p class="text-xs text-muted-foreground">{{ t('telegram.starsEnabledDesc') }}</p>
                    </div>
                  </div>
                  <button
                    :class="[
                      'relative w-10 h-5 rounded-full transition-colors',
                      formData.stars_enabled ? 'bg-green-500' : 'bg-gray-500'
                    ]"
                    @click="formData.stars_enabled = !formData.stars_enabled"
                  >
                    <span
:class="[
                      'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform',
                      formData.stars_enabled ? 'translate-x-5' : 'translate-x-0'
                    ]" />
                  </button>
                </div>

                <!-- YooKassa Token -->
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.yookassaToken') }}</label>
                  <p class="text-xs text-muted-foreground mb-1">{{ t('telegram.yookassaTokenDesc') }}</p>
                  <div class="relative">
                    <input
                      v-model="formData.yookassa_provider_token"
                      :type="showYookassaToken ? 'text' : 'password'"
                      class="w-full px-3 py-2 pr-10 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                      :placeholder="t('telegram.yookassaTokenPlaceholder')"
                    />
                    <button
                      class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      @click="showYookassaToken = !showYookassaToken"
                    >
                      <Eye v-if="!showYookassaToken" class="w-4 h-4" />
                      <EyeOff v-else class="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <!-- YooMoney OAuth2 -->
                <div class="p-3 bg-secondary rounded-lg space-y-3">
                  <div class="flex items-center gap-2">
                    <Wallet class="w-4 h-4 text-purple-500" />
                    <p class="font-medium text-sm">{{ t('telegram.yoomoney') }}</p>
                    <span
                      v-if="formData.yoomoney_configured"
                      class="px-2 py-0.5 text-xs bg-green-500/20 text-green-400 rounded-full"
                    >
                      {{ t('telegram.yoomoneyConnected') }}
                    </span>
                  </div>
                  <p class="text-xs text-muted-foreground">{{ t('telegram.yoomoneyDesc') }}</p>

                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div>
                      <label class="text-xs text-muted-foreground">client_id</label>
                      <input
                        v-model="formData.yoomoney_client_id"
                        class="w-full px-2 py-1 text-sm bg-background rounded focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder="client_id"
                      />
                    </div>
                    <div>
                      <label class="text-xs text-muted-foreground">client_secret</label>
                      <input
                        v-model="formData.yoomoney_client_secret"
                        type="password"
                        class="w-full px-2 py-1 text-sm bg-background rounded focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder="client_secret"
                      />
                    </div>
                  </div>

                  <div>
                    <label class="text-xs text-muted-foreground">redirect_uri ({{ t('telegram.yoomoneyRedirectHint') }})</label>
                    <input
                      v-model="formData.yoomoney_redirect_uri"
                      class="w-full px-2 py-1 text-sm bg-background rounded focus:outline-none focus:ring-1 focus:ring-primary"
                      :placeholder="`https://your-domain.com/admin/telegram/instances/${formData.id || 'BOT_ID'}/yoomoney/callback`"
                    />
                  </div>

                  <div v-if="formData.yoomoney_configured" class="flex items-center gap-2 text-sm">
                    <span class="text-muted-foreground">{{ t('telegram.yoomoneyWallet') }}:</span>
                    <span class="font-mono">{{ formData.yoomoney_wallet_id }}</span>
                    <button
                      class="ml-auto px-2 py-1 text-xs bg-red-500/20 text-red-400 rounded hover:bg-red-500/30"
                      @click="disconnectYoomoney"
                    >
                      {{ t('telegram.yoomoneyDisconnect') }}
                    </button>
                  </div>

                  <button
                    v-if="formData.yoomoney_client_id && !formData.yoomoney_configured"
                    class="w-full px-3 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
                    @click="authorizeYoomoney"
                  >
                    {{ t('telegram.yoomoneyAuthorize') }}
                  </button>
                </div>

                <!-- Success Message -->
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.paymentSuccessMessage') }}</label>
                  <textarea
                    v-model="formData.payment_success_message"
                    rows="2"
                    class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                  />
                </div>

                <!-- Payment Products -->
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <label class="block text-sm font-medium">{{ t('telegram.paymentProducts') }}</label>
                    <button
                      class="flex items-center gap-1 px-2 py-1 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90"
                      @click="addPaymentProduct"
                    >
                      <Plus class="w-3 h-3" />
                      {{ t('telegram.addProduct') }}
                    </button>
                  </div>
                  <div v-if="!formData.payment_products?.length" class="text-center py-4 text-sm text-muted-foreground bg-secondary rounded-lg">
                    {{ t('telegram.noProducts') }}
                  </div>
                  <div v-else class="space-y-2">
                    <div
                      v-for="(product, idx) in formData.payment_products"
                      :key="idx"
                      class="p-3 bg-secondary rounded-lg space-y-2"
                    >
                      <div class="flex items-center justify-between">
                        <input
                          v-model="product.title"
                          class="flex-1 px-2 py-1 text-sm bg-background rounded focus:outline-none focus:ring-1 focus:ring-primary"
                          :placeholder="t('telegram.productTitle')"
                        />
                        <button
                          class="ml-2 p-1 text-muted-foreground hover:text-red-400"
                          @click="formData.payment_products?.splice(idx, 1)"
                        >
                          <Trash2 class="w-4 h-4" />
                        </button>
                      </div>
                      <input
                        v-model="product.description"
                        class="w-full px-2 py-1 text-sm bg-background rounded focus:outline-none focus:ring-1 focus:ring-primary"
                        :placeholder="t('telegram.productDescription')"
                      />
                      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <div>
                          <label class="text-xs text-muted-foreground">{{ t('telegram.productPriceRub') }}</label>
                          <input
                            v-model.number="product.price_rub"
                            type="number"
                            class="w-full px-2 py-1 text-sm bg-background rounded focus:outline-none focus:ring-1 focus:ring-primary"
                            placeholder="50000"
                          />
                        </div>
                        <div>
                          <label class="text-xs text-muted-foreground">{{ t('telegram.productPriceStars') }}</label>
                          <input
                            v-model.number="product.price_stars"
                            type="number"
                            class="w-full px-2 py-1 text-sm bg-background rounded focus:outline-none focus:ring-1 focus:ring-primary"
                            placeholder="100"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
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

    <!-- Logs Dialog -->
    <Teleport to="body">
      <div
        v-if="showLogsDialog"
        class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        @click.self="showLogsDialog = false"
      >
        <div class="bg-card rounded-xl border border-border w-full max-w-4xl max-h-[90vh] overflow-hidden">
          <div class="p-4 border-b border-border flex items-center justify-between">
            <h2 class="text-lg font-semibold">{{ t('telegram.logs') }} - {{ selectedInstance?.name }}</h2>
            <div class="flex items-center gap-2">
              <button
                class="p-2 hover:bg-secondary rounded-lg transition-colors"
                @click="() => refetchLogs()"
              >
                <RefreshCw class="w-4 h-4" />
              </button>
              <button class="p-1 hover:bg-secondary rounded" @click="showLogsDialog = false">
                <X class="w-5 h-5" />
              </button>
            </div>
          </div>
          <div class="p-4 max-h-[calc(90vh-80px)] overflow-y-auto">
            <pre class="bg-secondary rounded-lg p-4 text-sm font-mono whitespace-pre-wrap overflow-x-auto">{{ logsData?.logs || t('telegram.noLogs') }}</pre>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Sales CRUD Dialog -->
    <Teleport to="body">
      <div
        v-if="showSalesDialog"
        class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        @click.self="showSalesDialog = false"
      >
        <div class="bg-card rounded-xl border border-border w-full max-w-2xl max-h-[90vh] overflow-hidden">
          <div class="p-4 border-b border-border flex items-center justify-between">
            <h2 class="text-lg font-semibold">
              {{ salesDialogMode === 'create' ? t('common.create') : t('common.edit') }}
              — {{ t(`telegram.sales.${salesDialogType === 'prompt' ? 'prompts' : salesDialogType === 'quiz' ? 'quiz' : salesDialogType === 'segment' ? 'segments' : salesDialogType === 'followup' ? 'followups' : 'testimonials'}`) }}
            </h2>
            <button class="p-1 hover:bg-secondary rounded" @click="showSalesDialog = false">
              <X class="w-5 h-5" />
            </button>
          </div>

          <div class="p-4 overflow-y-auto max-h-[calc(90vh-120px)] space-y-4">
            <!-- Agent Prompt Form -->
            <template v-if="salesDialogType === 'prompt'">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.promptKey') }} *</label>
                  <input v-model="salesForm.prompt_key" type="text" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" placeholder="e.g. tz_qualified" />
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.name') }} *</label>
                  <input v-model="salesForm.name" type="text" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.description') }}</label>
                <input v-model="salesForm.description" type="text" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.systemPrompt') }} *</label>
                <textarea v-model="salesForm.system_prompt" rows="8" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-y font-mono text-sm" />
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.temperature') }}</label>
                  <input v-model.number="salesForm.temperature" type="number" step="0.1" min="0" max="2" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.maxTokens') }}</label>
                  <input v-model.number="salesForm.max_tokens" type="number" step="256" min="256" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.order') }}</label>
                  <input v-model.number="salesForm.order" type="number" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
              </div>
              <div class="flex items-center justify-between p-3 bg-secondary rounded-lg">
                <span class="font-medium text-sm">{{ t('common.enabled') }}</span>
                <button :class="['relative w-11 h-6 rounded-full transition-colors', salesForm.enabled ? 'bg-green-500' : 'bg-gray-500']" @click="salesForm.enabled = !salesForm.enabled">
                  <span :class="['absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform', salesForm.enabled ? 'translate-x-5' : 'translate-x-0']" />
                </button>
              </div>
            </template>

            <!-- Quiz Question Form -->
            <template v-if="salesDialogType === 'quiz'">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.questionKey') }} *</label>
                  <input v-model="salesForm.question_key" type="text" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" placeholder="e.g. project_type" />
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.order') }}</label>
                  <input v-model.number="salesForm.order" type="number" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.questionText') }} *</label>
                <textarea v-model="salesForm.text" rows="3" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none" />
              </div>
              <div>
                <div class="flex items-center justify-between mb-2">
                  <label class="block text-sm font-medium">{{ t('telegram.sales.form.options') }}</label>
                  <button class="flex items-center gap-1 px-2 py-1 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90" @click="addQuizOption">
                    <Plus class="w-3 h-3" />
                    {{ t('telegram.sales.form.addOption') }}
                  </button>
                </div>
                <div class="space-y-2">
                  <div v-for="(opt, i) in salesForm.options" :key="i" class="flex items-center gap-2">
                    <input v-model="opt.icon" type="text" maxlength="2" class="w-12 px-2 py-1.5 bg-secondary rounded text-center text-lg" placeholder="🔹" />
                    <input v-model="opt.label" type="text" class="flex-1 px-2 py-1.5 bg-secondary rounded text-sm" :placeholder="t('telegram.sales.form.optionLabel')" />
                    <input v-model="opt.value" type="text" class="w-32 px-2 py-1.5 bg-secondary rounded text-sm font-mono" :placeholder="t('telegram.sales.form.optionValue')" />
                    <button class="p-1 text-red-400 hover:bg-red-500/20 rounded" @click="removeQuizOption(i)">
                      <Trash2 class="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
              <div class="flex items-center justify-between p-3 bg-secondary rounded-lg">
                <span class="font-medium text-sm">{{ t('common.enabled') }}</span>
                <button :class="['relative w-11 h-6 rounded-full transition-colors', salesForm.enabled ? 'bg-green-500' : 'bg-gray-500']" @click="salesForm.enabled = !salesForm.enabled">
                  <span :class="['absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform', salesForm.enabled ? 'translate-x-5' : 'translate-x-0']" />
                </button>
              </div>
            </template>

            <!-- Segment Form -->
            <template v-if="salesDialogType === 'segment'">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.segmentKey') }} *</label>
                  <input v-model="salesForm.segment_key" type="text" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" placeholder="e.g. tz_qualified" />
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.name') }} *</label>
                  <input v-model="salesForm.name" type="text" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.description') }}</label>
                <input v-model="salesForm.description" type="text" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.path') }}</label>
                  <select v-model="salesForm.path" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary">
                    <option value="diy">diy</option>
                    <option value="basic">basic</option>
                    <option value="custom">custom</option>
                    <option value="qualified">qualified</option>
                    <option value="unqualified">unqualified</option>
                    <option value="needs_analysis">needs_analysis</option>
                  </select>
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.priority') }}</label>
                  <input v-model.number="salesForm.priority" type="number" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.agentPromptKey') }}</label>
                  <select v-model="salesForm.agent_prompt_key" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary">
                    <option value="">—</option>
                    <option v-for="p in salesPrompts" :key="p.prompt_key" :value="p.prompt_key">{{ p.name }} ({{ p.prompt_key }})</option>
                  </select>
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.matchRules') }} (JSON)</label>
                <textarea v-model="salesForm.match_rules" rows="4" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none font-mono text-sm" placeholder='{"project_type": ["ai_assistant"], "budget_range": ["200k_500k"]}' />
              </div>
              <div class="flex items-center justify-between p-3 bg-secondary rounded-lg">
                <span class="font-medium text-sm">{{ t('common.enabled') }}</span>
                <button :class="['relative w-11 h-6 rounded-full transition-colors', salesForm.enabled ? 'bg-green-500' : 'bg-gray-500']" @click="salesForm.enabled = !salesForm.enabled">
                  <span :class="['absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform', salesForm.enabled ? 'translate-x-5' : 'translate-x-0']" />
                </button>
              </div>
            </template>

            <!-- Follow-up Rule Form -->
            <template v-if="salesDialogType === 'followup'">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.name') }} *</label>
                  <input v-model="salesForm.name" type="text" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.trigger') }} *</label>
                  <input v-model="salesForm.trigger" type="text" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" placeholder="e.g. quiz_incomplete" />
                </div>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.delayHours') }}</label>
                  <input v-model.number="salesForm.delay_hours" type="number" min="1" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.maxSends') }}</label>
                  <input v-model.number="salesForm.max_sends" type="number" min="1" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.order') }}</label>
                  <input v-model.number="salesForm.order" type="number" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.segmentFilter') }}</label>
                <input v-model="salesForm.segment_filter" type="text" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" placeholder="e.g. tz_qualified" />
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.messageTemplate') }} *</label>
                <textarea v-model="salesForm.message_template" rows="4" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-y" />
              </div>
              <div class="flex items-center justify-between p-3 bg-secondary rounded-lg">
                <span class="font-medium text-sm">{{ t('common.enabled') }}</span>
                <button :class="['relative w-11 h-6 rounded-full transition-colors', salesForm.enabled ? 'bg-green-500' : 'bg-gray-500']" @click="salesForm.enabled = !salesForm.enabled">
                  <span :class="['absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform', salesForm.enabled ? 'translate-x-5' : 'translate-x-0']" />
                </button>
              </div>
            </template>

            <!-- Testimonial Form -->
            <template v-if="salesDialogType === 'testimonial'">
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.author') }} *</label>
                <input v-model="salesForm.author" type="text" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.text') }} *</label>
                <textarea v-model="salesForm.text" rows="4" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-y" />
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.rating') }}</label>
                  <div class="flex gap-1">
                    <button v-for="n in 5" :key="n" class="p-1" @click="salesForm.rating = n">
                      <Star :class="['w-5 h-5', n <= salesForm.rating ? 'text-yellow-400 fill-yellow-400' : 'text-gray-500']" />
                    </button>
                  </div>
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('telegram.sales.form.order') }}</label>
                  <input v-model.number="salesForm.order" type="number" class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
              </div>
              <div class="flex items-center justify-between p-3 bg-secondary rounded-lg">
                <span class="font-medium text-sm">{{ t('common.enabled') }}</span>
                <button :class="['relative w-11 h-6 rounded-full transition-colors', salesForm.enabled ? 'bg-green-500' : 'bg-gray-500']" @click="salesForm.enabled = !salesForm.enabled">
                  <span :class="['absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform', salesForm.enabled ? 'translate-x-5' : 'translate-x-0']" />
                </button>
              </div>
            </template>
          </div>

          <div class="p-4 border-t border-border flex justify-end gap-2">
            <button class="px-4 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors" @click="showSalesDialog = false">
              {{ t('common.cancel') }}
            </button>
            <button class="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors" @click="saveSalesItem">
              <Check class="w-4 h-4" />
              {{ t('common.save') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Button Edit Dialog -->
    <Teleport to="body">
      <div
        v-if="showButtonEditDialog"
        class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        @click.self="showButtonEditDialog = false"
      >
        <div class="bg-card rounded-xl border border-border w-full max-w-lg overflow-hidden">
          <div class="p-4 border-b border-border flex items-center justify-between">
            <h2 class="text-lg font-semibold">
              {{ editingButtonIndex >= 0 ? t('telegram.editButton') : t('telegram.addButton') }}
            </h2>
            <button class="p-1 hover:bg-secondary rounded" @click="showButtonEditDialog = false">
              <X class="w-5 h-5" />
            </button>
          </div>

          <div class="p-4 space-y-4">
            <!-- Label & Icon -->
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div class="col-span-2">
                <label class="block text-sm font-medium mb-1">{{ t('telegram.buttonLabel') }} *</label>
                <input
                  v-model="editingButton.label"
                  type="text"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                  :placeholder="t('telegram.buttonLabelPlaceholder')"
                />
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('telegram.buttonIcon') }}</label>
                <input
                  v-model="editingButton.icon"
                  type="text"
                  maxlength="2"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-center text-xl"
                  :placeholder="t('telegram.buttonIconPlaceholder')"
                />
              </div>
            </div>

            <!-- LLM Backend -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('telegram.buttonLlmBackend') }}</label>
              <select
                v-model="editingButton.llm_backend"
                class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">{{ t('telegram.useDefaultBackend') }}</option>
                <option v-for="option in availableLlmOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </div>

            <!-- System Prompt -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('telegram.buttonSystemPrompt') }}</label>
              <textarea
                v-model="editingButton.system_prompt"
                rows="4"
                class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                :placeholder="t('telegram.buttonSystemPromptPlaceholder')"
              />
            </div>

            <!-- Enabled -->
            <div class="flex items-center justify-between p-3 bg-secondary rounded-lg">
              <span class="font-medium">{{ t('telegram.buttonEnabled') }}</span>
              <button
                :class="[
                  'relative w-11 h-6 rounded-full transition-colors',
                  editingButton.enabled ? 'bg-green-500' : 'bg-gray-500'
                ]"
                @click="editingButton.enabled = !editingButton.enabled"
              >
                <span
:class="[
                  'absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform',
                  editingButton.enabled ? 'translate-x-5' : 'translate-x-0'
                ]" />
              </button>
            </div>
          </div>

          <div class="p-4 border-t border-border flex justify-end gap-2">
            <button
              class="px-4 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
              @click="showButtonEditDialog = false"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              :disabled="!editingButton.label"
              class="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
              @click="saveButton"
            >
              <Check class="w-4 h-4" />
              {{ t('common.save') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
