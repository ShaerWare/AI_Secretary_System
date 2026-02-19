<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { chatApi, type ChatShare, type ShareableUser } from '@/api'
import { X, UserPlus, Trash2, Loader2 } from 'lucide-vue-next'

const props = defineProps<{
  sessionId: string
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const { t } = useI18n()
const queryClient = useQueryClient()

const searchQuery = ref('')
const selectedUserId = ref<number | null>(null)
const selectedPermission = ref<'read' | 'write'>('read')

// Fetch shares for this session
const { data: sharesData, isLoading: sharesLoading } = useQuery({
  queryKey: ['chat-shares', computed(() => props.sessionId)],
  queryFn: () => chatApi.getShares(props.sessionId),
  enabled: computed(() => props.open && !!props.sessionId),
})

// Fetch shareable users
const { data: usersData } = useQuery({
  queryKey: ['shareable-users'],
  queryFn: () => chatApi.getShareableUsers(),
  enabled: computed(() => props.open),
})

const shares = computed(() => sharesData.value?.shares || [])
const shareableUsers = computed(() => {
  const users = usersData.value?.users || []
  const sharedUserIds = new Set(shares.value.map((s: ChatShare) => s.user_id))
  return users.filter((u: ShareableUser) => !sharedUserIds.has(u.id))
})

const filteredUsers = computed(() => {
  if (!searchQuery.value) return shareableUsers.value
  const q = searchQuery.value.toLowerCase()
  return shareableUsers.value.filter(
    (u: ShareableUser) =>
      u.username.toLowerCase().includes(q) ||
      (u.display_name && u.display_name.toLowerCase().includes(q))
  )
})

// Mutations
const addShareMutation = useMutation({
  mutationFn: () =>
    chatApi.shareSession(props.sessionId, selectedUserId.value!, selectedPermission.value),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['chat-shares', props.sessionId] })
    queryClient.invalidateQueries({ queryKey: ['chat-session', props.sessionId] })
    selectedUserId.value = null
    searchQuery.value = ''
  },
})

const removeShareMutation = useMutation({
  mutationFn: (userId: number) => chatApi.removeShare(props.sessionId, userId),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['chat-shares', props.sessionId] })
    queryClient.invalidateQueries({ queryKey: ['chat-session', props.sessionId] })
  },
})

const updatePermMutation = useMutation({
  mutationFn: ({ userId, permission }: { userId: number; permission: string }) =>
    chatApi.updateSharePermission(props.sessionId, userId, permission),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['chat-shares', props.sessionId] })
  },
})

function addShare() {
  if (!selectedUserId.value) return
  addShareMutation.mutate()
}

function removeShare(userId: number) {
  removeShareMutation.mutate(userId)
}

function togglePermission(share: ChatShare) {
  const newPerm = share.permission === 'read' ? 'write' : 'read'
  updatePermMutation.mutate({ userId: share.user_id, permission: newPerm })
}

function selectUser(user: ShareableUser) {
  selectedUserId.value = user.id
  searchQuery.value = user.display_name || user.username
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    emit('close')
  }
}

