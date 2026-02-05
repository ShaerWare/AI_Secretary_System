<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { finetuneApi, ttsFinetune, type TrainingConfig, type DatasetConfig, type VoiceSample, type TTSConfig, type TTSProcessingStatus, type TTSTrainingStatus } from '@/api'
import {
  Sparkles,
  Upload,
  PlayCircle,
  StopCircle,
  RefreshCw,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Database,
  Settings2,
  Loader2,
  FileJson,
  FolderOpen,
  Mic,
  User,
  MessageSquare,
  AudioWaveform,
  Edit3,
  Save,
  X,
  BookOpen,
  GraduationCap,
  ShieldAlert,
  FileText,
  Zap,
  Code2
} from 'lucide-vue-next'
import { ref, computed, watch, onUnmounted } from 'vue'

const queryClient = useQueryClient()

// Active tab
const activeTab = ref<'llm' | 'tts'>('llm')

// ============== LLM Training State ==============
const uploadingFile = ref<File | null>(null)
const trainingLog = ref<string[]>([])
const localConfig = ref<Partial<TrainingConfig>>({})
const datasetConfig = ref<Partial<DatasetConfig>>({
  owner_name: 'Артем Юрьевич',
  transcribe_voice: false,
  include_groups: false,
  output_name: 'dataset'
})
let logEventSource: { close: () => void } | null = null

// ============== Project Dataset State ==============
const projectDatasetConfig = ref({
  include_tz: true,
  include_faq: true,
  include_docs: true,
  include_escalation: true,
  include_code: true,
  output_name: 'project_dataset'
})
const projectDatasetResult = ref<{
  total_dialogs: number
  total_messages: number
  sources: Record<string, number>
} | null>(null)

// ============== TTS Training State ==============
const uploadingVoiceSamples = ref<File[]>([])
const editingSample = ref<string | null>(null)
const editingTranscript = ref('')
const ttsTrainingLog = ref<string[]>([])

// ============== LLM Queries ==============
const { data: statsData, refetch: refetchStats } = useQuery({
  queryKey: ['finetune-dataset-stats'],
  queryFn: () => finetuneApi.getDatasetStats(),
})

const { data: datasetsData, refetch: refetchDatasets } = useQuery({
  queryKey: ['finetune-datasets'],
  queryFn: () => finetuneApi.listDatasets(),
})

const { data: configData } = useQuery({
  queryKey: ['finetune-config'],
  queryFn: () => finetuneApi.getConfig(),
})

const { data: datasetConfigData } = useQuery({
  queryKey: ['finetune-dataset-config'],
  queryFn: () => finetuneApi.getDatasetConfig(),
})

const { data: processingStatusData, refetch: refetchProcessingStatus } = useQuery({
  queryKey: ['finetune-processing-status'],
  queryFn: () => finetuneApi.getProcessingStatus(),
  refetchInterval: (query) => query.state.data?.status?.is_running ? 1000 : false,
})

const { data: statusData, refetch: refetchStatus } = useQuery({
  queryKey: ['finetune-status'],
  queryFn: () => finetuneApi.getTrainingStatus(),
  refetchInterval: (query) => query.state.data?.status?.is_running ? 2000 : false,
})

const { data: adaptersData, refetch: refetchAdapters } = useQuery({
  queryKey: ['finetune-adapters'],
  queryFn: () => finetuneApi.listAdapters(),
})

// ============== TTS Queries ==============
const { data: ttsSamplesData, refetch: refetchTtsSamples } = useQuery({
  queryKey: ['tts-finetune-samples'],
  queryFn: () => ttsFinetune.getSamples(),
  enabled: computed(() => activeTab.value === 'tts'),
})

const { data: ttsConfigData } = useQuery({
  queryKey: ['tts-finetune-config'],
  queryFn: () => ttsFinetune.getConfig(),
  enabled: computed(() => activeTab.value === 'tts'),
})

const { data: ttsProcessingData, refetch: refetchTtsProcessing } = useQuery({
  queryKey: ['tts-finetune-processing'],
  queryFn: () => ttsFinetune.getProcessingStatus(),
  enabled: computed(() => activeTab.value === 'tts'),
  refetchInterval: (query) => query.state.data?.status?.is_running ? 1000 : false,
})

const { data: ttsTrainingData, refetch: refetchTtsTraining } = useQuery({
  queryKey: ['tts-finetune-training'],
  queryFn: () => ttsFinetune.getTrainingStatus(),
  enabled: computed(() => activeTab.value === 'tts'),
  refetchInterval: (query) => query.state.data?.status?.is_running ? 2000 : false,
})

const { data: ttsModelsData, refetch: refetchTtsModels } = useQuery({
  queryKey: ['tts-finetune-models'],
  queryFn: () => ttsFinetune.getTrainedModels(),
  enabled: computed(() => activeTab.value === 'tts'),
})

