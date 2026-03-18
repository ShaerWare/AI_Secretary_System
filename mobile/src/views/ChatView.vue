<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  chatApi,
  type ChatMessage,
  type ChatSession,
  type StreamChunk,
  type BranchNode,
  type ContextFile,
} from "@/api/chat";
import {
  adminApi,
  type CloudProvider,
  type KnowledgeCollection,
  type LlmOption,
} from "@/api/admin";
import { useAuthStore } from "@/stores/auth";
import { useTts } from "@/composables/useTts";
import MessageBubble from "@/components/MessageBubble.vue";
import ChatInput from "@/components/ChatInput.vue";

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
const branches = ref<BranchNode[]>([]);
const contextFiles = ref<ContextFile[]>([]);
const branchesLoading = ref(false);
const contextFileInputRef = ref<HTMLInputElement | null>(null);

// Admin: LLM & RAG
const llmProviders = ref<CloudProvider[]>([]);
const ragCollections = ref<KnowledgeCollection[]>([]);
const selectedLlm = ref<string>("default");
const selectedCollectionIds = ref<number[]>([]);
const showLlmDropdown = ref(false);
const showRagDropdown = ref(false);
const showExportDropdown = ref(false);
const customPrompt = ref("");

const llmOptions = computed<LlmOption[]>(() => {
  const opts: LlmOption[] = [
    { value: "default", label: "Default", type: "vllm" },
    { value: "vllm", label: "vLLM (Local)", type: "vllm" },
  ];
  for (const p of llmProviders.value) {
    opts.push({
      value: `cloud:${p.id}`,
      label: `${p.name} (${p.model_name})`,
      type: "cloud",
    });
  }
  return opts;
});

// Resizable panel height (portrait) / width (landscape)
const panelSize = ref(200);
const isResizing = ref(false);
const resizeStartPos = ref(0);
const resizeStartSize = ref(0);

// Orientation
const isLandscape = ref(false);
function updateOrientation() {
  isLandscape.value = window.innerWidth > window.innerHeight;
}

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
    panelSize.value = Math.max(100, Math.min(window.innerHeight * 0.6, resizeStartSize.value + delta));
  }
}

function onResizeEnd() {
  isResizing.value = false;
}

// === Admin data ===

async function loadAdminData() {
  if (!isAdmin.value) return;
  try {
    const [providerData, collectionData] = await Promise.all([
      adminApi.getProviders(),
      adminApi.getCollections(),
    ]);
    llmProviders.value = providerData.providers;
    ragCollections.value = collectionData.collections.filter((c) => c.enabled);
  } catch {
    // Non-critical — admin features just won't show options
  }
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
    await scrollToBottom();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load";
  } finally {
    isLoading.value = false;
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

  // Build LLM/RAG overrides for admin
  const overrides: Record<string, unknown> = {};
  if (isAdmin.value) {
    if (selectedLlm.value && selectedLlm.value !== "default") {
      overrides.llm_backend = selectedLlm.value;
    }
    if (selectedCollectionIds.value.length > 0) {
      overrides.rag_mode = "selected";
      overrides.knowledge_collection_ids = selectedCollectionIds.value;
    }
  }

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
          streamingContent.value += "\n_Searching..._\n";
          break;
        case "done":
          isStreaming.value = false;
          streamingContent.value = "";
          break;
        case "error":
          isStreaming.value = false;
          streamingContent.value = "";
          error.value = chunk.content || "Stream error";
          break;
      }
    },
    overrides,
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
    error.value = e instanceof Error ? e.message : "Failed to switch";
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
    error.value = e instanceof Error ? e.message : "Failed to create branch";
  }
}

