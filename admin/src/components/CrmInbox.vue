<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import {
  Search,
  Send as SendIcon,
  RefreshCw,
  MessageSquare,
  Globe,
  MessageCircle,
  Bot,
  ChevronRight,
  ChevronDown,
} from 'lucide-vue-next'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { chatApi, type ChatSessionSummary, type ChatMessage, type GroupedSessions } from '@/api'
import { amocrmApi } from '@/api/amocrm'
import CrmInboxAmoCRM from './CrmInboxAmoCRM.vue'

const { t } = useI18n()

// Sub-tabs: AI Chats / amoCRM Inbox
const activeSubTab = ref<'ai' | 'amocrm'>('ai')

// Check if amojo configured (for amoCRM sub-tab visibility)
const { data: configData } = useQuery({
  queryKey: ['crm-config'],
  queryFn: () => amocrmApi.getConfig(),
})

const isAmojoConfigured = computed(() => {
  const config = configData.value?.config as Record<string, unknown> | undefined
  return !!(config?.amojo_scope_id && config?.amojo_inbox_configured)
})

// Grouped sessions (exclude admin)
const searchQuery = ref('')
const selectedSessionId = ref<string | null>(null)
const replyText = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const isStreaming = ref(false)
const streamingContent = ref('')
const collapsedGroups = ref<Set<string>>(new Set())

// Source groups to display (order matters)
const inboxGroups = ['telegram', 'whatsapp', 'widget'] as const

// Fetch grouped sessions
const { data: groupedData, isLoading: sessionsLoading, refetch: refetchSessions } = useQuery({
  queryKey: ['crm-inbox-grouped'],
  queryFn: () => chatApi.listSessionsGrouped(),
  refetchInterval: 15000,
})

const groupedSessions = computed<Record<string, ChatSessionSummary[]>>(() => {
  const raw = groupedData.value?.sessions
  if (!raw) return {}
  const result: Record<string, ChatSessionSummary[]> = {}
  for (const group of inboxGroups) {
    const sessions = raw[group as keyof GroupedSessions] || []
    if (sessions.length > 0) {
      result[group] = sessions
    }
  }
  return result
})

// Filtered sessions per group (search)
const filteredGroups = computed<Record<string, ChatSessionSummary[]>>(() => {
  const q = searchQuery.value.toLowerCase()
  if (!q) return groupedSessions.value

  const result: Record<string, ChatSessionSummary[]> = {}
  for (const [group, sessions] of Object.entries(groupedSessions.value)) {
    const filtered = sessions.filter(s =>
      s.title.toLowerCase().includes(q) ||
      (s.last_message && s.last_message.toLowerCase().includes(q))
    )
    if (filtered.length > 0) {
      result[group] = filtered
    }
  }
  return result
})

const totalSessions = computed(() =>
  Object.values(filteredGroups.value).reduce((sum, g) => sum + g.length, 0)
)

function toggleGroup(groupName: string) {
  if (collapsedGroups.value.has(groupName)) {
    collapsedGroups.value.delete(groupName)
  } else {
    collapsedGroups.value.add(groupName)
  }
}

// Fetch messages for selected session
const { data: sessionData, isLoading: messagesLoading, refetch: refetchMessages } = useQuery({
  queryKey: ['crm-inbox-session', selectedSessionId],
  queryFn: () => {
    if (!selectedSessionId.value) return null
    return chatApi.getSession(selectedSessionId.value)
  },
  enabled: computed(() => !!selectedSessionId.value),
  refetchInterval: 10000,
})

const messages = computed<ChatMessage[]>(() => {
  const session = sessionData.value?.session
  if (!session) return []
  return (session.messages || []).filter(m => m.is_active !== false)
})

function selectSession(sessionId: string) {
  selectedSessionId.value = sessionId
}

// Find selected session info across all groups
const selectedSession = computed<ChatSessionSummary | undefined>(() => {
  if (!selectedSessionId.value) return undefined
  for (const sessions of Object.values(filteredGroups.value)) {
    const found = sessions.find(s => s.id === selectedSessionId.value)
    if (found) return found
  }
  return undefined
})

function getSourceIcon(source?: string | null) {
  switch (source) {
    case 'telegram': case 'telegram_bot': return SendIcon
    case 'widget': return Globe
    case 'whatsapp': return MessageCircle
    default: return Bot
  }
}

function getGroupIcon(group: string) {
  return getSourceIcon(group)
}

function renderMarkdown(content: string): string {
  const raw = marked.parse(content) as string
  return DOMPurify.sanitize(raw)
}

