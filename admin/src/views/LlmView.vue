<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { llmApi, type LlmParams, type LlmPreset, type CloudProvider } from '@/api'
import {
  Brain,
  User,
  Settings2,
  Trash2,
  Save,
  RotateCw,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Cpu,
  Cloud,
  CloudOff,
  Plus,
  Edit2,
  Play,
  Star,
  RefreshCw,
  Shield,
  Wifi,
  ChevronDown,
  ChevronUp
} from 'lucide-vue-next'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToastStore } from '@/stores/toast'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const queryClient = useQueryClient()
const toast = useToastStore()
const authStore = useAuthStore()

// State
const stopUnusedVllm = ref(false)
const switchingModel = ref<string | null>(null)

// Persona editor state
const showPersonaModal = ref(false)
const editingPreset = ref<LlmPreset | null>(null)
const showGenParams = ref(false)
const presetForm = ref({
  id: '',
  name: '',
  description: '',
  system_prompt: '',
  temperature: 0.7,
  max_tokens: 512,
  top_p: 0.9,
  repetition_penalty: 1.1,
})

// Cloud provider state
const showProviderModal = ref(false)
const editingProvider = ref<CloudProvider | null>(null)
const providerForm = ref({
  name: '',
  provider_type: 'openrouter',
  api_key: '',
  base_url: '',
  model_name: '',
  description: '',
  enabled: true,
})
const useCustomModel = ref(false)
const customModelName = ref('')

// VLESS proxy state (supports multiple URLs, one per line)
const vlessUrlsText = ref('')
const vlessTestResults = ref<Array<{ success?: boolean; message?: string; error?: string; remark?: string }>>([])
const testingAllProxies = ref(false)
const testingProviderId = ref<string | null>(null)

// Queries
const { data: backendData, isLoading: backendLoading } = useQuery({
  queryKey: ['llm-backend'],
  queryFn: () => llmApi.getBackend(),
})

const { data: modelsData } = useQuery({
  queryKey: ['llm-models'],
  queryFn: () => llmApi.getModels(),
})

// Preset queries (replace old persona queries)
const { data: presetsData } = useQuery({
  queryKey: ['llm-presets'],
  queryFn: () => llmApi.getPresets(),
})

const { data: currentPresetData } = useQuery({
  queryKey: ['llm-preset-current'],
  queryFn: () => llmApi.getCurrentPreset(),
})

const { data: paramsData } = useQuery({
  queryKey: ['llm-params'],
  queryFn: () => llmApi.getParams(),
})

const { data: historyData, refetch: refetchHistory } = useQuery({
  queryKey: ['llm-history'],
  queryFn: () => llmApi.getHistory(),
})

// Cloud providers query
const { data: providersData, refetch: refetchProviders } = useQuery({
  queryKey: ['llm-providers'],
  queryFn: () => llmApi.getProviders(),
})

// Proxy status query
const { data: proxyStatusData } = useQuery({
  queryKey: ['proxy-status'],
  queryFn: () => llmApi.getProxyStatus(),
})

// Bridge status query
const { data: bridgeStatusData, refetch: refetchBridgeStatus } = useQuery({
  queryKey: ['bridge-status'],
  queryFn: () => llmApi.getBridgeStatus(),
  refetchInterval: 10000,
})

// Local state for params
const localParams = ref<Partial<LlmParams>>({})

watch(paramsData, (data) => {
  if (data?.params) {
    localParams.value = { ...data.params }
  }
}, { immediate: true })

// Computed для списка моделей текущего провайдера
const currentProviderModels = computed(() => {
  return providersData.value?.provider_types?.[providerForm.value.provider_type]?.default_models || []
})

// Переключение на кастомную модель когда выбрано "Other"
watch(() => providerForm.value.model_name, (newVal) => {
  if (newVal === '' && !useCustomModel.value && currentProviderModels.value.length > 0) {
    useCustomModel.value = true
  }
})

// Computed
const presets = computed(() => presetsData.value?.presets || [])
const currentPresetId = computed(() => currentPresetData.value?.current?.id || null)

const isVllm = computed(() => backendData.value?.backend === 'vllm')
const isCloudBackend = computed(() => backendData.value?.backend?.startsWith('cloud:'))
const currentCloudProviderId = computed(() => {
  if (isCloudBackend.value && backendData.value?.backend) {
    return backendData.value.backend.split(':')[1]
  }
  return null
})

// Check if current provider form is for Gemini
const isGeminiProvider = computed(() => providerForm.value.provider_type === 'gemini')

// Enabled cloud providers (for status display)
const enabledProviders = computed(() =>
  (providersData.value?.providers || []).filter((p: CloudProvider) => p.enabled),
)

// Get the default (or first enabled) cloud provider ID for the toggle button
const defaultCloudProviderId = computed(() => {
  const providers = providersData.value?.providers || []
  const defaultProvider = providers.find((p: CloudProvider) => p.is_default && p.enabled)
  if (defaultProvider) return defaultProvider.id
  const firstEnabled = providers.find((p: CloudProvider) => p.enabled)
  return firstEnabled ? firstEnabled.id : null
})

// Check if current provider form is for Bridge
const isBridgeProvider = computed(() => providerForm.value.provider_type === 'claude_bridge')

// Bridge-specific state
const bridgePort = ref(8787)
const bridgePermission = ref('chat')

// Proxy status
const proxyStatus = computed(() => proxyStatusData.value?.proxy)

// Built-in preset IDs (cannot be deleted)
const builtinPresetIds = ['anna', 'marina']

// Mutations
const setBackendMutation = useMutation({
  mutationFn: (backend: string) => llmApi.setBackend(backend, backend !== 'vllm' && stopUnusedVllm.value),
  onSuccess: (data) => {
    queryClient.invalidateQueries({ queryKey: ['llm-backend'] })
    toast.success(data.message || `Переключено на ${data.backend}`)
  },
  onError: (error: Error) => {
    toast.error(`Ошибка переключения: ${error.message}`)
  },
})

