<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { chatApi, type ChatSessionSummary } from "@/api/chat";
import {
  adminApi,
  type CloudProvider,
  type KnowledgeCollection,
  type ShareableUser,
  type ChatShare,
  type MobileInstance,
} from "@/api/admin";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const auth = useAuthStore();
const isAdmin = computed(() => auth.isAdmin);

const sessions = ref<ChatSessionSummary[]>([]);
const isLoading = ref(false);
const error = ref<string | null>(null);
const isCreating = ref(false);
const welcomeInput = ref("");
const isSending = ref(false);

// Admin data (loaded once)
const llmProviders = ref<CloudProvider[]>([]);
const ragCollections = ref<KnowledgeCollection[]>([]);
const shareableUsers = ref<ShareableUser[]>([]);
const mobileInstances = ref<MobileInstance[]>([]);

// Per-session expanded panel
const expandedSessionId = ref<string | null>(null);
const panelTab = ref<"llm" | "rag" | "share" | "mobile" | "rename">("llm");
const panelLoading = ref(false);

// Per-session state (loaded when expanded)
const sessionShares = ref<ChatShare[]>([]);

// Rename
const renameValue = ref("");

// LLM per-session override
const sessionLlm = ref("default");

// RAG per-session override
const sessionRagIds = ref<number[]>([]);

// Mobile instance attached to session
const sessionMobileInstanceId = ref<string | null>(null);