function formatTime(ts: string): string {
  if (!ts) return ''
  const date = new Date(ts)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  if (isToday) {
    return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }) + ' ' +
    date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

// Send reply via streaming
let activeStream: { abort: () => void } | null = null

function handleSendReply() {
  const text = replyText.value.trim()
  if (!text || !selectedSessionId.value || isStreaming.value) return

  replyText.value = ''
  isStreaming.value = true
  streamingContent.value = ''

  activeStream = chatApi.streamMessage(
    selectedSessionId.value,
    text,
    (data) => {
      if (data.type === 'chunk' && data.content) {
        streamingContent.value += data.content
      } else if (data.type === 'done') {
        isStreaming.value = false
        streamingContent.value = ''
        refetchMessages()
      } else if (data.type === 'error') {
        isStreaming.value = false
        streamingContent.value = ''
      }
    }
  )
}

// Scroll to bottom when messages change
watch(messages, async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
})

watch(streamingContent, async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
})

// Auto-refresh
let refreshTimer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  refreshTimer = setInterval(() => refetchSessions(), 15000)
})
onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (activeStream) activeStream.abort()
})
</script>

<template>
  <div>
    <!-- Sub-tabs -->
    <div class="flex gap-2 mb-4">
      <button
        :class="[
          'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
          activeSubTab === 'ai' ? 'bg-primary text-primary-foreground' : 'bg-secondary hover:bg-secondary/80'
        ]"
        @click="activeSubTab = 'ai'"
      >
        {{ t('crm.inbox.aiChats') }}
      </button>
      <button
        v-if="isAmojoConfigured"
        :class="[
          'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
          activeSubTab === 'amocrm' ? 'bg-primary text-primary-foreground' : 'bg-secondary hover:bg-secondary/80'
        ]"
        @click="activeSubTab = 'amocrm'"
      >
        {{ t('crm.inbox.amocrmInbox') }}
      </button>
    </div>

    <!-- amoCRM Inbox sub-tab -->
    <CrmInboxAmoCRM v-if="activeSubTab === 'amocrm'" />

    <!-- AI Chats sub-tab -->
    <div v-else class="flex border border-border rounded-xl overflow-hidden bg-card" style="height: 600px;">
      <!-- Session list (left panel) -->
      <div class="w-80 flex-shrink-0 border-r border-border flex flex-col">
        <!-- Search -->
        <div class="p-3 border-b border-border">
          <div class="relative">
            <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              v-model="searchQuery"
              type="text"
              :placeholder="t('crm.inbox.searchChats')"
              class="input w-full pl-10 text-sm"
            />
          </div>
        </div>

        <!-- Grouped session list -->
        <div class="flex-1 overflow-y-auto">
          <div v-if="sessionsLoading" class="flex items-center justify-center py-8">
            <RefreshCw class="w-5 h-5 animate-spin text-muted-foreground" />
          </div>

          <div v-else-if="totalSessions === 0" class="text-center py-8 text-muted-foreground text-sm">
            {{ t('crm.inbox.noChats') }}
          </div>

          <template v-else>
            <template v-for="group in inboxGroups" :key="group">
              <template v-if="filteredGroups[group]?.length">
                <!-- Group header -->
                <div
                  class="px-3 py-2 bg-secondary/30 flex items-center gap-2 cursor-pointer hover:bg-secondary/50 sticky top-0 z-10"
                  @click="toggleGroup(group)"
                >
                  <ChevronRight v-if="collapsedGroups.has(group)" class="w-4 h-4 text-muted-foreground" />
                  <ChevronDown v-else class="w-4 h-4 text-muted-foreground" />
                  <component :is="getGroupIcon(group)" class="w-3.5 h-3.5 text-muted-foreground" />
                  <span class="text-xs font-medium uppercase text-muted-foreground">
                    {{ t(`crm.inbox.groups.${group}`) }}
                  </span>
                  <span class="text-xs text-muted-foreground ml-auto">
                    {{ filteredGroups[group].length }}
                  </span>
                </div>

                <!-- Sessions in group -->
                <div v-if="!collapsedGroups.has(group)">
                  <div
                    v-for="session in filteredGroups[group]"
                    :key="session.id"
                    :class="[
                      'flex items-start gap-3 px-3 py-3 cursor-pointer border-b border-border/50 transition-colors',
                      selectedSessionId === session.id ? 'bg-primary/10' : 'hover:bg-secondary/50'
                    ]"
                    @click="selectSession(session.id)"
                  >
                    <div class="w-8 h-8 rounded-full bg-secondary flex items-center justify-center flex-shrink-0 mt-0.5">
                      <component :is="getSourceIcon(session.source)" class="w-4 h-4 text-muted-foreground" />
                    </div>

                    <div class="flex-1 min-w-0">
                      <div class="flex items-center gap-1.5">
                        <span class="font-medium text-sm truncate">{{ session.title }}</span>
                        <span class="text-xs text-muted-foreground shrink-0">{{ session.message_count }}</span>
                      </div>
                      <p v-if="session.last_message" class="text-xs text-muted-foreground truncate mt-0.5">
                        {{ session.last_message }}
                      </p>
                      <div class="text-xs text-muted-foreground/50 mt-1">
                        {{ formatTime(session.updated) }}
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </template>
          </template>
        </div>
      </div>

      <!-- Messages (right panel) -->
      <div class="flex-1 flex flex-col">
        <!-- No session selected -->
        <div v-if="!selectedSessionId" class="flex-1 flex items-center justify-center text-muted-foreground">
          <div class="text-center">
            <MessageSquare class="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p class="text-sm">{{ t('crm.inbox.selectChat') }}</p>
          </div>
        </div>

        <!-- Chat view -->
        <template v-else>
          <!-- Chat header -->
          <div class="px-4 py-3 border-b border-border flex items-center gap-3">
            <component
              :is="getSourceIcon(selectedSession?.source)"
              class="w-5 h-5 text-muted-foreground"
            />
            <div class="flex-1 min-w-0">
              <div class="font-medium text-sm truncate">
                {{ selectedSession?.title || 'Chat' }}
              </div>
            </div>
            <button class="btn btn-ghost btn-sm" :disabled="messagesLoading" @click="refetchMessages()">
              <RefreshCw :class="['w-4 h-4', messagesLoading && 'animate-spin']" />
            </button>
          </div>

          <!-- Messages area -->
          <div ref="messagesContainer" class="flex-1 overflow-y-auto p-4 space-y-3">
            <div v-if="messagesLoading && messages.length === 0" class="flex items-center justify-center py-8">
              <RefreshCw class="w-5 h-5 animate-spin text-muted-foreground" />
            </div>

            <div v-else-if="messages.length === 0 && !isStreaming" class="text-center py-8 text-muted-foreground text-sm">
              {{ t('crm.inbox.noMessages') }}
            </div>

            <template v-else>
              <div
                v-for="msg in messages"
                :key="msg.id"
                :class="[
                  'max-w-[80%] rounded-lg px-3 py-2',
                  msg.role === 'assistant'
                    ? 'bg-secondary'
                    : msg.role === 'user'
                      ? 'ml-auto bg-primary text-primary-foreground'
                      : 'bg-muted text-xs italic'
                ]"
              >
                <div class="text-xs text-muted-foreground mb-1">
                  {{ msg.role === 'assistant' ? 'AI' : msg.role === 'user' ? t('crm.inbox.user') : 'System' }}
                  <span v-if="msg.timestamp" class="ml-1">&middot; {{ formatTime(msg.timestamp) }}</span>
                </div>
                <div
                  v-if="msg.role === 'assistant'"
                  class="text-sm chat-markdown"
                  v-html="renderMarkdown(msg.content)"
                />
                <div v-else class="text-sm whitespace-pre-wrap">{{ msg.content }}</div>
              </div>

              <!-- Streaming indicator -->
              <div v-if="isStreaming" class="max-w-[80%] rounded-lg px-3 py-2 bg-secondary">
                <div class="text-xs text-muted-foreground mb-1">AI</div>
                <div
                  v-if="streamingContent"
                  class="text-sm chat-markdown"
                  v-html="renderMarkdown(streamingContent)"
                />
                <div v-else class="flex items-center gap-2 text-sm text-muted-foreground">
                  <RefreshCw class="w-3 h-3 animate-spin" />
                  {{ t('crm.inbox.thinking') }}
                </div>
              </div>
            </template>
          </div>

          <!-- Reply input -->
          <div class="p-3 border-t border-border">
            <div class="flex gap-2">
              <input
                v-model="replyText"
                type="text"
                :placeholder="t('crm.inbox.typeMessage')"
                class="input flex-1"
                :disabled="isStreaming"
                @keydown.enter="handleSendReply"
              />
              <button
                class="btn btn-primary"
                :disabled="!replyText.trim() || isStreaming"
                @click="handleSendReply"
              >
                <SendIcon class="w-4 h-4" />
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
