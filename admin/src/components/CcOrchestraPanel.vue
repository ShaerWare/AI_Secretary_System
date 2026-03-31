<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Terminal, Map, X, Loader2, ExternalLink, Clock, CheckCircle2, AlertCircle, XCircle } from 'lucide-vue-next'
import { claudeCodeApi, type CcSessionSummary } from '@/api/claudeCode'

const props = defineProps<{
  sessionId: string | null
}>()

const emit = defineEmits<{
  close: []
  'open-session': [ccSessionId: string]
}>()

const { t } = useI18n()

const activeTab = ref<'orchestras' | 'roadmap'>('orchestras')
const sessions = ref<CcSessionSummary[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function loadSessions() {
  if (!props.sessionId) {
    sessions.value = []
    return
  }
  loading.value = true
  error.value = null
  try {
    const resp = await claudeCodeApi.listByChatSession(props.sessionId)
    sessions.value = resp.sessions || []
  } catch (e: unknown) {
    error.value = (e as Error).message || 'Failed to load sessions'
    sessions.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.sessionId, () => {
  if (activeTab.value === 'orchestras') loadSessions()
}, { immediate: true })

watch(activeTab, (tab) => {
  if (tab === 'orchestras') loadSessions()
})

onMounted(() => {
  if (activeTab.value === 'orchestras') loadSessions()
})

function formatTime(isoStr: string) {
  const d = new Date(isoStr)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60_000) return 'just now'
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}h ago`
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
}

const statusConfig: Record<string, { icon: typeof CheckCircle2; class: string }> = {
  active: { icon: Loader2, class: 'text-blue-400 animate-spin' },
  completed: { icon: CheckCircle2, class: 'text-green-400' },
  error: { icon: AlertCircle, class: 'text-red-400' },
  aborted: { icon: XCircle, class: 'text-muted-foreground' },
}
</script>

<template>
  <div class="border-l border-border bg-card/50 flex flex-col flex-shrink-0 h-full">
    <!-- Header with tabs -->
    <div class="border-b border-border flex-shrink-0">
      <div class="flex items-center justify-between px-3 pt-2">
        <div class="flex items-center gap-1">
          <button
            :class="[
              'px-2.5 py-1.5 text-xs font-medium rounded-t transition-colors',
              activeTab === 'orchestras'
                ? 'bg-secondary text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            ]"
            @click="activeTab = 'orchestras'"
          >
            <Terminal class="w-3 h-3 inline mr-1" />
            {{ t('chatView.ccPanel.orchestras') }}
          </button>
          <button
            :class="[
              'px-2.5 py-1.5 text-xs font-medium rounded-t transition-colors',
              activeTab === 'roadmap'
                ? 'bg-secondary text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            ]"
            @click="activeTab = 'roadmap'"
          >
            <Map class="w-3 h-3 inline mr-1" />
            {{ t('chatView.ccPanel.roadmap') }}
          </button>
        </div>
        <button
          class="p-1 rounded hover:bg-secondary text-muted-foreground transition-colors"
          @click="emit('close')"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <!-- Tab content -->
    <div class="flex-1 overflow-auto">
      <!-- Orchestras tab -->
      <template v-if="activeTab === 'orchestras'">
        <!-- Loading -->
        <div v-if="loading" class="flex items-center justify-center p-8">
          <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
        </div>

        <!-- Error -->
        <div v-else-if="error" class="p-4 text-center text-xs text-destructive">
          {{ error }}
        </div>

        <!-- No session selected -->
        <div v-else-if="!sessionId" class="p-4 text-center text-xs text-muted-foreground">
          {{ t('chatView.ccPanel.noChat') }}
        </div>

        <!-- Empty -->
        <div v-else-if="sessions.length === 0" class="p-4 text-center text-xs text-muted-foreground">
          {{ t('chatView.ccPanel.noOrchestras') }}
        </div>

        <!-- Session list -->
        <div v-else class="p-2 space-y-1">
          <button
            v-for="s in sessions"
            :key="s.id"
            class="w-full text-left px-3 py-2.5 rounded-lg hover:bg-secondary/60 transition-colors group"
            @click="emit('open-session', s.id)"
          >
            <div class="flex items-center gap-2 mb-1">
              <component
                :is="statusConfig[s.status]?.icon || Terminal"
                :class="['w-3.5 h-3.5 shrink-0', statusConfig[s.status]?.class || 'text-muted-foreground']"
              />
              <span class="text-sm font-medium truncate flex-1">{{ s.title || 'Untitled' }}</span>
              <ExternalLink class="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 shrink-0 transition-opacity" />
            </div>
            <div class="flex items-center gap-3 text-[10px] text-muted-foreground pl-5">
              <span class="flex items-center gap-1">
                <Clock class="w-2.5 h-2.5" />
                {{ formatTime(s.updated || s.created) }}
              </span>
              <span v-if="s.model" class="font-mono">{{ s.model }}</span>
              <span>{{ s.total_turns }} turns</span>
            </div>
          </button>
        </div>
      </template>

      <!-- Roadmap tab -->
      <template v-if="activeTab === 'roadmap'">
        <div class="p-4 text-center text-xs text-muted-foreground">
          {{ t('chatView.ccPanel.roadmapPlaceholder') }}
        </div>
      </template>
    </div>
  </div>
</template>