// Watch config data
watch(configData, (data) => {
  if (data?.config) {
    localConfig.value = { ...data.config }
  }
}, { immediate: true })

watch(datasetConfigData, (data) => {
  if (data?.config) {
    datasetConfig.value = { ...data.config }
  }
}, { immediate: true })

// ============== LLM Mutations ==============
const uploadMutation = useMutation({
  mutationFn: (file: File) => finetuneApi.uploadDataset(file),
  onSuccess: () => {
    refetchStats()
    refetchDatasets()
    uploadingFile.value = null
  },
})

const processMutation = useMutation({
  mutationFn: (config?: Partial<DatasetConfig>) => finetuneApi.processDataset(config),
  onSuccess: () => {
    refetchStats()
    refetchDatasets()
    refetchProcessingStatus()
  },
})

const saveConfigMutation = useMutation({
  mutationFn: (config: Partial<TrainingConfig>) => finetuneApi.setConfig(config),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['finetune-config'] }),
})

const startTrainingMutation = useMutation({
  mutationFn: () => finetuneApi.startTraining(),
  onSuccess: () => {
    refetchStatus()
    startLogStream()
  },
})

const stopTrainingMutation = useMutation({
  mutationFn: () => finetuneApi.stopTraining(),
  onSuccess: () => {
    refetchStatus()
    stopLogStream()
  },
})

const activateAdapterMutation = useMutation({
  mutationFn: (adapter: string) => finetuneApi.activateAdapter(adapter),
  onSuccess: () => refetchAdapters(),
})

const deleteAdapterMutation = useMutation({
  mutationFn: (name: string) => finetuneApi.deleteAdapter(name),
  onSuccess: () => refetchAdapters(),
})

const generateProjectMutation = useMutation({
  mutationFn: (config: typeof projectDatasetConfig.value) => finetuneApi.generateProjectDataset(config),
  onSuccess: (data) => {
    if (data.stats) {
      projectDatasetResult.value = data.stats
    }
    refetchStats()
    refetchDatasets()
  },
})

// ============== TTS Mutations ==============
const uploadTtsSampleMutation = useMutation({
  mutationFn: (file: File) => ttsFinetune.uploadSample(file),
  onSuccess: () => refetchTtsSamples(),
})

const deleteTtsSampleMutation = useMutation({
  mutationFn: (filename: string) => ttsFinetune.deleteSample(filename),
  onSuccess: () => refetchTtsSamples(),
})

const updateTranscriptMutation = useMutation({
  mutationFn: ({ filename, transcript }: { filename: string; transcript: string }) =>
    ttsFinetune.updateTranscript(filename, transcript),
  onSuccess: () => {
    refetchTtsSamples()
    editingSample.value = null
  },
})

const transcribeMutation = useMutation({
  mutationFn: () => ttsFinetune.transcribe(),
  onSuccess: () => refetchTtsProcessing(),
})

const prepareTtsDatasetMutation = useMutation({
  mutationFn: () => ttsFinetune.prepareDataset(),
  onSuccess: () => refetchTtsProcessing(),
})

const startTtsTrainingMutation = useMutation({
  mutationFn: () => ttsFinetune.startTraining(),
  onSuccess: () => refetchTtsTraining(),
})

const stopTtsTrainingMutation = useMutation({
  mutationFn: () => ttsFinetune.stopTraining(),
  onSuccess: () => refetchTtsTraining(),
})

// ============== LLM Computed ==============
const stats = computed(() => statsData.value?.stats)
const datasets = computed(() => datasetsData.value?.datasets || [])
const presets = computed(() => configData.value?.presets || {})
const status = computed(() => statusData.value?.status)
const processingStatus = computed(() => processingStatusData.value?.status)
const adapters = computed(() => adaptersData.value?.adapters || [])

const progressPercent = computed(() => {
  if (!status.value?.total_steps) return 0
  return Math.round((status.value.current_step / status.value.total_steps) * 100)
})

const processingPercent = computed(() => {
  if (!processingStatus.value?.total) return 0
  return Math.round((processingStatus.value.current / processingStatus.value.total) * 100)
})

const formattedEta = computed(() => {
  if (!status.value?.eta_seconds) return 'N/A'
  const minutes = Math.floor(status.value.eta_seconds / 60)
  const seconds = Math.floor(status.value.eta_seconds % 60)
  return `${minutes}m ${seconds}s`
})

// ============== TTS Computed ==============
const ttsSamples = computed(() => ttsSamplesData.value?.samples || [])
const ttsConfig = computed(() => ttsConfigData.value?.config)
const ttsProcessing = computed(() => ttsProcessingData.value?.status)
const ttsTraining = computed(() => ttsTrainingData.value?.status)
const ttsModels = computed(() => ttsModelsData.value?.models || [])

