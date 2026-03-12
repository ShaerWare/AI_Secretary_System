<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { useResponsive } from '@/composables/useResponsive'
import {
  Smartphone,
  Plus,
  X,
  Power,
  Loader2,
  Trash2,
  Edit3,
  ChevronRight,
  Cpu,
  Volume2,
  Settings2,
  BookOpen,
  Share2,
  Users
} from 'lucide-vue-next'
import { mobileInstancesApi, llmApi, type MobileAppInstance, type CloudProvider } from '@/api'
import { wikiRagApi } from '@/api/wikiRag'
import { useToastStore } from '@/stores/toast'
import ResourceShareDialog from '@/components/ResourceShareDialog.vue'

const { t } = useI18n()
const queryClient = useQueryClient()
const toast = useToastStore()
const { isMobile } = useResponsive()

const showMobileList = ref(true)
const selectedInstanceId = ref<string | null>(null)
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showShareDialog = ref(false)
const activeTab = ref<'settings' | 'ai' | 'rag'>('settings')

const formData = ref<Partial<MobileAppInstance>>({
  name: '',
  description: '',
  enabled: true,
  llm_backend: 'vllm',
  llm_persona: 'anna',
  system_prompt: '',
  llm_params: {},
  tts_engine: 'xtts',
  tts_voice: 'anna',
  tts_preset: '',
  rag_mode: 'all',
  knowledge_collection_ids: [],
  rate_limit_count: null,
  rate_limit_hours: null,
})

// Queries
const { data: instancesData, isLoading } = useQuery({
  queryKey: ['mobile-instances'],
  queryFn: () => mobileInstancesApi.list(),
})
const instances = computed(() => instancesData.value?.instances || [])

const selectedInstance = computed(() =>
  instances.value.find(i => i.id === selectedInstanceId.value) || null
)

const { data: cloudProvidersData } = useQuery({
  queryKey: ['llm-providers'],
  queryFn: () => llmApi.getProviders(),
})
const cloudProviders = computed(() => cloudProvidersData.value?.providers || [])

const { data: collectionsData } = useQuery({
  queryKey: ['knowledge-collections'],
  queryFn: () => wikiRagApi.getCollections(),
})
const knowledgeCollections = computed(() => collectionsData.value?.collections || [])

// LLM backend options
const llmOptions = computed(() => {
  const opts: { value: string; label: string }[] = [
    { value: 'vllm', label: 'Local vLLM' },
  ]
  for (const p of cloudProviders.value) {
    opts.push({ value: `cloud:${p.id}`, label: `☁️ ${p.name}` })
  }
  return opts
})

// Mutations
const createMutation = useMutation({
  mutationFn: (data: Partial<MobileAppInstance>) => mobileInstancesApi.create(data),
  onSuccess: (data) => {
    queryClient.invalidateQueries({ queryKey: ['mobile-instances'] })
    toast.success(t('mobile.created'))
    showCreateDialog.value = false
    selectedInstanceId.value = data.instance.id
    if (isMobile.value) showMobileList.value = false
  },
  onError: () => toast.error(t('mobile.createError')),
})

const updateMutation = useMutation({
  mutationFn: ({ id, data }: { id: string; data: Partial<MobileAppInstance> }) =>
    mobileInstancesApi.update(id, data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['mobile-instances'] })
    toast.success(t('mobile.saved'))
    showEditDialog.value = false
  },
  onError: () => toast.error(t('mobile.saveError')),
})

const deleteMutation = useMutation({
  mutationFn: (id: string) => mobileInstancesApi.delete(id),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['mobile-instances'] })
    toast.success(t('mobile.deleted'))
    selectedInstanceId.value = null
    if (isMobile.value) showMobileList.value = true
  },
  onError: () => toast.error(t('mobile.deleteError')),
})

const toggleMutation = useMutation({
  mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
    mobileInstancesApi.update(id, { enabled }),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mobile-instances'] }),
})

// Helpers
function selectInstance(id: string) {
  selectedInstanceId.value = id
  activeTab.value = 'settings'
  if (isMobile.value) showMobileList.value = false
}

function openCreate() {
  formData.value = {
    name: '',
    description: '',
    enabled: true,
    llm_backend: 'vllm',
    llm_persona: 'anna',
    system_prompt: '',
    llm_params: {},
    tts_engine: 'xtts',
    tts_voice: 'anna',
    tts_preset: '',
    rag_mode: 'all',
    knowledge_collection_ids: [],
    rate_limit_count: null,
    rate_limit_hours: null,
  }
  showCreateDialog.value = true
}

