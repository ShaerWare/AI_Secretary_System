<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { chatApi, type ChatSessionSummary } from "@/api/chat";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const auth = useAuthStore();
const isAdmin = computed(() => auth.isAdmin);

const sessions = ref<ChatSessionSummary[]>([]);
const isLoading = ref(false);
const error = ref<string | null>(null);
const isCreating = ref(false);

// For non-admins: only shared chats
const visibleSessions = computed(() => {
  if (isAdmin.value) return sessions.value;
  return sessions.value.filter((s) => s.is_shared_with_me);
});

async function loadSessions() {
  isLoading.value = true;
  error.value = null;
  try {
    const data = await chatApi.listSessions();
    sessions.value = data.sessions.sort(
      (a, b) =>
        new Date(b.updated).getTime() - new Date(a.updated).getTime(),
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load";
  } finally {
    isLoading.value = false;
  }
}

function openChat(id: string) {
  router.push(`/chat/${id}`);
}

async function createNewChat() {
  if (isCreating.value) return;
  isCreating.value = true;
  try {
    const data = await chatApi.createSession();
    router.push(`/chat/${data.session.id}`);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to create";
  } finally {
    isCreating.value = false;
  }
}

async function deleteSession(id: string, event: Event) {
  event.stopPropagation();
  if (!confirm("Delete this chat?")) return;
  try {
    await chatApi.deleteSession(id);
    sessions.value = sessions.value.filter((s) => s.id !== id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to delete";
  }
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / 86400000);

  if (days === 0) {
    return date.toLocaleTimeString("ru", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString("ru", {
    day: "numeric",
    month: "short",
  });
}

function truncate(text: string, len: number): string {
  if (!text) return "";
  return text.length > len ? text.slice(0, len) + "..." : text;
}

onMounted(loadSessions);
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- ============ ADMIN VIEW ============ -->
    <template v-if="isAdmin">
      <!-- Header -->
      <div class="shrink-0 flex items-center justify-between px-4 py-3 border-b border-stone-800">
        <h1 class="text-lg font-semibold text-white">Chats</h1>
        <div class="flex items-center gap-3">
          <button class="text-stone-400 hover:text-white transition-colors" @click="$router.push('/settings')">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
          <button class="text-stone-400 hover:text-white transition-colors" @click="auth.logout(); $router.replace('/login')">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto">
        <div v-if="isLoading && !sessions.length" class="flex items-center justify-center h-32">
          <div class="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
        </div>
        <div v-else-if="error" class="p-4 text-center">
          <p class="text-red-400 text-sm">{{ error }}</p>
          <button class="mt-2 text-amber-400 text-sm" @click="loadSessions">Retry</button>
        </div>
        <div v-else-if="!sessions.length" class="flex flex-col items-center justify-center h-64 text-stone-500">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="mb-3 opacity-50">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          <p class="text-sm mb-3">No chats yet</p>
          <button class="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm transition-colors" @click="createNewChat">Start a chat</button>
        </div>
        <div v-else>
          <div
            v-for="session in sessions"
            :key="session.id"
            class="w-full text-left px-4 py-3 border-b border-stone-800/50 hover:bg-stone-800/50 active:bg-stone-800 transition-colors flex items-center gap-2 cursor-pointer"
            @click="openChat(session.id)"
          >
            <div class="flex-1 min-w-0">
              <div class="flex items-center justify-between mb-0.5">
                <span class="font-medium text-sm text-white truncate mr-2">{{ session.title || "New Chat" }}</span>
                <span class="text-xs text-stone-500 shrink-0">{{ formatDate(session.updated) }}</span>
              </div>
              <p class="text-xs text-stone-400 truncate">{{ truncate(session.last_message || "", 80) }}</p>
              <span class="text-xs text-stone-600">{{ session.message_count }} messages</span>
            </div>
            <button
              class="shrink-0 p-2 rounded-lg text-stone-600 hover:text-red-400 hover:bg-red-900/20 transition-colors"
              title="Delete chat"
              @click="deleteSession(session.id, $event)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- FAB -->
      <button
        class="fixed bottom-6 right-6 w-14 h-14 rounded-full bg-amber-600 hover:bg-amber-700 active:bg-amber-800 shadow-lg shadow-amber-900/30 flex items-center justify-center transition-all safe-bottom"
        :class="isCreating ? 'opacity-50' : ''"
        :disabled="isCreating"
        @click="createNewChat"
      >
        <div v-if="isCreating" class="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-white">
          <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>
    </template>

    <!-- ============ NON-ADMIN: CLAUDE-LIKE WELCOME ============ -->
    <template v-else>
      <div class="flex-1 flex flex-col">
        <!-- Minimal header -->
        <div class="shrink-0 flex items-center justify-between px-4 py-3">
          <div class="flex items-center gap-2">
            <div class="w-8 h-8 rounded-xl bg-amber-600 flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <span class="text-white font-semibold">AI Secretary</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-stone-500">{{ auth.user?.username }}</span>
            <button
              class="p-1.5 rounded-lg text-stone-500 hover:text-white transition-colors"
              @click="auth.logout(); $router.replace('/login')"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        </div>

        <!-- Main welcome area -->
        <div class="flex-1 flex flex-col items-center justify-center px-6">
          <!-- Loading -->
          <div v-if="isLoading" class="flex items-center justify-center">
            <div class="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
          </div>

          <!-- Error -->
          <div v-else-if="error" class="text-center">
            <p class="text-red-400 text-sm mb-2">{{ error }}</p>
            <button class="text-amber-400 text-sm" @click="loadSessions">Retry</button>
          </div>

          <template v-else>
            <!-- Greeting -->
            <div class="text-center mb-8">
              <h1 class="text-2xl font-bold text-white mb-2">
                Hello, {{ auth.user?.username }}
              </h1>
              <p class="text-stone-400 text-sm">
                Your conversations are ready
              </p>
            </div>

            <!-- Shared chats as cards -->
            <div v-if="visibleSessions.length" class="w-full max-w-sm space-y-3 mb-6">
              <button
                v-for="session in visibleSessions"
                :key="session.id"
                class="w-full text-left p-4 rounded-2xl bg-stone-800/60 border border-stone-700/50 hover:border-amber-600/40 hover:bg-stone-800 active:bg-stone-700/80 transition-all group"
                @click="openChat(session.id)"
              >
                <div class="flex items-start gap-3">
                  <!-- Chat icon -->
                  <div class="shrink-0 w-10 h-10 rounded-xl bg-amber-600/15 flex items-center justify-center mt-0.5">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-amber-500">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-1">
                      <span class="font-medium text-sm text-white truncate group-hover:text-amber-200 transition-colors">
                        {{ session.title || "Chat" }}
                      </span>
                      <span class="text-[10px] text-stone-500 shrink-0">
                        {{ formatDate(session.updated) }}
                      </span>
                    </div>
                    <p v-if="session.last_message" class="text-xs text-stone-400 truncate">
                      {{ truncate(session.last_message, 60) }}
                    </p>
                    <p v-else class="text-xs text-stone-500 italic">Start chatting</p>
                  </div>
                  <!-- Arrow -->
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-stone-600 group-hover:text-amber-500 shrink-0 mt-1 transition-colors">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </div>
              </button>
            </div>

            <!-- No shared chats -->
            <div v-else class="text-center">
              <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-stone-800/60 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-stone-600">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <p class="text-stone-400 text-sm mb-1">No conversations yet</p>
              <p class="text-stone-600 text-xs">Ask your admin to share a chat with you</p>
            </div>
          </template>
        </div>
      </div>
    </template>
  </div>
</template>
