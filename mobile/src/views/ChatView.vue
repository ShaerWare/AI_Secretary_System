<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Capacitor } from "@capacitor/core";
import {
  chatApi,
  type ChatMessage,
  type ChatSession,
  type ChatSessionPrompt,
  type StreamChunk,
  type BranchNode,
  type ContextFile,
  type ChatImage,
} from "@/api/chat";
import { useAuthStore } from "@/stores/auth";
import MessageBubble from "@/components/MessageBubble.vue";
import ChatInput from "@/components/ChatInput.vue";
import ContextFilesPanel from "@/components/ContextFilesPanel.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
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

// Assistant switcher: list of chats accessible to user (own + shared)
type AvailableAssistant = {
  id: string;
  title: string;
  is_shared_with_me?: boolean;
  is_default_mobile?: boolean;
};
const availableAssistants = ref<AvailableAssistant[]>([]);
const showAssistantSwitcher = ref(false);

// Panels
const showBranches = ref(false);
const showContextFiles = ref(false);
const showSettings = ref(false);
const settingsTab = ref<"files" | "prompt">("files");
const customPrompt = ref("");
const sessionPrompts = ref<ChatSessionPrompt[]>([]);
const selectedPromptId = ref<number | null>(null);
const promptActionPending = ref(false);
const branches = ref<BranchNode[]>([]);
const contextFiles = ref<ContextFile[]>([]);
const branchesLoading = ref(false);
const contextFileInputRef = ref<HTMLInputElement | null>(null);

// Web search
const webSearchEnabled = ref(false);

// Token usage
const tokenUsage = ref<{ tokens: number; context_window: number; percent: number } | null>(null);

// Per-user token total for the current Claude billing period (from /admin/usage/me)
const periodUsage = ref<{ tokens: number; period_end: string } | null>(null);

async function refreshPeriodUsage() {
  try {
    const data = await chatApi.getMyUsage();
    periodUsage.value = { tokens: data.tokens, period_end: data.period_end };
  } catch {
    // best-effort — never break chat on usage fetch failure
  }
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

const contextTicks = computed(() => {
  if (!tokenUsage.value) return [];
  const cw = tokenUsage.value.context_window;
  if (cw <= 0) return [];
  const candidates = [4096, 8192, 16384, 32768, 65536, 131072, 200000, 500000, 1000000];
  const ticks: { tokens: number; pct: number; label: string }[] = [];
  for (const t of candidates) {
    const pct = (t / cw) * 100;
    if (pct > 10 && pct < 90) {
      ticks.push({ tokens: t, pct, label: formatTokens(t) });
    }
  }
  // Keep max 4 ticks to avoid clutter
  if (ticks.length > 4) {
    const step = Math.ceil(ticks.length / 4);
    return ticks.filter((_, i) => i % step === 0).slice(0, 4);
  }
  return ticks;
});

// File upload
const pendingFiles = ref<ChatImage[]>([]);
const isUploading = ref(false);

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
    tokenUsage.value = data.session.token_usage || null;
    await loadSessionPrompts();
    await scrollToBottom();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось загрузить";
  } finally {
    isLoading.value = false;
  }
}

async function loadAvailableAssistants() {
  try {
    const data = await chatApi.listSessions();
    if (isAdmin.value) {
      // Admins see all their sessions
      availableAssistants.value = data.sessions.map((s) => ({
        id: s.id,
        title: s.title,
        is_shared_with_me: s.is_shared_with_me,
        is_default_mobile: s.is_default_mobile,
      }));
    } else {
      // Non-admins: only chats shared with them by admin (the assistants)
      availableAssistants.value = data.sessions
        .filter((s) => s.is_shared_with_me || s.is_default_mobile)
        .map((s) => ({
          id: s.id,
          title: s.title,
          is_shared_with_me: s.is_shared_with_me,
          is_default_mobile: s.is_default_mobile,
        }));
    }
  } catch {
    // Non-critical — switcher just won't show
    availableAssistants.value = [];
  }
}

function toggleAssistantSwitcher() {
  if (!showAssistantSwitcher.value) {
    loadAvailableAssistants();
  }
  showAssistantSwitcher.value = !showAssistantSwitcher.value;
}

function switchToAssistant(id: string) {
  showAssistantSwitcher.value = false;
  if (id === sessionId.value) return;
  closePanel();
  router.replace(`/chat/${id}`);
}

function toggleWebSearch() {
  webSearchEnabled.value = !webSearchEnabled.value;
  if (sessionId.value) {
    chatApi.updateSession(sessionId.value, {
      web_search_enabled: webSearchEnabled.value,
    });
  }
}