async function deleteBranch() {
  const activeMessages = messages.value;
  if (!activeMessages.length) {
    error.value = "No messages to delete";
    return;
  }
  if (!confirm("Delete current branch? All messages will be removed from the server.")) return;
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
    error.value = e instanceof Error ? e.message : "Failed to delete";
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

function removeContextFile(index: number) {
  contextFiles.value.splice(index, 1);
  saveContextFiles();
}

async function saveContextFiles() {
  try {
    await chatApi.updateSession(sessionId.value, {
      context_files: contextFiles.value,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to save files";
  }
}

// === Settings panel ===

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
    error.value = e instanceof Error ? e.message : "Failed to save prompt";
  }
}

// === LLM / RAG dropdowns ===

function selectLlm(value: string) {
  selectedLlm.value = value;
  showLlmDropdown.value = false;
}

function toggleCollection(id: number) {
  const idx = selectedCollectionIds.value.indexOf(id);
  if (idx >= 0) {
    selectedCollectionIds.value.splice(idx, 1);
  } else {
    selectedCollectionIds.value.push(id);
  }
}

// === Export ===

function copyChatToClipboard() {
  const text = messages.value
    .map((m) => `**${m.role === "user" ? "User" : "Assistant"}:**\n${m.content}`)
    .join("\n\n---\n\n");
  navigator.clipboard.writeText(text);
  showExportDropdown.value = false;
}

function exportChatMarkdown() {
  const text = `# ${title.value}\n\n` + messages.value
    .map((m) => `## ${m.role === "user" ? "User" : "Assistant"}\n\n${m.content}`)
    .join("\n\n---\n\n");
  downloadFile(`${title.value}.md`, text, "text/markdown");
  showExportDropdown.value = false;
}

function exportChatJson() {
  const data = {
    title: title.value,
    exported: new Date().toISOString(),
    messages: messages.value.map((m) => ({
      role: m.role,
      content: m.content,
      timestamp: m.timestamp,
    })),
  };
  downloadFile(`${title.value}.json`, JSON.stringify(data, null, 2), "application/json");
  showExportDropdown.value = false;
}

function downloadFile(name: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

// === Message actions ===

async function handleEditMessage(messageId: string, content: string) {
  try {
    await chatApi.editMessage(sessionId.value, messageId, content);
    await loadSession();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to edit";
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
    error.value = e instanceof Error ? e.message : "Failed to summarize";
  }
}

async function handleRegenerateResponse(messageId: string) {
  try {
    await chatApi.regenerateResponse(sessionId.value, messageId);
    await loadSession();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to regenerate";
  }
}

async function handleDeleteFromMessage(messageId: string) {
  if (!confirm("Delete this message and everything after it?")) return;
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
    error.value = e instanceof Error ? e.message : "Failed to delete";
    await loadSession();
  }
}

const anyPanelOpen = computed(() => showBranches.value || showContextFiles.value || showSettings.value);
const activePanelName = computed(() => {
  if (showBranches.value) return "Branch Tree";
  if (showContextFiles.value) return "Context Files";
  if (showSettings.value) return "Settings";
  return "";
});

function closePanel() {
  showBranches.value = false;
  showContextFiles.value = false;
  showSettings.value = false;
}

// Close dropdowns on outside click
function onGlobalClick() {
  showLlmDropdown.value = false;
  showRagDropdown.value = false;
  showExportDropdown.value = false;
}

watch(streamingContent, () => {
  scrollToBottom();
});

onMounted(() => {
  loadSession();
  loadAdminData();
  updateOrientation();
  window.addEventListener("resize", updateOrientation);
  window.addEventListener("mousemove", onResizeMove);
  window.addEventListener("mouseup", onResizeEnd);
  window.addEventListener("touchmove", onResizeMove, { passive: false });
  window.addEventListener("touchend", onResizeEnd);
  document.addEventListener("click", onGlobalClick);
});

onUnmounted(() => {
  window.removeEventListener("resize", updateOrientation);
  window.removeEventListener("mousemove", onResizeMove);
  window.removeEventListener("mouseup", onResizeEnd);
  window.removeEventListener("touchmove", onResizeMove);
  window.removeEventListener("touchend", onResizeEnd);
  document.removeEventListener("click", onGlobalClick);
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
        <h1 class="text-sm font-medium text-white truncate flex-1">
          {{ title }}
        </h1>

        <!-- Admin toolbar buttons -->
        <template v-if="isAdmin">
          <!-- LLM Selector -->
          <div class="relative" @click.stop>
            <button
              class="p-1.5 rounded-lg transition-colors"
              :class="selectedLlm !== 'default' ? 'bg-amber-600/20 text-amber-400' : 'text-stone-400 hover:text-white'"
              title="LLM Provider"
              @click="showLlmDropdown = !showLlmDropdown; showRagDropdown = false; showExportDropdown = false"
            >
              <!-- Brain icon -->
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2a8 8 0 0 0-8 8c0 3.5 2 6 5 7.5V21h6v-3.5c3-1.5 5-4 5-7.5a8 8 0 0 0-8-8z" />
              </svg>
            </button>
            <!-- LLM Dropdown -->
            <div
              v-if="showLlmDropdown"
              class="absolute right-0 top-full mt-1 bg-stone-900 border border-stone-700 rounded-xl shadow-xl z-50 min-w-[200px] py-1 max-h-[300px] overflow-y-auto"
            >
              <button
                v-for="opt in llmOptions"
                :key="opt.value"
                class="w-full text-left px-3 py-2 text-xs hover:bg-stone-800 transition-colors flex items-center gap-2"
                :class="selectedLlm === opt.value ? 'text-amber-400' : 'text-stone-300'"
                @click="selectLlm(opt.value)"
              >
                <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="opt.type === 'cloud' ? 'bg-blue-400' : 'bg-green-400'" />
                {{ opt.label }}
                <svg v-if="selectedLlm === opt.value" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="ml-auto shrink-0">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </button>
            </div>
          </div>

          <!-- RAG Collections -->
          <div v-if="ragCollections.length" class="relative" @click.stop>
            <button
              class="p-1.5 rounded-lg transition-colors"
              :class="selectedCollectionIds.length ? 'bg-amber-600/20 text-amber-400' : 'text-stone-400 hover:text-white'"
              title="Knowledge Base"
              @click="showRagDropdown = !showRagDropdown; showLlmDropdown = false; showExportDropdown = false"
            >
              <!-- BookOpen icon -->
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" /><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
              </svg>
            </button>
            <!-- RAG Dropdown -->
            <div
              v-if="showRagDropdown"
              class="absolute right-0 top-full mt-1 bg-stone-900 border border-stone-700 rounded-xl shadow-xl z-50 min-w-[220px] py-1 max-h-[300px] overflow-y-auto"
            >
              <label
                v-for="col in ragCollections"
                :key="col.id"
                class="flex items-center gap-2 px-3 py-2 text-xs hover:bg-stone-800 transition-colors cursor-pointer"
                :class="selectedCollectionIds.includes(col.id) ? 'text-amber-400' : 'text-stone-300'"
              >
                <input
                  type="checkbox"
                  :checked="selectedCollectionIds.includes(col.id)"
                  class="accent-amber-500"
                  @change="toggleCollection(col.id)"
                />
                <span class="flex-1">{{ col.name }}</span>
                <span class="text-stone-600 text-[10px]">{{ col.document_count }} docs</span>
              </label>
            </div>
          </div>

          <!-- Settings (system prompt) -->
          <button
            class="p-1.5 rounded-lg transition-colors"
            :class="showSettings ? 'bg-amber-600/20 text-amber-400' : 'text-stone-400 hover:text-white'"
            title="Session settings"
            @click="toggleSettings"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>

          <!-- Export -->
          <div class="relative" @click.stop>
            <button
              class="p-1.5 rounded-lg text-stone-400 hover:text-white transition-colors"
              title="Export"
              @click="showExportDropdown = !showExportDropdown; showLlmDropdown = false; showRagDropdown = false"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
              </svg>
            </button>
            <!-- Export Dropdown -->
            <div
              v-if="showExportDropdown"
              class="absolute right-0 top-full mt-1 bg-stone-900 border border-stone-700 rounded-xl shadow-xl z-50 min-w-[160px] py-1"
            >
              <button class="w-full text-left px-3 py-2 text-xs text-stone-300 hover:bg-stone-800 transition-colors" @click="copyChatToClipboard">
                Copy to clipboard
              </button>
              <button class="w-full text-left px-3 py-2 text-xs text-stone-300 hover:bg-stone-800 transition-colors" @click="exportChatMarkdown">
                Export Markdown
              </button>
              <button class="w-full text-left px-3 py-2 text-xs text-stone-300 hover:bg-stone-800 transition-colors" @click="exportChatJson">
                Export JSON
              </button>
            </div>
          </div>
        </template>

        <!-- Toolbar buttons (admin: all, non-admin: none of branch/context) -->
        <template v-if="isAdmin">
          <button
            class="p-1.5 rounded-lg transition-colors"
            :class="showContextFiles ? 'bg-amber-600/20 text-amber-400' : 'text-stone-400 hover:text-white'"
            title="Context files"
            @click="toggleContextFiles"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>

          <button
            class="p-1.5 rounded-lg transition-colors"
            :class="showBranches ? 'bg-amber-600/20 text-amber-400' : 'text-stone-400 hover:text-white'"
            title="Branch tree"
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
            class="p-1.5 rounded-lg text-stone-400 hover:text-white transition-colors"
            title="New branch"
            @click="createNewBranch"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>

          <button
            class="p-1.5 rounded-lg text-stone-400 hover:text-red-400 transition-colors"
            title="Delete branch"
            @click="deleteBranch"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
          </button>
        </template>
      </div>

      <!-- Portrait: panel drops down below header -->
      <template v-if="!isLandscape && anyPanelOpen">
        <!-- Panel content -->
        <div
          class="shrink-0 bg-stone-900/95 border-b border-stone-700 overflow-y-auto"
          :style="{ height: panelSize + 'px' }"
        >
          <!-- Branch Tree -->
          <template v-if="showBranches">
            <div class="px-3 py-2 text-xs font-medium text-stone-400 uppercase tracking-wide">
              Branch Tree
            </div>
            <div v-if="branchesLoading" class="flex justify-center py-4">
              <div class="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
            </div>
            <div v-else-if="!flatBranches.length" class="px-3 py-3 text-sm text-stone-500">
              No branches yet
            </div>
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
                  <span v-if="node.is_active" class="shrink-0 text-[10px] bg-amber-600/30 text-amber-400 px-1 rounded">active</span>
                </button>
              </div>
            </div>
          </template>

          <!-- Context Files -->
          <template v-if="showContextFiles">
            <div class="px-3 py-2 flex items-center justify-between">
              <span class="text-xs font-medium text-stone-400 uppercase tracking-wide">
                Context Files ({{ contextFiles.length }})
              </span>
              <button class="text-xs text-amber-400 hover:text-amber-300 transition-colors" @click="triggerFileUpload">
                + Add file
              </button>
            </div>
            <input ref="contextFileInputRef" type="file" multiple accept=".txt,.md,.json,.csv,.xml,.yaml,.yml,.log,.py,.js,.ts,.html,.css" class="hidden" @change="handleFileUpload" />
            <div v-if="!contextFiles.length" class="px-3 py-3 text-sm text-stone-500">No files attached</div>
            <div v-else class="pb-2">
              <div v-for="(file, index) in contextFiles" :key="index" class="flex items-center gap-2 px-3 py-1.5 hover:bg-stone-800/50">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-stone-500 shrink-0">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
                </svg>
                <span class="text-xs text-stone-300 truncate flex-1">{{ file.name }}</span>
                <span class="text-[10px] text-stone-500">{{ Math.round(file.content.length / 1024) || '<1' }}KB</span>
                <button class="text-stone-500 hover:text-red-400 transition-colors" @click="removeContextFile(index)">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            </div>
          </template>

          <!-- Settings panel -->
          <template v-if="showSettings">
            <div class="px-3 py-2 text-xs font-medium text-stone-400 uppercase tracking-wide">
              Session Settings
            </div>
            <div class="px-3 pb-3">
              <label class="block text-xs text-stone-400 mb-1">System Prompt</label>
              <textarea
                v-model="customPrompt"
                rows="5"
                class="w-full bg-stone-950 text-stone-200 text-xs rounded-lg p-2 border border-stone-700 focus:border-amber-500 focus:outline-none resize-y min-h-[80px]"
                placeholder="Custom system prompt for this session..."
              />
              <button
                class="mt-2 w-full py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium transition-colors"
                @click="saveSystemPrompt"
              >
                Save prompt
              </button>
            </div>
          </template>
        </div>

        <!-- Resize handle (portrait: horizontal bar at bottom of panel) -->
        <div
          class="shrink-0 h-3 flex items-center justify-center cursor-row-resize bg-stone-900/80 border-b border-stone-700 touch-none select-none"
          @mousedown="onResizeStart"
          @touchstart="onResizeStart"
        >
          <div class="w-10 h-1 rounded-full bg-stone-600" />
        </div>
      </template>

      <!-- Messages wrapper (relative for scroll buttons) -->
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
            <button class="ml-2 underline text-xs" @click="error = null">dismiss</button>
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

      <!-- Input -->
      <ChatInput
        :disabled="isLoading"
        :is-streaming="isStreaming"
        @send="sendMessage"
        @stop="stopStreaming"
      />
    </div>

    <!-- Landscape: side panel slides from right -->
    <template v-if="isLandscape && anyPanelOpen">
      <!-- Resize handle (vertical bar on left edge of panel) -->
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
        <!-- Panel header with close -->
        <div class="shrink-0 flex items-center justify-between px-3 py-2 border-b border-stone-800">
          <span class="text-xs font-medium text-stone-400 uppercase tracking-wide">
            {{ activePanelName }}
          </span>
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
          <div v-else-if="!flatBranches.length" class="px-3 py-3 text-sm text-stone-500">No branches yet</div>
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
                <span v-if="node.is_active" class="shrink-0 text-[10px] bg-amber-600/30 text-amber-400 px-1 rounded">active</span>
              </button>
            </div>
          </div>
        </template>

        <!-- Context Files (landscape) -->
        <template v-if="showContextFiles">
          <div class="shrink-0 px-3 py-2 flex justify-end">
            <button class="text-xs text-amber-400 hover:text-amber-300 transition-colors" @click="triggerFileUpload">
              + Add file
            </button>
          </div>
          <input ref="contextFileInputRef" type="file" multiple accept=".txt,.md,.json,.csv,.xml,.yaml,.yml,.log,.py,.js,.ts,.html,.css" class="hidden" @change="handleFileUpload" />
          <div v-if="!contextFiles.length" class="px-3 py-3 text-sm text-stone-500">No files attached</div>
          <div v-else class="flex-1 overflow-y-auto pb-2">
            <div v-for="(file, index) in contextFiles" :key="index" class="flex items-center gap-2 px-3 py-1.5 hover:bg-stone-800/50">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-stone-500 shrink-0">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
              </svg>
              <span class="text-xs text-stone-300 truncate flex-1">{{ file.name }}</span>
              <span class="text-[10px] text-stone-500">{{ Math.round(file.content.length / 1024) || '<1' }}KB</span>
              <button class="text-stone-500 hover:text-red-400 transition-colors" @click="removeContextFile(index)">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>
        </template>

        <!-- Settings (landscape) -->
        <template v-if="showSettings">
          <div class="px-3 py-3">
            <label class="block text-xs text-stone-400 mb-1">System Prompt</label>
            <textarea
              v-model="customPrompt"
              rows="8"
              class="w-full bg-stone-950 text-stone-200 text-xs rounded-lg p-2 border border-stone-700 focus:border-amber-500 focus:outline-none resize-y min-h-[80px]"
              placeholder="Custom system prompt for this session..."
            />
            <button
              class="mt-2 w-full py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium transition-colors"
              @click="saveSystemPrompt"
            >
              Save prompt
            </button>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>
