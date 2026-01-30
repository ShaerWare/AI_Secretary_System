<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { llmApi, type LlmParams, type CloudProvider } from '@/api'
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
  Sparkles,
  Code,
  Languages,
  Cloud,
  CloudOff,
  Plus,
  Edit2,
  Play,
  Star,
  RefreshCw
} from 'lucide-vue-next'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToastStore } from '@/stores/toast'

const { t } = useI18n()
const queryClient = useQueryClient()
const toast = useToastStore()

// State
const editingPrompt = ref(false)
const promptText = ref('')
const selectedPersonaForPrompt = ref('gulya')
const stopUnusedVllm = ref(false)

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

// Queries
const { data: backendData, isLoading: backendLoading } = useQuery({
  queryKey: ['llm-backend'],
  queryFn: () => llmApi.getBackend(),
})

const { data: modelsData } = useQuery({
  queryKey: ['llm-models'],
  queryFn: () => llmApi.getModels(),
})

const { data: personasData } = useQuery({
  queryKey: ['llm-personas'],
  queryFn: () => llmApi.getPersonas(),
})

const { data: currentPersonaData } = useQuery({
  queryKey: ['llm-persona'],
  queryFn: () => llmApi.getCurrentPersona(),
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

// Mutations
const setBackendMutation = useMutation({
  mutationFn: (backend: string) => llmApi.setBackend(backend, backend === 'gemini' && stopUnusedVllm.value),
  onSuccess: (data) => {
    queryClient.invalidateQueries({ queryKey: ['llm-backend'] })
    toast.success(data.message || `Переключено на ${data.backend}`)
  },
  onError: (error: Error) => {
    toast.error(`Ошибка переключения: ${error.message}`)
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
  mutationFn: (id: string) => llmApi.testProvider(id),
  onSuccess: (data) => {
    if (data.available) {
      toast.success(`Connection OK: ${data.test_response?.substring(0, 50)}`)
    } else {
      toast.error(`Connection failed: ${data.message}`)
    }
  },
  onError: (error: Error) => {
    toast.error(`Test failed: ${error.message}`)
  },
})

const setPersonaMutation = useMutation({
  mutationFn: (persona: string) => llmApi.setPersona(persona),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['llm-persona'] })
    queryClient.invalidateQueries({ queryKey: ['llm-history'] })
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

const savePromptMutation = useMutation({
  mutationFn: ({ persona, prompt }: { persona: string; prompt: string }) =>
    llmApi.setPrompt(persona, prompt),
  onSuccess: () => {
    editingPrompt.value = false
  },
})

// Computed
const personas = computed(() => personasData.value?.personas || {})

const isVllm = computed(() => backendData.value?.backend === 'vllm')
const isCloudBackend = computed(() => backendData.value?.backend?.startsWith('cloud:'))
const currentCloudProviderId = computed(() => {
  if (isCloudBackend.value && backendData.value?.backend) {
    return backendData.value.backend.split(':')[1]
  }
  return null
})

// Methods
async function loadPromptForEdit(personaId: string) {
  selectedPersonaForPrompt.value = personaId
  try {
    const response = await llmApi.getPrompt(personaId)
    promptText.value = response.prompt
    editingPrompt.value = true
  } catch (e) {
    console.error('Failed to load prompt:', e)
  }
}

function saveParams() {
  setParamsMutation.mutate(localParams.value)
}

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
}

function saveProvider() {
  const data = { ...providerForm.value }

  // Используем кастомную модель если выбрана опция "Другая"
  if (useCustomModel.value && customModelName.value) {
    data.model_name = customModelName.value
  }

  if (!data.api_key) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (data as any).api_key // Don't update if empty
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
          <!-- Backend Toggle -->
          <div class="flex items-center gap-4">
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
                :disabled="setBackendMutation.isPending.value"
                :class="[
                  'px-4 py-2 rounded-lg transition-colors flex items-center justify-center gap-2',
                  !isVllm ? 'bg-primary text-primary-foreground' : 'hover:bg-secondary/80',
                  setBackendMutation.isPending.value && 'opacity-50 cursor-not-allowed'
                ]"
                @click="setBackendMutation.mutate('gemini')"
              >
                <Loader2 v-if="setBackendMutation.isPending.value && isVllm" class="w-4 h-4 animate-spin" />
                {{ t('llm.cloudAI') }}
              </button>
            </div>
          </div>

          <!-- Status -->
          <div class="flex items-center gap-2 text-sm">
            <Loader2 v-if="setBackendMutation.isPending.value" class="w-4 h-4 animate-spin text-primary" />
            <CheckCircle2 v-else class="w-4 h-4 text-green-500" />
            <span v-if="setBackendMutation.isPending.value" class="text-muted-foreground">
              Переключение... (vLLM может запускаться до 2 минут)
            </span>
            <span v-else>
              Current: <strong>{{ backendData?.backend }}</strong>
              <span v-if="backendData?.model" class="text-muted-foreground">
                ({{ backendData.model }})
              </span>
            </span>
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
                  :disabled="testProviderMutation.isPending.value"
                  class="p-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
                  title="Test connection"
                  @click="testProviderMutation.mutate(provider.id)"
                >
                  <Loader2 v-if="testProviderMutation.isPending.value" class="w-4 h-4 animate-spin" />
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

    <!-- Available Models (vLLM) -->
    <div v-if="isVllm" class="bg-card rounded-lg border border-border">
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

            <div class="mt-3 pt-3 border-t border-border">
              <code class="text-xs bg-secondary px-2 py-1 rounded block">
                ./start_gpu.sh {{ model.start_flag || '' }}
              </code>
            </div>
          </div>
        </div>

        <p class="text-sm text-muted-foreground mt-4">
          <AlertCircle class="w-4 h-4 inline mr-1" />
          Для смены модели перезапустите систему с нужным флагом. Hot-swap требует рестарта vLLM.
        </p>
      </div>
    </div>

    <!-- Persona Selection -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border">
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <User class="w-5 h-5" />
          Secretary Persona
        </h2>
      </div>

      <div class="p-4">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div
            v-for="(persona, id) in personas"
            :key="id"
            :class="[
              'p-4 rounded-lg border cursor-pointer transition-all',
              currentPersonaData?.id === id
                ? 'border-primary bg-primary/10'
                : 'border-border hover:border-primary/50'
            ]"
            @click="setPersonaMutation.mutate(id as string)"
          >
            <div class="font-medium">{{ persona.name }}</div>
            <div class="text-sm text-muted-foreground">{{ persona.full_name }}</div>
            <button
              class="mt-2 text-xs text-primary hover:underline"
              @click.stop="loadPromptForEdit(id as string)"
            >
              Edit Prompt
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Generation Parameters -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border flex items-center justify-between">
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <Settings2 class="w-5 h-5" />
          Generation Parameters
        </h2>
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
            <span>Temperature</span>
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
            <span>Max Tokens</span>
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
            <span>Top P</span>
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
            <span>Repetition Penalty</span>
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

    <!-- Prompt Editor Modal -->
    <div
      v-if="editingPrompt"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="editingPrompt = false"
    >
      <div class="bg-card border border-border rounded-lg w-full max-w-2xl p-6">
        <h3 class="text-lg font-semibold mb-4">
          Edit System Prompt: {{ personas[selectedPersonaForPrompt]?.name }}
        </h3>

        <textarea
          v-model="promptText"
          rows="15"
          class="w-full p-3 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none font-mono text-sm"
        />

        <div class="flex justify-end gap-2 mt-4">
          <button
            class="px-4 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
            @click="editingPrompt = false"
          >
            Cancel
          </button>
          <button
            :disabled="savePromptMutation.isPending.value"
            class="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
            @click="savePromptMutation.mutate({ persona: selectedPersonaForPrompt, prompt: promptText })"
          >
            Save Prompt
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
      <div class="bg-card border border-border rounded-lg w-full max-w-lg p-6 m-4">
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

          <div>
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