function openEdit() {
  if (!selectedInstance.value) return
  formData.value = { ...selectedInstance.value }
  showEditDialog.value = true
}

function handleCreate() {
  createMutation.mutate(formData.value)
}

function handleUpdate() {
  if (!selectedInstanceId.value) return
  updateMutation.mutate({ id: selectedInstanceId.value, data: formData.value })
}

function handleDelete() {
  if (!selectedInstanceId.value) return
  if (confirm(t('mobile.confirmDelete'))) {
    deleteMutation.mutate(selectedInstanceId.value)
  }
}

function backToList() {
  showMobileList.value = true
}

function toggleCollection(id: number) {
  formData.value.knowledge_collection_ids = formData.value.knowledge_collection_ids || []
  const idx = formData.value.knowledge_collection_ids.indexOf(id)
  if (idx >= 0) formData.value.knowledge_collection_ids.splice(idx, 1)
  else formData.value.knowledge_collection_ids.push(id)
}

// Auto-select first on desktop
watch(instances, (list) => {
  if (!isMobile.value && !selectedInstanceId.value && list.length > 0) {
    selectedInstanceId.value = list[0].id
  }
})
</script>

<template>
  <div class="h-full flex">
    <!-- Instance List -->
    <div
      v-show="!isMobile || showMobileList"
      class="w-full md:w-80 border-r border-border flex flex-col shrink-0"
    >
      <div class="flex items-center justify-between p-4 border-b border-border">
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <Smartphone :size="20" />
          {{ t('mobile.title') }}
        </h2>
        <button
          class="p-2 rounded-lg bg-primary text-primary-foreground hover:opacity-90"
          @click="openCreate"
        >
          <Plus :size="16" />
        </button>
      </div>

      <div class="flex-1 overflow-y-auto">
        <div v-if="isLoading" class="flex items-center justify-center h-32">
          <Loader2 :size="24" class="animate-spin text-muted-foreground" />
        </div>
        <div v-else-if="!instances.length" class="p-4 text-center text-muted-foreground text-sm">
          {{ t('mobile.noInstances') }}
        </div>
        <button
          v-for="inst in instances"
          :key="inst.id"
          class="w-full text-left px-4 py-3 border-b border-border hover:bg-accent/50 transition-colors"
          :class="{ 'bg-accent': inst.id === selectedInstanceId }"
          @click="selectInstance(inst.id)"
        >
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2 min-w-0">
              <span class="w-2 h-2 rounded-full shrink-0" :class="inst.enabled ? 'bg-green-500' : 'bg-muted-foreground'" />
              <span class="font-medium text-sm truncate">{{ inst.name }}</span>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <span v-if="inst.share_count" class="text-xs text-muted-foreground flex items-center gap-0.5">
                <Users :size="12" />
                {{ inst.share_count }}
              </span>
              <ChevronRight :size="14" class="text-muted-foreground" />
            </div>
          </div>
          <p v-if="inst.description" class="text-xs text-muted-foreground truncate mt-0.5">
            {{ inst.description }}
          </p>
        </button>
      </div>
    </div>

    <!-- Detail Panel -->
    <div
      v-show="!isMobile || !showMobileList"
      class="flex-1 flex flex-col min-w-0"
    >
      <template v-if="selectedInstance">
        <!-- Header -->
        <div class="flex items-center justify-between p-4 border-b border-border">
          <div class="flex items-center gap-3 min-w-0">
            <button v-if="isMobile" class="text-muted-foreground" @click="backToList">
              ←
            </button>
            <div class="min-w-0">
              <h3 class="font-semibold truncate">{{ selectedInstance.name }}</h3>
              <p v-if="selectedInstance.description" class="text-xs text-muted-foreground truncate">
                {{ selectedInstance.description }}
              </p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="p-2 rounded-lg hover:bg-accent transition-colors"
              :class="selectedInstance.enabled ? 'text-green-500' : 'text-muted-foreground'"
              :title="selectedInstance.enabled ? t('mobile.disable') : t('mobile.enable')"
              @click="toggleMutation.mutate({ id: selectedInstance.id, enabled: !selectedInstance.enabled })"
            >
              <Power :size="16" />
            </button>
            <button
              class="p-2 rounded-lg hover:bg-accent text-muted-foreground"
              :title="t('mobile.assignUsers')"
              @click="showShareDialog = true"
            >
              <Share2 :size="16" />
            </button>
            <button
              class="p-2 rounded-lg hover:bg-accent text-muted-foreground"
              @click="openEdit"
            >
              <Edit3 :size="16" />
            </button>
            <button
              class="p-2 rounded-lg hover:bg-accent text-destructive"
              @click="handleDelete"
            >
              <Trash2 :size="16" />
            </button>
          </div>
        </div>

        <!-- Tabs -->
        <div class="flex border-b border-border px-4">
          <button
            v-for="tab in [
              { id: 'settings', label: t('mobile.tabSettings'), icon: Settings2 },
              { id: 'ai', label: t('mobile.tabAI'), icon: Cpu },
              { id: 'rag', label: t('mobile.tabRAG'), icon: BookOpen },
            ]"
            :key="tab.id"
            class="flex items-center gap-1.5 px-3 py-2.5 text-sm transition-colors border-b-2 -mb-px"
            :class="activeTab === tab.id
              ? 'border-primary text-foreground'
              : 'border-transparent text-muted-foreground hover:text-foreground'"
            @click="activeTab = tab.id as typeof activeTab"
          >
            <component :is="tab.icon" :size="14" />
            {{ tab.label }}
          </button>
        </div>

        <!-- Tab Content -->
        <div class="flex-1 overflow-y-auto p-4 space-y-4">
          <!-- Settings Tab -->
          <template v-if="activeTab === 'settings'">
            <div class="grid gap-4 max-w-lg">
              <div>
                <label class="block text-sm font-medium mb-1">ID</label>
                <span class="text-sm text-muted-foreground font-mono">{{ selectedInstance.id }}</span>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('mobile.name') }}</label>
                <span class="text-sm">{{ selectedInstance.name }}</span>
              </div>
              <div v-if="selectedInstance.description">
                <label class="block text-sm font-medium mb-1">{{ t('mobile.description') }}</label>
                <span class="text-sm text-muted-foreground">{{ selectedInstance.description }}</span>
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('mobile.ttsEngine') }}</label>
                  <span class="text-sm">{{ selectedInstance.tts_engine }}</span>
                </div>
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('mobile.ttsVoice') }}</label>
                  <span class="text-sm">{{ selectedInstance.tts_voice }}</span>
                </div>
              </div>
              <div v-if="selectedInstance.rate_limit_count" class="grid grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium mb-1">{{ t('mobile.rateLimit') }}</label>
                  <span class="text-sm">{{ selectedInstance.rate_limit_count }} / {{ selectedInstance.rate_limit_hours }}h</span>
                </div>
              </div>
            </div>
          </template>

          <!-- AI Tab -->
          <template v-if="activeTab === 'ai'">
            <div class="grid gap-4 max-w-lg">
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('mobile.llmBackend') }}</label>
                <span class="text-sm">{{ selectedInstance.llm_backend }}</span>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('mobile.persona') }}</label>
                <span class="text-sm">{{ selectedInstance.llm_persona }}</span>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('mobile.systemPrompt') }}</label>
                <pre v-if="selectedInstance.system_prompt" class="text-sm bg-muted rounded-lg p-3 whitespace-pre-wrap max-h-64 overflow-y-auto">{{ selectedInstance.system_prompt }}</pre>
                <span v-else class="text-sm text-muted-foreground italic">{{ t('mobile.defaultPrompt') }}</span>
              </div>
            </div>
          </template>

          <!-- RAG Tab -->
          <template v-if="activeTab === 'rag'">
            <div class="grid gap-4 max-w-lg">
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('mobile.ragMode') }}</label>
                <span class="text-sm">{{ selectedInstance.rag_mode || 'all' }}</span>
              </div>
              <div v-if="selectedInstance.knowledge_collection_ids?.length">
                <label class="block text-sm font-medium mb-1">{{ t('mobile.collections') }}</label>
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="cid in selectedInstance.knowledge_collection_ids"
                    :key="cid"
                    class="px-2 py-0.5 bg-muted rounded text-xs"
                  >
                    {{ knowledgeCollections.find(c => c.id === cid)?.name || `#${cid}` }}
                  </span>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- Share Dialog -->
        <ResourceShareDialog
          :resource-type="'mobile_app_instance'"
          :resource-id="selectedInstanceId || ''"
          :open="showShareDialog"
          :get-shares="mobileInstancesApi.getShares"
          :add-share="mobileInstancesApi.shareInstance"
          :update-permission="mobileInstancesApi.updateSharePermission"
          :remove-share="mobileInstancesApi.removeShare"
          @close="showShareDialog = false"
          @updated="queryClient.invalidateQueries({ queryKey: ['mobile-instances'] })"
        />
      </template>

      <div v-else class="flex-1 flex items-center justify-center text-muted-foreground">
        <div class="text-center">
          <Smartphone :size="48" class="mx-auto mb-3 opacity-30" />
          <p class="text-sm">{{ t('mobile.selectInstance') }}</p>
        </div>
      </div>
    </div>

    <!-- Create/Edit Dialog -->
    <Teleport to="body">
      <div
        v-if="showCreateDialog || showEditDialog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="showCreateDialog = false; showEditDialog = false"
      >
        <div class="bg-card border border-border rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto m-4">
          <div class="flex items-center justify-between p-4 border-b border-border">
            <h3 class="font-semibold">
              {{ showCreateDialog ? t('mobile.createTitle') : t('mobile.editTitle') }}
            </h3>
            <button
              class="p-1 hover:bg-accent rounded"
              @click="showCreateDialog = false; showEditDialog = false"
            >
              <X :size="18" />
            </button>
          </div>

          <div class="p-4 space-y-4">
            <!-- Name -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('mobile.name') }} *</label>
              <input
                v-model="formData.name"
                type="text"
                class="w-full rounded-lg bg-background border border-input px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                :placeholder="t('mobile.namePlaceholder')"
              />
            </div>

            <!-- Description -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('mobile.description') }}</label>
              <input
                v-model="formData.description"
                type="text"
                class="w-full rounded-lg bg-background border border-input px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>

            <!-- LLM Backend -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('mobile.llmBackend') }}</label>
              <select
                v-model="formData.llm_backend"
                class="w-full rounded-lg bg-background border border-input px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option v-for="opt in llmOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </div>

            <!-- Persona -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('mobile.persona') }}</label>
              <input
                v-model="formData.llm_persona"
                type="text"
                class="w-full rounded-lg bg-background border border-input px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>

            <!-- System Prompt -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('mobile.systemPrompt') }}</label>
              <textarea
                v-model="formData.system_prompt"
                rows="4"
                class="w-full rounded-lg bg-background border border-input px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring resize-y"
                :placeholder="t('mobile.systemPromptPlaceholder')"
              />
            </div>

            <!-- TTS -->
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('mobile.ttsEngine') }}</label>
                <select
                  v-model="formData.tts_engine"
                  class="w-full rounded-lg bg-background border border-input px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="xtts">XTTS v2</option>
                  <option value="piper">Piper</option>
                  <option value="openvoice">OpenVoice</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('mobile.ttsVoice') }}</label>
                <input
                  v-model="formData.tts_voice"
                  type="text"
                  class="w-full rounded-lg bg-background border border-input px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
            </div>

            <!-- RAG Mode -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('mobile.ragMode') }}</label>
              <select
                v-model="formData.rag_mode"
                class="w-full rounded-lg bg-background border border-input px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="all">{{ t('mobile.ragAll') }}</option>
                <option value="selected">{{ t('mobile.ragSelected') }}</option>
                <option value="none">{{ t('mobile.ragNone') }}</option>
              </select>
            </div>

            <!-- Knowledge Collections (if selected) -->
            <div v-if="formData.rag_mode === 'selected' && knowledgeCollections.length">
              <label class="block text-sm font-medium mb-1">{{ t('mobile.collections') }}</label>
              <div class="space-y-1 max-h-32 overflow-y-auto">
                <label
                  v-for="col in knowledgeCollections"
                  :key="col.id"
                  class="flex items-center gap-2 text-sm cursor-pointer hover:bg-accent/50 px-2 py-1 rounded"
                >
                  <input
                    type="checkbox"
                    :checked="formData.knowledge_collection_ids?.includes(col.id)"
                    @change="toggleCollection(col.id)"
                  />
                  {{ col.name }}
                </label>
              </div>
            </div>

            <!-- Rate Limiting -->
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('mobile.rateLimitCount') }}</label>
                <input
                  v-model.number="formData.rate_limit_count"
                  type="number"
                  min="0"
                  class="w-full rounded-lg bg-background border border-input px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t('mobile.rateLimitHours') }}</label>
                <input
                  v-model.number="formData.rate_limit_hours"
                  type="number"
                  min="1"
                  class="w-full rounded-lg bg-background border border-input px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
            </div>
          </div>

          <div class="flex justify-end gap-2 p-4 border-t border-border">
            <button
              class="px-4 py-2 rounded-lg text-sm hover:bg-accent transition-colors"
              @click="showCreateDialog = false; showEditDialog = false"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 transition-colors disabled:opacity-50"
              :disabled="!formData.name?.trim() || createMutation.isPending.value || updateMutation.isPending.value"
              @click="showCreateDialog ? handleCreate() : handleUpdate()"
            >
              <Loader2 v-if="createMutation.isPending.value || updateMutation.isPending.value" :size="14" class="animate-spin inline mr-1" />
              {{ showCreateDialog ? t('common.create') : t('common.save') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