// vLLM model switching mutation
const setVllmModelMutation = useMutation({
  mutationFn: (model: string) => {
    switchingModel.value = model
    return llmApi.setVllmModel(model)
  },
  onSuccess: (data) => {
    switchingModel.value = null
    queryClient.invalidateQueries({ queryKey: ['llm-models'] })
    queryClient.invalidateQueries({ queryKey: ['llm-backend'] })
    toast.success(data.message || `Модель изменена на ${data.model}`)
  },
  onError: (error: Error) => {
    switchingModel.value = null
    toast.error(`Ошибка смены модели: ${error.message}`)
  },
})

// Cloud provider mutations
const createProviderMutation = useMutation({
  mutationFn: (data: Partial<CloudProvider>) => llmApi.createProvider(data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['llm-providers'] })
    showProviderModal.value = false
    toast.success('Provider created')
  },
  onError: (error: Error) => {
    toast.error(`Error: ${error.message}`)
  },
})

const updateProviderMutation = useMutation({
  mutationFn: ({ id, data }: { id: string; data: Partial<CloudProvider> }) =>
    llmApi.updateProvider(id, data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['llm-providers'] })
    showProviderModal.value = false
    toast.success('Provider updated')
  },
  onError: (error: Error) => {
    toast.error(`Error: ${error.message}`)
  },
})

const deleteProviderMutation = useMutation({
  mutationFn: (id: string) => llmApi.deleteProvider(id),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['llm-providers'] })
    toast.success('Provider deleted')
  },
  onError: (error: Error) => {
    toast.error(`Error: ${error.message}`)
  },
})

const testProviderMutation = useMutation({
  mutationFn: (id: string) => {
    testingProviderId.value = id
    return llmApi.testProvider(id)
  },
  onSuccess: (data) => {
    testingProviderId.value = null
    if (data.available) {
      toast.success(`Connection OK: ${data.test_response?.substring(0, 50)}`)
    } else {
      toast.error(`Connection failed: ${data.message}`)
    }
  },
  onError: (error: Error) => {
    testingProviderId.value = null
    toast.error(`Test failed: ${error.message}`)
  },
})

// Preset mutations
const activatePresetMutation = useMutation({
  mutationFn: (presetId: string) => llmApi.activatePreset(presetId),
  onSuccess: (data) => {
    queryClient.invalidateQueries({ queryKey: ['llm-preset-current'] })
    queryClient.invalidateQueries({ queryKey: ['llm-presets'] })
    queryClient.invalidateQueries({ queryKey: ['llm-params'] })
    toast.success(data.message || 'Persona activated')
  },
  onError: (error: Error) => {
    toast.error(`Error: ${error.message}`)
  },
})

const createPresetMutation = useMutation({
  mutationFn: (data: Partial<LlmPreset>) => llmApi.createPreset(data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['llm-presets'] })
    showPersonaModal.value = false
    toast.success(t('llm.newPersona') + ' created')
  },
  onError: (error: Error) => {
    toast.error(`Error: ${error.message}`)
  },
})

const updatePresetMutation = useMutation({
  mutationFn: ({ id, data }: { id: string; data: Partial<LlmPreset> }) =>
    llmApi.updatePreset(id, data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['llm-presets'] })
    queryClient.invalidateQueries({ queryKey: ['llm-preset-current'] })
    queryClient.invalidateQueries({ queryKey: ['llm-params'] })
    showPersonaModal.value = false
    toast.success('Persona updated')
  },
  onError: (error: Error) => {
    toast.error(`Error: ${error.message}`)
  },
})

const deletePresetMutation = useMutation({
  mutationFn: (id: string) => llmApi.deletePreset(id),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['llm-presets'] })
    queryClient.invalidateQueries({ queryKey: ['llm-preset-current'] })
    toast.success('Persona deleted')
  },
  onError: (error: Error) => {
    toast.error(`Error: ${error.message}`)
  },
})

const setParamsMutation = useMutation({
  mutationFn: (params: Partial<LlmParams>) => llmApi.setParams(params),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['llm-params'] }),
})

const clearHistoryMutation = useMutation({
  mutationFn: () => llmApi.clearHistory(),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['llm-history'] }),
})

// VLESS proxy test mutation (supports multiple URLs)
const testProxyMutation = useMutation({
  mutationFn: (vlessUrls: string[]) => llmApi.testMultipleProxies(vlessUrls),
  onSuccess: (data) => {
    vlessTestResults.value = data.results.map(r => ({
      success: r.success,
      message: r.message,
      error: r.error,
      remark: r.proxy_remark,
    }))
    testingAllProxies.value = false
    if (data.successful > 0) {
      toast.success(`${data.successful}/${data.total} proxies connected successfully`)
    } else {
      toast.error('All proxy connections failed')
    }
  },
  onError: (error: Error) => {
    vlessTestResults.value = [{ success: false, error: error.message }]
    testingAllProxies.value = false
    toast.error(`Proxy test failed: ${error.message}`)
  },
})

// Parse VLESS URLs from textarea
function getVlessUrls(): string[] {
  return vlessUrlsText.value
    .split('\n')
    .map(url => url.trim())
    .filter(url => url && url.startsWith('vless://'))
}

// Test all configured proxies
function testAllProxies() {
  const urls = getVlessUrls()
  if (urls.length === 0) {
    toast.error('No valid VLESS URLs found')
    return
  }
  testingAllProxies.value = true
  vlessTestResults.value = []
  testProxyMutation.mutate(urls)
}

// Get proxy count from provider config
function getProxyCount(config: Record<string, unknown> | undefined): number {
  if (!config) return 0
  const urls = config.vless_urls as string[] | undefined
  const url = config.vless_url as string | undefined
  if (urls && Array.isArray(urls)) return urls.length
  if (url) return 1
  return 0
}

function saveParams() {
  setParamsMutation.mutate(localParams.value)
}

// Generate slug from name
function generateSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[а-яё]/g, (c) => {
      const map: Record<string, string> = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
      }
      return map[c] || c
    })
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .substring(0, 50)
}

// Persona modal methods
function openCreatePersonaModal() {
  editingPreset.value = null
  presetForm.value = {
    id: '',
    name: '',
    description: '',
    system_prompt: '',
    temperature: 0.7,
    max_tokens: 512,
    top_p: 0.9,
    repetition_penalty: 1.1,
  }
  showGenParams.value = false
  showPersonaModal.value = true
}

