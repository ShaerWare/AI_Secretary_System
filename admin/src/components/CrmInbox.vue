<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation } from '@tanstack/vue-query'
import {
  Search,
  Send,
  RefreshCw,
  MessageSquare,
  AlertCircle,
  User,
  Settings2,
} from 'lucide-vue-next'
import { amocrmApi } from '@/api/amocrm'
import type { AmoCRMChatMessage, AmoCRMContact } from '@/api/amocrm'
import { useToastStore } from '@/stores/toast'

const { t } = useI18n()
const toast = useToastStore()

const searchQuery = ref('')
const selectedChatId = ref<string | null>(null)
const messageText = ref('')
const messagesContainer = ref<HTMLElement | null>(null)

// Check if inbox is configured
const { data: configData } = useQuery({
  queryKey: ['crm-config'],
  queryFn: () => amocrmApi.getConfig(),
})

const isInboxConfigured = computed(() => {
  const config = configData.value?.config as Record<string, unknown> | undefined
  return !!(config?.amojo_scope_id && config?.amojo_inbox_configured)
})

// Fetch contacts for the chat list
const { data: contactsData, isLoading: contactsLoading, refetch: refetchContacts } = useQuery({
  queryKey: ['crm-inbox-contacts', searchQuery],
  queryFn: () => amocrmApi.getContacts(1, 50, searchQuery.value || undefined),
  enabled: isInboxConfigured,
})

const contacts = computed<AmoCRMContact[]>(() =>
  contactsData.value?._embedded?.contacts || []
)

// Fetch chat history for selected contact
const { data: messagesData, isLoading: messagesLoading, refetch: refetchMessages } = useQuery({
  queryKey: ['crm-inbox-messages', selectedChatId],
  queryFn: () => {
    if (!selectedChatId.value) return Promise.resolve({ messages: [] })
    return amocrmApi.getChatHistory(selectedChatId.value)
  },
  enabled: computed(() => !!selectedChatId.value),
  refetchInterval: 10000,
})

const messages = computed<AmoCRMChatMessage[]>(() =>
  messagesData.value?.messages || []
)

// Send message
const sendMutation = useMutation({
  mutationFn: (text: string) => {
    if (!selectedChatId.value) throw new Error('No chat selected')
    return amocrmApi.sendChatMessage(selectedChatId.value, text)
  },
  onSuccess: () => {
    messageText.value = ''
    refetchMessages()
  },
  onError: () => toast.error(t('crm.inbox.sendFailed')),
})

function selectChat(chatId: string) {
  selectedChatId.value = chatId
}

function handleSend() {
  const text = messageText.value.trim()
  if (!text) return
  sendMutation.mutate(text)
}

function formatTime(ts: number): string {
  if (!ts) return ''
  const date = new Date(ts * 1000)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  if (isToday) {
    return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }) + ' ' +
    date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

// Scroll to bottom when messages change
watch(messages, async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
})

function doSearch() {
  refetchContacts()
}
</script>

<template>
  <div>
    <!-- Not configured -->
    <div v-if="!isInboxConfigured" class="card p-8 text-center">
      <AlertCircle class="w-12 h-12 text-yellow-400 mx-auto mb-4" />
      <h3 class="text-lg font-semibold mb-2">{{ t('crm.inbox.setupRequired') }}</h3>
      <p class="text-muted-foreground mb-4">{{ t('crm.inbox.setupHint') }}</p>
      <div class="flex items-center justify-center gap-2 text-sm text-muted-foreground">
        <Settings2 class="w-4 h-4" />
        {{ t('crm.inbox.goToSettings') }}
      </div>
    </div>

    <!-- Inbox layout -->
    <div v-else class="flex border border-border rounded-xl overflow-hidden bg-card" style="height: 600px;">
      <!-- Chat list (left panel) -->
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
              @keydown.enter="doSearch"
            />
          </div>
        </div>

        <!-- Contact list -->
        <div class="flex-1 overflow-y-auto">
          <div v-if="contactsLoading" class="flex items-center justify-center py-8">
            <RefreshCw class="w-5 h-5 animate-spin text-muted-foreground" />
          </div>

          <div v-else-if="contacts.length === 0" class="text-center py-8 text-muted-foreground text-sm">
            {{ t('crm.inbox.noChats') }}
          </div>

          <div
            v-for="contact in contacts"
            :key="contact.id"
            :class="[
              'flex items-center gap-3 px-4 py-3 cursor-pointer border-b border-border/50 transition-colors',
              selectedChatId === String(contact.id) ? 'bg-primary/10' : 'hover:bg-secondary/50'
            ]"
            @click="selectChat(String(contact.id))"
          >
            <div class="w-10 h-10 rounded-full bg-secondary flex items-center justify-center flex-shrink-0">
              <User class="w-5 h-5 text-muted-foreground" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-medium text-sm truncate">{{ contact.name }}</div>
              <div class="text-xs text-muted-foreground truncate">ID: {{ contact.id }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Messages (right panel) -->
      <div class="flex-1 flex flex-col">
        <!-- No chat selected -->
        <div v-if="!selectedChatId" class="flex-1 flex items-center justify-center text-muted-foreground">
          <div class="text-center">
            <MessageSquare class="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p class="text-sm">{{ t('crm.inbox.selectChat') }}</p>
          </div>
        </div>

        <!-- Chat view -->
        <template v-else>
          <!-- Chat header -->
          <div class="px-4 py-3 border-b border-border flex items-center gap-3">
            <div class="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
              <User class="w-4 h-4 text-muted-foreground" />
            </div>
            <div class="font-medium text-sm">
              {{ contacts.find(c => String(c.id) === selectedChatId)?.name || 'Chat' }}
            </div>
            <div class="flex-1" />
            <button class="btn btn-ghost btn-sm" :disabled="messagesLoading" @click="refetchMessages()">
              <RefreshCw :class="['w-4 h-4', messagesLoading && 'animate-spin']" />
            </button>
          </div>

          <!-- Messages area -->
          <div ref="messagesContainer" class="flex-1 overflow-y-auto p-4 space-y-3">
            <div v-if="messagesLoading && messages.length === 0" class="flex items-center justify-center py-8">
              <RefreshCw class="w-5 h-5 animate-spin text-muted-foreground" />
            </div>

            <div v-if="!messagesLoading && messages.length === 0" class="text-center py-8 text-muted-foreground text-sm">
              {{ t('crm.inbox.noMessages') }}
            </div>

            <div
              v-for="msg in messages"
              :key="msg.id"
              :class="[
                'max-w-[75%] rounded-lg px-3 py-2',
                msg.sender.id === 'admin'
                  ? 'ml-auto bg-primary/20 text-primary-foreground'
                  : 'bg-secondary'
              ]"
            >
              <div class="text-xs text-muted-foreground mb-1">
                {{ msg.sender.name }} &middot; {{ formatTime(msg.timestamp) }}
              </div>
              <div class="text-sm">{{ msg.message.text || '' }}</div>
            </div>
          </div>

          <!-- Message input -->
          <div class="p-3 border-t border-border">
            <div class="flex gap-2">
              <input
                v-model="messageText"
                type="text"
                :placeholder="t('crm.inbox.typeMessage')"
                class="input flex-1"
                @keydown.enter="handleSend"
              />
              <button
                class="btn btn-primary"
                :disabled="!messageText.trim() || sendMutation.isPending.value"
                @click="handleSend"
              >
                <Send class="w-4 h-4" />
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
