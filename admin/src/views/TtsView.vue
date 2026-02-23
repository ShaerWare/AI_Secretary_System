<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { ttsApi, type Voice, type XttsParams } from '@/api'
import {
  Mic,
  Play,
  Volume2,
  Settings2,
  Plus,
  Trash2,
  Save,
  CheckCircle2
} from 'lucide-vue-next'
import { ref, computed, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const queryClient = useQueryClient()

// State
const testText = ref('Здравствуйте! Это тестовое сообщение для проверки голоса.')
const testAudioUrl = ref<string | null>(null)
const testLoading = ref(false)
const showCreatePreset = ref(false)
const newPresetName = ref('')

// Local params state
const localParams = ref<Partial<XttsParams>>({})

// Queries
const { data: voicesData, isLoading: voicesLoading } = useQuery({
  queryKey: ['tts-voices'],
  queryFn: () => ttsApi.getVoices(),
})

const { data: xttsParams } = useQuery({
  queryKey: ['tts-xtts-params'],
  queryFn: () => ttsApi.getXttsParams(),
})

const { data: presetsData } = useQuery({
  queryKey: ['tts-presets'],
  queryFn: () => ttsApi.getBuiltinPresets(),
})

const { data: customPresetsData, refetch: refetchCustomPresets } = useQuery({
  queryKey: ['tts-custom-presets'],
  queryFn: () => ttsApi.getCustomPresets(),
})

const { data: cacheData, refetch: refetchCache } = useQuery({
  queryKey: ['tts-cache'],
  queryFn: () => ttsApi.getCacheStats(),
})

// Watch xtts params
watch(xttsParams, (data) => {
  if (data?.current_params) {
    localParams.value = { ...data.current_params }
  }
}, { immediate: true })

// Mutations
const setVoiceMutation = useMutation({
  mutationFn: (voice: string) => ttsApi.setVoice(voice),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tts-voices'] }),
})

const setPresetMutation = useMutation({
  mutationFn: (preset: string) => ttsApi.setPreset(preset),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['tts-presets'] })
    queryClient.invalidateQueries({ queryKey: ['tts-xtts-params'] })
  },
})

const saveParamsMutation = useMutation({
  mutationFn: (params: Partial<XttsParams>) => ttsApi.setXttsParams(params),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tts-xtts-params'] }),
})

const createPresetMutation = useMutation({
  mutationFn: ({ name, params }: { name: string; params: Partial<XttsParams> }) =>
    ttsApi.createCustomPreset(name, params),
  onSuccess: () => {
    refetchCustomPresets()
    showCreatePreset.value = false
    newPresetName.value = ''
  },
})

const deletePresetMutation = useMutation({
  mutationFn: (name: string) => ttsApi.deleteCustomPreset(name),
  onSuccess: () => refetchCustomPresets(),
})

const clearCacheMutation = useMutation({
  mutationFn: () => ttsApi.clearCache(),
  onSuccess: () => refetchCache(),
})

// Computed
const voices = computed(() => voicesData.value?.voices || [])
const currentVoice = computed(() => voicesData.value?.current?.voice || '')
const currentEngine = computed(() => voicesData.value?.current?.engine || '')

const xttsVoices = computed(() => voices.value.filter(v => v.engine === 'xtts'))
const piperVoices = computed(() => voices.value.filter(v => v.engine === 'piper'))
const openvoiceVoices = computed(() => voices.value.filter(v => v.engine === 'openvoice'))

// Check if engine section is active (has the currently selected voice)
const isXttsActive = computed(() => currentEngine.value === 'xtts')
const isPiperActive = computed(() => currentEngine.value === 'piper')
const isOpenvoiceActive = computed(() => currentEngine.value === 'openvoice')

const presets = computed(() => presetsData.value?.presets || {})
const customPresets = computed(() => customPresetsData.value?.presets || {})
const currentPreset = computed(() => presetsData.value?.current || 'natural')

// Methods
async function testVoice(voiceId: string) {
  testLoading.value = true
  try {
    const blob = await ttsApi.testVoice(voiceId)
    if (testAudioUrl.value) {
      URL.revokeObjectURL(testAudioUrl.value)
    }
    testAudioUrl.value = URL.createObjectURL(blob)
  } catch (e) {
    console.error('Test failed:', e)
  } finally {
    testLoading.value = false
  }
}