// Reset state when dialog closes
watch(() => props.open, (isOpen) => {
  if (!isOpen) {
    searchQuery.value = ''
    selectedUserId.value = null
    selectedPermission.value = 'read'
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="ease-out duration-300"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="ease-in duration-200"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        class="fixed inset-0 z-50 overflow-y-auto"
        @keydown="handleKeydown"
      >
        <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
          <!-- Backdrop -->
          <div
            class="fixed inset-0 bg-black/75 transition-opacity"
            @click="emit('close')"
          />

          <!-- Dialog -->
          <div class="relative transform overflow-hidden rounded-lg bg-zinc-900 px-4 pb-4 pt-5 text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-md sm:p-6">
            <!-- Header -->
            <div class="flex items-center justify-between mb-4">
              <h3 class="text-base font-semibold text-white">
                {{ t('chatView.shareDialog.title') }}
              </h3>
              <button
                class="p-1 rounded hover:bg-zinc-800 text-gray-400 hover:text-white"
                @click="emit('close')"
              >
                <X class="w-5 h-5" />
              </button>
            </div>

            <!-- Add share form -->
            <div class="mb-4">
              <div class="flex gap-2">
                <div class="relative flex-1">
                  <input
                    v-model="searchQuery"
                    type="text"
                    :placeholder="t('chatView.shareDialog.searchUsers')"
                    class="block w-full rounded-md border-0 bg-zinc-800 px-3 py-2 text-white text-sm shadow-sm ring-1 ring-inset ring-zinc-700 placeholder:text-gray-500 focus:ring-2 focus:ring-inset focus:ring-blue-500"
                    @input="selectedUserId = null"
                  />
                  <!-- Dropdown -->
                  <div
                    v-if="searchQuery && !selectedUserId && filteredUsers.length > 0"
                    class="absolute z-10 mt-1 w-full max-h-40 overflow-y-auto rounded-md bg-zinc-800 shadow-lg ring-1 ring-zinc-700"
                  >
                    <button
                      v-for="u in filteredUsers"
                      :key="u.id"
                      class="w-full text-left px-3 py-2 text-sm text-white hover:bg-zinc-700"
                      @click="selectUser(u)"
                    >
                      <span class="font-medium">{{ u.display_name || u.username }}</span>
                      <span v-if="u.display_name" class="text-gray-400 ml-1">@{{ u.username }}</span>
                    </button>
                  </div>
                </div>

                <select
                  v-model="selectedPermission"
                  class="rounded-md border-0 bg-zinc-800 px-2 py-2 text-white text-sm ring-1 ring-inset ring-zinc-700 focus:ring-2 focus:ring-blue-500"
                >
                  <option value="read">{{ t('chatView.shareDialog.read') }}</option>
                  <option value="write">{{ t('chatView.shareDialog.write') }}</option>
                </select>

                <button
                  :disabled="!selectedUserId || addShareMutation.isPending.value"
                  class="inline-flex items-center gap-1 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  @click="addShare"
                >
                  <Loader2 v-if="addShareMutation.isPending.value" class="w-4 h-4 animate-spin" />
                  <UserPlus v-else class="w-4 h-4" />
                </button>
              </div>
            </div>

            <!-- Current shares list -->
            <div class="space-y-2">
              <div v-if="sharesLoading" class="flex justify-center py-4">
                <Loader2 class="w-5 h-5 animate-spin text-gray-400" />
              </div>

              <div v-else-if="shares.length === 0" class="text-sm text-gray-500 text-center py-4">
                {{ t('chatView.shareDialog.noShares') }}
              </div>

              <div
                v-for="share in shares"
                :key="share.id"
                class="flex items-center justify-between rounded-md bg-zinc-800 px-3 py-2"
              >
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-medium text-white truncate">
                    {{ share.display_name || share.username }}
                  </div>
                  <div v-if="share.display_name" class="text-xs text-gray-400">
                    @{{ share.username }}
                  </div>
                </div>

                <div class="flex items-center gap-2 ml-2">
                  <button
                    class="text-xs px-2 py-1 rounded font-medium transition-colors"
                    :class="share.permission === 'write'
                      ? 'bg-amber-900/50 text-amber-400 hover:bg-amber-900/70'
                      : 'bg-blue-900/50 text-blue-400 hover:bg-blue-900/70'"
                    @click="togglePermission(share)"
                  >
                    {{ share.permission === 'write' ? t('chatView.shareDialog.write') : t('chatView.shareDialog.read') }}
                  </button>

                  <button
                    class="p-1 rounded text-gray-400 hover:text-red-400 hover:bg-red-900/30"
                    :title="t('chatView.shareDialog.remove')"
                    @click="removeShare(share.user_id)"
                  >
                    <Trash2 class="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
