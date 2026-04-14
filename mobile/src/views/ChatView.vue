<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Capacitor } from "@capacitor/core";
import {
  chatApi,
  type ChatMessage,
  type ChatSession,
  type StreamChunk,
  type BranchNode,
  type ContextFile,
} from "@/api/chat";
import { useAuthStore } from "@/stores/auth";
import { useTts } from "@/composables/useTts";
import MessageBubble from "@/components/MessageBubble.vue";
import ChatInput from "@/components/ChatInput.vue";
import ContextFilesPanel from "@/components/ContextFilesPanel.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const tts = useTts();
const isAdmin = computed(() => auth.isAdmin);

const sessionId = computed(() => route.params.id as string);
const title = ref("Chat");
const messages = ref<ChatMessage[]>([]);
const currentSession = ref<ChatSession | null>(null);
const isLoading = ref(false);
const isStreaming = ref(false);
const streamingContent = ref("");
const error = ref<string | null>(null);
const messagesContainer = ref<HTMLElement | null>(null);

// Panels
const showBranches = ref(false);
const showContextFiles = ref(false);
const showSettings = ref(false);
const settingsTab = ref<"files" | "prompt">("files");
const customPrompt = ref("");
const branches = ref<BranchNode[]>([]);
const contextFiles = ref<ContextFile[]>([]);
const branchesLoading = ref(false);
const contextFileInputRef = ref<HTMLInputElement | null>(null);

// Web search
const webSearchEnabled = ref(false);

// Resizable panel height (portrait) / width (landscape)
const panelSize = ref(Math.round(window.innerHeight * 0.5));
const isResizing = ref(false);
const resizeStartPos = ref(0);
const resizeStartSize = ref(0);

// Orientation
const isLandscape = ref(false);
function updateOrientation() {
  isLandscape.value = window.innerWidth > window.innerHeight;
}

// On Android native, always add bottom padding for navigation bar.
// env(safe-area-inset-bottom) is unreliable in Android WebView.
const isNativeAndroid = Capacitor.isNativePlatform() && Capacitor.getPlatform() === "android";

let abortStream: (() => void) | null = null;

// === Resize handle ===

function onResizeStart(e: TouchEvent | MouseEvent) {
  isResizing.value = true;
  const pos = "touches" in e ? e.touches[0]! : e;
  resizeStartPos.value = isLandscape.value ? pos.clientX : pos.clientY;
  resizeStartSize.value = panelSize.value;
  e.preventDefault();
}

function onResizeMove(e: TouchEvent | MouseEvent) {
  if (!isResizing.value) return;
  const pos = "touches" in e ? e.touches[0]! : e;
  if (isLandscape.value) {
    const delta = resizeStartPos.value - pos.clientX;
    panelSize.value = Math.max(150, Math.min(window.innerWidth * 0.7, resizeStartSize.value + delta));
  } else {
    const delta = pos.clientY - resizeStartPos.value;
    panelSize.value = Math.max(100, Math.min(window.innerHeight * 0.9, resizeStartSize.value + delta));
  }
}

function onResizeEnd() {
  isResizing.value = false;
}

// === Session ===

async function loadSession() {
  isLoading.value = true;
  error.value = null;
  try {
    const data = await chatApi.getSession(sessionId.value);
    currentSession.value = data.session;
    title.value = data.session.title || "Chat";
    messages.value = data.session.messages.filter(
      (m) => m.is_active !== false,
    );
    contextFiles.value = data.session.context_files || [];
    customPrompt.value = data.session.system_prompt || "";
    webSearchEnabled.value = !!data.session.web_search_enabled;
    await scrollToBottom();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось загрузить";
  } finally {
    isLoading.value = false;
  }
}

function toggleWebSearch() {
  webSearchEnabled.value = !webSearchEnabled.value;
  if (sessionId.value) {
    chatApi.updateSession(sessionId.value, {
      web_search_enabled: webSearchEnabled.value,
    });
  }
}