const samplesWithTranscript = computed(() => ttsSamples.value.filter(s => s.transcript))
const samplesWithoutTranscript = computed(() => ttsSamples.value.filter(s => !s.transcript))

const ttsProgressPercent = computed(() => {
  if (!ttsProcessing.value?.total) return 0
  return Math.round((ttsProcessing.value.current / ttsProcessing.value.total) * 100)
})

const ttsTrainingProgressPercent = computed(() => {
  if (!ttsTraining.value?.total_epochs) return 0
  return Math.round(((ttsTraining.value.current_epoch + (ttsTraining.value.current_step / 100)) / ttsTraining.value.total_epochs) * 100)
})

// ============== LLM Methods ==============
function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    uploadingFile.value = file
  }
}

function uploadFile() {
  if (uploadingFile.value) {
    uploadMutation.mutate(uploadingFile.value)
  }
}

function applyPreset(presetName: string) {
  const preset = presets.value[presetName]
  if (preset) {
    localConfig.value = { ...localConfig.value, ...preset }
  }
}

function saveConfig() {
  saveConfigMutation.mutate(localConfig.value)
}

function processDataset() {
  processMutation.mutate(datasetConfig.value)
}

function startLogStream() {
  trainingLog.value = []
  logEventSource = finetuneApi.streamTrainingLog((data) => {
    if (data.type === 'log' && data.line) {
      trainingLog.value.push(data.line)
      if (trainingLog.value.length > 1000) {
        trainingLog.value = trainingLog.value.slice(-500)
      }
    }
  })
}

function stopLogStream() {
  if (logEventSource) {
    logEventSource.close()
    logEventSource = null
  }
}

// ============== TTS Methods ==============
function handleVoiceSampleSelect(event: Event) {
  const target = event.target as HTMLInputElement
  const files = target.files
  if (files) {
    uploadingVoiceSamples.value = Array.from(files)
  }
}

async function uploadVoiceSamples() {
  for (const file of uploadingVoiceSamples.value) {
    await uploadTtsSampleMutation.mutateAsync(file)
  }
  uploadingVoiceSamples.value = []
}

function startEditTranscript(sample: VoiceSample) {
  editingSample.value = sample.filename
  editingTranscript.value = sample.transcript
}

function saveTranscript() {
  if (editingSample.value) {
    updateTranscriptMutation.mutate({
      filename: editingSample.value,
      transcript: editingTranscript.value
    })
  }
}

