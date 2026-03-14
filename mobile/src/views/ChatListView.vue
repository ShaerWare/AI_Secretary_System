<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { chatApi, type ChatSessionSummary } from "@/api/chat";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const auth = useAuthStore();

const sessions = ref<ChatSessionSummary[]>([]);
const isLoading = ref(false);
const error = ref<string | null>(null);

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
    <!-- Header -->
    <div
      class="shrink-0 flex items-center justify-between px-4 py-3 border-b border-stone-800"
    >
      <h1 class="text-lg font-semibold text-white">Chats</h1>
      <div class="flex items-center gap-3">
        <button
          class="text-stone-400 hover:text-white transition-colors"
          @click="$router.push('/settings')"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="12" cy="12" r="3" />
            <path
              d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"
            />
          </svg>
        </button>
        <button
          class="text-stone-400 hover:text-white transition-colors"
          @click="auth.logout(); $router.replace('/login')"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto">
      <!-- Loading -->
      <div
        v-if="isLoading && !sessions.length"
        class="flex items-center justify-center h-32"
      >
        <div
          class="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"
        />
      </div>

      <!-- Error -->
      <div
        v-else-if="error"
        class="p-4 text-center"
      >
        <p class="text-red-400 text-sm">{{ error }}</p>
        <button
          class="mt-2 text-amber-400 text-sm"
          @click="loadSessions"
        >
          Retry
        </button>
      </div>

      <!-- Empty state -->
      <div
        v-else-if="!sessions.length"
        class="flex flex-col items-center justify-center h-64 text-stone-500"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="mb-3 opacity-50"
        >
          <path
            d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
          />
        </svg>
        <p class="text-sm">No chats yet</p>
      </div>

      <!-- Session list -->
      <div v-else>
        <button
          v-for="session in sessions"
          :key="session.id"
          class="w-full text-left px-4 py-3 border-b border-stone-800/50 hover:bg-stone-800/50 active:bg-stone-800 transition-colors"
          @click="openChat(session.id)"
        >
          <div class="flex items-center justify-between mb-0.5">
            <span class="font-medium text-sm text-white truncate mr-2">
              {{ session.title || "New Chat" }}
            </span>
            <span class="text-xs text-stone-500 shrink-0">
              {{ formatDate(session.updated) }}
            </span>
          </div>
          <p class="text-xs text-stone-400 truncate">
            {{ truncate(session.last_message || "", 80) }}
          </p>
          <span class="text-xs text-stone-600">
            {{ session.message_count }} messages
          </span>
        </button>
      </div>
    </div>

  </div>
</template>