// For non-admins: only the chat that admin explicitly assigned as
// "default mobile" for this user. Regular shares (via the Share menu)
// are not surfaced on mobile — the mobile app is a single-assistant
// surface, not a general chat browser.
const visibleSessions = computed(() => {
  if (isAdmin.value) return sessions.value;
  return sessions.value.filter((s) => s.is_default_mobile);
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
    if (!isAdmin.value) {
      await autoOpenChat();
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось загрузить";
  } finally {
    isLoading.value = false;
  }
}

async function loadAdminData() {
  try {
    const [providerData, collectionData, usersData, instancesData] = await Promise.all([
      adminApi.getProviders(),
      adminApi.getCollections(),
      adminApi.getShareableUsers(),
      adminApi.getMobileInstances(),
    ]);
    llmProviders.value = providerData.providers;
    ragCollections.value = collectionData.collections.filter((c) => c.enabled);
    shareableUsers.value = usersData.users;
    mobileInstances.value = instancesData.instances.filter((i) => i.enabled);
  } catch {
    // Non-critical
  }
}

async function autoOpenChat() {
  try {
    const resp = await chatApi.getMyDefaultMobileSession();
    if (resp.session_id) {
      router.replace(`/chat/${resp.session_id}`);
      return;
    }
  } catch {
    // fallback
  }
  if (visibleSessions.value.length > 0) {
    router.replace(`/chat/${visibleSessions.value[0]!.id}`);
    return;
  }
  try {
    const data = await chatApi.createSession();
    router.replace(`/chat/${data.session.id}`);
  } catch {
    // stay on list
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
    error.value = e instanceof Error ? e.message : "Не удалось создать";
  } finally {
    isCreating.value = false;
  }
}

async function deleteSession(id: string, event: Event) {
  event.stopPropagation();
  if (!confirm("Удалить этот чат?")) return;
  try {
    await chatApi.deleteSession(id);
    sessions.value = sessions.value.filter((s) => s.id !== id);
    if (expandedSessionId.value === id) expandedSessionId.value = null;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось удалить";
  }
}

// === Expand/collapse session panel ===

async function toggleSessionPanel(sessionId: string, tab: "llm" | "rag" | "share" | "mobile" | "rename", event: Event) {
  event.stopPropagation();
  if (expandedSessionId.value === sessionId && panelTab.value === tab) {
    expandedSessionId.value = null;
    return;
  }
  expandedSessionId.value = sessionId;
  panelTab.value = tab;

  if (tab === "share") {
    await loadSessionShares(sessionId);
  } else if (tab === "rename") {
    const s = sessions.value.find((s) => s.id === sessionId);
    renameValue.value = s?.title || "";
  } else {
    // llm, rag, mobile — all need session details
    await loadSessionDetails(sessionId);
  }
}

async function loadSessionDetails(sessionId: string) {
  panelLoading.value = true;
  try {
    const data = await chatApi.getSession(sessionId);
    const s = data.session;

    // Source-based LLM: if linked to mobile instance, resolve its LLM
    sessionLlm.value = "default";
    if (s.source === "mobile" && s.source_id) {
      const inst = mobileInstances.value.find((i) => i.id === s.source_id);
      if (inst?.llm_backend) {
        sessionLlm.value = inst.llm_backend;
      }
    }

    // RAG collections from session
    sessionRagIds.value = [];
    if (s.knowledge_collection_ids) {
      const ids = typeof s.knowledge_collection_ids === "string"
        ? JSON.parse(s.knowledge_collection_ids)
        : s.knowledge_collection_ids;
      if (Array.isArray(ids)) sessionRagIds.value = ids;
    } else if (s.knowledge_collection_id) {
      sessionRagIds.value = [s.knowledge_collection_id];
    }

    // Also set mobile instance
    sessionMobileInstanceId.value = s.source_id || null;
  } catch {
    sessionLlm.value = "default";
    sessionRagIds.value = [];
  } finally {
    panelLoading.value = false;
  }
}

async function loadSessionShares(sessionId: string) {
  panelLoading.value = true;
  try {
    const data = await adminApi.getSessionShares(sessionId);
    sessionShares.value = data.shares;
  } catch {
    sessionShares.value = [];
  } finally {
    panelLoading.value = false;
  }
}


// === Actions ===

async function renameSession() {
  if (!expandedSessionId.value || !renameValue.value.trim()) return;
  try {
    await chatApi.updateSession(expandedSessionId.value, { title: renameValue.value.trim() });
    const s = sessions.value.find((s) => s.id === expandedSessionId.value);
    if (s) s.title = renameValue.value.trim();
    expandedSessionId.value = null;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось переименовать";
  }
}

async function toggleRagCollection(colId: number) {
  const idx = sessionRagIds.value.indexOf(colId);
  if (idx >= 0) {
    sessionRagIds.value.splice(idx, 1);
  } else {
    sessionRagIds.value.push(colId);
  }
  // Auto-save
  if (!expandedSessionId.value) return;
  try {
    await chatApi.updateSession(expandedSessionId.value, {
      rag_mode: sessionRagIds.value.length > 0 ? "selected" : "all",
      knowledge_collection_ids: sessionRagIds.value,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось сохранить RAG";
  }
}

async function shareWithUser(userId: number) {
  if (!expandedSessionId.value) return;
  try {
    await adminApi.shareSession(expandedSessionId.value, userId, "read");
    await loadSessionShares(expandedSessionId.value);
    // Update share count in list
    const s = sessions.value.find((s) => s.id === expandedSessionId.value);
    if (s) s.share_count = sessionShares.value.length;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось поделиться";
  }
}

async function removeShare(userId: number) {
  if (!expandedSessionId.value) return;
  try {
    await adminApi.removeSessionShare(expandedSessionId.value, userId);
    await loadSessionShares(expandedSessionId.value);
    const s = sessions.value.find((s) => s.id === expandedSessionId.value);
    if (s) s.share_count = sessionShares.value.length;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось убрать доступ";
  }
}

async function attachMobileInstance(instanceId: string | null) {
  if (!expandedSessionId.value) return;
  try {
    await chatApi.updateSession(expandedSessionId.value, {
      source: instanceId ? "mobile" : "admin",
      source_id: instanceId || "",
    });
    sessionMobileInstanceId.value = instanceId;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось привязать";
  }
}

const llmOptions = computed(() => {
  const opts = [
    { value: "default", label: "По умолчанию" },
    { value: "vllm", label: "vLLM (Local)" },
  ];
  for (const p of llmProviders.value) {
    opts.push({ value: `cloud:${p.id}`, label: `${p.name} (${p.model_name})` });
  }
  return opts;
});

// Users not yet shared with
const unsharedUsers = computed(() => {
  const sharedIds = new Set(sessionShares.value.map((s) => s.user_id));
  return shareableUsers.value.filter((u) => !sharedIds.has(u.id));
});


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
  if (days === 1) return "вчера";
  if (days < 7) return `${days}д назад`;
  return date.toLocaleDateString("ru", {
    day: "numeric",
    month: "short",
  });
}

function truncate(text: string, len: number): string {
  if (!text) return "";
  return text.length > len ? text.slice(0, len) + "..." : text;
}

async function sendFromWelcome() {
  const text = welcomeInput.value.trim();
  if (!text || isSending.value) return;
  isSending.value = true;
  try {
    if (visibleSessions.value.length > 0) {
      const sessionId = visibleSessions.value[0]!.id;
      router.push(`/chat/${sessionId}?msg=${encodeURIComponent(text)}`);
    } else {
      const data = await chatApi.createSession(text);
      router.push(`/chat/${data.session.id}?msg=${encodeURIComponent(text)}`);
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось начать чат";
  } finally {
    isSending.value = false;
  }
}

onMounted(() => {
  loadSessions();
  if (isAdmin.value) loadAdminData();
});
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- ============ ADMIN VIEW ============ -->
    <template v-if="isAdmin">
      <!-- Header -->
      <div class="shrink-0 flex items-center justify-between px-4 py-3 border-b border-stone-800">
        <h1 class="text-lg font-semibold text-white">Чаты</h1>
        <div class="flex items-center gap-3">
          <button
            class="text-amber-400 hover:text-amber-300 transition-colors"
            :class="isCreating ? 'opacity-50' : ''"
            :disabled="isCreating"
            title="Новый чат"
            @click="createNewChat"
          >
            <div v-if="isCreating" class="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
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
          <button class="mt-2 text-amber-400 text-sm" @click="loadSessions">Повторить</button>
        </div>
        <div v-else-if="!sessions.length" class="flex flex-col items-center justify-center h-64 text-stone-500">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="mb-3 opacity-50">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          <p class="text-sm mb-3">Пока нет чатов</p>
          <button class="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm transition-colors" @click="createNewChat">Начать чат</button>
        </div>
        <div v-else>
          <div v-for="session in sessions" :key="session.id">
            <!-- Session row -->
            <div
              class="w-full text-left px-4 py-3 border-b border-stone-800/50 hover:bg-stone-800/50 active:bg-stone-800 transition-colors cursor-pointer"
              @click="openChat(session.id)"
            >
              <!-- Title + date row -->
              <div class="flex items-center justify-between mb-0.5">
                <span class="font-medium text-sm text-white truncate mr-2">{{ session.title || "Новый чат" }}</span>
                <span class="text-xs text-stone-500 shrink-0">{{ formatDate(session.updated) }}</span>
              </div>
              <!-- Last message -->
              <p class="text-xs text-stone-400 truncate mb-1.5">{{ truncate(session.last_message || "", 80) }}</p>
              <!-- Info + action buttons row -->
              <div class="flex items-center gap-1" @click.stop>
                <span class="text-xs text-stone-600 mr-auto">{{ session.message_count }} сообщ.</span>

                <!-- Rename -->
                <button
                  class="p-1.5 rounded-lg transition-colors"
                  :class="expandedSessionId === session.id && panelTab === 'rename' ? 'bg-amber-600/20 text-amber-400' : 'text-stone-600 hover:text-stone-300'"
                  title="Переименовать"
                  @click="toggleSessionPanel(session.id, 'rename', $event)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>

                <!-- LLM provider -->
                <button
                  class="p-1.5 rounded-lg transition-colors"
                  :class="expandedSessionId === session.id && panelTab === 'llm' ? 'bg-amber-600/20 text-amber-400' : 'text-stone-600 hover:text-stone-300'"
                  title="LLM провайдер"
                  @click="toggleSessionPanel(session.id, 'llm', $event)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 2a8 8 0 0 0-8 8c0 3.5 2 6 5 7.5V21h6v-3.5c3-1.5 5-4 5-7.5a8 8 0 0 0-8-8z" />
                  </svg>
                </button>

                <!-- RAG -->
                <button
                  v-if="ragCollections.length"
                  class="p-1.5 rounded-lg transition-colors"
                  :class="expandedSessionId === session.id && panelTab === 'rag' ? 'bg-amber-600/20 text-amber-400' : 'text-stone-600 hover:text-stone-300'"
                  title="База знаний"
                  @click="toggleSessionPanel(session.id, 'rag', $event)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" /><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
                  </svg>
                </button>

                <!-- Share -->
                <button
                  class="p-1.5 rounded-lg transition-colors"
                  :class="expandedSessionId === session.id && panelTab === 'share' ? 'bg-amber-600/20 text-amber-400' : ((session.share_count || 0) > 0 ? 'text-blue-400/60 hover:text-blue-300' : 'text-stone-600 hover:text-stone-300')"
                  title="Поделиться"
                  @click="toggleSessionPanel(session.id, 'share', $event)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
                    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                  </svg>
                </button>

                <!-- Mobile instance -->
                <button
                  v-if="mobileInstances.length"
                  class="p-1.5 rounded-lg transition-colors"
                  :class="expandedSessionId === session.id && panelTab === 'mobile' ? 'bg-amber-600/20 text-amber-400' : 'text-stone-600 hover:text-stone-300'"
                  title="Моб. приложение"
                  @click="toggleSessionPanel(session.id, 'mobile', $event)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="5" y="2" width="14" height="20" rx="2" ry="2" /><line x1="12" y1="18" x2="12.01" y2="18" />
                  </svg>
                </button>

                <!-- Delete -->
                <button
                  class="p-1.5 rounded-lg text-stone-600 hover:text-red-400 transition-colors"
                  title="Удалить"
                  @click="deleteSession(session.id, $event)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
              </div>
            </div>

            <!-- Expanded panel -->
            <div
              v-if="expandedSessionId === session.id"
              class="bg-stone-900/80 border-b border-stone-700 px-4 py-3"
              @click.stop
            >
              <!-- Loading -->
              <div v-if="panelLoading" class="flex justify-center py-3">
                <div class="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
              </div>

              <!-- Rename -->
              <template v-else-if="panelTab === 'rename'">
                <label class="block text-xs text-stone-400 mb-1.5">Название чата</label>
                <div class="flex gap-2">
                  <input
                    v-model="renameValue"
                    class="flex-1 bg-stone-950 text-stone-200 text-sm rounded-lg px-3 py-2 border border-stone-700 focus:border-amber-500 focus:outline-none"
                    placeholder="Введите название..."
                    @keydown.enter="renameSession"
                  />
                  <button
                    class="px-3 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium transition-colors"
                    @click="renameSession"
                  >OK</button>
                </div>
              </template>

              <!-- LLM Provider -->
              <template v-else-if="panelTab === 'llm'">
                <label class="block text-xs text-stone-400 mb-1.5">LLM провайдер</label>
                <!-- Current source info -->
                <div v-if="sessionMobileInstanceId" class="mb-2 px-3 py-2 bg-stone-800/50 rounded-lg text-xs text-stone-400">
                  Источник: моб. приложение
                  <span class="text-amber-400">{{ mobileInstances.find(i => i.id === sessionMobileInstanceId)?.name || sessionMobileInstanceId }}</span>
                </div>
                <div class="space-y-1 max-h-[200px] overflow-y-auto">
                  <button
                    v-for="opt in llmOptions"
                    :key="opt.value"
                    class="w-full text-left px-3 py-2 text-xs rounded-lg hover:bg-stone-800 transition-colors flex items-center gap-2"
                    :class="sessionLlm === opt.value ? 'text-amber-400 bg-amber-600/10' : 'text-stone-300'"
                  >
                    <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="opt.value.startsWith('cloud:') ? 'bg-blue-400' : 'bg-green-400'" />
                    {{ opt.label }}
                    <svg v-if="sessionLlm === opt.value" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="ml-auto shrink-0">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </button>
                </div>
                <p class="text-[10px] text-stone-600 mt-2">
                  <template v-if="sessionMobileInstanceId">Провайдер определяется привязанным моб. приложением</template>
                  <template v-else>Используется провайдер по умолчанию</template>
                </p>
              </template>

              <!-- RAG Collections -->
              <template v-else-if="panelTab === 'rag'">
                <label class="block text-xs text-stone-400 mb-1.5">Базы знаний</label>
                <div class="space-y-1 max-h-[200px] overflow-y-auto">
                  <label
                    v-for="col in ragCollections"
                    :key="col.id"
                    class="flex items-center gap-2 px-3 py-2 text-xs rounded-lg hover:bg-stone-800 transition-colors cursor-pointer"
                    :class="sessionRagIds.includes(col.id) ? 'text-amber-400' : 'text-stone-300'"
                  >
                    <input
                      type="checkbox"
                      :checked="sessionRagIds.includes(col.id)"
                      class="accent-amber-500"
                      @change="toggleRagCollection(col.id)"
                    />
                    <span class="flex-1">{{ col.name }}</span>
                    <span class="text-stone-600 text-[10px]">{{ col.document_count }} docs</span>
                  </label>
                </div>
                <p class="text-[10px] text-stone-600 mt-2">
                  <template v-if="sessionRagIds.length">Выбрано: {{ sessionRagIds.length }}</template>
                  <template v-else>Используются все коллекции</template>
                </p>
              </template>

              <!-- Share -->
              <template v-else-if="panelTab === 'share'">
                <label class="block text-xs text-stone-400 mb-1.5">Поделиться чатом</label>
                <!-- Current shares -->
                <div v-if="sessionShares.length" class="space-y-1 mb-2">
                  <div
                    v-for="share in sessionShares"
                    :key="share.user_id"
                    class="flex items-center gap-2 px-3 py-1.5 bg-stone-800/50 rounded-lg"
                  >
                    <span class="text-xs text-stone-300 flex-1">{{ share.display_name || share.username }}</span>
                    <span class="text-[10px] px-1.5 py-0.5 rounded" :class="share.permission === 'write' ? 'bg-amber-600/20 text-amber-400' : 'bg-stone-700 text-stone-400'">
                      {{ share.permission === 'write' ? 'запись' : 'чтение' }}
                    </span>
                    <button class="text-stone-500 hover:text-red-400 transition-colors" @click="removeShare(share.user_id)">
                      <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </div>
                </div>
                <!-- Add new share -->
                <div v-if="unsharedUsers.length" class="space-y-1 max-h-[150px] overflow-y-auto">
                  <button
                    v-for="user in unsharedUsers"
                    :key="user.id"
                    class="w-full text-left px-3 py-1.5 text-xs text-stone-400 hover:text-white hover:bg-stone-800 rounded-lg transition-colors flex items-center gap-2"
                    @click="shareWithUser(user.id)"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                    {{ user.display_name || user.username }}
                    <span class="text-stone-600 text-[10px] ml-auto">{{ user.role }}</span>
                  </button>
                </div>
                <p v-else-if="!sessionShares.length" class="text-xs text-stone-600">Нет пользователей для шаринга</p>
              </template>

              <!-- Mobile instance attachment -->
              <template v-else-if="panelTab === 'mobile'">
                <label class="block text-xs text-stone-400 mb-1.5">Привязать моб. приложение</label>
                <div class="space-y-1 max-h-[200px] overflow-y-auto">
                  <!-- None option -->
                  <button
                    class="w-full text-left px-3 py-2 text-xs rounded-lg hover:bg-stone-800 transition-colors flex items-center gap-2"
                    :class="!sessionMobileInstanceId ? 'text-amber-400 bg-amber-600/10' : 'text-stone-300'"
                    @click="attachMobileInstance(null)"
                  >
                    <span class="w-1.5 h-1.5 rounded-full bg-stone-500 shrink-0" />
                    Без привязки
                    <svg v-if="!sessionMobileInstanceId" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="ml-auto shrink-0">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </button>
                  <!-- Instance options -->
                  <button
                    v-for="inst in mobileInstances"
                    :key="inst.id"
                    class="w-full text-left px-3 py-2 text-xs rounded-lg hover:bg-stone-800 transition-colors flex items-center gap-2"
                    :class="sessionMobileInstanceId === inst.id ? 'text-amber-400 bg-amber-600/10' : 'text-stone-300'"
                    @click="attachMobileInstance(inst.id)"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="shrink-0" :class="sessionMobileInstanceId === inst.id ? 'text-green-400' : 'text-stone-500'">
                      <rect x="5" y="2" width="14" height="20" rx="2" ry="2" /><line x1="12" y1="18" x2="12.01" y2="18" />
                    </svg>
                    <span class="flex-1">{{ inst.name }}</span>
                    <span v-if="inst.description" class="text-stone-600 text-[10px] truncate max-w-[100px]">{{ inst.description }}</span>
                    <svg v-if="sessionMobileInstanceId === inst.id" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="ml-auto shrink-0">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </button>
                </div>
                <p class="text-[10px] text-stone-600 mt-2">Привязка определяет LLM/RAG/промпт из настроек моб. приложения</p>
              </template>
            </div>
          </div>
        </div>
      </div>

    </template>

    <!-- ============ NON-ADMIN: CLAUDE-LIKE WELCOME ============ -->
    <template v-else>
      <div class="flex-1 flex flex-col">
        <!-- Minimal header -->
        <div class="shrink-0 flex items-center justify-between px-4 py-3">
          <div class="flex items-center gap-2">
            <div class="w-8 h-8">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="w-full h-full">
                <defs><linearGradient id="gl" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#F0A830"/><stop offset="100%" stop-color="#C27010"/></linearGradient></defs>
                <path fill="url(#gl)" fill-rule="evenodd" d="M 431.8 217.4 L 484.1 226.3 L 484.1 285.7 L 431.8 294.6 L 407.6 353.0 L 438.3 396.3 L 396.3 438.3 L 353.0 407.6 L 294.6 431.8 L 285.7 484.1 L 226.3 484.1 L 217.4 431.8 L 159.0 407.6 L 115.7 438.3 L 73.7 396.3 L 104.4 353.0 L 80.2 294.6 L 27.9 285.7 L 27.9 226.3 L 80.2 217.4 L 104.4 159.0 L 73.7 115.7 L 115.7 73.7 L 159.0 104.4 L 217.4 80.2 L 226.3 27.9 L 285.7 27.9 L 294.6 80.2 L 353.0 104.4 L 396.3 73.7 L 438.3 115.7 L 407.6 159.0 Z M 341.0 256.0 A 85 85 0 1 0 171.0 256.0 A 85 85 0 1 0 341.0 256.0 Z"/>
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
        <div class="flex-1 flex flex-col px-6">
          <div v-if="isLoading" class="flex-1 flex items-center justify-center">
            <div class="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
          </div>
          <div v-else-if="error" class="flex-1 flex items-center justify-center text-center">
            <div>
              <p class="text-red-400 text-sm mb-2">{{ error }}</p>
              <button class="text-amber-400 text-sm" @click="loadSessions">Повторить</button>
            </div>
          </div>
          <template v-else>
            <div class="flex-1" />
            <div class="text-center mb-6">
              <h1 class="text-2xl font-bold text-white mb-2">
                Привет, {{ auth.user?.username }}
              </h1>
              <p class="text-stone-400 text-sm leading-relaxed max-w-sm mx-auto">
                Я — ваш AI-ассистент. Помогу настроить чат под себя: от написания системного промпта до работы с массивами контекста. Просто опишите задачу — и я проведу вас по шагам.
              </p>
            </div>
            <div class="w-full max-w-sm mx-auto mb-6">
              <div class="flex items-end gap-2">
                <textarea
                  v-model="welcomeInput"
                  rows="1"
                  class="flex-1 resize-none rounded-2xl bg-stone-800 border border-stone-700 px-4 py-3 text-sm text-stone-300 placeholder-stone-500 focus:outline-none focus:border-amber-500 transition-colors"
                  placeholder="Напишите сообщение..."
                  @keydown.enter.exact.prevent="sendFromWelcome"
                  @input="($event.target as HTMLTextAreaElement).style.height = 'auto'; ($event.target as HTMLTextAreaElement).style.height = Math.min(($event.target as HTMLTextAreaElement).scrollHeight, 120) + 'px'"
                />
                <button
                  :disabled="!welcomeInput.trim() || isSending"
                  class="shrink-0 w-11 h-11 rounded-xl bg-amber-600 hover:bg-amber-700 disabled:bg-stone-700 disabled:text-stone-500 flex items-center justify-center transition-colors"
                  @click="sendFromWelcome"
                >
                  <div v-if="isSending" class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-white">
                    <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </button>
              </div>
            </div>
            <div class="w-full max-w-sm mx-auto flex gap-2 mb-6">
              <button
                class="flex-1 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-700 active:bg-amber-800 text-white text-sm font-medium transition-colors flex items-center justify-center gap-2"
                :disabled="isCreating"
                @click="createNewChat"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                Новый чат
              </button>
              <button
                class="py-2.5 px-4 rounded-xl bg-stone-800 hover:bg-stone-700 active:bg-stone-600 text-stone-300 text-sm transition-colors flex items-center justify-center gap-2"
                @click="$router.push('/settings')"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
              </button>
            </div>
            <div v-if="visibleSessions.length" class="w-full max-w-sm mx-auto space-y-2 mb-6">
              <p class="text-xs text-stone-500 uppercase tracking-wide mb-2">Ваши чаты</p>
              <button
                v-for="session in visibleSessions"
                :key="session.id"
                class="w-full text-left p-3 rounded-xl bg-stone-800/60 border border-stone-700/50 hover:border-amber-600/40 hover:bg-stone-800 active:bg-stone-700/80 transition-all group"
                @click="openChat(session.id)"
              >
                <div class="flex items-center gap-3">
                  <div class="shrink-0 w-9 h-9 rounded-lg bg-amber-600/15 flex items-center justify-center">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-amber-500">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                  </div>
                  <div class="flex-1 min-w-0">
                    <span class="font-medium text-sm text-white truncate block group-hover:text-amber-200 transition-colors">
                      {{ session.title || "Чат" }}
                    </span>
                    <span v-if="session.last_message" class="text-xs text-stone-500 truncate block">
                      {{ truncate(session.last_message, 50) }}
                    </span>
                  </div>
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-stone-600 group-hover:text-amber-500 shrink-0 transition-colors">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </div>
              </button>
            </div>
            <div class="flex-1" />
          </template>
        </div>
      </div>
    </template>
  </div>
</template>