function cancelEditTranscript() {
  editingSample.value = null
  editingTranscript.value = ''
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

onUnmounted(() => {
  stopLogStream()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Tab Selector -->
    <div class="flex gap-2 border-b border-border pb-4">
      <button
        :class="[
          'flex items-center gap-2 px-4 py-2 rounded-lg transition-colors',
          activeTab === 'llm' ? 'bg-primary text-primary-foreground' : 'bg-secondary hover:bg-secondary/80'
        ]"
        @click="activeTab = 'llm'"
      >
        <MessageSquare class="w-4 h-4" />
        LLM Training
      </button>
      <button
        :class="[
          'flex items-center gap-2 px-4 py-2 rounded-lg transition-colors',
          activeTab === 'tts' ? 'bg-primary text-primary-foreground' : 'bg-secondary hover:bg-secondary/80'
        ]"
        @click="activeTab = 'tts'"
      >
        <AudioWaveform class="w-4 h-4" />
        TTS Training (Qwen3-TTS)
      </button>
    </div>

    <!-- ============== LLM TAB ============== -->
    <template v-if="activeTab === 'llm'">
      <!-- Project Dataset Generator -->
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <GraduationCap class="w-5 h-5" />
            Датасет из проекта
          </h2>
          <p class="text-sm text-muted-foreground mt-1">
            Генерация обучающих данных из ТЗ, FAQ, документации и шаблонов эскалации
          </p>
        </div>

        <div class="p-4 space-y-4">
          <!-- Sources checkboxes -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label class="flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-secondary/50 cursor-pointer transition-colors">
              <input v-model="projectDatasetConfig.include_tz" type="checkbox" class="w-4 h-4 rounded" />
              <BookOpen class="w-5 h-5 text-blue-500 flex-shrink-0" />
              <div>
                <p class="text-sm font-medium">Продажные сценарии (ТЗ)</p>
                <p class="text-xs text-muted-foreground">Тарифы, возражения, кейсы, воронка</p>
              </div>
            </label>

            <label class="flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-secondary/50 cursor-pointer transition-colors">
              <input v-model="projectDatasetConfig.include_faq" type="checkbox" class="w-4 h-4 rounded" />
              <MessageSquare class="w-5 h-5 text-green-500 flex-shrink-0" />
              <div>
                <p class="text-sm font-medium">FAQ из базы данных</p>
                <p class="text-xs text-muted-foreground">Типовые вопросы-ответы</p>
              </div>
            </label>

            <label class="flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-secondary/50 cursor-pointer transition-colors">
              <input v-model="projectDatasetConfig.include_docs" type="checkbox" class="w-4 h-4 rounded" />
              <FileText class="w-5 h-5 text-purple-500 flex-shrink-0" />
              <div>
                <p class="text-sm font-medium">Техническая документация</p>
                <p class="text-xs text-muted-foreground">Установка, настройка, API, модели</p>
              </div>
            </label>

            <label class="flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-secondary/50 cursor-pointer transition-colors">
              <input v-model="projectDatasetConfig.include_escalation" type="checkbox" class="w-4 h-4 rounded" />
              <ShieldAlert class="w-5 h-5 text-orange-500 flex-shrink-0" />
              <div>
                <p class="text-sm font-medium">Шаблоны эскалации</p>
                <p class="text-xs text-muted-foreground">Передача на старший уровень поддержки</p>
              </div>
            </label>

            <label class="flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-secondary/50 cursor-pointer transition-colors md:col-span-2">
              <input v-model="projectDatasetConfig.include_code" type="checkbox" class="w-4 h-4 rounded" />
              <Code2 class="w-5 h-5 text-cyan-500 flex-shrink-0" />
              <div>
                <p class="text-sm font-medium">Код и документация проекта</p>
                <p class="text-xs text-muted-foreground">API endpoints, модели, README, wiki-pages (~1000+ пар)</p>
              </div>
            </label>
          </div>

          <!-- Output name -->
          <div>
            <label class="block text-sm mb-1">Имя выходного файла</label>
            <input
              v-model="projectDatasetConfig.output_name" type="text" placeholder="project_dataset"
              class="w-full px-3 py-2 bg-secondary rounded-lg text-sm max-w-xs" />
          </div>

          <!-- Result stats -->
          <div v-if="projectDatasetResult" class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div class="p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
              <p class="text-xs text-muted-foreground">Диалогов</p>
              <p class="text-xl font-bold text-green-500">{{ projectDatasetResult.total_dialogs }}</p>
            </div>
            <div class="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
              <p class="text-xs text-muted-foreground">Сообщений</p>
              <p class="text-xl font-bold text-blue-500">{{ projectDatasetResult.total_messages }}</p>
            </div>
            <div v-for="(count, source) in projectDatasetResult.sources" :key="source" class="p-3 bg-secondary rounded-lg">
              <p class="text-xs text-muted-foreground">{{ source }}</p>
              <p class="text-xl font-bold">{{ count }}</p>
            </div>
          </div>

          <!-- Error -->
          <div v-if="generateProjectMutation.error.value" class="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-500 text-sm">
            <AlertCircle class="w-4 h-4 flex-shrink-0" />
            {{ generateProjectMutation.error.value }}
          </div>

          <!-- Generate button -->
          <button
            :disabled="generateProjectMutation.isPending.value"
            class="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
            @click="generateProjectMutation.mutate(projectDatasetConfig)">
            <Loader2 v-if="generateProjectMutation.isPending.value" class="w-4 h-4 animate-spin" />
            <Zap v-else class="w-4 h-4" />
            Сгенерировать датасет из проекта
          </button>
        </div>
      </div>

      <!-- Dataset Section (Telegram export) -->
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <Database class="w-5 h-5" />
            Dataset (Telegram Export)
          </h2>
        </div>

        <div class="p-4 space-y-4">
          <!-- Upload -->
          <div class="border-2 border-dashed border-border rounded-lg p-6 text-center">
            <Upload class="w-8 h-8 mx-auto text-muted-foreground mb-2" />
            <p class="text-sm text-muted-foreground mb-4">Upload Telegram export (result.json)</p>
            <input id="file-upload" type="file" accept=".json" class="hidden" @change="handleFileSelect" />
            <label for="file-upload" class="inline-block px-4 py-2 bg-secondary rounded-lg cursor-pointer hover:bg-secondary/80 transition-colors">
              Select File
            </label>
            <div v-if="uploadingFile" class="mt-4">
              <p class="text-sm">{{ uploadingFile.name }} ({{ (uploadingFile.size / 1024 / 1024).toFixed(2) }} MB)</p>
              <button
:disabled="uploadMutation.isPending.value" class="mt-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
                @click="uploadFile">
                <Loader2 v-if="uploadMutation.isPending.value" class="w-4 h-4 animate-spin inline mr-2" />
                Upload
              </button>
            </div>
          </div>

          <!-- Datasets List -->
          <div v-if="datasets.length" class="space-y-2">
            <h3 class="text-sm font-medium flex items-center gap-2">
              <FolderOpen class="w-4 h-4" />
              Available Datasets
            </h3>
            <div class="border border-border rounded-lg divide-y divide-border">
              <div v-for="dataset in datasets" :key="dataset.path" class="flex items-center justify-between p-3 hover:bg-secondary/50">
                <div class="flex items-center gap-3">
                  <FileJson class="w-5 h-5 text-muted-foreground" />
                  <div>
                    <p class="font-medium text-sm">{{ dataset.name }}</p>
                    <p class="text-xs text-muted-foreground">{{ dataset.size_mb }} MB</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Stats -->
          <div v-if="stats" class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="p-4 bg-secondary rounded-lg">
              <p class="text-sm text-muted-foreground">Sessions</p>
              <p class="text-2xl font-bold">{{ stats.total_sessions }}</p>
            </div>
            <div class="p-4 bg-secondary rounded-lg">
              <p class="text-sm text-muted-foreground">Messages</p>
              <p class="text-2xl font-bold">{{ stats.total_messages }}</p>
            </div>
            <div class="p-4 bg-secondary rounded-lg">
              <p class="text-sm text-muted-foreground">Tokens</p>
              <p class="text-2xl font-bold">{{ stats.total_tokens?.toLocaleString() }}</p>
            </div>
            <div class="p-4 bg-secondary rounded-lg">
              <p class="text-sm text-muted-foreground">File Size</p>
              <p class="text-2xl font-bold">{{ stats.file_size_mb }} MB</p>
            </div>
          </div>

          <!-- Dataset Config -->
          <div class="border border-border rounded-lg p-4 space-y-4">
            <h3 class="text-sm font-medium flex items-center gap-2">
              <Settings2 class="w-4 h-4" />
              Настройки обработки
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm mb-1 flex items-center gap-1">
                  <User class="w-3 h-3" />
                  Имя владельца (assistant)
                </label>
                <input
v-model="datasetConfig.owner_name" type="text" placeholder="Артем Юрьевич"
                  class="w-full px-3 py-2 bg-secondary rounded-lg text-sm" />
              </div>
              <div>
                <label class="block text-sm mb-1">Имя выходного файла</label>
                <input
v-model="datasetConfig.output_name" type="text" placeholder="dataset"
                  class="w-full px-3 py-2 bg-secondary rounded-lg text-sm" />
              </div>
            </div>
            <div class="flex flex-wrap gap-4">
              <label class="flex items-center gap-2 cursor-pointer">
                <input v-model="datasetConfig.transcribe_voice" type="checkbox" class="w-4 h-4 rounded" />
                <Mic class="w-4 h-4" />
                <span class="text-sm">Расшифровывать голосовые (Whisper)</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer">
                <input v-model="datasetConfig.include_groups" type="checkbox" class="w-4 h-4 rounded" />
                <span class="text-sm">Включать групповые чаты</span>
              </label>
            </div>
          </div>

          <!-- Processing Status -->
          <div v-if="processingStatus?.is_running" class="border border-primary/50 bg-primary/5 rounded-lg p-4 space-y-3">
            <div class="flex items-center gap-2">
              <Loader2 class="w-4 h-4 animate-spin text-primary" />
              <span class="text-sm font-medium">{{ processingStatus.stage }}</span>
            </div>
            <div class="h-2 bg-secondary rounded-full overflow-hidden">
              <div class="h-full bg-primary transition-all" :style="{ width: `${processingPercent}%` }" />
            </div>
          </div>

          <button
:disabled="processMutation.isPending.value || processingStatus?.is_running" class="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
            @click="processDataset">
            <Loader2 v-if="processMutation.isPending.value" class="w-4 h-4 animate-spin" />
            <FileJson v-else class="w-4 h-4" />
            Обработать Telegram Export
          </button>
        </div>
      </div>

      <!-- Training Config -->
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border flex items-center justify-between">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <Settings2 class="w-5 h-5" />
            Training Configuration
          </h2>
          <button
:disabled="saveConfigMutation.isPending.value" class="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
            @click="saveConfig">
            Save Config
          </button>
        </div>
        <div class="p-4">
          <div class="mb-6">
            <h3 class="text-sm font-medium mb-2">Presets</h3>
            <div class="flex gap-2">
              <button
v-for="(_, name) in presets" :key="name" class="px-3 py-1.5 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors text-sm"
                @click="applyPreset(name as string)">
                {{ name }}
              </button>
            </div>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div>
              <label class="block text-sm mb-1">LoRA Rank</label>
              <input v-model.number="localConfig.lora_rank" type="number" class="w-full px-3 py-2 bg-secondary rounded-lg" />
            </div>
            <div>
              <label class="block text-sm mb-1">LoRA Alpha</label>
              <input v-model.number="localConfig.lora_alpha" type="number" class="w-full px-3 py-2 bg-secondary rounded-lg" />
            </div>
            <div>
              <label class="block text-sm mb-1">Batch Size</label>
              <input v-model.number="localConfig.batch_size" type="number" class="w-full px-3 py-2 bg-secondary rounded-lg" />
            </div>
            <div>
              <label class="block text-sm mb-1">Learning Rate</label>
              <input v-model.number="localConfig.learning_rate" type="number" step="0.00001" class="w-full px-3 py-2 bg-secondary rounded-lg" />
            </div>
            <div>
              <label class="block text-sm mb-1">Epochs</label>
              <input v-model.number="localConfig.num_epochs" type="number" class="w-full px-3 py-2 bg-secondary rounded-lg" />
            </div>
            <div>
              <label class="block text-sm mb-1">Max Seq Length</label>
              <input v-model.number="localConfig.max_seq_length" type="number" class="w-full px-3 py-2 bg-secondary rounded-lg" />
            </div>
          </div>
        </div>
      </div>

      <!-- Training Status -->
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border flex items-center justify-between">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <PlayCircle class="w-5 h-5" />
            Training
          </h2>
          <div class="flex gap-2">
            <button
v-if="!status?.is_running" :disabled="startTrainingMutation.isPending.value" class="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
              @click="startTrainingMutation.mutate()">
              <PlayCircle class="w-4 h-4" />
              Start
            </button>
            <button
v-else :disabled="stopTrainingMutation.isPending.value" class="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
              @click="stopTrainingMutation.mutate()">
              <StopCircle class="w-4 h-4" />
              Stop
            </button>
          </div>
        </div>
        <div class="p-4">
          <div v-if="status?.is_running" class="space-y-4">
            <div>
              <div class="flex justify-between text-sm mb-1">
                <span>Progress</span>
                <span>{{ status.current_step }} / {{ status.total_steps }} ({{ progressPercent }}%)</span>
              </div>
              <div class="h-2 bg-secondary rounded-full overflow-hidden">
                <div class="h-full bg-primary transition-all" :style="{ width: `${progressPercent}%` }" />
              </div>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p class="text-sm text-muted-foreground">Epoch</p>
                <p class="font-medium">{{ status.current_epoch }} / {{ status.total_epochs }}</p>
              </div>
              <div>
                <p class="text-sm text-muted-foreground">Loss</p>
                <p class="font-medium">{{ status.loss?.toFixed(4) }}</p>
              </div>
              <div>
                <p class="text-sm text-muted-foreground">Learning Rate</p>
                <p class="font-medium">{{ status.learning_rate?.toExponential(2) }}</p>
              </div>
              <div>
                <p class="text-sm text-muted-foreground">ETA</p>
                <p class="font-medium">{{ formattedEta }}</p>
              </div>
            </div>
          </div>
          <div v-else-if="status?.error" class="flex items-center gap-2 text-red-500">
            <AlertCircle class="w-5 h-5" />
            {{ status.error }}
          </div>
          <div v-else class="text-muted-foreground text-center py-4">Training not running</div>
          <div v-if="trainingLog.length" class="mt-4">
            <h3 class="text-sm font-medium mb-2">Training Log</h3>
            <div class="h-48 overflow-auto bg-background rounded-lg p-3 font-mono text-xs">
              <div v-for="(line, i) in trainingLog.slice(-100)" :key="i" class="text-muted-foreground">{{ line }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Adapters -->
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border flex items-center justify-between">
          <h2 class="text-lg font-semibold">LoRA Adapters</h2>
          <button class="p-2 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors" @click="() => refetchAdapters()">
            <RefreshCw class="w-4 h-4" />
          </button>
        </div>
        <div v-if="!adapters.length" class="p-8 text-center text-muted-foreground">No adapters found</div>
        <div v-else class="divide-y divide-border">
          <div v-for="adapter in adapters" :key="adapter.name" class="flex items-center justify-between p-4">
            <div class="flex items-center gap-3">
              <CheckCircle2 v-if="adapter.active" class="w-5 h-5 text-green-500" />
              <div v-else class="w-5 h-5 rounded-full border-2 border-border" />
              <div>
                <p class="font-medium">{{ adapter.name }}</p>
                <p class="text-sm text-muted-foreground">{{ adapter.size_mb }} MB</p>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button
v-if="!adapter.active" :disabled="activateAdapterMutation.isPending.value" class="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors text-sm"
                @click="activateAdapterMutation.mutate(adapter.name)">
                Activate
              </button>
              <button
v-if="!adapter.active" :disabled="deleteAdapterMutation.isPending.value" class="p-2 text-red-500 hover:bg-red-500/20 rounded-lg transition-colors"
                @click="deleteAdapterMutation.mutate(adapter.name)">
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ============== TTS TAB ============== -->
    <template v-if="activeTab === 'tts'">
      <!-- Voice Samples Section -->
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <Mic class="w-5 h-5" />
            Voice Samples
          </h2>
        </div>

        <div class="p-4 space-y-4">
          <!-- Upload -->
          <div class="border-2 border-dashed border-border rounded-lg p-6 text-center">
            <Upload class="w-8 h-8 mx-auto text-muted-foreground mb-2" />
            <p class="text-sm text-muted-foreground mb-4">Upload WAV files with your voice</p>
            <input id="voice-upload" type="file" accept=".wav,.mp3,.ogg" multiple class="hidden" @change="handleVoiceSampleSelect" />
            <label for="voice-upload" class="inline-block px-4 py-2 bg-secondary rounded-lg cursor-pointer hover:bg-secondary/80 transition-colors">
              Select Files
            </label>
            <div v-if="uploadingVoiceSamples.length" class="mt-4">
              <p class="text-sm">{{ uploadingVoiceSamples.length }} files selected</p>
              <button
:disabled="uploadTtsSampleMutation.isPending.value" class="mt-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
                @click="uploadVoiceSamples">
                <Loader2 v-if="uploadTtsSampleMutation.isPending.value" class="w-4 h-4 animate-spin inline mr-2" />
                Upload All
              </button>
            </div>
          </div>

          <!-- Samples Stats -->
          <div class="grid grid-cols-3 gap-4">
            <div class="p-4 bg-secondary rounded-lg">
              <p class="text-sm text-muted-foreground">Total Samples</p>
              <p class="text-2xl font-bold">{{ ttsSamples.length }}</p>
            </div>
            <div class="p-4 bg-secondary rounded-lg">
              <p class="text-sm text-muted-foreground">Transcribed</p>
              <p class="text-2xl font-bold text-green-500">{{ samplesWithTranscript.length }}</p>
            </div>
            <div class="p-4 bg-secondary rounded-lg">
              <p class="text-sm text-muted-foreground">Pending</p>
              <p class="text-2xl font-bold text-orange-500">{{ samplesWithoutTranscript.length }}</p>
            </div>
          </div>

          <!-- Samples List -->
          <div v-if="ttsSamples.length" class="space-y-2">
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-medium">Voice Samples</h3>
              <button class="p-1.5 rounded-lg hover:bg-secondary transition-colors" @click="() => refetchTtsSamples()">
                <RefreshCw class="w-4 h-4" />
              </button>
            </div>
            <div class="border border-border rounded-lg divide-y divide-border max-h-96 overflow-auto">
              <div v-for="sample in ttsSamples" :key="sample.filename" class="p-3">
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-3 flex-1 min-w-0">
                    <AudioWaveform class="w-5 h-5 text-muted-foreground flex-shrink-0" />
                    <div class="min-w-0">
                      <p class="font-medium text-sm truncate">{{ sample.filename }}</p>
                      <p class="text-xs text-muted-foreground">
                        {{ formatDuration(sample.duration_sec) }} | {{ sample.size_kb.toFixed(1) }} KB
                        <span v-if="sample.transcript_edited" class="text-green-500 ml-2">edited</span>
                      </p>
                    </div>
                  </div>
                  <div class="flex items-center gap-2 flex-shrink-0">
                    <button class="p-1.5 hover:bg-secondary rounded-lg transition-colors" @click="startEditTranscript(sample)">
                      <Edit3 class="w-4 h-4" />
                    </button>
                    <button
:disabled="deleteTtsSampleMutation.isPending.value" class="p-1.5 text-red-500 hover:bg-red-500/20 rounded-lg transition-colors"
                      @click="deleteTtsSampleMutation.mutate(sample.filename)">
                      <Trash2 class="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <!-- Transcript Editor -->
                <div v-if="editingSample === sample.filename" class="mt-3 space-y-2">
                  <textarea
v-model="editingTranscript" rows="3" class="w-full px-3 py-2 bg-secondary rounded-lg text-sm"
                    placeholder="Enter transcript..." />
                  <div class="flex gap-2">
                    <button
:disabled="updateTranscriptMutation.isPending.value" class="flex items-center gap-1 px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm"
                      @click="saveTranscript">
                      <Save class="w-3 h-3" />
                      Save
                    </button>
                    <button
class="flex items-center gap-1 px-3 py-1.5 bg-secondary rounded-lg hover:bg-secondary/80 text-sm"
                      @click="cancelEditTranscript">
                      <X class="w-3 h-3" />
                      Cancel
                    </button>
                  </div>
                </div>

                <!-- Show transcript if not editing -->
                <div v-else-if="sample.transcript" class="mt-2 px-3 py-2 bg-secondary/50 rounded-lg text-sm text-muted-foreground">
                  {{ sample.transcript }}
                </div>
              </div>
            </div>
          </div>

          <!-- Transcription Button -->
          <div class="flex gap-2">
            <button
:disabled="transcribeMutation.isPending.value || ttsProcessing?.is_running || !samplesWithoutTranscript.length" class="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
              @click="transcribeMutation.mutate()">
              <Loader2 v-if="transcribeMutation.isPending.value || (ttsProcessing?.is_running && ttsProcessing?.stage === 'transcribing')" class="w-4 h-4 animate-spin" />
              <Mic v-else class="w-4 h-4" />
              Transcribe with Whisper ({{ samplesWithoutTranscript.length }})
            </button>
          </div>

          <!-- Processing Status -->
          <div v-if="ttsProcessing?.is_running" class="border border-primary/50 bg-primary/5 rounded-lg p-4 space-y-3">
            <div class="flex items-center gap-2">
              <Loader2 class="w-4 h-4 animate-spin text-primary" />
              <span class="text-sm font-medium">{{ ttsProcessing.message || ttsProcessing.stage }}</span>
            </div>
            <div v-if="ttsProcessing.total > 0" class="h-2 bg-secondary rounded-full overflow-hidden">
              <div class="h-full bg-primary transition-all" :style="{ width: `${ttsProgressPercent}%` }" />
            </div>
          </div>
        </div>
      </div>

      <!-- Dataset Preparation -->
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <Database class="w-5 h-5" />
            Dataset Preparation
          </h2>
        </div>

        <div class="p-4 space-y-4">
          <p class="text-sm text-muted-foreground">
            Prepare dataset for training by extracting audio codes from transcribed samples.
            Requires at least one sample with transcript.
          </p>

          <button
:disabled="prepareTtsDatasetMutation.isPending.value || ttsProcessing?.is_running || !samplesWithTranscript.length"
            class="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
            @click="prepareTtsDatasetMutation.mutate()">
            <Loader2 v-if="prepareTtsDatasetMutation.isPending.value || (ttsProcessing?.is_running && ttsProcessing?.stage === 'preparing')" class="w-4 h-4 animate-spin" />
            <FileJson v-else class="w-4 h-4" />
            Prepare Dataset ({{ samplesWithTranscript.length }} samples)
          </button>
        </div>
      </div>

      <!-- TTS Training -->
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border flex items-center justify-between">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <Sparkles class="w-5 h-5" />
            Training (Qwen3-TTS)
          </h2>
          <div class="flex gap-2">
            <button
v-if="!ttsTraining?.is_running" :disabled="startTtsTrainingMutation.isPending.value" class="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
              @click="startTtsTrainingMutation.mutate()">
              <PlayCircle class="w-4 h-4" />
              Start Training
            </button>
            <button
v-else :disabled="stopTtsTrainingMutation.isPending.value" class="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
              @click="stopTtsTrainingMutation.mutate()">
              <StopCircle class="w-4 h-4" />
              Stop
            </button>
          </div>
        </div>

        <div class="p-4">
          <div v-if="ttsTraining?.is_running" class="space-y-4">
            <div>
              <div class="flex justify-between text-sm mb-1">
                <span>Epoch {{ ttsTraining.current_epoch }} / {{ ttsTraining.total_epochs }}</span>
                <span>Step {{ ttsTraining.current_step }}</span>
              </div>
              <div class="h-2 bg-secondary rounded-full overflow-hidden">
                <div class="h-full bg-primary transition-all" :style="{ width: `${ttsTrainingProgressPercent}%` }" />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <p class="text-sm text-muted-foreground">Loss</p>
                <p class="font-medium">{{ ttsTraining.loss?.toFixed(4) }}</p>
              </div>
              <div>
                <p class="text-sm text-muted-foreground">Elapsed</p>
                <p class="font-medium">{{ Math.floor(ttsTraining.elapsed_seconds / 60) }}m</p>
              </div>
            </div>
          </div>
          <div v-else-if="ttsTraining?.error" class="flex items-center gap-2 text-red-500">
            <AlertCircle class="w-5 h-5" />
            {{ ttsTraining.error }}
          </div>
          <div v-else class="text-muted-foreground text-center py-4">Training not running</div>
        </div>
      </div>

      <!-- Trained TTS Models -->
      <div class="bg-card rounded-lg border border-border">
        <div class="p-4 border-b border-border flex items-center justify-between">
          <h2 class="text-lg font-semibold">Trained TTS Models</h2>
          <button class="p-2 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors" @click="() => refetchTtsModels()">
            <RefreshCw class="w-4 h-4" />
          </button>
        </div>
        <div v-if="!ttsModels.length" class="p-8 text-center text-muted-foreground">No trained models yet</div>
        <div v-else class="divide-y divide-border">
          <div v-for="model in ttsModels" :key="model.name" class="flex items-center justify-between p-4">
            <div>
              <p class="font-medium">{{ model.name }}</p>
              <p class="text-sm text-muted-foreground">{{ model.epochs }} epochs | {{ model.modified }}</p>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