async function handleUploadFiles(files: File[]) {
  if (!sessionId.value || isUploading.value) return;
  isUploading.value = true;
  try {
    for (const file of files) {
      const { image } = await chatApi.uploadImage(sessionId.value, file);
      pendingFiles.value.push(image);
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось загрузить файл";
  } finally {
    isUploading.value = false;
  }
}

function removePendingFile(id: string) {
  pendingFiles.value = pendingFiles.value.filter((f) => f.id !== id);
}

async function sendMessage(content: string) {
  const imageIds = pendingFiles.value.map((f) => f.id);
  pendingFiles.value = [];

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
      if (chunk.token_usage) {
        tokenUsage.value = chunk.token_usage;
      }
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
          refreshPeriodUsage();
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
    imageIds.length ? { image_ids: imageIds } : undefined,
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

function getVisibleMessageEl(): HTMLElement | null {
  const container = messagesContainer.value;
  if (!container) return null;
  const nodes = container.querySelectorAll<HTMLElement>("[data-message-id]");
  if (!nodes.length) return null;
  const containerRect = container.getBoundingClientRect();
  const viewportMid = containerRect.top + containerRect.height / 2;
  let best: HTMLElement | null = null;
  let bestDist = Infinity;
  nodes.forEach((el) => {
    const r = el.getBoundingClientRect();
    const mid = r.top + r.height / 2;
    const dist = Math.abs(mid - viewportMid);
    if (r.bottom < containerRect.top || r.top > containerRect.bottom) return;
    if (dist < bestDist) {
      bestDist = dist;
      best = el;
    }
  });
  return best;
}

function scrollToMessageTop() {
  const container = messagesContainer.value;
  const el = getVisibleMessageEl();
  if (!container || !el) return;
  const containerRect = container.getBoundingClientRect();
  const elRect = el.getBoundingClientRect();
  const targetTop = container.scrollTop + (elRect.top - containerRect.top) - 8;
  container.scrollTo({ top: targetTop, behavior: "smooth" });
}

function scrollToMessageBottom() {
  const container = messagesContainer.value;
  const el = getVisibleMessageEl();
  if (!container || !el) return;
  const containerRect = container.getBoundingClientRect();
  const elRect = el.getBoundingClientRect();
  const targetTop =
    container.scrollTop +
    (elRect.bottom - containerRect.top) -
    container.clientHeight +
    8;
  container.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" });
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
    await chatApi.switchBranch(sessionId.value, messageId);
    await loadSession();
    await loadBranches();
    await scrollToBottom();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось переключить";
  }
}

async function createNewBranch() {
  try {
    await chatApi.newBranch(sessionId.value);
    await loadSession();
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

const expandedBranchNodes = ref<Set<string>>(new Set());

function findBranchNode(nodes: BranchNode[], id: string): BranchNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    if (n.children?.length) {
      const found = findBranchNode(n.children, id);
      if (found) return found;
    }
  }
  return null;
}

function collectDescendantIds(node: BranchNode, out: string[]) {
  out.push(node.id);
  if (node.children?.length) {
    for (const c of node.children) collectDescendantIds(c, out);
  }
}

function toggleBranchNode(id: string) {
  const next = new Set(expandedBranchNodes.value);
  const node = findBranchNode(branches.value, id);
  if (!node) return;
  const ids: string[] = [];
  collectDescendantIds(node, ids);
  if (next.has(id)) {
    // Collapse: remove self + all descendants
    for (const d of ids) next.delete(d);
  } else {
    // Expand: add self + all descendants so the whole subtree is visible
    for (const d of ids) next.add(d);
  }
  expandedBranchNodes.value = next;
}

interface FlatBranch {
  node: BranchNode;
  depth: number;
  hasChildren: boolean;
  expanded: boolean;
}

function flattenBranches(nodes: BranchNode[], depth = 0): FlatBranch[] {
  // Sort siblings: pinned first, otherwise preserve original order
  const sorted = [...nodes].sort((a, b) => {
    const ap = a.is_pinned ? 1 : 0;
    const bp = b.is_pinned ? 1 : 0;
    return bp - ap;
  });
  const result: FlatBranch[] = [];
  for (const n of sorted) {
    const hasChildren = !!n.children?.length;
    const expanded = expandedBranchNodes.value.has(n.id);
    result.push({ node: n, depth, hasChildren, expanded });
    if (hasChildren && expanded) {
      result.push(...flattenBranches(n.children, depth + 1));
    }
  }
  return result;
}

const flatBranches = computed(() => flattenBranches(branches.value));

// === Branch Search ===
const branchSearchQuery = ref("");
const branchSearchResults = ref<string[]>([]);
const branchSearchLoading = ref(false);
let branchSearchDebounce: ReturnType<typeof setTimeout> | null = null;

watch(branchSearchQuery, (q) => {
  if (branchSearchDebounce) clearTimeout(branchSearchDebounce);
  if (!q.trim()) {
    branchSearchResults.value = [];
    return;
  }
  branchSearchDebounce = setTimeout(() => doBranchSearch(q.trim()), 300);
});

async function doBranchSearch(q: string) {
  if (!sessionId.value || !q) return;
  branchSearchLoading.value = true;
  try {
    const data = await chatApi.searchBranches(sessionId.value, q);
    branchSearchResults.value = data.matches.map((m) => m.id);
    // Auto-expand ancestors of matches
    if (branchSearchResults.value.length > 0) {
      const next = new Set(expandedBranchNodes.value);
      for (const matchId of branchSearchResults.value) {
        // Walk up ancestors via flatBranches/findBranchNode
        let current: BranchNode | null = findBranchNode(branches.value, matchId);
        if (current) {
          // expand all ancestors by adding them
          const ancestors = findAncestorIds(branches.value, matchId);
          for (const aid of ancestors) next.add(aid);
        }
      }
      expandedBranchNodes.value = next;
    }
  } catch {
    branchSearchResults.value = [];
  } finally {
    branchSearchLoading.value = false;
  }
}

function findAncestorIds(nodes: BranchNode[], targetId: string, path: string[] = []): string[] {
  for (const n of nodes) {
    if (n.id === targetId) return path;
    if (n.children?.length) {
      const result = findAncestorIds(n.children, targetId, [...path, n.id]);
      if (result.length > 0 || n.children.some((c) => c.id === targetId)) return [...path, n.id];
    }
  }
  return [];
}

// === Branch Rename ===
const renamingBranchId = ref<string | null>(null);
const renameBranchInput = ref("");

function startRenameBranch(nodeId: string, currentName: string) {
  renamingBranchId.value = nodeId;
  renameBranchInput.value = currentName;
}

async function confirmRenameBranch() {
  if (!renamingBranchId.value || !sessionId.value) return;
  try {
    await chatApi.renameBranch(sessionId.value, renamingBranchId.value, renameBranchInput.value.trim());
    await loadBranches();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось переименовать";
  } finally {
    renamingBranchId.value = null;
    renameBranchInput.value = "";
  }
}

function cancelRenameBranch() {
  renamingBranchId.value = null;
  renameBranchInput.value = "";
}

// === Branch Pin ===
async function pinBranchNode(nodeId: string, pinned: boolean) {
  if (!sessionId.value) return;
  try {
    await chatApi.pinBranch(sessionId.value, nodeId, pinned);
    await loadBranches();
  } catch {
    // ignore
  }
}

// === Branch Delete (single node) ===
async function deleteBranchNode(nodeId: string) {
  if (!sessionId.value) return;
  if (!confirm("Удалить эту ветку?")) return;
  try {
    await chatApi.deleteMessage(sessionId.value, nodeId);
    await loadBranches();
    await loadSession();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось удалить";
  }
}

// === Context Files ===

function toggleSettings() {
  showBranches.value = false;
  showContextFiles.value = false;
  showSettings.value = !showSettings.value;
}

async function loadSessionPrompts() {
  if (!sessionId.value) return;
  try {
    const res = await chatApi.listPrompts(sessionId.value);
    sessionPrompts.value = res.prompts || [];
    if (sessionPrompts.value.length === 0) {
      selectedPromptId.value = null;
    } else {
      const active = sessionPrompts.value.find((p) => p.is_active);
      selectedPromptId.value = active?.id ?? sessionPrompts.value[0]!.id;
      customPrompt.value =
        sessionPrompts.value.find((p) => p.id === selectedPromptId.value)?.content || "";
    }
  } catch {
    sessionPrompts.value = [];
    selectedPromptId.value = null;
  }
}

function selectPrompt(promptId: number) {
  selectedPromptId.value = promptId;
  const prompt = sessionPrompts.value.find((p) => p.id === promptId);
  if (prompt) customPrompt.value = prompt.content || "";
}

async function addNewPrompt() {
  if (!sessionId.value || promptActionPending.value) return;
  promptActionPending.value = true;
  try {
    const { prompt } = await chatApi.createPrompt(sessionId.value, { content: "" });
    sessionPrompts.value = [...sessionPrompts.value, prompt];
    selectedPromptId.value = prompt.id;
    customPrompt.value = prompt.content || "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось создать промпт";
  } finally {
    promptActionPending.value = false;
  }
}

async function renameSelectedPrompt() {
  const id = selectedPromptId.value;
  if (id == null || !sessionId.value) return;
  const current = sessionPrompts.value.find((p) => p.id === id);
  if (!current) return;
  const raw = window.prompt("Название промпта", current.name || "");
  if (raw === null) return;
  const newName = raw.trim().slice(0, 100);
  if ((current.name || "") === newName) return;
  try {
    const { prompt } = await chatApi.updatePrompt(sessionId.value, id, {
      name: newName || null,
    });
    const idx = sessionPrompts.value.findIndex((p) => p.id === id);
    if (idx >= 0) sessionPrompts.value[idx] = prompt;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось переименовать";
  }
}

async function saveSelectedPromptContent() {
  const id = selectedPromptId.value;
  if (id == null || !sessionId.value) return;
  const prompt = sessionPrompts.value.find((p) => p.id === id);
  if (!prompt || prompt.content === (customPrompt.value || "")) return;
  promptActionPending.value = true;
  try {
    const { prompt: updated } = await chatApi.updatePrompt(sessionId.value, id, {
      content: customPrompt.value || "",
    });
    const idx = sessionPrompts.value.findIndex((p) => p.id === id);
    if (idx >= 0) sessionPrompts.value[idx] = updated;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось сохранить промпт";
  } finally {
    promptActionPending.value = false;
  }
}

async function activateSelectedPrompt() {
  const id = selectedPromptId.value;
  if (id == null || !sessionId.value) return;
  const prompt = sessionPrompts.value.find((p) => p.id === id);
  if (!prompt || prompt.is_active) return;
  if (prompt.content !== (customPrompt.value || "")) {
    await saveSelectedPromptContent();
  }
  promptActionPending.value = true;
  try {
    const { prompt: updated } = await chatApi.activatePrompt(sessionId.value, id);
    sessionPrompts.value = sessionPrompts.value.map((p) => ({
      ...p,
      is_active: p.id === updated.id,
    }));
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось активировать";
  } finally {
    promptActionPending.value = false;
  }
}

async function deleteSelectedPrompt() {
  const id = selectedPromptId.value;
  if (id == null || !sessionId.value) return;
  if (sessionPrompts.value.length <= 1) {
    error.value = "Нельзя удалить единственный промпт";
    return;
  }
  if (!confirm("Удалить этот промпт?")) return;
  promptActionPending.value = true;
  try {
    await chatApi.deletePrompt(sessionId.value, id);
    await loadSessionPrompts();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось удалить";
  } finally {
    promptActionPending.value = false;
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

// Reload session data when route id changes (assistant switcher)
watch(sessionId, async (newId, oldId) => {
  if (!newId || newId === oldId) return;
  // Reset state so old chat doesn't flash
  messages.value = [];
  branches.value = [];
  contextFiles.value = [];
  sessionPrompts.value = [];
  selectedPromptId.value = null;
  streamingContent.value = "";
  await loadSession();
  if (showBranches.value) await loadBranches();
});

onMounted(async () => {
  await loadSession();
  loadAvailableAssistants();
  refreshPeriodUsage();
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
          class="text-stone-400 hover:text-amber-400 transition-colors p-1"
          title="Переключить ассистента"
          @click="toggleAssistantSwitcher"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <button
          class="shrink-0 hover:opacity-80 transition-opacity"
          title="Переключить ассистента"
          @click="toggleAssistantSwitcher"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="w-6 h-6">
            <defs><linearGradient id="hg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#F0A830"/><stop offset="100%" stop-color="#C27010"/></linearGradient></defs>
            <path fill="url(#hg)" fill-rule="evenodd" d="M 431.8 217.4 L 484.1 226.3 L 484.1 285.7 L 431.8 294.6 L 407.6 353.0 L 438.3 396.3 L 396.3 438.3 L 353.0 407.6 L 294.6 431.8 L 285.7 484.1 L 226.3 484.1 L 217.4 431.8 L 159.0 407.6 L 115.7 438.3 L 73.7 396.3 L 104.4 353.0 L 80.2 294.6 L 27.9 285.7 L 27.9 226.3 L 80.2 217.4 L 104.4 159.0 L 73.7 115.7 L 115.7 73.7 L 159.0 104.4 L 217.4 80.2 L 226.3 27.9 L 285.7 27.9 L 294.6 80.2 L 353.0 104.4 L 396.3 73.7 L 438.3 115.7 L 407.6 159.0 Z M 341.0 256.0 A 85 85 0 1 0 171.0 256.0 A 85 85 0 1 0 341.0 256.0 Z"/>
          </svg>
        </button>
        <!-- Title + assistant switcher -->
        <div class="relative flex-1 min-w-0">
          <button
            class="w-full flex items-center gap-1.5 text-left group"
            :disabled="availableAssistants.length <= 1"
            @click="toggleAssistantSwitcher"
          >
            <h1 class="text-sm font-medium text-white truncate flex-1">
              {{ title }}
            </h1>
            <svg
              v-if="availableAssistants.length > 1"
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              class="shrink-0 text-stone-400 group-hover:text-amber-400 transition-colors"
              :class="showAssistantSwitcher ? 'text-amber-400 rotate-180' : ''"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          <!-- Dropdown -->
          <div
            v-if="showAssistantSwitcher && availableAssistants.length > 1"
            class="absolute left-0 right-0 top-full mt-1 bg-stone-900 border border-stone-700 rounded-lg shadow-2xl z-50 max-h-[60vh] overflow-y-auto"
          >
            <div class="px-3 py-2 text-[10px] uppercase tracking-wide text-stone-500 border-b border-stone-800 sticky top-0 bg-stone-900">
              Переключить ассистента
            </div>
            <button
              v-for="a in availableAssistants"
              :key="a.id"
              class="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-stone-800 transition-colors"
              :class="a.id === sessionId ? 'bg-amber-600/15' : ''"
              @click="switchToAssistant(a.id)"
            >
              <span
                class="w-1.5 h-1.5 rounded-full shrink-0"
                :class="a.id === sessionId ? 'bg-amber-400' : 'bg-stone-600'"
              />
              <span
                class="text-sm flex-1 truncate"
                :class="a.id === sessionId ? 'text-amber-300 font-medium' : 'text-stone-200'"
              >{{ a.title }}</span>
              <span
                v-if="a.is_default_mobile"
                class="text-[10px] uppercase tracking-wide text-stone-500 shrink-0"
              >по умолч.</span>
            </button>
          </div>
        </div>

        <!-- Toolbar buttons -->
        <button
          class="w-8 h-8 rounded-lg border border-amber-500 bg-amber-600 text-white hover:bg-amber-500 flex items-center justify-center transition-colors shrink-0"
          title="Новая ветка"
          @click="createNewBranch"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
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
          class="p-1.5 rounded-lg text-stone-400 hover:text-white transition-colors"
          title="Профиль"
          @click="router.push('/settings')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
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
            <div class="px-3 py-2 flex items-center gap-2">
              <span class="text-xs font-medium text-stone-400 uppercase tracking-wide">Дерево веток</span>
              <input
                v-model="branchSearchQuery"
                class="flex-1 min-w-0 text-xs bg-stone-800 border border-stone-700 rounded px-2 py-1 text-stone-200 placeholder-stone-500 outline-none focus:ring-1 focus:ring-amber-500"
                placeholder="Поиск..."
              />
              <span v-if="branchSearchQuery && !branchSearchLoading" class="text-[10px] text-stone-500 whitespace-nowrap">{{ branchSearchResults.length }}</span>
            </div>
            <div v-if="branchesLoading" class="flex justify-center py-4">
              <div class="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
            </div>
            <div v-else-if="!flatBranches.length" class="px-3 py-3 text-sm text-stone-500">Пока нет истории диалогов</div>
            <div v-else class="pb-2 overflow-y-auto">
                <div
                  v-for="{ node, depth, hasChildren, expanded } in flatBranches"
                  :key="node.id"
                  class="w-full flex items-center gap-1 px-2 py-1.5 text-xs hover:bg-stone-800/50 transition-colors"
                  :class="[
                    node.is_active ? 'text-amber-400' : 'text-stone-400',
                    branchSearchResults.includes(node.id) ? 'bg-yellow-500/20 ring-1 ring-yellow-500/30' : '',
                  ]"
                  :style="{ paddingLeft: `${8 + depth * 14}px` }"
                >
                  <button
                    v-if="hasChildren"
                    class="shrink-0 w-4 h-4 flex items-center justify-center text-stone-500 hover:text-stone-200 transition-transform"
                    :class="expanded ? 'rotate-90' : ''"
                    @click.stop="toggleBranchNode(node.id)"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </button>
                  <span v-else class="shrink-0 w-4" />

                  <!-- Inline rename -->
                  <template v-if="renamingBranchId === node.id">
                    <input
                      v-model="renameBranchInput"
                      class="flex-1 min-w-0 text-xs bg-stone-800 border border-stone-600 rounded px-1 py-0.5 text-stone-200 outline-none focus:ring-1 focus:ring-amber-500"
                      @keydown.enter="confirmRenameBranch"
                      @keydown.escape="cancelRenameBranch"
                      @click.stop
                    />
                    <button class="shrink-0 text-emerald-400 hover:text-emerald-300 p-0.5" @click.stop="confirmRenameBranch">
                      <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12" /></svg>
                    </button>
                    <button class="shrink-0 text-stone-500 hover:text-stone-300 p-0.5" @click.stop="cancelRenameBranch">
                      <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                    </button>
                  </template>

                  <!-- Normal display -->
                  <template v-else>
                    <!-- Pinned indicator -->
                    <svg v-if="node.is_pinned" xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="shrink-0 text-amber-400">
                      <path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>
                    </svg>
                    <button
                      class="flex items-center gap-1 flex-1 text-left min-w-0"
                      @click="switchBranch(node.id)"
                    >
                      <span class="shrink-0">
                        <svg v-if="node.role === 'user'" xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
                        </svg>
                        <svg v-else xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <path d="M12 2a8 8 0 0 0-8 8c0 3.5 2 6 5 7.5V21h6v-3.5c3-1.5 5-4 5-7.5a8 8 0 0 0-8-8z" />
                        </svg>
                      </span>
                      <span class="truncate" :class="node.branch_name ? 'italic' : ''">{{ node.branch_name || node.content_preview || '...' }}</span>
                      <span v-if="node.is_active" class="shrink-0 text-[10px] bg-amber-600/30 text-amber-400 px-1 rounded">*</span>
                    </button>
                    <!-- Action buttons -->
                    <div class="shrink-0 flex items-center">
                      <button class="p-1 text-stone-600 hover:text-amber-400" title="Закрепить" @click.stop="pinBranchNode(node.id, !node.is_pinned)">
                        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>
                      </button>
                      <button class="p-1 text-stone-600 hover:text-stone-300" title="Переименовать" @click.stop="startRenameBranch(node.id, node.branch_name || '')">
                        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" /></svg>
                      </button>
                      <button class="p-1 text-stone-600 hover:text-red-400" title="Удалить" @click.stop="deleteBranchNode(node.id)">
                        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
                      </button>
                    </div>
                  </template>
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
              <div class="flex-1 flex flex-col min-h-0 px-3 py-2 gap-2">
                <!-- Prompt chips -->
                <div class="flex flex-wrap gap-1.5 items-center">
                  <button
                    v-for="p in sessionPrompts"
                    :key="p.id"
                    :class="[
                      'inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] border transition-colors max-w-[160px]',
                      selectedPromptId === p.id
                        ? 'border-amber-500 text-amber-400 bg-amber-500/10'
                        : 'border-stone-700 text-stone-300 hover:bg-stone-800',
                      p.is_active ? 'font-semibold' : ''
                    ]"
                    @click="selectPrompt(p.id)"
                  >
                    <span v-if="p.is_active" class="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                    <span class="truncate">{{ p.name || "(без имени)" }}</span>
                  </button>
                  <button
                    class="inline-flex items-center justify-center w-6 h-6 rounded-full border border-dashed border-stone-700 text-stone-400 hover:text-amber-400 hover:border-amber-500 transition-colors"
                    :disabled="promptActionPending"
                    title="Добавить промпт"
                    @click="addNewPrompt"
                  >+</button>
                </div>

                <!-- Actions -->
                <div v-if="selectedPromptId !== null" class="flex flex-wrap gap-1.5 text-[11px]">
                  <button
                    class="px-2 py-1 rounded-md border border-stone-700 text-stone-300 hover:bg-stone-800 transition-colors"
                    :disabled="promptActionPending"
                    @click="renameSelectedPrompt"
                  >Переименовать</button>
                  <button
                    v-if="!sessionPrompts.find(p => p.id === selectedPromptId)?.is_active"
                    class="px-2 py-1 rounded-md border border-amber-500 text-amber-400 hover:bg-amber-500/10 transition-colors"
                    :disabled="promptActionPending"
                    @click="activateSelectedPrompt"
                  >Сделать активным</button>
                  <span
                    v-else
                    class="px-2 py-1 rounded-md bg-amber-500/10 text-amber-400"
                  >Активный</span>
                  <span class="flex-1" />
                  <button
                    class="px-2 py-1 rounded-md border border-red-600/60 text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                    :disabled="promptActionPending || sessionPrompts.length <= 1"
                    @click="deleteSelectedPrompt"
                  >Удалить</button>
                </div>

                <textarea
                  v-model="customPrompt"
                  class="flex-1 w-full bg-stone-950 text-stone-200 text-xs rounded-lg p-2 border border-stone-700 focus:border-amber-500 focus:outline-none resize-none min-h-[60px]"
                  placeholder="Пользовательский промпт для этой сессии..."
                  :disabled="selectedPromptId === null"
                />
              </div>
              <div class="shrink-0 px-3 pb-1">
                <button
                  class="w-full py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
                  :disabled="promptActionPending || selectedPromptId === null"
                  @click="saveSelectedPromptContent"
                >Сохранить</button>
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
              :is-admin="isAdmin"
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

        <!-- Scroll to top of dialog — pinned to top edge -->
        <button
          class="absolute right-2 top-2 z-10 p-2 rounded-full bg-stone-800/80 backdrop-blur border border-stone-700 shadow-md text-stone-400 hover:text-white active:bg-stone-700 transition-colors"
          title="В начало диалога"
          @click="scrollToTop"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <polyline points="5 12 12 5 19 12" />
            <line x1="5" y1="3" x2="19" y2="3" />
          </svg>
        </button>

        <!-- Message scroll buttons — centered vertically -->
        <div class="absolute right-2 top-1/2 -translate-y-1/2 z-10 flex flex-col gap-1.5">
          <button
            class="p-2 rounded-full bg-stone-800/80 backdrop-blur border border-stone-700 shadow-md text-stone-400 hover:text-white active:bg-stone-700 transition-colors"
            title="К началу ответа"
            @click="scrollToMessageTop"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <polyline points="5 12 12 5 19 12" />
            </svg>
          </button>
          <button
            class="p-2 rounded-full bg-stone-800/80 backdrop-blur border border-stone-700 shadow-md text-stone-400 hover:text-white active:bg-stone-700 transition-colors"
            title="К концу ответа"
            @click="scrollToMessageBottom"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <polyline points="5 12 12 19 19 12" />
            </svg>
          </button>
        </div>

        <!-- Scroll to bottom of dialog — pinned to bottom edge -->
        <button
          class="absolute right-2 bottom-2 z-10 p-2 rounded-full bg-stone-800/80 backdrop-blur border border-stone-700 shadow-md text-stone-400 hover:text-white active:bg-stone-700 transition-colors"
          title="В конец диалога"
          @click="scrollToBottom"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <polyline points="5 12 12 19 19 12" />
            <line x1="5" y1="21" x2="19" y2="21" />
          </svg>
        </button>
      </div>

      <!-- Input with web search toggle -->
      <div
        class="flex items-end gap-1 px-2 pt-1 border-t border-stone-700/50 bg-stone-900/95"
        :class="tokenUsage ? 'pb-0.5' : (isNativeAndroid ? 'pb-14' : 'pb-2')"
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
            :pending-files="pendingFiles"
            :is-uploading="isUploading"
            @send="sendMessage"
            @stop="stopStreaming"
            @upload-files="handleUploadFiles"
            @remove-file="removePendingFile"
          />
        </div>
      </div>

      <!-- Context usage bar -->
      <div
        v-if="tokenUsage"
        class="relative bg-stone-900/95 px-3"
        :class="isNativeAndroid ? 'pb-12 pt-0.5' : 'pt-0.5 pb-1'"
      >
        <!-- Track background -->
        <div class="relative h-1.5 rounded-full bg-stone-800 overflow-hidden">
          <!-- Fill bar with gradient -->
          <div
            class="h-full rounded-full transition-all duration-500"
            :class="[
              tokenUsage.percent >= 90 ? 'bg-gradient-to-r from-green-500 via-yellow-500 to-red-500' :
              tokenUsage.percent >= 70 ? 'bg-gradient-to-r from-green-500 via-yellow-400 to-amber-500' :
              'bg-gradient-to-r from-emerald-500 to-green-400'
            ]"
            :style="{ width: Math.min(tokenUsage.percent, 100) + '%' }"
          />
          <!-- Tick marks -->
          <template v-if="tokenUsage.context_window > 0">
            <div
              v-for="tick in contextTicks"
              :key="tick.tokens"
              class="absolute top-0 h-full w-px bg-stone-600/60"
              :style="{ left: tick.pct + '%' }"
            />
          </template>
        </div>
        <!-- Labels row -->
        <div class="relative h-3 mt-0.5">
          <!-- Left: current usage -->
          <span class="absolute left-0 text-[9px] leading-none" :class="tokenUsage.percent >= 90 ? 'text-red-400 font-medium' : tokenUsage.percent >= 70 ? 'text-amber-400' : 'text-stone-500'">
            {{ formatTokens(tokenUsage.tokens) }}
          </span>
          <!-- Tick labels -->
          <span
            v-for="tick in contextTicks"
            :key="'l' + tick.tokens"
            class="absolute text-[8px] text-stone-600 leading-none -translate-x-1/2"
            :style="{ left: tick.pct + '%' }"
          >{{ tick.label }}</span>
          <!-- Right: total -->
          <span class="absolute right-0 text-[9px] text-stone-500 leading-none">{{ formatTokens(tokenUsage.context_window) }}</span>
        </div>
        <!-- Per-user Claude period usage (informational, no limit) -->
        <div v-if="periodUsage" class="mt-0.5">
          <div class="relative h-0.5 rounded-full bg-gradient-to-r from-orange-500 to-red-500 opacity-90" />
          <div class="text-[9px] text-orange-400/80 leading-none mt-0.5">
            Период: {{ formatTokens(periodUsage.tokens) }} токенов
          </div>
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
          <div class="px-3 py-2 flex items-center gap-2 border-b border-stone-800">
            <input
              v-model="branchSearchQuery"
              class="flex-1 min-w-0 text-xs bg-stone-800 border border-stone-700 rounded px-2 py-1 text-stone-200 placeholder-stone-500 outline-none focus:ring-1 focus:ring-amber-500"
              placeholder="Поиск..."
            />
            <span v-if="branchSearchQuery && !branchSearchLoading" class="text-[10px] text-stone-500 whitespace-nowrap">{{ branchSearchResults.length }}</span>
          </div>
          <div v-if="branchesLoading" class="flex justify-center py-4">
            <div class="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
          </div>
          <div v-else-if="!flatBranches.length" class="px-3 py-3 text-sm text-stone-500">Пока нет истории диалогов</div>
          <div v-else class="flex-1 overflow-y-auto pb-2">
              <div
                v-for="{ node, depth } in flatBranches"
                :key="node.id"
                class="w-full text-left px-2 py-1.5 text-xs hover:bg-stone-800/50 transition-colors flex items-center gap-1"
                :class="[
                  node.is_active ? 'text-amber-400' : 'text-stone-400',
                  branchSearchResults.includes(node.id) ? 'bg-yellow-500/20 ring-1 ring-yellow-500/30' : '',
                ]"
                :style="{ paddingLeft: `${8 + depth * 14}px` }"
              >
                <!-- Inline rename -->
                <template v-if="renamingBranchId === node.id">
                  <input
                    v-model="renameBranchInput"
                    class="flex-1 min-w-0 text-xs bg-stone-800 border border-stone-600 rounded px-1 py-0.5 text-stone-200 outline-none focus:ring-1 focus:ring-amber-500"
                    @keydown.enter="confirmRenameBranch"
                    @keydown.escape="cancelRenameBranch"
                    @click.stop
                  />
                  <button class="shrink-0 text-emerald-400 hover:text-emerald-300 p-0.5" @click.stop="confirmRenameBranch">
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12" /></svg>
                  </button>
                  <button class="shrink-0 text-stone-500 hover:text-stone-300 p-0.5" @click.stop="cancelRenameBranch">
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                  </button>
                </template>

                <!-- Normal display -->
                <template v-else>
                  <svg v-if="node.is_pinned" xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="shrink-0 text-amber-400">
                    <path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>
                  </svg>
                  <button class="flex items-center gap-1 flex-1 text-left min-w-0" @click="switchBranch(node.id)">
                    <span class="shrink-0">
                      <svg v-if="node.role === 'user'" xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
                      </svg>
                      <svg v-else xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 2a8 8 0 0 0-8 8c0 3.5 2 6 5 7.5V21h6v-3.5c3-1.5 5-4 5-7.5a8 8 0 0 0-8-8z" />
                      </svg>
                    </span>
                    <span class="truncate" :class="node.branch_name ? 'italic' : ''">{{ node.branch_name || node.content_preview || '...' }}</span>
                    <span v-if="node.is_active" class="shrink-0 text-[10px] bg-amber-600/30 text-amber-400 px-1 rounded">*</span>
                  </button>
                  <div class="shrink-0 flex items-center">
                    <button class="p-1 text-stone-600 hover:text-amber-400" title="Закрепить" @click.stop="pinBranchNode(node.id, !node.is_pinned)">
                      <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>
                    </button>
                    <button class="p-1 text-stone-600 hover:text-stone-300" title="Переименовать" @click.stop="startRenameBranch(node.id, node.branch_name || '')">
                      <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" /></svg>
                    </button>
                    <button class="p-1 text-stone-600 hover:text-red-400" title="Удалить" @click.stop="deleteBranchNode(node.id)">
                      <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
                    </button>
                  </div>
                </template>
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
            <div class="flex-1 flex flex-col min-h-0 px-3 py-2 gap-2">
              <div class="flex flex-wrap gap-1.5 items-center">
                <button
                  v-for="p in sessionPrompts"
                  :key="p.id"
                  :class="[
                    'inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] border transition-colors max-w-[160px]',
                    selectedPromptId === p.id
                      ? 'border-amber-500 text-amber-400 bg-amber-500/10'
                      : 'border-stone-700 text-stone-300 hover:bg-stone-800',
                    p.is_active ? 'font-semibold' : ''
                  ]"
                  @click="selectPrompt(p.id)"
                >
                  <span v-if="p.is_active" class="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                  <span class="truncate">{{ p.name || "(без имени)" }}</span>
                </button>
                <button
                  class="inline-flex items-center justify-center w-6 h-6 rounded-full border border-dashed border-stone-700 text-stone-400 hover:text-amber-400 hover:border-amber-500 transition-colors"
                  :disabled="promptActionPending"
                  title="Добавить промпт"
                  @click="addNewPrompt"
                >+</button>
              </div>
              <div v-if="selectedPromptId !== null" class="flex flex-wrap gap-1.5 text-[11px]">
                <button
                  class="px-2 py-1 rounded-md border border-stone-700 text-stone-300 hover:bg-stone-800 transition-colors"
                  :disabled="promptActionPending"
                  @click="renameSelectedPrompt"
                >Переименовать</button>
                <button
                  v-if="!sessionPrompts.find(p => p.id === selectedPromptId)?.is_active"
                  class="px-2 py-1 rounded-md border border-amber-500 text-amber-400 hover:bg-amber-500/10 transition-colors"
                  :disabled="promptActionPending"
                  @click="activateSelectedPrompt"
                >Сделать активным</button>
                <span
                  v-else
                  class="px-2 py-1 rounded-md bg-amber-500/10 text-amber-400"
                >Активный</span>
                <span class="flex-1" />
                <button
                  class="px-2 py-1 rounded-md border border-red-600/60 text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                  :disabled="promptActionPending || sessionPrompts.length <= 1"
                  @click="deleteSelectedPrompt"
                >Удалить</button>
              </div>
              <textarea
                v-model="customPrompt"
                class="flex-1 w-full bg-stone-950 text-stone-200 text-xs rounded-lg p-2 border border-stone-700 focus:border-amber-500 focus:outline-none resize-none min-h-[60px]"
                placeholder="Пользовательский промпт для этой сессии..."
                :disabled="selectedPromptId === null"
              />
            </div>
            <div class="shrink-0 px-3 pb-2">
              <button
                class="w-full py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
                :disabled="promptActionPending || selectedPromptId === null"
                @click="saveSelectedPromptContent"
              >Сохранить</button>
            </div>
          </template>
        </template>

      </div>
    </template>
  </div>
</template>