const audioRef = ref<HTMLAudioElement | null>(null)

async function synthesizeTest() {
  testLoading.value = true
  try {
    const blob = await ttsApi.testSynthesize(testText.value, currentPreset.value)
    // Освобождаем предыдущий URL
    if (testAudioUrl.value) {
      URL.revokeObjectURL(testAudioUrl.value)
    }
    // Создаём URL для воспроизведения
    testAudioUrl.value = URL.createObjectURL(blob)
    // Автоматически воспроизводим
    setTimeout(() => {
      audioRef.value?.play()
    }, 100)
  } catch (e) {
    console.error('Synthesis failed:', e)
  } finally {
    testLoading.value = false
  }
}

function saveParams() {
  saveParamsMutation.mutate(localParams.value)
}

function createPreset() {
  if (newPresetName.value) {
    createPresetMutation.mutate({
      name: newPresetName.value,
      params: localParams.value,
    })
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Voice Selection -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border">
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <Mic class="w-5 h-5" />
          Voice Selection
        </h2>
        <p class="text-sm text-muted-foreground">
          Current: <strong>{{ currentVoice }}</strong> ({{ currentEngine }})
        </p>
      </div>

      <div class="p-4 space-y-6">
        <!-- XTTS Voices (hidden for web role) -->
        <div v-if="xttsVoices.length && authStore.canEdit('speech')" :class="['transition-opacity duration-200', !isXttsActive && 'opacity-60']">
          <div class="flex items-center gap-2 mb-3">
            <h3 class="text-sm font-medium text-muted-foreground">XTTS v2 (GPU CC >= 7.0)</h3>
            <span v-if="isXttsActive" class="px-2 py-0.5 text-xs font-medium bg-primary/20 text-primary rounded-full">
              Active
            </span>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div
              v-for="voice in xttsVoices"
              :key="voice.id"
              :class="[
                'p-4 rounded-lg border cursor-pointer transition-all',
                currentVoice === voice.id
                  ? 'border-primary bg-primary/10 ring-2 ring-primary/30'
                  : 'border-border hover:border-primary/50'
              ]"
              @click="setVoiceMutation.mutate(voice.id)"
            >
              <div class="flex items-center justify-between mb-2">
                <span class="font-medium">{{ voice.name }}</span>
                <CheckCircle2 v-if="currentVoice === voice.id" class="w-4 h-4 text-primary" />
              </div>
              <p class="text-xs text-muted-foreground mb-2">{{ voice.description }}</p>
              <div class="flex items-center justify-between">
                <span v-if="voice.samples_count" class="text-xs text-muted-foreground">
                  {{ voice.samples_count }} samples
                </span>
                <button
                  :disabled="testLoading"
                  class="p-1.5 rounded bg-secondary hover:bg-secondary/80 transition-colors"
                  @click.stop="testVoice(voice.id)"
                >
                  <Play class="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- OpenVoice Voices -->
        <div v-if="openvoiceVoices.length" :class="['transition-opacity duration-200', !isOpenvoiceActive && 'opacity-60']">
          <div class="flex items-center gap-2 mb-3">
            <h3 class="text-sm font-medium text-muted-foreground">OpenVoice v2 (GPU CC >= 6.1)</h3>
            <span v-if="isOpenvoiceActive" class="px-2 py-0.5 text-xs font-medium bg-primary/20 text-primary rounded-full">
              Active
            </span>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div
              v-for="voice in openvoiceVoices"
              :key="voice.id"
              :class="[
                'p-4 rounded-lg border cursor-pointer transition-all',
                currentVoice === voice.id
                  ? 'border-primary bg-primary/10 ring-2 ring-primary/30'
                  : 'border-border hover:border-primary/50'
              ]"
              @click="setVoiceMutation.mutate(voice.id)"
            >
              <div class="flex items-center justify-between mb-2">
                <span class="font-medium">{{ voice.name }}</span>
                <CheckCircle2 v-if="currentVoice === voice.id" class="w-4 h-4 text-primary" />
              </div>
              <p class="text-xs text-muted-foreground mb-2">{{ voice.description }}</p>
              <div class="flex justify-end">
                <button
                  :disabled="testLoading"
                  class="p-1.5 rounded bg-secondary hover:bg-secondary/80 transition-colors"
                  @click.stop="testVoice(voice.id)"
                >
                  <Play class="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Piper Voices -->
        <div v-if="piperVoices.length" :class="['transition-opacity duration-200', !isPiperActive && 'opacity-60']">
          <div class="flex items-center gap-2 mb-3">
            <h3 class="text-sm font-medium text-muted-foreground">Piper (CPU)</h3>
            <span v-if="isPiperActive" class="px-2 py-0.5 text-xs font-medium bg-primary/20 text-primary rounded-full">
              Active
            </span>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div
              v-for="voice in piperVoices"
              :key="voice.id"
              :class="[
                'p-4 rounded-lg border cursor-pointer transition-all',
                voice.available
                  ? currentVoice === voice.id
                    ? 'border-primary bg-primary/10 ring-2 ring-primary/30'
                    : 'border-border hover:border-primary/50'
                  : 'border-border opacity-50 cursor-not-allowed'
              ]"
              @click="voice.available && setVoiceMutation.mutate(voice.id)"
            >
              <div class="flex items-center justify-between mb-2">
                <span class="font-medium">{{ voice.name }}</span>
                <CheckCircle2 v-if="currentVoice === voice.id" class="w-4 h-4 text-primary" />
              </div>
              <p class="text-xs text-muted-foreground mb-2">{{ voice.description }}</p>
              <div v-if="voice.available" class="flex justify-end">
                <button
                  :disabled="testLoading"
                  class="p-1.5 rounded bg-secondary hover:bg-secondary/80 transition-colors"
                  @click.stop="testVoice(voice.id)"
                >
                  <Play class="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- XTTS Parameters (hidden for web role) -->
    <div v-if="currentEngine === 'xtts' && authStore.canEdit('speech')" class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border flex items-center justify-between">
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <Settings2 class="w-5 h-5" />
          XTTS Parameters
        </h2>
        <button
          :disabled="saveParamsMutation.isPending.value"
          class="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
          @click="saveParams"
        >
          <Save class="w-4 h-4" />
          Apply
        </button>
      </div>

      <div class="p-4">
        <!-- Presets -->
        <div class="mb-6">
          <h3 class="text-sm font-medium mb-3">Presets</h3>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="(preset, name) in presets"
              :key="name"
              :class="[
                'px-3 py-1.5 rounded-lg text-sm transition-colors',
                currentPreset === name
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary hover:bg-secondary/80'
              ]"
              @click="setPresetMutation.mutate(name as string)"
            >
              {{ preset.display_name }}
            </button>
          </div>
        </div>

        <!-- Parameters Grid -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <!-- Temperature -->
          <div>
            <label class="flex items-center justify-between text-sm mb-2">
              <span>Temperature</span>
              <span class="text-muted-foreground">{{ localParams.temperature?.toFixed(2) }}</span>
            </label>
            <input
              v-model.number="localParams.temperature"
              type="range"
              min="0.1"
              max="1"
              step="0.05"
              class="w-full"
            />
          </div>

          <!-- Speed -->
          <div>
            <label class="flex items-center justify-between text-sm mb-2">
              <span>Speed</span>
              <span class="text-muted-foreground">{{ localParams.speed?.toFixed(2) }}</span>
            </label>
            <input
              v-model.number="localParams.speed"
              type="range"
              min="0.5"
              max="2"
              step="0.05"
              class="w-full"
            />
          </div>

          <!-- Top K -->
          <div>
            <label class="flex items-center justify-between text-sm mb-2">
              <span>Top K</span>
              <span class="text-muted-foreground">{{ localParams.top_k }}</span>
            </label>
            <input
              v-model.number="localParams.top_k"
              type="range"
              min="1"
              max="100"
              step="1"
              class="w-full"
            />
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
          </div>

          <!-- Repetition Penalty -->
          <div>
            <label class="flex items-center justify-between text-sm mb-2">
              <span>Repetition Penalty</span>
              <span class="text-muted-foreground">{{ localParams.repetition_penalty?.toFixed(1) }}</span>
            </label>
            <input
              v-model.number="localParams.repetition_penalty"
              type="range"
              min="1"
              max="10"
              step="0.5"
              class="w-full"
            />
          </div>

          <!-- GPT Cond Length -->
          <div>
            <label class="flex items-center justify-between text-sm mb-2">
              <span>GPT Cond Length</span>
              <span class="text-muted-foreground">{{ localParams.gpt_cond_len }}s</span>
            </label>
            <input
              v-model.number="localParams.gpt_cond_len"
              type="range"
              min="6"
              max="30"
              step="1"
              class="w-full"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Custom Presets -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border flex items-center justify-between">
        <h2 class="text-lg font-semibold">Custom Presets</h2>
        <button
          class="flex items-center gap-2 px-3 py-1.5 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
          @click="showCreatePreset = true"
        >
          <Plus class="w-4 h-4" />
          Create
        </button>
      </div>

      <div class="p-4">
        <div v-if="!Object.keys(customPresets).length" class="text-center text-muted-foreground py-4">
          No custom presets yet
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="(params, name) in customPresets"
            :key="name"
            class="flex items-center justify-between p-3 bg-secondary rounded-lg"
          >
            <div>
              <span class="font-medium">{{ name }}</span>
              <span class="text-xs text-muted-foreground ml-2">
                temp={{ (params as any).temperature }}, speed={{ (params as any).speed }}
              </span>
            </div>
            <button
              class="p-1.5 text-red-500 hover:bg-red-500/20 rounded transition-colors"
              @click="deletePresetMutation.mutate(name as string)"
            >
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Cache Stats -->
    <div class="bg-card rounded-lg border border-border">
      <div class="p-4 border-b border-border flex items-center justify-between">
        <h2 class="text-lg font-semibold">TTS Cache</h2>
        <button
          :disabled="clearCacheMutation.isPending.value"
          class="flex items-center gap-2 px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
          @click="clearCacheMutation.mutate()"
        >
          <Trash2 class="w-4 h-4" />
          Clear
        </button>
      </div>
      <div class="p-4 grid grid-cols-2 gap-4">
        <div>
          <p class="text-sm text-muted-foreground">Cached Items</p>
          <p class="text-2xl font-bold">{{ cacheData?.cache_size || 0 }}</p>
        </div>
        <div>
          <p class="text-sm text-muted-foreground">Active Sessions</p>
          <p class="text-2xl font-bold">{{ cacheData?.active_sessions || 0 }}</p>
        </div>
      </div>
    </div>

    <!-- Test Synthesis -->
    <div class="bg-card rounded-lg border border-border p-4">
      <h2 class="text-lg font-semibold mb-4 flex items-center gap-2">
        <Volume2 class="w-5 h-5" />
        Test Synthesis
      </h2>
      <div class="space-y-4">
        <textarea
          v-model="testText"
          rows="3"
          placeholder="Enter text to synthesize..."
          class="w-full p-3 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
        />
        <div class="flex items-center gap-4">
          <button
            :disabled="testLoading || !testText"
            class="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
            @click="synthesizeTest"
          >
            <Play v-if="!testLoading" class="w-4 h-4" />
            <span v-else class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            {{ testLoading ? 'Synthesizing...' : 'Synthesize' }}
          </button>
        </div>
        <!-- Audio Player -->
        <div v-if="testAudioUrl" class="flex items-center gap-4 p-3 bg-secondary rounded-lg">
          <Volume2 class="w-5 h-5 text-muted-foreground flex-shrink-0" />
          <audio ref="audioRef" controls :src="testAudioUrl" class="flex-1 h-10" />
        </div>
      </div>
    </div>

    <!-- Create Preset Modal -->
    <div
      v-if="showCreatePreset"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="showCreatePreset = false"
    >
      <div class="bg-card border border-border rounded-lg w-full max-w-md p-6">
        <h3 class="text-lg font-semibold mb-4">Create Custom Preset</h3>
        <p class="text-sm text-muted-foreground mb-4">
          Save current parameters as a new preset
        </p>

        <input
          v-model="newPresetName"
          type="text"
          placeholder="Preset name..."
          class="w-full p-3 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary mb-4"
        />

        <div class="flex justify-end gap-2">
          <button
            class="px-4 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
            @click="showCreatePreset = false"
          >
            Cancel
          </button>
          <button
            :disabled="!newPresetName || createPresetMutation.isPending.value"
            class="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
            @click="createPreset"
          >
            Create
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