function openEditPersonaModal(preset: LlmPreset) {
  editingPreset.value = preset
  presetForm.value = {
    id: preset.id,
    name: preset.name,
    description: preset.description || '',
    system_prompt: preset.system_prompt || '',
    temperature: preset.temperature,
    max_tokens: preset.max_tokens,
    top_p: preset.top_p,
    repetition_penalty: preset.repetition_penalty,
  }
  showGenParams.value = false
  showPersonaModal.value = true
}

function savePersona() {
  if (editingPreset.value) {
    // Update existing
    updatePresetMutation.mutate({
      id: editingPreset.value.id,
      data: {
        name: presetForm.value.name,
        description: presetForm.value.description || undefined,
        system_prompt: presetForm.value.system_prompt || undefined,
        temperature: presetForm.value.temperature,
        max_tokens: presetForm.value.max_tokens,
        top_p: presetForm.value.top_p,
        repetition_penalty: presetForm.value.repetition_penalty,
      },
    })
  } else {
    // Create new
    const id = presetForm.value.id || generateSlug(presetForm.value.name)
    createPresetMutation.mutate({
      id,
      name: presetForm.value.name,
      description: presetForm.value.description || undefined,
      system_prompt: presetForm.value.system_prompt || undefined,
      temperature: presetForm.value.temperature,
      max_tokens: presetForm.value.max_tokens,
      top_p: presetForm.value.top_p,
      repetition_penalty: presetForm.value.repetition_penalty,
    })
  }
}

function confirmDeletePreset(preset: LlmPreset) {
  if (builtinPresetIds.includes(preset.id)) {
    toast.error(t('llm.cannotDeleteBuiltin'))
    return
  }
  if (confirm(t('llm.deleteConfirm'))) {
    deletePresetMutation.mutate(preset.id)
  }
}

// Auto-generate slug from name (only when creating)
watch(() => presetForm.value.name, (name) => {
  if (!editingPreset.value && name) {
    presetForm.value.id = generateSlug(name)
  }
})

// Cloud provider methods
function openCreateProviderModal() {
  editingProvider.value = null
  const defaultType = 'openrouter'
  const typeConfig = providersData.value?.provider_types?.[defaultType]
  providerForm.value = {
    name: '',
    provider_type: defaultType,
    api_key: '',
    base_url: typeConfig?.default_base_url || 'https://openrouter.ai/api/v1',
    model_name: typeConfig?.default_models?.[0] || '',
    description: '',
    enabled: true,
  }
  useCustomModel.value = false
  customModelName.value = ''
  vlessUrlsText.value = ''
  vlessTestResults.value = []
  bridgePort.value = 8787
  bridgePermission.value = 'chat'
  showProviderModal.value = true
}

function openEditProviderModal(provider: CloudProvider) {
  editingProvider.value = provider
  const typeConfig = providersData.value?.provider_types?.[provider.provider_type]
  const defaultModels = typeConfig?.default_models || []
  const isCustomModel = Boolean(provider.model_name && !defaultModels.includes(provider.model_name))

  providerForm.value = {
    name: provider.name,
    provider_type: provider.provider_type,
    api_key: '', // Don't prefill key
    base_url: provider.base_url || '',
    model_name: isCustomModel ? '' : provider.model_name,
    description: provider.description || '',
    enabled: provider.enabled,
  }
  useCustomModel.value = isCustomModel
  customModelName.value = isCustomModel ? provider.model_name : ''

  // Load VLESS URLs from config if present (Gemini only)
  // Support both vless_urls (array) and legacy vless_url (string)
  const vlessUrls = provider.config?.vless_urls as string[] | undefined
  const legacyUrl = provider.config?.vless_url as string | undefined
  if (vlessUrls && Array.isArray(vlessUrls)) {
    vlessUrlsText.value = vlessUrls.join('\n')
  } else if (legacyUrl) {
    vlessUrlsText.value = legacyUrl
  } else {
    vlessUrlsText.value = ''
  }
  vlessTestResults.value = []

  // Load bridge config if present
  bridgePort.value = (provider.config?.bridge_port as number) || 8787
  bridgePermission.value = (provider.config?.permission_level as string) || 'chat'

  showProviderModal.value = true
}

function onProviderTypeChange() {
  const typeConfig = providersData.value?.provider_types?.[providerForm.value.provider_type]
  if (typeConfig) {
    providerForm.value.base_url = typeConfig.default_base_url || ''
    providerForm.value.model_name = typeConfig.default_models?.[0] || ''
    useCustomModel.value = false
    customModelName.value = ''
  }
  // Reset VLESS when changing provider type
  if (providerForm.value.provider_type !== 'gemini') {
    vlessUrlsText.value = ''
    vlessTestResults.value = []
  }
}

function saveProvider() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data: any = { ...providerForm.value }

  // Используем кастомную модель если выбрана опция "Другая"
  if (useCustomModel.value && customModelName.value) {
    data.model_name = customModelName.value
  }

  if (!data.api_key) {
    delete data.api_key // Don't update if empty
  }

  // Add bridge config for claude_bridge providers
  if (providerForm.value.provider_type === 'claude_bridge') {
    data.config = {
      ...(editingProvider.value?.config || {}),
      bridge_port: bridgePort.value,
      permission_level: bridgePermission.value,
    }
  }

  // Add VLESS URLs to config for Gemini providers
  const vlessUrls = getVlessUrls()
  if (providerForm.value.provider_type === 'gemini' && vlessUrls.length > 0) {
    data.config = {
      ...(editingProvider.value?.config || {}),
      vless_urls: vlessUrls,
    }
    // Remove legacy vless_url if present
    delete data.config.vless_url
  } else if (providerForm.value.provider_type === 'gemini') {
    // Remove vless_urls and vless_url if empty
    const existingConfig = editingProvider.value?.config || {}
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { vless_url, vless_urls, ...restConfig } = existingConfig as { vless_url?: string; vless_urls?: string[] }
    if (Object.keys(restConfig).length > 0) {
      data.config = restConfig
    }
  }

  if (editingProvider.value) {
    updateProviderMutation.mutate({ id: editingProvider.value.id, data })
  } else {
    createProviderMutation.mutate(data)
  }
}