async function sendMessage(content: string) {
  const userMsg: ChatMessage = {
    id: "temp-" + Date.now(),
    role: "user",
    content,
    timestamp: new Date().toISOString(),
  };
  messages.value.push(userMsg);
  await scrollToBottom();

  isStreaming.value = true;
  streamingContent.value = "";

  const { abort } = chatApi.streamMessage(
    sessionId.value,
    content,
    (chunk: StreamChunk) => {
      switch (chunk.type) {
        case "chunk":
          streamingContent.value += chunk.content || "";
          scrollToBottom();
          break;
        case "assistant_message":
          if (chunk.message) {
            messages.value.push(chunk.message);
            streamingContent.value = "";
            isStreaming.value = false;
            scrollToBottom();
          }
          break;
        case "user_message":
          if (chunk.message) {
            const idx = messages.value.findIndex(
              (m) => m.id === userMsg.id,
            );
            if (idx >= 0) messages.value[idx] = chunk.message;
          }
          break;
        case "tool_start":
          streamingContent.value +=
            chunk.name === "web_search"
              ? `\n_Поиск в интернете: «${chunk.query || ""}»_\n`
              : `\n_Поиск по базе знаний: «${chunk.query || ""}»_\n`;
          break;
        case "done":
          isStreaming.value = false;
          streamingContent.value = "";
          break;
        case "error":
          isStreaming.value = false;
          // Preserve partial response so the user can still see what was streamed
          if (streamingContent.value) {
            messages.value.push({
              id: "partial-" + Date.now(),
              role: "assistant",
              content: streamingContent.value,
              timestamp: new Date().toISOString(),
            });
            streamingContent.value = "";
          }
          error.value = chunk.content || "Stream error";
          break;
      }
    },
  );

  abortStream = abort;
}

function stopStreaming() {
  if (abortStream) {
    abortStream();
    abortStream = null;
  }
  isStreaming.value = false;
  if (streamingContent.value) {
    messages.value.push({
      id: "partial-" + Date.now(),
      role: "assistant",
      content: streamingContent.value,
      timestamp: new Date().toISOString(),
    });
    streamingContent.value = "";
  }
}

function scrollToTop() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTo({ top: 0, behavior: "smooth" });
  }
}

async function scrollToBottom() {
  await nextTick();
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop =
      messagesContainer.value.scrollHeight;
  }
}

// === Branches ===

async function loadBranches() {
  branchesLoading.value = true;
  try {
    const data = await chatApi.getBranches(sessionId.value);
    branches.value = data.branches;
  } catch {
    branches.value = [];
  } finally {
    branchesLoading.value = false;
  }
}

function toggleBranches() {
  showContextFiles.value = false;
  showSettings.value = false;
  showBranches.value = !showBranches.value;
  if (showBranches.value) loadBranches();
}

async function switchBranch(messageId: string) {
  try {
    const data = await chatApi.switchBranch(sessionId.value, messageId);
    if (data.session) {
      messages.value = data.session.messages.filter(
        (m) => m.is_active !== false,
      );
      title.value = data.session.title || "Chat";
    }
    await loadBranches();
    await scrollToBottom();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось переключить";
  }
}

async function createNewBranch() {
  try {
    const data = await chatApi.newBranch(sessionId.value);
    if (data.session) {
      messages.value = data.session.messages.filter(
        (m) => m.is_active !== false,
      );
    }
    if (showBranches.value) await loadBranches();
    await scrollToBottom();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось создать ветку";
  }
}

async function deleteBranch() {
  const activeMessages = messages.value;
  if (!activeMessages.length) {
    error.value = "Нет сообщений для удаления";
    return;
  }
  if (!confirm("Удалить текущую ветку? Все сообщения будут удалены с сервера.")) return;
  try {
    for (let i = activeMessages.length - 1; i >= 0; i--) {
      const m = activeMessages[i]!;
      if (!m.id.startsWith("temp-") && !m.id.startsWith("partial-")) {
        await chatApi.deleteMessage(sessionId.value, m.id);
      }
    }
    messages.value = [];
    if (showBranches.value) await loadBranches();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось удалить";
    await loadSession();
  }
}

function flattenBranches(
  nodes: BranchNode[],
  depth = 0,
): { node: BranchNode; depth: number }[] {
  const result: { node: BranchNode; depth: number }[] = [];
  for (const n of nodes) {
    result.push({ node: n, depth });
    if (n.children?.length) {
      result.push(...flattenBranches(n.children, depth + 1));
    }
  }
  return result;
}