function switchToCloudProvider(providerId: string) {
  setBackendMutation.mutate(`cloud:${providerId}`)
}
</script>

<template>
  <div class="space-y-6">
    <!-- Backend Selection -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border">
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <Brain class="w-5 h-5" />
          LLM Backend
        </h2>
      </div>

      <div class="p-4">
        <div v-if="backendLoading" class="text-muted-foreground">Loading...</div>
        <div v-else class="space-y-4">
          <!-- Backend Toggle (admin only can switch to vLLM) -->
          <div v-if="authStore.canManage('llm')" class="flex items-center gap-4">
            <div class="grid grid-cols-2 gap-2 p-1 bg-secondary rounded-lg">
              <button
                :disabled="setBackendMutation.isPending.value"
                :class="[
                  'px-4 py-2 rounded-lg transition-colors flex items-center justify-center gap-2',
                  isVllm ? 'bg-primary text-primary-foreground' : 'hover:bg-secondary/80',
                  setBackendMutation.isPending.value && 'opacity-50 cursor-not-allowed'
                ]"
                @click="setBackendMutation.mutate('vllm')"
              >
                <Loader2 v-if="setBackendMutation.isPending.value && !isVllm" class="w-4 h-4 animate-spin" />
                vLLM (Local)
              </button>
              <button
                :disabled="setBackendMutation.isPending.value || !defaultCloudProviderId"
                :class="[
                  'px-4 py-2 rounded-lg transition-colors flex items-center justify-center gap-2',
                  !isVllm ? 'bg-primary text-primary-foreground' : 'hover:bg-secondary/80',
                  setBackendMutation.isPending.value && 'opacity-50 cursor-not-allowed'
                ]"
                :title="defaultCloudProviderId ? '' : 'No cloud provider configured'"
                @click="defaultCloudProviderId && setBackendMutation.mutate(`cloud:${defaultCloudProviderId}`)"
              >
                <Loader2 v-if="setBackendMutation.isPending.value && isVllm" class="w-4 h-4 animate-spin" />
                {{ t('llm.cloudAI') }}
              </button>
            </div>
          </div>

          <!-- Status -->
          <div class="text-sm">
            <div v-if="setBackendMutation.isPending.value" class="flex items-center gap-2">
              <Loader2 class="w-4 h-4 animate-spin text-primary" />
              <span class="text-muted-foreground">
                Переключение... (vLLM может запускаться до 2 минут)
              </span>
            </div>
            <div v-else-if="enabledProviders.length" class="flex flex-wrap items-center gap-2">
              <span
                v-for="p in enabledProviders"
                :key="p.id"
                :class="[
                  'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs border cursor-pointer transition-colors',
                  currentCloudProviderId === p.id
                    ? 'border-green-500/50 bg-green-500/10 text-green-600 font-medium'
                    : 'border-border bg-secondary/50 text-muted-foreground hover:border-primary/50'
                ]"
                @click="switchToCloudProvider(p.id)"
              >
                <CheckCircle2 v-if="currentCloudProviderId === p.id" class="w-3 h-3" />
                <Cloud v-else class="w-3 h-3" />
                {{ p.name }}
                <span class="opacity-70">{{ p.model_name }}</span>
              </span>
            </div>
          </div>

          <!-- Stop vLLM checkbox (show when using vLLM) -->
          <div v-if="isVllm" class="flex items-center gap-2">
            <input
              id="stopVllm"
              v-model="stopUnusedVllm"
              type="checkbox"
              class="w-4 h-4 rounded border-border"
            />
            <label for="stopVllm" class="text-sm text-muted-foreground">
              {{ t('llm.stopVllmHint') }}
            </label>
          </div>

          <!-- Warning/Info messages -->
          <div v-if="setBackendMutation.isError.value" class="flex items-center gap-2 text-sm text-red-500">
            <AlertCircle class="w-4 h-4" />
            {{ setBackendMutation.error.value?.message || 'Ошибка переключения' }}
          </div>
        </div>
      </div>
    </div>

    <!-- Cloud LLM Providers -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border flex items-center justify-between">
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <Cloud class="w-5 h-5" />
          Cloud LLM Providers
        </h2>
        <div class="flex gap-2">
          <button
            class="p-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
            title="Refresh"
            @click="() => refetchProviders()"
          >
            <RefreshCw class="w-4 h-4" />
          </button>
          <button
            class="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
            @click="openCreateProviderModal"
          >
            <Plus class="w-4 h-4" />
            Add Provider
          </button>
        </div>
      </div>

      <div class="p-4">
        <div v-if="!providersData?.providers?.length" class="text-center py-8 text-muted-foreground">
          <CloudOff class="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>No cloud providers configured</p>
          <p class="text-sm mt-1">Add a provider to use cloud LLM services</p>
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="provider in providersData.providers"
            :key="provider.id"
            :class="[
              'p-4 rounded-lg border transition-all',
              currentCloudProviderId === provider.id
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-primary/50'
            ]"
          >
            <div class="flex items-start justify-between">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <h3 class="font-semibold">{{ provider.name }}</h3>
                  <span class="px-2 py-0.5 bg-secondary rounded text-xs">
                    {{ provider.provider_type }}
                  </span>
                  <span v-if="provider.is_default" class="flex items-center gap-1 px-2 py-0.5 bg-yellow-500/20 text-yellow-600 rounded text-xs">
                    <Star class="w-3 h-3" /> Default
                  </span>
                  <span v-if="!provider.enabled" class="px-2 py-0.5 bg-red-500/20 text-red-600 rounded text-xs">
                    Disabled
                  </span>
                  <span v-if="currentCloudProviderId === provider.id" class="px-2 py-0.5 bg-green-500/20 text-green-600 rounded text-xs">
                    Active
                  </span>
                  <span
                    v-if="provider.provider_type === 'gemini' && getProxyCount(provider.config) > 0"
                    class="flex items-center gap-1 px-2 py-0.5 bg-purple-500/20 text-purple-600 rounded text-xs"
                    :title="`${getProxyCount(provider.config)} VLESS proxy(ies) configured`"
                  >
                    <Shield class="w-3 h-3" /> {{ getProxyCount(provider.config) }} Proxy
                  </span>
                  <span
                    v-if="provider.provider_type === 'claude_bridge'"
                    :class="[
                      'flex items-center gap-1 px-2 py-0.5 rounded text-xs',
                      bridgeStatusData?.is_running
                        ? 'bg-green-500/20 text-green-600'
                        : 'bg-gray-500/20 text-gray-500'
                    ]"
                  >
                    <Cpu class="w-3 h-3" />
                    {{ bridgeStatusData?.is_running ? t('llm.bridgeRunning') : t('llm.bridgeStopped') }}
                  </span>
                </div>
                <p class="text-sm text-muted-foreground">
                  Model: {{ provider.model_name || 'Not set' }}
                </p>
                <p v-if="provider.description" class="text-sm text-muted-foreground mt-1">
                  {{ provider.description }}
                </p>
              </div>

              <div class="flex items-center gap-2">
                <button
                  :disabled="testingProviderId !== null"
                  class="p-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
                  title="Test connection"
                  @click="testProviderMutation.mutate(provider.id)"
                >
                  <Loader2 v-if="testingProviderId === provider.id" class="w-4 h-4 animate-spin" />
                  <Play v-else class="w-4 h-4" />
                </button>
                <button
                  :disabled="!provider.enabled || setBackendMutation.isPending.value"
                  class="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors text-sm"
                  @click="switchToCloudProvider(provider.id)"
                >
                  Use
                </button>
                <button
                  class="p-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
                  @click="openEditProviderModal(provider)"
                >
                  <Edit2 class="w-4 h-4" />
                </button>
                <button
                  :disabled="deleteProviderMutation.isPending.value"
                  class="p-2 bg-red-600/20 text-red-600 rounded-lg hover:bg-red-600/30 transition-colors"
                  @click="deleteProviderMutation.mutate(provider.id)"
                >
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Available Models (vLLM) — admin only -->
    <div v-if="isVllm && authStore.canManage('llm')" class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border">
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <Cpu class="w-5 h-5" />
          vLLM Models
        </h2>
      </div>

      <div class="p-4">
        <!-- Current Model -->
        <div v-if="modelsData?.current_model" class="mb-4 p-4 bg-primary/10 rounded-lg border border-primary/30">
          <div class="flex items-center gap-2 mb-2">
            <CheckCircle2 class="w-5 h-5 text-green-500" />
            <span class="font-semibold">Текущая модель:</span>
            <span>{{ modelsData.current_model.name }}</span>
            <span v-if="modelsData.current_model.lora" class="px-2 py-0.5 bg-primary/20 rounded text-xs">
              + {{ modelsData.current_model.lora }} LoRA
            </span>
          </div>
          <p v-if="modelsData.current_model.description" class="text-sm text-muted-foreground">
            {{ modelsData.current_model.description }}
          </p>
        </div>

        <!-- Available Models Grid -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div
            v-for="(model, id) in modelsData?.available_models"
            :key="id"
            :class="[
              'p-4 rounded-lg border transition-all',
              modelsData?.current_model?.id === id
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-primary/50'
            ]"
          >
            <div class="flex items-center justify-between mb-2">
              <h3 class="font-semibold">{{ model.name }}</h3>
              <span v-if="modelsData?.current_model?.id === id" class="px-2 py-0.5 bg-green-500/20 text-green-600 rounded text-xs">
                Active
              </span>
            </div>

            <p class="text-sm text-muted-foreground mb-3">{{ model.description }}</p>

            <div class="flex flex-wrap gap-1 mb-3">
              <span
                v-for="feature in model.features"
                :key="feature"
                class="px-2 py-0.5 bg-secondary rounded-full text-xs"
              >
                {{ feature }}
              </span>
            </div>

            <div class="text-xs text-muted-foreground space-y-1">
              <div class="flex justify-between">
                <span>VRAM:</span>
                <span>{{ model.size }}</span>
              </div>
              <div v-if="model.lora_support" class="flex justify-between">
                <span>LoRA:</span>
                <span class="text-green-500">Поддерживается</span>
              </div>
            </div>

            <div class="mt-3 pt-3 border-t border-border flex items-center justify-between gap-2">
              <code class="text-xs bg-secondary px-2 py-1 rounded flex-1 overflow-hidden text-ellipsis">
                {{ model.vllm_model_name || model.full_name }}
              </code>
              <button
                v-if="modelsData?.current_model?.id !== id && (model.vllm_model_name || model.full_name)"
                class="px-3 py-1 bg-primary text-primary-foreground rounded text-xs hover:bg-primary/90 disabled:opacity-50 flex items-center gap-1"
                :disabled="switchingModel !== null"
                @click="setVllmModelMutation.mutate((model.vllm_model_name || model.full_name) as string)"
              >
                <Loader2 v-if="switchingModel === (model.vllm_model_name || model.full_name)" class="w-3 h-3 animate-spin" />
                <Play v-else class="w-3 h-3" />
                {{ switchingModel === (model.vllm_model_name || model.full_name) ? 'Загрузка...' : 'Выбрать' }}
              </button>
            </div>
          </div>
        </div>

        <p v-if="switchingModel" class="text-sm text-primary mt-4">
          <Loader2 class="w-4 h-4 inline mr-1 animate-spin" />
          Переключение на {{ switchingModel }}... Загрузка модели занимает 2-3 минуты.
        </p>
        <p v-else class="text-sm text-muted-foreground mt-4">
          <AlertCircle class="w-4 h-4 inline mr-1" />
          Смена модели перезапускает контейнер vLLM. Загрузка новой модели занимает 2-3 минуты.
        </p>
      </div>
    </div>

    <!-- Secretary Personas -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <User class="w-5 h-5" />
            {{ t('llm.personas') }}
          </h2>
          <p class="text-sm text-muted-foreground mt-1">
            {{ t('llm.personasDesc') }}
          </p>
        </div>
        <button
          class="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          @click="openCreatePersonaModal"
        >
          <Plus class="w-4 h-4" />
          {{ t('llm.addPersona') }}
        </button>
      </div>

      <div class="p-4">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="preset in presets"
            :key="preset.id"
            :class="[
              'p-4 rounded-lg border cursor-pointer transition-all',
              currentPresetId === preset.id
                ? 'border-primary bg-primary/10'
                : 'border-border hover:border-primary/50'
            ]"
            @click="activatePresetMutation.mutate(preset.id)"
          >
            <div class="flex items-start justify-between mb-2">
              <div>
                <div class="flex items-center gap-2">
                  <h3 class="font-semibold">{{ preset.name }}</h3>
                  <span
                    v-if="currentPresetId === preset.id"
                    class="px-2 py-0.5 bg-green-500/20 text-green-600 rounded text-xs"
                  >
                    {{ t('llm.active') }}
                  </span>
                </div>
                <p v-if="preset.description" class="text-sm text-muted-foreground mt-1">
                  {{ preset.description }}
                </p>
              </div>
            </div>

            <div class="text-xs text-muted-foreground space-y-1 mb-3">
              <div class="flex justify-between">
                <span>{{ t('llm.temperature') }}:</span>
                <span>{{ preset.temperature }}</span>
              </div>
              <div class="flex justify-between">
                <span>{{ t('llm.maxTokens') }}:</span>
                <span>{{ preset.max_tokens }}</span>
              </div>
            </div>

            <div class="flex items-center gap-2 pt-2 border-t border-border">
              <button
                class="flex items-center gap-1 px-2 py-1 text-xs bg-secondary rounded hover:bg-secondary/80 transition-colors"
                @click.stop="openEditPersonaModal(preset)"
              >
                <Edit2 class="w-3 h-3" />
                {{ t('llm.editPersona') }}
              </button>
              <button
                v-if="!builtinPresetIds.includes(preset.id)"
                :disabled="deletePresetMutation.isPending.value"
                class="flex items-center gap-1 px-2 py-1 text-xs bg-red-600/20 text-red-600 rounded hover:bg-red-600/30 transition-colors"
                @click.stop="confirmDeletePreset(preset)"
              >
                <Trash2 class="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Generation Parameters -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <Settings2 class="w-5 h-5" />
            {{ t('llm.parameters') }}
          </h2>
          <p class="text-sm text-muted-foreground">
            Parameters for current preset (vLLM only)
          </p>
        </div>
        <button
          :disabled="setParamsMutation.isPending.value"
          class="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
          @click="saveParams"
        >
          <Save class="w-4 h-4" />
          Save
        </button>
      </div>

      <div class="p-4 grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Temperature -->
        <div>
          <label class="flex items-center justify-between text-sm mb-2">
            <span>{{ t('llm.temperature') }}</span>
            <span class="text-muted-foreground">{{ localParams.temperature?.toFixed(2) }}</span>
          </label>
          <input
            v-model.number="localParams.temperature"
            type="range"
            min="0"
            max="2"
            step="0.05"
            class="w-full"
          />
          <p class="text-xs text-muted-foreground mt-1">Higher = more creative, lower = more focused</p>
        </div>

        <!-- Max Tokens -->
        <div>
          <label class="flex items-center justify-between text-sm mb-2">
            <span>{{ t('llm.maxTokens') }}</span>
            <span class="text-muted-foreground">{{ localParams.max_tokens }}</span>
          </label>
          <input
            v-model.number="localParams.max_tokens"
            type="range"
            min="64"
            max="2048"
            step="64"
            class="w-full"
          />
          <p class="text-xs text-muted-foreground mt-1">Maximum response length</p>
        </div>

        <!-- Top P -->
        <div>
          <label class="flex items-center justify-between text-sm mb-2">
            <span>{{ t('llm.topP') }}</span>
            <span class="text-muted-foreground">{{ localParams.top_p?.toFixed(2) }}</span>
          </label>
          <input
            v-model.number="localParams.top_p"
            type="range"
            min="0.1"
            max="1"
            step="0.05"
            class="w-full"
          />
          <p class="text-xs text-muted-foreground mt-1">Nucleus sampling threshold</p>
        </div>

        <!-- Repetition Penalty -->
        <div>
          <label class="flex items-center justify-between text-sm mb-2">
            <span>{{ t('llm.repetitionPenalty') }}</span>
            <span class="text-muted-foreground">{{ localParams.repetition_penalty?.toFixed(2) }}</span>
          </label>
          <input
            v-model.number="localParams.repetition_penalty"
            type="range"
            min="1"
            max="2"
            step="0.05"
            class="w-full"
          />
          <p class="text-xs text-muted-foreground mt-1">Higher = less repetition</p>
        </div>
      </div>
    </div>

    <!-- Conversation History -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border flex items-center justify-between">
        <h2 class="text-lg font-semibold">
          Conversation History
          <span v-if="historyData?.count" class="text-sm font-normal text-muted-foreground">
            ({{ historyData.count }} messages)
          </span>
        </h2>
        <div class="flex items-center gap-2">
          <button
            class="p-2 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors"
            @click="() => refetchHistory()"
          >
            <RotateCw class="w-4 h-4" />
          </button>
          <button
            :disabled="clearHistoryMutation.isPending.value || !historyData?.count"
            class="flex items-center gap-2 px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
            @click="clearHistoryMutation.mutate()"
          >
            <Trash2 class="w-4 h-4" />
            Clear
          </button>
        </div>
      </div>

      <div class="max-h-64 overflow-auto p-4">
        <div v-if="!historyData?.history?.length" class="text-muted-foreground text-center py-4">
          No conversation history
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="(msg, i) in historyData.history"
            :key="i"
            :class="[
              'p-3 rounded-lg',
              msg.role === 'user' ? 'bg-secondary' : 'bg-primary/10 ml-4'
            ]"
          >
            <div class="text-xs text-muted-foreground mb-1 capitalize">{{ msg.role }}</div>
            <div class="text-sm">{{ msg.content }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Persona Editor Modal -->
    <div
      v-if="showPersonaModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="showPersonaModal = false"
    >
      <div class="bg-card border border-border rounded-lg w-full max-w-2xl p-6 m-4 max-h-[90vh] overflow-auto">
        <h3 class="text-lg font-semibold mb-4 flex items-center gap-2">
          <User class="w-5 h-5" />
          {{ editingPreset ? t('llm.editPersona') : t('llm.newPersona') }}
        </h3>

        <div class="space-y-4">
          <!-- ID (only on create) -->
          <div v-if="!editingPreset">
            <label class="block text-sm font-medium mb-1">{{ t('llm.personaId') }}</label>
            <input
              v-model="presetForm.id"
              type="text"
              class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
              placeholder="my-persona"
            />
            <p class="text-xs text-muted-foreground mt-1">Auto-generated from name, or set manually</p>
          </div>

          <!-- Name -->
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('llm.personaName') }}</label>
            <input
              v-model="presetForm.name"
              type="text"
              class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Алиса"
            />
          </div>

          <!-- Description -->
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('llm.personaDesc') }}</label>
            <input
              v-model="presetForm.description"
              type="text"
              class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Дружелюбная и профессиональная секретарь"
            />
          </div>

          <!-- System Prompt -->
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('llm.personaPrompt') }}</label>
            <textarea
              v-model="presetForm.system_prompt"
              rows="10"
              class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none font-mono text-sm"
              placeholder="Ты — секретарь компании..."
            />
          </div>

          <!-- Generation Parameters (collapsible) -->
          <div class="border-t border-border pt-4">
            <button
              class="flex items-center gap-2 text-sm font-medium hover:text-primary transition-colors"
              @click="showGenParams = !showGenParams"
            >
              <ChevronDown v-if="!showGenParams" class="w-4 h-4" />
              <ChevronUp v-else class="w-4 h-4" />
              {{ t('llm.genParams') }}
            </button>

            <div v-if="showGenParams" class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              <!-- Temperature -->
              <div>
                <label class="flex items-center justify-between text-sm mb-2">
                  <span>{{ t('llm.temperature') }}</span>
                  <span class="text-muted-foreground">{{ presetForm.temperature.toFixed(2) }}</span>
                </label>
                <input
                  v-model.number="presetForm.temperature"
                  type="range"
                  min="0"
                  max="2"
                  step="0.05"
                  class="w-full"
                />
              </div>

              <!-- Max Tokens -->
              <div>
                <label class="flex items-center justify-between text-sm mb-2">
                  <span>{{ t('llm.maxTokens') }}</span>
                  <span class="text-muted-foreground">{{ presetForm.max_tokens }}</span>
                </label>
                <input
                  v-model.number="presetForm.max_tokens"
                  type="range"
                  min="64"
                  max="4096"
                  step="64"
                  class="w-full"
                />
              </div>

              <!-- Top P -->
              <div>
                <label class="flex items-center justify-between text-sm mb-2">
                  <span>{{ t('llm.topP') }}</span>
                  <span class="text-muted-foreground">{{ presetForm.top_p.toFixed(2) }}</span>
                </label>
                <input
                  v-model.number="presetForm.top_p"
                  type="range"
                  min="0.1"
                  max="1"
                  step="0.05"
                  class="w-full"
                />
              </div>

              <!-- Repetition Penalty -->
              <div>
                <label class="flex items-center justify-between text-sm mb-2">
                  <span>{{ t('llm.repetitionPenalty') }}</span>
                  <span class="text-muted-foreground">{{ presetForm.repetition_penalty.toFixed(2) }}</span>
                </label>
                <input
                  v-model.number="presetForm.repetition_penalty"
                  type="range"
                  min="1"
                  max="2"
                  step="0.05"
                  class="w-full"
                />
              </div>
            </div>
          </div>
        </div>

        <div class="flex justify-end gap-2 mt-6">
          <button
            class="px-4 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
            @click="showPersonaModal = false"
          >
            Cancel
          </button>
          <button
            :disabled="!presetForm.name || createPresetMutation.isPending.value || updatePresetMutation.isPending.value"
            class="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
            @click="savePersona"
          >
            <Loader2 v-if="createPresetMutation.isPending.value || updatePresetMutation.isPending.value" class="w-4 h-4 inline mr-1 animate-spin" />
            {{ editingPreset ? 'Update' : 'Create' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Cloud Provider Modal -->
    <div
      v-if="showProviderModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="showProviderModal = false"
    >
      <div class="bg-card border border-border rounded-lg w-full max-w-lg p-6 m-4 max-h-[90vh] overflow-auto">
        <h3 class="text-lg font-semibold mb-4 flex items-center gap-2">
          <Cloud class="w-5 h-5" />
          {{ editingProvider ? 'Edit Provider' : 'Add Cloud Provider' }}
        </h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium mb-1">Name</label>
            <input
              v-model="providerForm.name"
              type="text"
              class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="My Kimi Provider"
            />
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">Provider Type</label>
            <select
              v-model="providerForm.provider_type"
              class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              @change="onProviderTypeChange"
            >
              <option v-for="(type, key) in providersData?.provider_types" :key="key" :value="key">
                {{ type.name }}
              </option>
            </select>
          </div>

          <div v-if="!isBridgeProvider">
            <label class="block text-sm font-medium mb-1">API Key</label>
            <input
              v-model="providerForm.api_key"
              type="password"
              class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              :placeholder="editingProvider ? 'Leave empty to keep current' : 'Enter API key'"
            />
          </div>

          <div v-if="providersData?.provider_types?.[providerForm.provider_type]?.requires_base_url">
            <label class="block text-sm font-medium mb-1">Base URL</label>
            <input
              v-model="providerForm.base_url"
              type="text"
              class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="https://api.moonshot.ai/v1"
            />
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">Model</label>
            <select
              v-if="!useCustomModel"
              v-model="providerForm.model_name"
              class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option
                v-for="model in currentProviderModels"
                :key="model"
                :value="model"
              >
                {{ model }}
              </option>
              <option value="">— Other (custom) —</option>
            </select>
            <input
              v-else
              v-model="customModelName"
              type="text"
              class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="e.g. anthropic/claude-3.5-sonnet"
            />
            <button
              v-if="useCustomModel"
              class="mt-1 text-xs text-primary hover:underline"
              @click="useCustomModel = false; customModelName = ''"
            >
              ← Back to list
            </button>
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">Description (optional)</label>
            <input
              v-model="providerForm.description"
              type="text"
              class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Production Kimi instance"
            />
          </div>

          <!-- VLESS Proxy Section (Gemini only) -->
          <div v-if="isGeminiProvider" class="border-t border-border pt-4 mt-2">
            <div class="flex items-center gap-2 mb-3">
              <Shield class="w-4 h-4 text-purple-500" />
              <span class="text-sm font-medium">VLESS Proxy (optional)</span>
              <span
                v-if="proxyStatus?.xray_available"
                class="px-2 py-0.5 bg-green-500/20 text-green-600 rounded text-xs"
              >
                xray available
              </span>
              <span
                v-else
                class="px-2 py-0.5 bg-yellow-500/20 text-yellow-600 rounded text-xs"
              >
                xray not found
              </span>
            </div>

            <p class="text-xs text-muted-foreground mb-3">
              Configure VLESS proxies to route Google Gemini API requests. Add multiple URLs (one per line)
              for automatic failover when a proxy becomes unavailable.
            </p>

            <div class="space-y-3">
              <div>
                <label class="block text-sm font-medium mb-1">
                  VLESS URLs
                  <span class="text-muted-foreground font-normal">(one per line)</span>
                </label>
                <textarea
                  v-model="vlessUrlsText"
                  rows="4"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary font-mono text-xs resize-none"
                  placeholder="vless://uuid@host1:port?security=reality&pbk=...#proxy1
vless://uuid@host2:port?security=reality&pbk=...#proxy2"
                />
                <p class="text-xs text-muted-foreground mt-1">
                  {{ getVlessUrls().length }} valid URL(s) configured
                </p>
              </div>

              <!-- Test results (multiple) -->
              <div v-if="vlessTestResults.length > 0" class="space-y-2 max-h-32 overflow-auto">
                <div
                  v-for="(result, idx) in vlessTestResults"
                  :key="idx"
                  class="flex items-center gap-2 text-sm p-2 rounded bg-secondary/50"
                >
                  <CheckCircle2 v-if="result.success" class="w-4 h-4 text-green-500 flex-shrink-0" />
                  <AlertCircle v-else class="w-4 h-4 text-red-500 flex-shrink-0" />
                  <span class="font-mono text-xs truncate" :title="result.remark">
                    {{ result.remark || `Proxy ${idx + 1}` }}:
                  </span>
                  <span
                    :class="result.success ? 'text-green-600' : 'text-red-600'"
                    class="truncate text-xs"
                    :title="result.success ? result.message : result.error"
                  >
                    {{ result.success ? 'OK' : (result.error || 'Failed') }}
                  </span>
                </div>
              </div>

              <div class="flex gap-2">
                <button
                  :disabled="getVlessUrls().length === 0 || testingAllProxies || !proxyStatus?.xray_available"
                  class="flex items-center gap-2 px-3 py-1.5 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors text-sm"
                  @click="testAllProxies"
                >
                  <Loader2 v-if="testingAllProxies" class="w-4 h-4 animate-spin" />
                  <Wifi v-else class="w-4 h-4" />
                  Test All Proxies
                </button>
                <button
                  v-if="vlessUrlsText"
                  class="px-3 py-1.5 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors text-sm"
                  @click="vlessUrlsText = ''; vlessTestResults = []"
                >
                  Clear
                </button>
              </div>

              <p v-if="!proxyStatus?.xray_available" class="text-xs text-yellow-600">
                <AlertCircle class="w-3 h-3 inline mr-1" />
                xray-core binary not found. Install it to use VLESS proxy.
              </p>
            </div>
          </div>

          <!-- Bridge Settings (claude_bridge only) -->
          <div v-if="isBridgeProvider" class="border-t border-border pt-4 mt-2">
            <div class="flex items-center gap-2 mb-3">
              <Cpu class="w-4 h-4 text-blue-500" />
              <span class="text-sm font-medium">{{ t('llm.bridgeSettings') }}</span>
              <span
                v-if="bridgeStatusData?.is_running"
                class="px-2 py-0.5 bg-green-500/20 text-green-600 rounded text-xs"
              >
                {{ t('llm.bridgeRunning') }}
              </span>
              <span
                v-else
                class="px-2 py-0.5 bg-red-500/20 text-red-600 rounded text-xs"
              >
                {{ t('llm.bridgeStopped') }}
              </span>
            </div>

            <p class="text-xs text-muted-foreground mb-3">
              {{ t('llm.bridgeDescription') }}
            </p>

            <div class="space-y-3">
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('llm.bridgePermission') }}</label>
                <select
                  v-model="bridgePermission"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="chat">{{ t('llm.bridgePermissionChat') }}</option>
                  <option value="readonly">{{ t('llm.bridgePermissionReadonly') }}</option>
                  <option value="edit">{{ t('llm.bridgePermissionEdit') }}</option>
                  <option value="full">{{ t('llm.bridgePermissionFull') }}</option>
                </select>
              </div>

              <div>
                <label class="block text-sm font-medium mb-1">{{ t('llm.bridgePort') }}</label>
                <input
                  v-model.number="bridgePort"
                  type="number"
                  min="1024"
                  max="65535"
                  class="w-full px-3 py-2 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <input
              id="provider-enabled"
              v-model="providerForm.enabled"
              type="checkbox"
              class="w-4 h-4 rounded border-border"
            />
            <label for="provider-enabled" class="text-sm">Enabled</label>
          </div>
        </div>

        <div class="flex justify-end gap-2 mt-6">
          <button
            class="px-4 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
            @click="showProviderModal = false"
          >
            Cancel
          </button>
          <button
            :disabled="!providerForm.name || createProviderMutation.isPending.value || updateProviderMutation.isPending.value"
            class="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
            @click="saveProvider"
          >
            <Loader2 v-if="createProviderMutation.isPending.value || updateProviderMutation.isPending.value" class="w-4 h-4 inline mr-1 animate-spin" />
            {{ editingProvider ? 'Update' : 'Create' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