const flatBranches = computed(() => flattenBranches(branches.value));

// === Context Files ===

function toggleContextFiles() {
  showBranches.value = false;
  showSettings.value = false;
  showContextFiles.value = !showContextFiles.value;
}

function toggleSettings() {
  showBranches.value = false;
  showContextFiles.value = false;
  showSettings.value = !showSettings.value;
}

async function saveSystemPrompt() {
  try {
    await chatApi.updateSession(sessionId.value, {
      system_prompt: customPrompt.value,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось сохранить промпт";
  }
}

function triggerFileUpload() {
  contextFileInputRef.value?.click();
}

function handleFileUpload(event: Event) {
  const input = event.target as HTMLInputElement;
  if (!input.files) return;
  const files = Array.from(input.files);
  let loaded = 0;
  files.forEach((file) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      contextFiles.value.push({ name: file.name, content });
      loaded++;
      if (loaded === files.length) saveContextFiles();
    };
    reader.readAsText(file);
  });
  input.value = "";
}

function updateContextFiles(next: ContextFile[]) {
  contextFiles.value = next;
  saveContextFiles();
}

async function saveContextFiles() {
  try {
    await chatApi.updateSession(sessionId.value, {
      context_files: contextFiles.value,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось сохранить файлы";
  }
}

// === Message actions ===

async function handleEditMessage(messageId: string, content: string) {
  try {
    await chatApi.editMessage(sessionId.value, messageId, content);
    await loadSession();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось отредактировать";
  }
}

function handleSaveToContext(_messageId: string, content: string) {
  const name = `message-${Date.now()}.md`;
  contextFiles.value.push({ name, content });
  saveContextFiles();
  showContextFiles.value = true;
  showBranches.value = false;
  showSettings.value = false;
}

async function handleSummarizeBranch(messageId: string) {
  try {
    const data = await chatApi.summarizeBranch(sessionId.value, messageId);
    const name = `summary-${Date.now()}.md`;
    contextFiles.value.push({ name, content: data.summary });
    saveContextFiles();
    showContextFiles.value = true;
    showBranches.value = false;
    showSettings.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось суммаризировать";
  }
}

async function handleRegenerateResponse(messageId: string) {
  try {
    await chatApi.regenerateResponse(sessionId.value, messageId);
    await loadSession();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось перегенерировать";
  }
}

async function handleDeleteFromMessage(messageId: string) {
  if (!confirm("Удалить это сообщение и все последующие?")) return;
  const idx = messages.value.findIndex((m) => m.id === messageId);
  if (idx < 0) return;
  try {
    const toDelete = messages.value.slice(idx).reverse();
    for (const m of toDelete) {
      if (!m.id.startsWith("temp-") && !m.id.startsWith("partial-")) {
        await chatApi.deleteMessage(sessionId.value, m.id);
      }
    }
    messages.value = messages.value.slice(0, idx);
    if (showBranches.value) await loadBranches();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось удалить";
    await loadSession();
  }
}

const anyPanelOpen = computed(() => showBranches.value || showContextFiles.value || showSettings.value);
const activePanelName = computed(() => {
  if (showBranches.value) return "Дерево веток";
  if (showContextFiles.value) return "Файлы контекста";
  if (showSettings.value) return "Настройки";
  return "";
});

function closePanel() {
  showBranches.value = false;
  showContextFiles.value = false;
  showSettings.value = false;
}

watch(streamingContent, () => {
  scrollToBottom();
});

onMounted(async () => {
  await loadSession();
  const msg = route.query.msg as string | undefined;
  if (msg) {
    router.replace({ path: route.path, query: {} });
    sendMessage(msg);
  }
  updateOrientation();
  window.addEventListener("resize", updateOrientation);
  window.addEventListener("mousemove", onResizeMove);
  window.addEventListener("mouseup", onResizeEnd);
  window.addEventListener("touchmove", onResizeMove, { passive: false });
  window.addEventListener("touchend", onResizeEnd);
});

onUnmounted(() => {
  window.removeEventListener("resize", updateOrientation);
  window.removeEventListener("mousemove", onResizeMove);
  window.removeEventListener("mouseup", onResizeEnd);
  window.removeEventListener("touchmove", onResizeMove);
  window.removeEventListener("touchend", onResizeEnd);
});
</script>

<template>
  <div class="h-full flex" :class="isLandscape ? 'flex-row' : 'flex-col'">
    <!-- Main chat area -->
    <div class="flex-1 flex flex-col min-w-0 min-h-0">
      <!-- Header -->
      <div
        class="shrink-0 flex items-center gap-1.5 px-2 py-2.5 border-b border-stone-800 bg-stone-950/95 backdrop-blur"
      >
        <button
          class="text-stone-400 hover:text-white transition-colors p-1"
          @click="router.back()"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="w-6 h-6 shrink-0">
          <defs><linearGradient id="hg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#F0A830"/><stop offset="100%" stop-color="#C27010"/></linearGradient></defs>
          <path fill="url(#hg)" fill-rule="evenodd" d="M 431.8 217.4 L 484.1 226.3 L 484.1 285.7 L 431.8 294.6 L 407.6 353.0 L 438.3 396.3 L 396.3 438.3 L 353.0 407.6 L 294.6 431.8 L 285.7 484.1 L 226.3 484.1 L 217.4 431.8 L 159.0 407.6 L 115.7 438.3 L 73.7 396.3 L 104.4 353.0 L 80.2 294.6 L 27.9 285.7 L 27.9 226.3 L 80.2 217.4 L 104.4 159.0 L 73.7 115.7 L 115.7 73.7 L 159.0 104.4 L 217.4 80.2 L 226.3 27.9 L 285.7 27.9 L 294.6 80.2 L 353.0 104.4 L 396.3 73.7 L 438.3 115.7 L 407.6 159.0 Z M 341.0 256.0 A 85 85 0 1 0 171.0 256.0 A 85 85 0 1 0 341.0 256.0 Z"/>
        </svg>
        <h1 class="text-sm font-medium text-white truncate flex-1">
          {{ title }}
        </h1>

        <!-- Toolbar buttons -->
        <button
          class="p-1.5 rounded-lg text-stone-400 hover:text-white transition-colors"
          title="Новая ветка"
          @click="createNewBranch"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>

        <button
          class="p-1.5 rounded-lg transition-colors"
          :class="showContextFiles ? 'bg-amber-600/20 text-amber-400' : 'text-stone-400 hover:text-white'"
          title="Файлы контекста"
          @click="toggleContextFiles"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
          </svg>
        </button>

        <button
          class="p-1.5 rounded-lg transition-colors"
          :class="showBranches ? 'bg-amber-600/20 text-amber-400' : 'text-stone-400 hover:text-white'"
          title="Дерево веток"
          @click="toggleBranches"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="6" y1="3" x2="6" y2="15" />
            <circle cx="18" cy="6" r="3" />
            <circle cx="6" cy="18" r="3" />
            <path d="M18 9a9 9 0 0 1-9 9" />
          </svg>
        </button>

        <button
          class="p-1.5 rounded-lg transition-colors"
          :class="showSettings ? 'bg-amber-600/20 text-amber-400' : 'text-stone-400 hover:text-white'"
          title="Настройки сессии"
          @click="toggleSettings"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 7h-9" /><path d="M14 17H5" /><circle cx="17" cy="17" r="3" /><circle cx="7" cy="7" r="3" />
          </svg>
        </button>

        <button
          class="p-1.5 rounded-lg text-stone-400 hover:text-red-400 transition-colors"
          title="Удалить ветку"
          @click="deleteBranch"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </svg>
        </button>

        <button
          class="p-1.5 rounded-lg text-stone-400 hover:text-red-400 transition-colors"
          title="Выйти"
          @click="auth.logout(); router.replace('/login')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
          </svg>
        </button>
      </div>

      <!-- Portrait: panel drops down below header -->
      <template v-if="!isLandscape && anyPanelOpen">
        <div
          class="shrink-0 bg-stone-900/95 border-b border-stone-700 overflow-y-auto flex flex-col"
          :style="{ height: panelSize + 'px' }"
        >
          <!-- Branch Tree -->
          <template v-if="showBranches">
            <div class="px-3 py-2 text-xs font-medium text-stone-400 uppercase tracking-wide">Дерево веток</div>
            <div v-if="branchesLoading" class="flex justify-center py-4">
              <div class="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
            </div>
            <div v-else-if="!flatBranches.length" class="px-3 py-3 text-sm text-stone-500">Пока нет истории диалогов</div>
            <div v-else class="pb-2 overflow-x-auto">
              <div class="min-w-max">
                <button
                  v-for="{ node, depth } in flatBranches"
                  :key="node.id"
                  class="w-full text-left px-3 py-1.5 text-xs hover:bg-stone-800/50 transition-colors flex items-center gap-1.5 whitespace-nowrap"
                  :class="node.is_active ? 'text-amber-400' : 'text-stone-400'"
                  :style="{ paddingLeft: `${12 + depth * 16}px` }"
                  @click="switchBranch(node.id)"
                >
                  <span class="shrink-0">
                    <svg v-if="node.role === 'user'" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
                    </svg>
                    <svg v-else xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 2a8 8 0 0 0-8 8c0 3.5 2 6 5 7.5V21h6v-3.5c3-1.5 5-4 5-7.5a8 8 0 0 0-8-8z" />
                    </svg>
                  </span>
                  <span>{{ node.content_preview || '...' }}</span>
                  <span v-if="node.is_active" class="shrink-0 text-[10px] bg-amber-600/30 text-amber-400 px-1 rounded">текущая</span>
                </button>
              </div>
            </div>
          </template>

          <!-- Context Files -->
          <template v-if="showContextFiles">
            <input ref="contextFileInputRef" type="file" multiple accept=".txt,.md,.json,.csv,.xml,.yaml,.yml,.log,.py,.js,.ts,.html,.css" class="hidden" @change="handleFileUpload" />
            <ContextFilesPanel
              :files="contextFiles"
              @update="updateContextFiles"
              @upload="triggerFileUpload"
            />
          </template>

          <!-- Settings panel with tabs -->
          <template v-if="showSettings">
            <div class="flex border-b border-stone-700">
              <button
                class="flex-1 px-3 py-2 text-xs font-medium uppercase tracking-wide transition-colors"
                :class="settingsTab === 'files' ? 'text-amber-400 border-b-2 border-amber-400' : 'text-stone-500 hover:text-stone-300'"
                @click="settingsTab = 'files'"
              >Файлы ({{ contextFiles.length }})</button>
              <button
                class="flex-1 px-3 py-2 text-xs font-medium uppercase tracking-wide transition-colors"
                :class="settingsTab === 'prompt' ? 'text-amber-400 border-b-2 border-amber-400' : 'text-stone-500 hover:text-stone-300'"
                @click="settingsTab = 'prompt'"
              >Промпт</button>
            </div>
            <template v-if="settingsTab === 'files'">
              <input ref="contextFileInputRef" type="file" multiple accept=".txt,.md,.json,.csv,.xml,.yaml,.yml,.log,.py,.js,.ts,.html,.css" class="hidden" @change="handleFileUpload" />
              <ContextFilesPanel
                :files="contextFiles"
                @update="updateContextFiles"
                @upload="triggerFileUpload"
              />
            </template>
            <template v-if="settingsTab === 'prompt'">
              <div class="flex-1 flex flex-col min-h-0 px-3 py-2">
                <label class="block text-xs text-stone-400 mb-1">Системный промпт</label>
                <textarea
                  v-model="customPrompt"
                  class="flex-1 w-full bg-stone-950 text-stone-200 text-xs rounded-lg p-2 border border-stone-700 focus:border-amber-500 focus:outline-none resize-none min-h-[60px]"
                  placeholder="Пользовательский промпт для этой сессии..."
                />
              </div>
              <div class="shrink-0 px-3 pb-1">
                <button class="w-full py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium transition-colors" @click="saveSystemPrompt">Сохранить</button>
              </div>
            </template>
          </template>

        </div>

        <!-- Resize handle (portrait) -->
        <div
          class="shrink-0 h-3 flex items-center justify-center cursor-row-resize bg-stone-900/80 border-b border-stone-700 touch-none select-none"
          @mousedown="onResizeStart"
          @touchstart="onResizeStart"
        >
          <div class="w-10 h-1 rounded-full bg-stone-600" />
        </div>
      </template>

      <!-- Messages wrapper -->
      <div class="flex-1 relative min-h-0">
        <div
          ref="messagesContainer"
          class="absolute inset-0 overflow-y-auto py-4"
        >
          <div v-if="isLoading" class="flex items-center justify-center h-32">
            <div class="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
          </div>

          <div v-if="error" class="mx-4 mb-3 p-3 rounded-xl bg-red-900/30 border border-red-800/50 text-red-400 text-sm">
            {{ error }}
            <button class="ml-2 underline text-xs" @click="error = null">закрыть</button>
          </div>

          <template v-if="!isLoading">
            <MessageBubble
              v-for="msg in messages"
              :key="msg.id"
              :message="msg"
              :is-speaking="tts.speakingMessageId.value === msg.id"
              :is-admin="isAdmin"
              @speak="tts.speak($event, msg.id)"
              @stop-speak="tts.stop()"
              @edit="handleEditMessage"
              @save-to-context="handleSaveToContext"
              @summarize-branch="handleSummarizeBranch"
              @delete-branch="handleDeleteFromMessage"
              @regenerate="handleRegenerateResponse"
            />

            <MessageBubble
              v-if="isStreaming && streamingContent"
              :message="{ id: 'streaming', role: 'assistant', content: streamingContent, timestamp: new Date().toISOString() }"
              :is-streaming="true"
              :is-admin="isAdmin"
            />

            <div v-if="isStreaming && !streamingContent" class="flex justify-start px-4 mb-3">
              <div class="bg-stone-800 rounded-2xl rounded-bl-md px-4 py-3 flex gap-1">
                <div class="w-2 h-2 rounded-full bg-slate-500 animate-bounce" style="animation-delay: 0ms" />
                <div class="w-2 h-2 rounded-full bg-slate-500 animate-bounce" style="animation-delay: 150ms" />
                <div class="w-2 h-2 rounded-full bg-slate-500 animate-bounce" style="animation-delay: 300ms" />
              </div>
            </div>
          </template>
        </div>

        <!-- Scroll buttons -->
        <div class="absolute right-2 top-1/2 -translate-y-1/2 z-10 flex flex-col gap-1.5">
          <button
            class="p-2 rounded-full bg-stone-800/80 backdrop-blur border border-stone-700 shadow-md text-stone-400 hover:text-white active:bg-stone-700 transition-colors"
            @click="scrollToTop"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <polyline points="5 12 12 5 19 12" />
              <line x1="5" y1="3" x2="19" y2="3" />
            </svg>
          </button>
          <button
            class="p-2 rounded-full bg-stone-800/80 backdrop-blur border border-stone-700 shadow-md text-stone-400 hover:text-white active:bg-stone-700 transition-colors"
            @click="scrollToBottom"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <polyline points="5 12 12 19 19 12" />
              <line x1="5" y1="21" x2="19" y2="21" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Input with web search toggle -->
      <div
        class="flex items-end gap-1 px-2 pt-1 border-t border-stone-700/50 bg-stone-900/95"
        :class="isNativeAndroid ? 'pb-14' : 'pb-2'"
      >
        <button
          :class="[
            'p-2.5 rounded-xl transition-colors shrink-0',
            webSearchEnabled ? 'bg-blue-500/20 text-blue-400' : 'text-stone-500 hover:text-stone-300'
          ]"
          :title="webSearchEnabled ? 'Веб-поиск включён' : 'Веб-поиск выключен'"
          @click="toggleWebSearch"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>
        </button>
        <div class="flex-1">
          <ChatInput
            :disabled="isLoading"
            :is-streaming="isStreaming"
            @send="sendMessage"
            @stop="stopStreaming"
          />
        </div>
      </div>
    </div>

    <!-- Landscape: side panel slides from right -->
    <template v-if="isLandscape && anyPanelOpen">
      <div
        class="shrink-0 w-3 flex items-center justify-center cursor-col-resize bg-stone-900/80 border-l border-stone-700 touch-none select-none"
        @mousedown="onResizeStart"
        @touchstart="onResizeStart"
      >
        <div class="h-10 w-1 rounded-full bg-stone-600" />
      </div>

      <div
        class="shrink-0 bg-stone-900/95 border-l border-stone-700 overflow-y-auto flex flex-col"
        :style="{ width: panelSize + 'px' }"
      >
        <div class="shrink-0 flex items-center justify-between px-3 py-2 border-b border-stone-800">
          <span class="text-xs font-medium text-stone-400 uppercase tracking-wide">{{ activePanelName }}</span>
          <button class="text-stone-500 hover:text-white transition-colors" @click="closePanel">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <!-- Branch Tree (landscape) -->
        <template v-if="showBranches">
          <div v-if="branchesLoading" class="flex justify-center py-4">
            <div class="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
          </div>
          <div v-else-if="!flatBranches.length" class="px-3 py-3 text-sm text-stone-500">Пока нет истории диалогов</div>
          <div v-else class="flex-1 overflow-y-auto overflow-x-auto pb-2">
            <div class="min-w-max">
              <button
                v-for="{ node, depth } in flatBranches"
                :key="node.id"
                class="w-full text-left px-3 py-1.5 text-xs hover:bg-stone-800/50 transition-colors flex items-center gap-1.5 whitespace-nowrap"
                :class="node.is_active ? 'text-amber-400' : 'text-stone-400'"
                :style="{ paddingLeft: `${12 + depth * 16}px` }"
                @click="switchBranch(node.id)"
              >
                <span class="shrink-0">
                  <svg v-if="node.role === 'user'" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
                  </svg>
                  <svg v-else xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 2a8 8 0 0 0-8 8c0 3.5 2 6 5 7.5V21h6v-3.5c3-1.5 5-4 5-7.5a8 8 0 0 0-8-8z" />
                  </svg>
                </span>
                <span>{{ node.content_preview || '...' }}</span>
                <span v-if="node.is_active" class="shrink-0 text-[10px] bg-amber-600/30 text-amber-400 px-1 rounded">текущая</span>
              </button>
            </div>
          </div>
        </template>

        <!-- Context Files (landscape) -->
        <template v-if="showContextFiles">
          <input ref="contextFileInputRef" type="file" multiple accept=".txt,.md,.json,.csv,.xml,.yaml,.yml,.log,.py,.js,.ts,.html,.css" class="hidden" @change="handleFileUpload" />
          <ContextFilesPanel
            :files="contextFiles"
            @update="updateContextFiles"
            @upload="triggerFileUpload"
          />
        </template>

        <!-- Settings (landscape) -->
        <template v-if="showSettings">
          <div class="flex border-b border-stone-700">
            <button
              class="flex-1 px-3 py-2 text-xs font-medium uppercase tracking-wide transition-colors"
              :class="settingsTab === 'files' ? 'text-amber-400 border-b-2 border-amber-400' : 'text-stone-500 hover:text-stone-300'"
              @click="settingsTab = 'files'"
            >Файлы ({{ contextFiles.length }})</button>
            <button
              class="flex-1 px-3 py-2 text-xs font-medium uppercase tracking-wide transition-colors"
              :class="settingsTab === 'prompt' ? 'text-amber-400 border-b-2 border-amber-400' : 'text-stone-500 hover:text-stone-300'"
              @click="settingsTab = 'prompt'"
            >Промпт</button>
          </div>
          <template v-if="settingsTab === 'files'">
            <ContextFilesPanel
              :files="contextFiles"
              @update="updateContextFiles"
              @upload="triggerFileUpload"
            />
          </template>
          <template v-if="settingsTab === 'prompt'">
            <div class="flex-1 flex flex-col min-h-0 px-3 py-2">
              <label class="block text-xs text-stone-400 mb-1">Системный промпт</label>
              <textarea
                v-model="customPrompt"
                class="flex-1 w-full bg-stone-950 text-stone-200 text-xs rounded-lg p-2 border border-stone-700 focus:border-amber-500 focus:outline-none resize-none min-h-[60px]"
                placeholder="Пользовательский промпт для этой сессии..."
              />
            </div>
            <div class="shrink-0 px-3 pb-2">
              <button class="w-full py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium transition-colors" @click="saveSystemPrompt">Сохранить</button>
            </div>
          </template>
        </template>

      </div>
    </template>
  </div>
</template>
