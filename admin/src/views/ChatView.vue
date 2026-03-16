<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import Prism from 'prismjs'
import 'prismjs/components/prism-javascript'
import 'prismjs/components/prism-typescript'
import 'prismjs/components/prism-python'
import 'prismjs/components/prism-bash'
import 'prismjs/components/prism-json'
import 'prismjs/components/prism-css'
import 'prismjs/components/prism-markup'
import 'prismjs/components/prism-yaml'
import 'prismjs/components/prism-sql'
import 'prismjs/components/prism-docker'
import 'prismjs/components/prism-nginx'
import 'prismjs/components/prism-go'
import 'prismjs/components/prism-rust'
import 'prismjs/components/prism-java'
import 'prismjs/components/prism-diff'
import 'prismjs/components/prism-markdown'
import 'prismjs/components/prism-jsx'
import 'prismjs/components/prism-tsx'
import { chatApi, ttsApi, llmApi, sttApi, wikiRagApi, type ChatSession, type ChatMessage, type ChatImage, type ChatSessionSummary, type CloudProvider, type BranchNode, type SiblingInfo, type TokenUsage } from '@/api'
import BranchTree from '@/components/BranchTree.vue'
import ChatShareDialog from '@/components/ChatShareDialog.vue'
import ArtifactPanel, { type Artifact } from '@/components/ArtifactPanel.vue'
import { useConfirmStore } from '@/stores/confirm'
import { useToastStore } from '@/stores/toast'
import { useAuthStore } from '@/stores/auth'
import {
  MessageSquare,
  Plus,
  Send,
  Trash2,
  Edit3,
  RefreshCw,
  Settings2,
  Check,
  X,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Bot,
  User,
  Copy,
  Volume2,
  VolumeX,
  Square,
  FileText,
  Mic,
  MicOff,
  ListChecks,
  FileOutput,
  Brain,
  BookOpen,
  GitBranch,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  PinOff,
  Paperclip,
  Download,
  ArrowDownToLine,
  ArrowUpToLine,
  Share2,
  GitFork,
  Users,
  Terminal,
  StopCircle,
  ChevronDown,
  FolderOpen,
  Maximize2,
  Minimize2,
  Globe,
  Server,
  Search,
  ImagePlus
} from 'lucide-vue-next'
import { useSidebarCollapse } from '@/composables/useSidebarCollapse'
import { useClaudeCode } from '@/composables/useClaudeCode'
import { claudeCodeApi, type CcProject, type CcProjectInput } from '@/api/claudeCode'
import { kanbanApi, type KanbanTask } from '@/api/kanban'
import { useResizablePanel } from '@/composables/useResizablePanel'
import { getChatEmoji } from '@/utils/chatEmoji'
import { shouldTreatAsPaste, createPastedBlock, buildMessageContent, type PastedBlock } from '@/utils/pasteDetect'
import { useChatFullscreenStore } from '@/stores/chatFullscreen'

const { t } = useI18n()
const confirmStore = useConfirmStore()
const toastStore = useToastStore()
const authStore = useAuthStore()
const fullscreenStore = useChatFullscreenStore()

const queryClient = useQueryClient()

// Claude Code mode
const cc = useClaudeCode()
const expandedThinking = ref<Set<number>>(new Set())

function toggleThinkingBlock(idx: number) {
  if (expandedThinking.value.has(idx)) {
    expandedThinking.value.delete(idx)
  } else {
    expandedThinking.value.add(idx)
  }
  expandedThinking.value = new Set(expandedThinking.value) // trigger reactivity
}

// State
const currentSessionId = ref<string | null>(null)
const inputMessage = ref('')
const isStreaming = ref(false)
const streamingContent = ref('')
const searchingQuery = ref<string | null>(null)
const pendingUserContent = ref<string | null>(null)
const summarizingMessageId = ref<string | null>(null)
const editingMessageId = ref<string | null>(null)
const editingContent = ref('')
const showSettings = ref(false)
const settingsTab = ref<'session' | 'files'>('session')
const customPrompt = ref('')
const contextFiles = ref<{ name: string; content: string }[]>([])
const contextFilesSessionId = ref<string | null>(null) // tracks which session files belong to
const editingFileIndex = ref<number | null>(null)
const editingFileName = ref('')
const editingFileContent = ref('')
const contextFileInputRef = ref<HTMLInputElement | null>(null)
const messagesContainer = ref<HTMLElement | null>(null)
const messageInputRef = ref<HTMLTextAreaElement | null>(null)
const showSidebar = ref(true)
const showExportMenu = ref(false)
const showRagMenu = ref(false)
const showCcDirMenu = ref(false)
const ccProjects = ref<CcProject[]>([])
const showCcAddProject = ref(false)
const ccNewProject = ref<CcProjectInput>({ name: '', path: '', type: 'local' })
const showCcFilesMenu = ref(false)
const showCcKanbanMenu = ref(false)
const ccKanbanTasks = ref<KanbanTask[]>([])
const showShareDialog = ref(false)
const showZenSettings = ref(false)
const showZenLlmMenu = ref(false)
const inputPosition = ref<'top' | 'bottom'>(
  (localStorage.getItem('chat-input-position') as 'top' | 'bottom') || 'top'
)

// Sidebar collapse (desktop)
const { collapsed: sidebarCollapsed, toggle: toggleSidebarCollapse } = useSidebarCollapse('chat-sidebar-collapsed')

// Resizable panels
const { width: sidebarWidth, startResize: startSidebarResize, startTouchResize: startSidebarTouchResize } = useResizablePanel('chat-sidebar-width', 288, 200, 480, 'right')
const { width: branchTreeWidth, startResize: startBranchResize, startTouchResize: startBranchTouchResize } = useResizablePanel('chat-branch-width', 208, 160, 400, 'left')
const { width: settingsWidth, startResize: startSettingsResize, startTouchResize: startSettingsTouchResize } = useResizablePanel('chat-settings-width', 500, 300, 800, 'left')
const { width: artifactWidth, startResize: startArtifactResize, startTouchResize: startArtifactTouchResize } = useResizablePanel('chat-artifact-width', 500, 300, 800, 'left')

// Pasted content blocks
const pastedBlocks = ref<PastedBlock[]>([])

function onPaste(e: ClipboardEvent) {
  // Handle pasted images
  const items = e.clipboardData?.items
  if (items && currentSessionId.value) {
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        e.preventDefault()
        const file = item.getAsFile()
        if (file) {
          isUploadingImage.value = true
          chatApi.uploadImage(currentSessionId.value, file)
            .then(({ image }) => pendingImages.value.push(image))
            .catch(err => toastStore.error(String(err)))
            .finally(() => { isUploadingImage.value = false })
        }
        return
      }
    }
  }
  // Handle pasted text
  const text = e.clipboardData?.getData('text/plain')
  if (!text || !shouldTreatAsPaste(text)) return
  e.preventDefault()
  pastedBlocks.value.push(createPastedBlock(text))
}

function removePastedBlock(id: string) {
  pastedBlocks.value = pastedBlocks.value.filter(b => b.id !== id)
}

// Pending image uploads
const pendingImages = ref<ChatImage[]>([])
const isUploadingImage = ref(false)
const imageInputRef = ref<HTMLInputElement | null>(null)

async function handleImageUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files?.length || !currentSessionId.value) return

  isUploadingImage.value = true
  try {
    for (const file of Array.from(files)) {
      if (!file.type.startsWith('image/')) continue
      const { image } = await chatApi.uploadImage(currentSessionId.value, file)
      pendingImages.value.push(image)
    }
  } catch (err) {
    toastStore.error(String(err))
  } finally {
    isUploadingImage.value = false
    input.value = ''
  }
}

function removePendingImage(id: string) {
  pendingImages.value = pendingImages.value.filter(i => i.id !== id)
}

// Fullscreen image viewer
const fullscreenImage = ref<string | null>(null)

// Artifact viewer state
const showArtifact = ref(false)
const activeArtifact = ref<Artifact | null>(null)

function openArtifact(artifact: Artifact) {
  activeArtifact.value = artifact
  showArtifact.value = true
  // Close other panels
  showBranchTree.value = false
  showSettings.value = false
}

function closeArtifact() {
  showArtifact.value = false
  activeArtifact.value = null
}

// Delegated click handler for code block buttons (v-html can't have Vue bindings)
function handleMessagesClick(e: MouseEvent) {
  const target = e.target as HTMLElement

  // Handle "open in viewer" button
  const openBtn = target.closest('[data-artifact-open]') as HTMLElement | null
  if (openBtn) {
    e.preventDefault()
    const container = openBtn.closest('.code-block-container') as HTMLElement | null
    if (container) {
      const id = container.dataset.artifactId || ''
      const lang = container.dataset.lang || ''
      const msgId = container.dataset.msgId || ''
      const codeEl = container.querySelector('pre code')
      const code = codeEl?.textContent || ''
      openArtifact({ id, language: lang, code, messageId: msgId })
    }
    return
  }

  // Handle "copy" button
  const copyBtn = target.closest('[data-artifact-copy]') as HTMLElement | null
  if (copyBtn) {
    e.preventDefault()
    const container = copyBtn.closest('.code-block-container') as HTMLElement | null
    if (container) {
      const codeEl = container.querySelector('pre code')
      const code = codeEl?.textContent || ''
      navigator.clipboard.writeText(code)
      toastStore.success(t('common.copied'))
    }
    return
  }

  // Handle code-block expand/collapse toggle
  const codeContainer = target.closest('.code-block-container') as HTMLElement | null
  if (codeContainer && !target.closest('button') && !target.closest('a')) {
    codeContainer.classList.toggle('expanded')
    return
  }

  // Handle "save to context" button
  const saveBtn = target.closest('[data-artifact-save]') as HTMLElement | null
  if (saveBtn) {
    e.preventDefault()
    if (!currentSessionId.value) return
    const container = saveBtn.closest('.code-block-container') as HTMLElement | null
    if (container) {
      const lang = container.dataset.lang || 'txt'
      const codeEl = container.querySelector('pre code')
      const code = codeEl?.textContent || ''
      const ext = lang === 'typescript' ? 'ts' : lang === 'javascript' ? 'js' : lang === 'python' ? 'py' : lang || 'txt'
      const ts = new Date().toISOString().slice(0, 16).replace('T', '_')
      contextFiles.value.push({ name: `artifact_${ts}.${ext}`, content: code })
      saveContextFilesMutation.mutate({
        sessionId: currentSessionId.value,
        files: contextFiles.value,
      })
      toastStore.success(t('chatView.savedToContext'))
    }
    return
  }
}

// Markdown renderer with code block headers
let codeBlockCounter = 0
let currentMsgId = ''

marked.use({
  breaks: true,
  gfm: true,
  renderer: {
    link({ href, title, text }) {
      const titleAttr = title ? ` title="${title}"` : ''
      return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`
    },
    code({ text, lang }) {
      const language = lang || ''
      const artifactId = `artifact-${currentMsgId}-${codeBlockCounter++}`
      // Map common lang aliases to Prism grammar keys
      const langMap: Record<string, string> = {
        js: 'javascript', ts: 'typescript', py: 'python',
        sh: 'bash', shell: 'bash', zsh: 'bash',
        yml: 'yaml', html: 'markup', xml: 'markup',
        dockerfile: 'docker', conf: 'nginx',
      }
      const prismLang = langMap[language] || language
      const grammar = prismLang ? Prism.languages[prismLang] : undefined
      const highlightedCode = grammar
        ? Prism.highlight(text, grammar, prismLang)
        : text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
      // SVG icons for buttons
      const copySvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
      const viewSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>'
      const saveSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>'
      return `<div class="code-block-container" data-artifact-id="${artifactId}" data-lang="${language}" data-msg-id="${currentMsgId}">
        <div class="code-block-header">
          <span class="code-block-lang">${language || 'code'}</span>
          <div class="code-block-actions">
            <button class="code-block-btn" data-artifact-copy="${artifactId}" title="${t('chatView.copyCode')}">${copySvg}</button>
            <button class="code-block-btn" data-artifact-save="${artifactId}" title="${t('chatView.saveToContext')}">${saveSvg}</button>
            <button class="code-block-btn" data-artifact-open="${artifactId}" title="${t('chatView.openInViewer')}">${viewSvg}</button>
          </div>
        </div>
        <pre><code class="language-${language}">${highlightedCode}</code></pre>
      </div>`
    }
  }
})

function renderMarkdown(content: string, messageId?: string): string {
  if (!content) return ''
  codeBlockCounter = 0
  currentMsgId = messageId || ''
  const html = marked.parse(content) as string
  return DOMPurify.sanitize(html, {
    ADD_ATTR: ['data-artifact-id', 'data-artifact-open', 'data-artifact-copy', 'data-artifact-save', 'data-lang', 'data-code', 'data-msg-id'],
    ADD_TAGS: ['svg', 'path', 'polyline', 'line', 'rect'],
  })
}

// Branch tree toggle
const showBranchTree = ref(false)

// Mutual exclusivity: panel watchers
watch(showBranchTree, (v) => { if (v) closeArtifact() })
watch(showSettings, (v) => { if (v) closeArtifact() })

// File attachment state
const attachedFiles = ref<{ name: string; content: string }[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

// Selection mode state
const selectionMode = ref(false)
const selectedIds = ref<Set<string>>(new Set())

// Inline rename state
const renamingSessionId = ref<string | null>(null)
const renamingTitle = ref('')

// Header title edit state
const editingHeaderTitle = ref(false)
const headerTitleValue = ref('')

// (grouping removed — admin chats only)

// TTS state
const audioRef = ref<HTMLAudioElement | null>(null)
const audioUrl = ref<string | null>(null)
const speakingMessageId = ref<string | null>(null)
const isSpeaking = ref(false)
const ttsLoading = ref<string | null>(null)

// Voice mode - auto-play TTS for assistant responses
const voiceMode = ref(localStorage.getItem('chat-voice-mode') === 'true')
const pendingTtsMessageId = ref<string | null>(null)

// Voice input (STT) state
const isRecording = ref(false)
const isTranscribing = ref(false)
const mediaRecorder = ref<MediaRecorder | null>(null)
const audioChunks = ref<Blob[]>([])

// LLM selection state
const selectedLlmBackend = ref<string>(localStorage.getItem('chat-llm-backend') || '')

// RAG selection state (per-session, loaded from session data)
const selectedRagMode = ref<string>('')
const selectedCollectionIds = ref<number[]>([])

// Save voice mode preference
watch(voiceMode, (val) => {
  localStorage.setItem('chat-voice-mode', val ? 'true' : 'false')
})

// Save selected LLM backend
watch(selectedLlmBackend, (val) => {
  localStorage.setItem('chat-llm-backend', val)
})

// Save RAG selection to session (per-chat)
let ragSaveTimer: ReturnType<typeof setTimeout> | null = null
function saveRagToSession() {
  if (!currentSessionId.value) return
  if (ragSaveTimer) clearTimeout(ragSaveTimer)
  ragSaveTimer = setTimeout(() => {
    if (!currentSessionId.value) return
    // Auto-determine rag_mode from selected collections
    const hasCollections = selectedCollectionIds.value.length > 0
    const mode = hasCollections ? 'selected' : 'all'
    chatApi.updateSession(currentSessionId.value, {
      rag_mode: mode,
      knowledge_collection_ids: hasCollections ? selectedCollectionIds.value : [],
    })
  }, 500)
}
watch(selectedRagMode, saveRagToSession)
watch(selectedCollectionIds, saveRagToSession, { deep: true })

// Queries
const { data: sessionsData, refetch: refetchSessions } = useQuery({
  queryKey: ['chat-sessions'],
  queryFn: () => chatApi.listSessions('admin'),
})

const { data: sessionData, refetch: refetchSession } = useQuery({
  queryKey: ['chat-session', currentSessionId],
  queryFn: () => currentSessionId.value ? chatApi.getSession(currentSessionId.value) : null,
  enabled: computed(() => !!currentSessionId.value),
})

// (grouped sessions query removed)

// LLM queries
const { data: llmBackendData } = useQuery({
  queryKey: ['llm-backend'],
  queryFn: () => llmApi.getBackend(),
})

const { data: llmProvidersData } = useQuery({
  queryKey: ['llm-providers-enabled'],
  queryFn: () => llmApi.getProviders(true),
})

const { data: collectionsData } = useQuery({
  queryKey: ['knowledge-collections'],
  queryFn: () => wikiRagApi.getCollections(),
})
const knowledgeCollections = computed(() => collectionsData.value?.collections || [])

// Branch tree query
const { data: branchData, refetch: refetchBranches } = useQuery({
  queryKey: ['chat-branches', currentSessionId],
  queryFn: () => currentSessionId.value ? chatApi.getBranches(currentSessionId.value) : null,
  enabled: computed(() => !!currentSessionId.value),
})

// Computed
const sessions = computed(() => sessionsData.value?.sessions || [])
const currentSession = computed(() => sessionData.value?.session)
const messages = computed(() => currentSession.value?.messages || [])
const branchTree = computed(() => branchData.value?.branches || [])
const siblingInfo = computed(() => currentSession.value?.sibling_info || {})

// CC sub-sessions per chat
const ccSubSessionsMap = ref<Record<string, import('@/api/claudeCode').CcSessionSummary[]>>({})
const standaloneCcSessions = ref<import('@/api/claudeCode').CcSessionSummary[]>([])

function getCcSubSessions(chatSessionId: string) {
  return ccSubSessionsMap.value[chatSessionId] || []
}

async function fetchCcSubSessions(chatSessionId: string) {
  try {
    const result = await claudeCodeApi.listByChatSession(chatSessionId)
    ccSubSessionsMap.value[chatSessionId] = result.sessions
  } catch {
    // ignore
  }
}

async function fetchAllCcSessions() {
  try {
    const result = await claudeCodeApi.listSessions()
    // Standalone = those without chat_session_id
    standaloneCcSessions.value = result.sessions.filter((s: import('@/api/claudeCode').CcSessionSummary) => !s.chat_session_id)
    // Group by chat_session_id
    const map: Record<string, import('@/api/claudeCode').CcSessionSummary[]> = {}
    for (const s of result.sessions) {
      if (s.chat_session_id) {
        if (!map[s.chat_session_id]) map[s.chat_session_id] = []
        map[s.chat_session_id].push(s)
      }
    }
    ccSubSessionsMap.value = map
  } catch {
    // ignore
  }
}

function loadCcSession(ccSessionId: string) {
  currentSessionId.value = null
  cc.loadSession(ccSessionId)
  showSidebar.value = false
}

function toggleCcMode() {
  if (!cc.isActive.value) {
    // Activating CC — link to current chat if one is selected
    cc.chatSessionId.value = currentSessionId.value
    cc.toggle()
  } else {
    cc.toggle()
  }
}

async function openCcKanbanMenu() {
  showCcKanbanMenu.value = !showCcKanbanMenu.value
  if (showCcKanbanMenu.value && ccKanbanTasks.value.length === 0) {
    try {
      const result = await kanbanApi.getTasks()
      ccKanbanTasks.value = result.tasks
    } catch { /* ignore */ }
  }
}

async function linkCcToKanbanTask(task: KanbanTask) {
  cc.kanbanTaskId.value = task.id
  showCcKanbanMenu.value = false
  // Persist to DB if session already exists
  if (cc.dbSessionId.value) {
    try {
      await claudeCodeApi.patchSession(cc.dbSessionId.value, { kanban_task_id: task.id })
    } catch { /* ignore */ }
  }
}

function unlinkCcKanbanTask() {
  cc.kanbanTaskId.value = null
  showCcKanbanMenu.value = false
  if (cc.dbSessionId.value) {
    claudeCodeApi.patchSession(cc.dbSessionId.value, { kanban_task_id: null as unknown as number }).catch(() => {})
  }
}

// Token usage
const tokenUsage = computed(() => currentSession.value?.token_usage)

// Sharing computed
const isSessionOwner = computed(() => {
  if (!currentSession.value) return false
  const ownerId = currentSession.value.owner_id
  return authStore.canManage('chat') || ownerId === authStore.user?.id || ownerId === null || ownerId === undefined
})
const isSharedWithMe = computed(() => currentSession.value?.is_shared_with_me === true)
const isReadOnly = computed(() => isSharedWithMe.value && currentSession.value?.share_permission === 'read')

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function tokenBarColor(percent: number): string {
  if (percent >= 90) return 'bg-red-500'
  if (percent >= 70) return 'bg-yellow-500'
  return 'bg-green-500'
}

// Available LLM options for dropdown
interface LlmOption {
  value: string
  label: string
  type: 'vllm' | 'cloud'
}

const availableLlmOptions = computed<LlmOption[]>(() => {
  const options: LlmOption[] = []

  // Add vLLM option if backend supports it (always available as option)
  options.push({
    value: 'vllm',
    label: 'vLLM (Local)',
    type: 'vllm'
  })

  // Add enabled cloud providers
  const providers = llmProvidersData.value?.providers || []
  for (const provider of providers) {
    if (provider.enabled) {
      options.push({
        value: `cloud:${provider.id}`,
        label: `${provider.name} (${provider.model_name})`,
        type: 'cloud'
      })
    }
  }

  return options
})

// Current LLM display name
const currentLlmLabel = computed(() => {
  const backend = selectedLlmBackend.value || llmBackendData.value?.backend || 'vllm'
  const option = availableLlmOptions.value.find(o => o.value === backend)
  return option?.label || backend
})

// Watch for session change to load custom prompt and reset state
watch(currentSession, (session) => {
  if (session) {
    customPrompt.value = session.system_prompt || ''
    // Only reset context files when switching to a different session (not on refetch)
    if (session.id !== contextFilesSessionId.value) {
      contextFiles.value = session.context_files ? [...session.context_files] : []
      contextFilesSessionId.value = session.id
    }
    // Load per-session RAG settings
    selectedRagMode.value = session.rag_mode || ''
    selectedCollectionIds.value = session.knowledge_collection_ids || []
  }
  attachedFiles.value = []
})

// Mutations
const createSessionMutation = useMutation({
  mutationFn: () => chatApi.createSession(undefined, undefined, 'admin'),
  onSuccess: (data) => {
    refetchSessions()
    currentSessionId.value = data.session.id
  },
})

const deleteSessionMutation = useMutation({
  mutationFn: (sessionId: string) => chatApi.deleteSession(sessionId),
  onSuccess: () => {
    refetchSessions()
    if (sessions.value.length > 0) {
      currentSessionId.value = sessions.value[0].id
    } else {
      currentSessionId.value = null
    }
  },
})

const bulkDeleteMutation = useMutation({
  mutationFn: (sessionIds: string[]) => chatApi.bulkDeleteSessions(sessionIds),
  onSuccess: () => {
    selectedIds.value.clear()
    selectionMode.value = false
    refetchSessions()
    // Select first remaining session or clear
    if (sessions.value.length > 0) {
      currentSessionId.value = sessions.value[0].id
    } else {
      currentSessionId.value = null
    }
  },
})

const updateSessionMutation = useMutation({
  mutationFn: ({ sessionId, data }: { sessionId: string; data: { title?: string; system_prompt?: string; pinned?: boolean } }) =>
    chatApi.updateSession(sessionId, data),
  onSuccess: () => {
    refetchSession()
    refetchSessions()
  },
})

function togglePin(sessionId: string, currentPinned?: boolean) {
  updateSessionMutation.mutate({
    sessionId,
    data: { pinned: !currentPinned },
  })
}

const sendMessageMutation = useMutation({
  mutationFn: ({ sessionId, content }: { sessionId: string; content: string }) =>
    chatApi.sendMessage(sessionId, content),
  onSuccess: () => {
    refetchSession()
    refetchBranches()
    refetchSessions()
    scrollToBottom()
  },
})

const editMessageMutation = useMutation({
  mutationFn: ({ sessionId, messageId, content }: { sessionId: string; messageId: string; content: string }) =>
    chatApi.editMessage(sessionId, messageId, content),
  onSuccess: () => {
    isStreaming.value = false
    streamingContent.value = ''
    refetchSession()
    refetchBranches()
    scrollToBottom()
  },
  onError: () => {
    isStreaming.value = false
    streamingContent.value = ''
  },
})

const regenerateMutation = useMutation({
  mutationFn: ({ sessionId, messageId }: { sessionId: string; messageId: string }) =>
    chatApi.regenerateResponse(sessionId, messageId),
  onSuccess: () => {
    isStreaming.value = false
    streamingContent.value = ''
    refetchSession()
    refetchBranches()
    scrollToBottom()
  },
  onError: () => {
    isStreaming.value = false
    streamingContent.value = ''
  },
})

// Track which message to scroll to after branch switch
const pendingScrollMessageId = ref<string | null>(null)

const switchBranchMutation = useMutation({
  mutationFn: ({ sessionId, messageId }: { sessionId: string; messageId: string }) =>
    chatApi.switchBranch(sessionId, messageId),
  onSuccess: async () => {
    await refetchSession()
    await refetchBranches()
    if (pendingScrollMessageId.value) {
      scrollToMessage(pendingScrollMessageId.value)
      pendingScrollMessageId.value = null
    }
  },
})

const newBranchMutation = useMutation({
  mutationFn: (sessionId: string) => chatApi.newBranchFromScratch(sessionId),
  onSuccess: async () => {
    showBranchTree.value = true
    await refetchSession()
    await refetchBranches()
  },
})

function startNewBranch() {
  if (!currentSessionId.value) return
  newBranchMutation.mutate(currentSessionId.value)
}

function startNewBranchAndShowTree() {
  if (!currentSessionId.value) return
  showBranchTree.value = true
  newBranchMutation.mutate(currentSessionId.value)
}

const deleteMessageMutation = useMutation({
  mutationFn: ({ sessionId, messageId }: { sessionId: string; messageId: string }) =>
    chatApi.deleteMessage(sessionId, messageId),
  onSuccess: () => {
    refetchSession()
    refetchBranches()
    refetchSessions()
  },
})

const saveContextFilesMutation = useMutation({
  mutationFn: ({ sessionId, files }: { sessionId: string; files: { name: string; content: string }[] }) =>
    chatApi.updateSession(sessionId, { context_files: files }),
  onSuccess: (_data, variables) => {
    // Sync local state with what was saved to avoid watcher overwrite
    contextFilesSessionId.value = variables.sessionId
    refetchSession()
  },
})

function autoSaveContextFiles() {
  if (!currentSessionId.value) return
  saveContextFilesMutation.mutate({
    sessionId: currentSessionId.value,
    files: contextFiles.value,
  })
}

const summarizeBranchMutation = useMutation({
  mutationFn: ({ sessionId, messageId }: { sessionId: string; messageId: string }) =>
    chatApi.summarizeBranch(sessionId, messageId),
  onSuccess: (data) => {
    const ts = new Date().toISOString().slice(0, 16).replace('T', '_')
    contextFiles.value.push({ name: `summary_${ts}.md`, content: data.summary })
    if (currentSessionId.value) {
      saveContextFilesMutation.mutate({
        sessionId: currentSessionId.value,
        files: contextFiles.value,
      })
    }
    summarizingMessageId.value = null
  },
  onError: () => {
    summarizingMessageId.value = null
  },
})

const forkSessionMutation = useMutation({
  mutationFn: (sessionId: string) => chatApi.forkSession(sessionId),
  onSuccess: (data) => {
    queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    if (data.session) {
      currentSessionId.value = data.session.id
    }
    toastStore.success(t('chatView.chatForked'))
  },
})

// Methods
function isNearBottom(): boolean {
  if (!messagesContainer.value) return true
  const { scrollTop, scrollHeight, clientHeight } = messagesContainer.value
  return scrollHeight - scrollTop - clientHeight < 150
}

function scrollToTop() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
    // Second pass for async-rendered content (images, code blocks, etc.)
    setTimeout(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    }, 50)
  })
}

function scrollToMessage(messageId: string) {
  nextTick(() => {
    const el = document.getElementById(`msg-${messageId}`)
    if (el && messagesContainer.value) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      // Brief highlight flash
      el.classList.add('ring-2', 'ring-primary', 'ring-offset-1', 'ring-offset-background')
      setTimeout(() => {
        el.classList.remove('ring-2', 'ring-primary', 'ring-offset-1', 'ring-offset-background')
      }, 1500)
    }
  })
}

function selectSession(sessionId: string) {
  currentSessionId.value = sessionId
  showSidebar.value = false
}

function createNewChat() {
  createSessionMutation.mutate()
}

async function deleteCurrentSession() {
  if (!currentSessionId.value) return
  const session = sessions.value.find(s => s.id === currentSessionId.value)

  const confirmed = await confirmStore.confirmDelete(
    session?.title || 'chat',
    'chat'
  )

  if (confirmed) {
    deleteSessionMutation.mutate(currentSessionId.value)
  }
}

// Selection mode methods
function toggleSelection(sessionId: string) {
  if (selectedIds.value.has(sessionId)) {
    selectedIds.value.delete(sessionId)
  } else {
    selectedIds.value.add(sessionId)
  }
}

function selectAllSessions() {
  sessions.value.forEach(s => selectedIds.value.add(s.id))
}

function deselectAll() {
  selectedIds.value.clear()
}

async function deleteSelected() {
  if (selectedIds.value.size === 0) return

  const confirmed = await confirmStore.confirm({
    title: t('chatView.deleteSelected'),
    message: t('chatView.confirmBulkDelete', { count: selectedIds.value.size }),
    confirmText: t('common.delete'),
    type: 'danger'
  })

  if (confirmed) {
    bulkDeleteMutation.mutate([...selectedIds.value])
  }
}

// Inline rename methods
function startRename(session: ChatSessionSummary, event: Event) {
  event.stopPropagation()
  renamingSessionId.value = session.id
  renamingTitle.value = session.title
  nextTick(() => {
    const input = document.querySelector('.rename-input') as HTMLInputElement
    input?.focus()
    input?.select()
  })
}

function cancelRename() {
  renamingSessionId.value = null
  renamingTitle.value = ''
}

function saveRename() {
  if (!renamingSessionId.value || !renamingTitle.value.trim()) {
    cancelRename()
    return
  }

  updateSessionMutation.mutate({
    sessionId: renamingSessionId.value,
    data: { title: renamingTitle.value.trim() }
  })

  renamingSessionId.value = null
  renamingTitle.value = ''
}

// Header title inline edit
function startHeaderRename() {
  if (!currentSession.value) return
  editingHeaderTitle.value = true
  headerTitleValue.value = currentSession.value.title
  nextTick(() => {
    const input = document.querySelector('.header-rename-input') as HTMLInputElement
    input?.focus()
    input?.select()
  })
}

function saveHeaderRename() {
  if (!currentSession.value || !headerTitleValue.value.trim()) {
    cancelHeaderRename()
    return
  }
  updateSessionMutation.mutate({
    sessionId: currentSession.value.id,
    data: { title: headerTitleValue.value.trim() }
  })
  editingHeaderTitle.value = false
  headerTitleValue.value = ''
}

function cancelHeaderRename() {
  editingHeaderTitle.value = false
  headerTitleValue.value = ''
}

// Delete single session from list
async function deleteSingleSession(session: ChatSessionSummary, event: Event) {
  event.stopPropagation()

  const confirmed = await confirmStore.confirmDelete(
    session.title,
    'chat'
  )

  if (confirmed) {
    deleteSessionMutation.mutate(session.id)
  }
}

function getCcIndicator(session: { id: string; status: string }) {
  const isCurrent = cc.dbSessionId.value === session.id
  if (isCurrent && cc.isProcessing.value) {
    return { bg: 'bg-green-500', pulse: true, title: 'Работает…' }
  }
  if (isCurrent && session.status === 'active') {
    return { bg: 'bg-yellow-400', pulse: true, title: 'Ждёт вашего ответа' }
  }
  switch (session.status) {
    case 'active':    return { bg: 'bg-green-500/50', pulse: false, title: 'Активна' }
    case 'completed': return { bg: 'bg-gray-400',     pulse: false, title: 'Завершена' }
    case 'error':     return { bg: 'bg-red-500',      pulse: false, title: 'Ошибка' }
    case 'aborted':   return { bg: 'bg-orange-400',   pulse: false, title: 'Прервана' }
    default:          return { bg: 'bg-gray-400',     pulse: false, title: '' }
  }
}

async function deleteCcSession(ccSessionId: string, title: string, event: Event) {
  event.stopPropagation()
  const confirmed = await confirmStore.confirmDelete(title, 'chat')
  if (!confirmed) return
  try {
    await claudeCodeApi.deleteSession(ccSessionId)
    // If viewing this session, deactivate CC mode
    if (cc.dbSessionId.value === ccSessionId) {
      if (cc.isActive.value) cc.toggle()
    }
    await fetchAllCcSessions()
  } catch {
    // ignore
  }
}

function sendMessage() {
  const hasText = inputMessage.value.trim().length > 0
  const hasPaste = pastedBlocks.value.length > 0
  const hasImages = pendingImages.value.length > 0
  if ((!hasText && !hasPaste && !hasImages) || !currentSessionId.value || isStreaming.value) return

  const content = buildMessageContent(inputMessage.value.trim(), pastedBlocks.value)
  const imageIds = pendingImages.value.map(i => i.id)
  inputMessage.value = ''
  pastedBlocks.value = []
  pendingImages.value = []
  if (messageInputRef.value) messageInputRef.value.style.height = 'auto'

  // Show user message immediately (optimistic)
  pendingUserContent.value = content
  isStreaming.value = true
  streamingContent.value = ''
  scrollToBottom()

  let fullContent = ''
  // Build LLM override if a specific backend or RAG collections are selected
  const hasCollections = selectedCollectionIds.value.length > 0
  const hasOverride = selectedLlmBackend.value || hasCollections
  const llmOverride = hasOverride ? {
    ...(selectedLlmBackend.value ? { llm_backend: selectedLlmBackend.value } : {}),
    ...(hasCollections ? { rag_mode: 'selected', knowledge_collection_ids: selectedCollectionIds.value } : {}),
  } : undefined

  const stream = chatApi.streamMessage(currentSessionId.value, content, (data) => {
    if (data.type === 'tool_start') {
      searchingQuery.value = data.query || ''
    } else if (data.type === 'tool_end') {
      searchingQuery.value = null
    } else if (data.type === 'chunk' && data.content) {
      streamingContent.value += data.content
      fullContent += data.content
      if (isNearBottom()) scrollToBottom()
    } else if (data.type === 'done' || data.type === 'assistant_message') {
      isStreaming.value = false
      pendingUserContent.value = null
      searchingQuery.value = null
      const responseText = fullContent || streamingContent.value
      streamingContent.value = ''

      // Update token_usage from stream event
      if (data.token_usage && currentSessionId.value) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        queryClient.setQueryData(['chat-session', currentSessionId.value], (old: any) => {
          if (!old?.session) return old
          return { ...old, session: { ...old.session, token_usage: data.token_usage } }
        })
      }

      refetchSession().then(() => scrollToBottom())
      refetchBranches()
      refetchSessions()
      scrollToBottom()
      nextTick(() => messageInputRef.value?.focus())

      // Voice mode: auto-play TTS for the response
      const messageId = data.message?.id
      if (voiceMode.value && responseText && messageId) {
        // Small delay to ensure session is refetched
        setTimeout(() => {
          speakMessage(messageId, responseText)
        }, 100)
      }
    } else if (data.type === 'error') {
      isStreaming.value = false
      pendingUserContent.value = null
      searchingQuery.value = null
      streamingContent.value = ''
      console.error('Stream error:', data.content)
      // Refetch to show user message that was already saved to DB
      refetchSession()
      refetchSessions()
      nextTick(() => messageInputRef.value?.focus())
    }
  }, llmOverride, undefined, imageIds.length ? imageIds : undefined)
}

function ccSendMessage() {
  const hasText = inputMessage.value.trim().length > 0
  const hasPaste = pastedBlocks.value.length > 0
  if ((!hasText && !hasPaste) || cc.isProcessing.value) return
  const prompt = buildMessageContent(inputMessage.value.trim(), pastedBlocks.value)
  inputMessage.value = ''
  pastedBlocks.value = []
  if (messageInputRef.value) messageInputRef.value.style.height = 'auto'
  cc.sendMessage(prompt)
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function toggleCcContextFile(file: { name: string; content: string }) {
  const idx = cc.pendingContextFiles.value.findIndex(f => f.name === file.name)
  if (idx >= 0) {
    cc.pendingContextFiles.value.splice(idx, 1)
  } else {
    cc.pendingContextFiles.value.push({ name: file.name, content: file.content })
  }
}

function isCcFileSelected(name: string) {
  return cc.pendingContextFiles.value.some(f => f.name === name)
}

function selectCcDir(dir: string) {
  cc.workingDir.value = dir
  cc.projectId.value = null
  showCcDirMenu.value = false
}

function selectProject(project: CcProject) {
  cc.workingDir.value = project.path
  cc.projectId.value = project.id
  showCcDirMenu.value = false
}

async function fetchCcProjects() {
  try {
    const res = await claudeCodeApi.listProjects()
    ccProjects.value = res.projects
  } catch {
    ccProjects.value = []
  }
}

async function addCcProject() {
  const p = ccNewProject.value
  if (!p.name.trim() || !p.path.trim()) return
  try {
    await claudeCodeApi.addProject(p)
    ccNewProject.value = { name: '', path: '', type: 'local' }
    showCcAddProject.value = false
    await fetchCcProjects()
  } catch (e: unknown) {
    console.error('Failed to add project', e)
  }
}

async function deleteCcProject(id: number) {
  try {
    await claudeCodeApi.deleteProject(id)
    await fetchCcProjects()
  } catch (e: unknown) {
    console.error('Failed to delete project', e)
  }
}

watch(showCcDirMenu, (open) => {
  if (open) fetchCcProjects()
})

function startEditing(message: ChatMessage) {
  editingMessageId.value = message.id
  editingContent.value = message.content
  nextTick(() => {
    const ta = document.querySelector('[data-edit-textarea]') as HTMLTextAreaElement | null
    if (ta) autoResizeTextarea(ta)
  })
}

function autoResizeTextarea(el: HTMLTextAreaElement) {
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

function onInputAutoResize(e: Event) {
  autoResizeTextarea(e.target as HTMLTextAreaElement)
}

function cancelEditing() {
  editingMessageId.value = null
  editingContent.value = ''
}

function saveEdit() {
  if (!currentSessionId.value || !editingMessageId.value) return
  const sessionId = currentSessionId.value
  const messageId = editingMessageId.value
  const content = editingContent.value

  // Detect role of the message being edited
  const editedMessage = messages.value.find(m => m.id === messageId)
  const isAssistantEdit = editedMessage?.role === 'assistant'

  // Close edit form immediately
  editingMessageId.value = null
  editingContent.value = ''

  // Optimistic update: show edited text immediately
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  queryClient.setQueryData(['chat-session', sessionId], (old: any) => {
    if (!old?.session?.messages) return old
    return {
      ...old,
      session: {
        ...old.session,
        messages: old.session.messages.map((m: ChatMessage) =>
          m.id === messageId ? { ...m, content, edited: true } : m
        )
      }
    }
  })

  if (!isAssistantEdit) {
    // User message edit: show loading for LLM regeneration
    isStreaming.value = true
    streamingContent.value = ''
    scrollToBottom()
  }

  editMessageMutation.mutate({ sessionId, messageId, content })
  nextTick(() => messageInputRef.value?.focus())
}

function regenerateResponse(messageId: string) {
  if (!currentSessionId.value) return
  isStreaming.value = true
  streamingContent.value = ''
  scrollToBottom()
  regenerateMutation.mutate({
    sessionId: currentSessionId.value,
    messageId,
  })
}

function regenerateAssistantResponse(assistantMessageId: string) {
  if (!currentSessionId.value) return
  isStreaming.value = true
  streamingContent.value = ''
  scrollToBottom()
  regenerateMutation.mutate({
    sessionId: currentSessionId.value,
    messageId: assistantMessageId,
  })
}

function onBranchSwitch(messageId: string) {
  if (!currentSessionId.value) return
  pendingScrollMessageId.value = messageId
  switchBranchMutation.mutate({
    sessionId: currentSessionId.value,
    messageId,
  })
}

function onBranchScrollTo(messageId: string) {
  scrollToMessage(messageId)
}

function switchToSibling(messageId: string) {
  if (!currentSessionId.value) return
  switchBranchMutation.mutate({
    sessionId: currentSessionId.value,
    messageId,
  })
}

function getSiblingInfo(messageId: string): SiblingInfo | null {
  return siblingInfo.value[messageId] || null
}

function deleteMessage(messageId: string) {
  if (!currentSessionId.value) return
  if (confirm('Delete this message and all following?')) {
    deleteMessageMutation.mutate({
      sessionId: currentSessionId.value,
      messageId,
    })
  }
}

async function deleteBranchNode(messageId: string) {
  if (!currentSessionId.value) return
  const confirmed = await confirmStore.confirm({
    title: t('chatView.deleteBranch'),
    message: t('chatView.confirmDeleteBranch'),
    confirmText: t('common.delete'),
    type: 'danger',
  })
  if (!confirmed) return
  deleteMessageMutation.mutate({
    sessionId: currentSessionId.value,
    messageId,
  })
}

async function deleteBranches(messageIds: string[]) {
  if (!currentSessionId.value || messageIds.length === 0) return
  const confirmed = await confirmStore.confirm({
    title: t('chatView.deleteBranches'),
    message: t('chatView.confirmDeleteBranches', { n: messageIds.length }),
    confirmText: t('common.delete'),
    type: 'danger',
  })
  if (!confirmed) return
  const sessionId = currentSessionId.value
  for (const messageId of messageIds) {
    deleteMessageMutation.mutate({ sessionId, messageId })
  }
}

function triggerFileUpload() {
  fileInputRef.value?.click()
}

function handleFileUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (!files) return

  for (const file of files) {
    if (!file.name.endsWith('.txt') && !file.name.endsWith('.md')) continue

    const reader = new FileReader()
    reader.onload = () => {
      const content = reader.result as string
      attachedFiles.value.push({ name: file.name, content })
      // Append to prompt textarea
      const separator = customPrompt.value.trim() ? '\n\n' : ''
      customPrompt.value += `${separator}# ${file.name}\n${content}`
    }
    reader.readAsText(file)
  }
  // Reset input so the same file can be re-selected
  input.value = ''
}

function removeAttachedFile(index: number) {
  attachedFiles.value.splice(index, 1)
}

function saveSettings() {
  if (!currentSessionId.value) return
  updateSessionMutation.mutate({
    sessionId: currentSessionId.value,
    data: { system_prompt: customPrompt.value || undefined },
  })
  showSettings.value = false
}

function triggerContextFileUpload() {
  contextFileInputRef.value?.click()
}

function handleContextFileUpload(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files) return
  const files = Array.from(input.files)
  let loaded = 0
  files.forEach(file => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const content = e.target?.result as string
      contextFiles.value.push({ name: file.name, content })
      loaded++
      if (loaded === files.length) autoSaveContextFiles()
    }
    reader.readAsText(file)
  })
  input.value = ''
}

function addEmptyContextFile() {
  const idx = contextFiles.value.length + 1
  contextFiles.value.push({ name: `file_${idx}.txt`, content: '' })
  editingFileIndex.value = contextFiles.value.length - 1
  editingFileName.value = contextFiles.value[editingFileIndex.value].name
  editingFileContent.value = ''
}

function editContextFile(index: number) {
  editingFileIndex.value = index
  editingFileName.value = contextFiles.value[index].name
  editingFileContent.value = contextFiles.value[index].content
}

function saveContextFileEdit() {
  if (editingFileIndex.value === null) return
  contextFiles.value[editingFileIndex.value] = {
    name: editingFileName.value || 'untitled.txt',
    content: editingFileContent.value,
  }
  editingFileIndex.value = null
  editingFileName.value = ''
  editingFileContent.value = ''
  autoSaveContextFiles()
}

function cancelContextFileEdit() {
  // If the file was just added empty and has no content, remove it
  if (editingFileIndex.value !== null) {
    const file = contextFiles.value[editingFileIndex.value]
    if (!file.content && editingFileContent.value === '') {
      contextFiles.value.splice(editingFileIndex.value, 1)
    }
  }
  editingFileIndex.value = null
  editingFileName.value = ''
  editingFileContent.value = ''
}

function removeContextFile(index: number) {
  contextFiles.value.splice(index, 1)
  if (editingFileIndex.value === index) {
    editingFileIndex.value = null
  }
  autoSaveContextFiles()
}

function saveContextFiles() {
  autoSaveContextFiles()
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text)
}

function toggleInputPosition() {
  inputPosition.value = inputPosition.value === 'top' ? 'bottom' : 'top'
  localStorage.setItem('chat-input-position', inputPosition.value)
}

function formatChatAsMarkdown(msgs: ChatMessage[], title: string): string {
  let md = `# ${title}\n\n`
  for (const msg of msgs) {
    const role = msg.role === 'user' ? '**User**' : '**Assistant**'
    md += `${role}:\n${msg.content}\n\n---\n\n`
  }
  return md
}

function copyChatToClipboard() {
  if (!currentSession.value) return
  const md = formatChatAsMarkdown(messages.value, currentSession.value.title)
  navigator.clipboard.writeText(md)
  toastStore.success(t('chatView.chatCopied'))
  showExportMenu.value = false
}

function exportChatMarkdown() {
  if (!currentSession.value) return
  const md = formatChatAsMarkdown(messages.value, currentSession.value.title)
  const blob = new Blob([md], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${currentSession.value.title.replace(/[^a-zA-Zа-яА-Я0-9]/g, '_')}.md`
  a.click()
  URL.revokeObjectURL(url)
  showExportMenu.value = false
}

function exportChatJson() {
  if (!currentSession.value) return
  const data = {
    title: currentSession.value.title,
    created: currentSession.value.created,
    messages: messages.value.map(m => ({
      role: m.role,
      content: m.content,
      timestamp: m.timestamp,
    })),
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${currentSession.value.title.replace(/[^a-zA-Zа-яА-Я0-9]/g, '_')}.json`
  a.click()
  URL.revokeObjectURL(url)
  showExportMenu.value = false
}

function saveMessageToContext(message: ChatMessage) {
  if (!currentSessionId.value) return
  const ts = new Date().toISOString().slice(0, 16).replace('T', '_')
  contextFiles.value.push({ name: `response_${ts}.md`, content: message.content })
  saveContextFilesMutation.mutate({
    sessionId: currentSessionId.value,
    files: contextFiles.value,
  })
  toastStore.success(t('chatView.savedToContext'))
}

function summarizeBranch(messageId: string) {
  if (!currentSessionId.value || summarizingMessageId.value) return
  summarizingMessageId.value = messageId
  summarizeBranchMutation.mutate({
    sessionId: currentSessionId.value,
    messageId,
  })
}

// TTS functions
async function speakMessage(messageId: string, text: string) {
  // If already speaking this message, stop
  if (speakingMessageId.value === messageId && isSpeaking.value) {
    stopSpeaking()
    return
  }

  // Stop any current playback
  stopSpeaking()

  ttsLoading.value = messageId
  try {
    const blob = await ttsApi.testSynthesize(text)

    // Cleanup previous URL
    if (audioUrl.value) {
      URL.revokeObjectURL(audioUrl.value)
    }

    audioUrl.value = URL.createObjectURL(blob)
    speakingMessageId.value = messageId

    // Play audio
    nextTick(() => {
      if (audioRef.value) {
        audioRef.value.play()
        isSpeaking.value = true
      }
    })
  } catch (e) {
    console.error('TTS failed:', e)
  } finally {
    ttsLoading.value = null
  }
}

function stopSpeaking() {
  if (audioRef.value) {
    audioRef.value.pause()
    audioRef.value.currentTime = 0
  }
  isSpeaking.value = false
  speakingMessageId.value = null
}

function onAudioEnded() {
  isSpeaking.value = false
  speakingMessageId.value = null
}

// Voice input (STT) functions
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })

    mediaRecorder.value = new MediaRecorder(stream, {
      mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4'
    })
    audioChunks.value = []

    mediaRecorder.value.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.value.push(event.data)
      }
    }

    mediaRecorder.value.onstop = async () => {
      // Stop all tracks
      stream.getTracks().forEach(track => track.stop())

      if (audioChunks.value.length === 0) return

      const audioBlob = new Blob(audioChunks.value, { type: mediaRecorder.value?.mimeType || 'audio/webm' })

      // Transcribe
      isTranscribing.value = true
      try {
        const result = await sttApi.transcribe(audioBlob)
        if (result.text) {
          // Append to input or replace
          inputMessage.value = inputMessage.value
            ? inputMessage.value + ' ' + result.text
            : result.text
        }
      } catch (e) {
        console.error('Transcription failed:', e)
      } finally {
        isTranscribing.value = false
      }
    }

    mediaRecorder.value.start()
    isRecording.value = true
  } catch (e) {
    console.error('Failed to start recording:', e)
    alert('Could not access microphone. Please check permissions.')
  }
}

function stopRecording() {
  if (mediaRecorder.value && isRecording.value) {
    mediaRecorder.value.stop()
    isRecording.value = false
  }
}

function toggleRecording() {
  if (isRecording.value) {
    stopRecording()
  } else {
    startRecording()
  }
}

// Cleanup on unmount
onUnmounted(() => {
  document.removeEventListener('click', handleGlobalClick)
  document.removeEventListener('keydown', handleEscapeKey)
  fullscreenStore.exit()
  stopSpeaking()
  stopRecording()
  if (audioUrl.value) {
    URL.revokeObjectURL(audioUrl.value)
  }
})

function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

// Close dropdown menus on outside click
function handleGlobalClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (showExportMenu.value && !target.closest('.relative')) {
    showExportMenu.value = false
  }
  if (showRagMenu.value && !target.closest('.relative')) {
    showRagMenu.value = false
  }
  if (showCcDirMenu.value && !target.closest('.relative')) {
    showCcDirMenu.value = false
  }
  if (showCcFilesMenu.value && !target.closest('.relative')) {
    showCcFilesMenu.value = false
  }
  if (showCcKanbanMenu.value && !target.closest('.relative')) {
    showCcKanbanMenu.value = false
  }
  if (showZenSettings.value && !target.closest('.zen-settings-anchor')) {
    showZenSettings.value = false
  }
  if (showZenLlmMenu.value && !target.closest('.zen-llm-anchor')) {
    showZenLlmMenu.value = false
  }
}

// Zen mode: restore from localStorage
if (localStorage.getItem('chat-fullscreen') === 'true') {
  fullscreenStore.enter()
}
watch(() => fullscreenStore.isFullscreen, (val) => {
  localStorage.setItem('chat-fullscreen', val ? 'true' : 'false')
  if (!val) { showZenSettings.value = false; showZenLlmMenu.value = false }
})

function handleEscapeKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && fullscreenStore.isFullscreen) {
    fullscreenStore.exit()
  }
}

// Initialize: select first session or create new
onMounted(() => {
  document.addEventListener('click', handleGlobalClick)
  document.addEventListener('keydown', handleEscapeKey)
  if (sessions.value.length > 0) {
    currentSessionId.value = sessions.value[0].id
  }
  fetchAllCcSessions()
})

watch(sessions, (newSessions) => {
  if (!currentSessionId.value && newSessions.length > 0) {
    currentSessionId.value = newSessions[0].id
  }
})

// Refresh CC sidebar sessions when CC processing finishes
watch(() => cc.isProcessing.value, (processing, wasProcesing) => {
  if (wasProcesing && !processing) {
    fetchAllCcSessions()
  }
})
</script>

<template>
  <!-- Hidden audio element for TTS playback -->
  <audio ref="audioRef" :src="audioUrl || undefined" class="hidden" @ended="onAudioEnded" />

  <div :class="['flex h-full', fullscreenStore.isFullscreen ? 'zen-enter' : '']">
    <!-- Sidebar: Chat List (hidden in zen mode) -->
    <div
      v-if="!fullscreenStore.isFullscreen"
      :class="[
        'border-r border-border bg-card flex flex-col transition-all',
        showSidebar ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
        'fixed md:relative inset-y-0 left-0 z-40 md:z-0',
        sidebarCollapsed ? 'w-full md:!w-14' : 'w-full'
      ]"
      :style="!sidebarCollapsed ? { width: sidebarWidth + 'px' } : undefined"
    >
      <!-- Collapsed mode (desktop only) -->
      <template v-if="sidebarCollapsed">
        <!-- Collapsed header: expand + new chat -->
        <div class="hidden md:flex flex-col items-center gap-1 p-2 border-b border-border">
          <button class="p-2 rounded-lg border border-border text-muted-foreground hover:bg-secondary/50 transition-colors" :title="t('chatView.expandSidebar')" @click="toggleSidebarCollapse">
            <PanelLeftOpen class="w-4 h-4" />
          </button>
          <button
            class="p-2 rounded-lg text-muted-foreground hover:bg-secondary/50 transition-colors"
            :title="t('chatView.zenMode')"
            @click="fullscreenStore.enter()"
          >
            <Maximize2 class="w-4 h-4" />
          </button>
          <button
            :disabled="createSessionMutation.isPending.value"
            class="p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            :title="t('chatView.newChat')"
            @click="createNewChat"
          >
            <Plus class="w-4 h-4" />
          </button>
        </div>

        <!-- Collapsed items list -->
        <div class="hidden md:block flex-1 overflow-y-auto">
          <button
            v-for="session in sessions"
            :key="session.id"
            :title="session.title"
            :class="[
              'w-full flex items-center justify-center py-2 transition-colors relative',
              currentSessionId === session.id
                ? 'bg-primary/10 border-l-2 border-l-primary'
                : 'hover:bg-secondary/50'
            ]"
            @click="selectSession(session.id)"
          >
            <div v-if="session.pinned" class="absolute top-1 left-1 w-2 h-2 rounded-full bg-primary" />
            <div class="w-8 h-8 rounded-full border border-border bg-transparent flex items-center justify-center text-xs font-medium text-muted-foreground shrink-0 relative">
              {{ session.title.trim().slice(0, 2).toUpperCase() }}
              <span v-if="session.is_shared_with_me" class="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-blue-400 border-2 border-card" :title="t('chatView.sharedWithYou')" />
              <span v-else-if="(session.share_count ?? 0) > 0" class="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-green-400 border-2 border-card" :title="t('chatView.sharedByYou', { count: session.share_count })" />
            </div>
          </button>
        </div>
      </template>

      <!-- Expanded mode -->
      <template v-else>
      <!-- Header -->
      <div class="p-4 border-b border-border flex items-center justify-between">
        <h2 class="font-semibold flex items-center gap-2">
          <MessageSquare class="w-5 h-5" />
          {{ t('chatView.title') }}
        </h2>
        <div class="flex items-center gap-1">
          <button
            class="hidden md:inline-flex p-2 rounded-lg border border-border text-muted-foreground hover:bg-secondary/50 transition-colors"
            :title="t('chatView.collapseSidebar')"
            @click="toggleSidebarCollapse"
          >
            <PanelLeftClose class="w-4 h-4" />
          </button>
          <button
            class="p-2 rounded-lg hover:bg-secondary transition-colors text-muted-foreground"
            :title="t('chatView.zenMode')"
            @click="fullscreenStore.enter()"
          >
            <Maximize2 class="w-4 h-4" />
          </button>
          <button
            :class="[
              'p-2 rounded-lg transition-colors',
              selectionMode ? 'bg-primary text-primary-foreground' : 'hover:bg-secondary'
            ]"
            :title="selectionMode ? t('chatView.deselectAll') : t('chatView.selectAll')"
            @click="selectionMode = !selectionMode"
          >
            <ListChecks class="w-4 h-4" />
          </button>
          <button
            :disabled="createSessionMutation.isPending.value"
            class="p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            @click="createNewChat"
          >
            <Plus class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- Bulk actions toolbar (when in selection mode) -->
      <div v-if="selectionMode && selectedIds.size > 0" class="p-2 border-b border-border bg-secondary/50">
        <div class="flex items-center justify-between text-sm">
          <span class="text-muted-foreground">{{ t('chatView.selectedCount', { count: selectedIds.size }) }}</span>
          <div class="flex gap-2">
            <button class="text-xs text-primary hover:underline" @click="selectAllSessions">{{ t('chatView.selectAll') }}</button>
            <button class="text-xs hover:underline" @click="deselectAll">{{ t('chatView.deselectAll') }}</button>
            <button class="text-xs text-red-500 hover:underline" @click="deleteSelected">{{ t('chatView.deleteSelected') }}</button>
          </div>
        </div>
      </div>

      <!-- Sessions List -->
      <div class="flex-1 overflow-y-auto">
        <!-- Standalone CC sessions (no parent chat) -->
        <template v-if="standaloneCcSessions.length">
          <div class="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-green-500/70 bg-green-500/5 border-b border-border/50">
            Claude Code
          </div>
          <div
            v-for="ccSub in standaloneCcSessions"
            :key="ccSub.id"
            :class="[
              'pl-4 pr-3 py-2 cursor-pointer border-b border-border/50 transition-colors group',
              cc.dbSessionId.value === ccSub.id
                ? 'bg-green-600/10 border-l-2 border-l-green-500'
                : 'hover:bg-secondary/30'
            ]"
            @click="loadCcSession(ccSub.id)"
          >
            <div class="flex items-center gap-2">
              <span
                :class="['w-2 h-2 rounded-full flex-shrink-0',
                         getCcIndicator(ccSub).bg,
                         getCcIndicator(ccSub).pulse ? 'animate-pulse' : '']"
                :title="getCcIndicator(ccSub).title"
              />
              <Terminal class="w-3.5 h-3.5 text-green-500 shrink-0" />
              <p class="text-xs truncate text-green-400/80">{{ ccSub.title }}</p>
              <span class="text-[10px] text-muted-foreground ml-auto">{{ ccSub.total_turns }}t</span>
              <button
                class="p-0.5 rounded hover:bg-background text-red-500 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                :title="t('chatView.deleteChat')"
                @click.stop="deleteCcSession(ccSub.id, ccSub.title, $event)"
              >
                <Trash2 class="w-3 h-3" />
              </button>
            </div>
          </div>
        </template>

        <template v-for="session in sessions" :key="session.id">
          <div
            :class="[
              'p-3 cursor-pointer border-b border-border transition-colors group',
              currentSessionId === session.id
                ? 'bg-primary/10 border-l-2 border-l-primary'
                : 'hover:bg-secondary/50'
            ]"
            @click="!selectionMode && selectSession(session.id)"
          >
            <div class="flex items-start gap-2">
              <!-- Checkbox (selection mode) -->
              <input
                v-if="selectionMode"
                type="checkbox"
                :checked="selectedIds.has(session.id)"
                class="mt-1 rounded border-border"
                @click.stop="toggleSelection(session.id)"
              />

              <div class="flex-1 min-w-0">
                <!-- Title (normal or editing) -->
                <template v-if="renamingSessionId === session.id">
                  <input
                    v-model="renamingTitle"
                    class="rename-input w-full px-1 py-0.5 text-sm bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                    @keydown.enter="saveRename"
                    @keydown.escape="cancelRename"
                    @blur="saveRename"
                    @click.stop
                  />
                </template>
                <template v-else>
                  <p
                    class="font-medium text-sm truncate flex items-center gap-1"
                    @dblclick="startRename(session, $event)"
                  >
                    <Pin v-if="session.pinned" class="w-3 h-3 text-primary shrink-0" />
                    <Users v-if="session.is_shared_with_me" class="w-3 h-3 text-blue-400 shrink-0" :title="t('chatView.sharedWithYou')" />
                    <Share2 v-else-if="(session.share_count ?? 0) > 0" class="w-3 h-3 text-green-400 shrink-0" :title="t('chatView.sharedByYou', { count: session.share_count })" />
                    {{ session.title }}
                  </p>
                </template>

                <p class="text-xs text-muted-foreground truncate mt-1">
                  {{ session.last_message || 'No messages' }}
                </p>
                <p class="text-xs text-muted-foreground mt-1">
                  {{ session.message_count }} messages
                </p>
              </div>

              <!-- Action buttons (on hover, not in selection mode) -->
              <div v-if="!selectionMode && renamingSessionId !== session.id" class="flex gap-0.5 opacity-0 group-hover:opacity-100">
                <button
                  class="p-1 rounded hover:bg-background text-muted-foreground"
                  :title="session.pinned ? 'Unpin' : 'Pin'"
                  @click.stop="togglePin(session.id, session.pinned)"
                >
                  <PinOff v-if="session.pinned" class="w-3 h-3" />
                  <Pin v-else class="w-3 h-3" />
                </button>
                <button
                  class="p-1 rounded hover:bg-background text-muted-foreground"
                  :title="t('chatView.rename')"
                  @click.stop="startRename(session, $event)"
                >
                  <Edit3 class="w-3 h-3" />
                </button>
                <button
                  class="p-1 rounded hover:bg-background text-red-500"
                  :title="t('chatView.deleteChat')"
                  @click.stop="deleteSingleSession(session, $event)"
                >
                  <Trash2 class="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>

          <!-- CC sub-sessions for this chat -->
          <div
            v-for="ccSub in getCcSubSessions(session.id)"
            :key="ccSub.id"
            :class="[
              'pl-8 pr-3 py-2 cursor-pointer border-b border-border/50 transition-colors group',
              cc.dbSessionId.value === ccSub.id
                ? 'bg-green-600/10 border-l-2 border-l-green-500'
                : 'hover:bg-secondary/30'
            ]"
            @click="loadCcSession(ccSub.id)"
          >
            <div class="flex items-center gap-2">
              <span
                :class="['w-2 h-2 rounded-full flex-shrink-0',
                         getCcIndicator(ccSub).bg,
                         getCcIndicator(ccSub).pulse ? 'animate-pulse' : '']"
                :title="getCcIndicator(ccSub).title"
              />
              <Terminal class="w-3.5 h-3.5 text-green-500 shrink-0" />
              <p class="text-xs truncate text-green-400/80">{{ ccSub.title }}</p>
              <span class="text-[10px] text-muted-foreground ml-auto">{{ ccSub.total_turns }}t</span>
              <button
                class="p-0.5 rounded hover:bg-background text-red-500 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                :title="t('chatView.deleteChat')"
                @click.stop="deleteCcSession(ccSub.id, ccSub.title, $event)"
              >
                <Trash2 class="w-3 h-3" />
              </button>
            </div>
          </div>
        </template>

        <div v-if="!sessions.length && !standaloneCcSessions.length" class="p-4 text-center text-muted-foreground">
          <p>{{ t('chatView.noChats') }}</p>
          <button
            class="mt-2 text-primary hover:underline"
            @click="createNewChat"
          >
            {{ t('chatView.createFirst') }}
          </button>
        </div>
      </div>
      </template>
    </div>

    <!-- Sidebar resize handle (desktop only) -->
    <div
      v-if="!sidebarCollapsed && !fullscreenStore.isFullscreen"
      class="hidden md:block w-1.5 cursor-col-resize hover:bg-primary/30 active:bg-primary/50 transition-colors flex-shrink-0"
      @mousedown="startSidebarResize"
      @touchstart="startSidebarTouchResize"
    />

    <!-- Mobile sidebar backdrop -->
    <div
      v-if="showSidebar && !fullscreenStore.isFullscreen"
      class="md:hidden fixed inset-0 bg-black/50 z-30"
      @click="showSidebar = false"
    />

    <!-- Mobile sidebar toggle -->
    <button
      v-if="!fullscreenStore.isFullscreen"
      class="md:hidden fixed left-4 bottom-24 z-50 p-3 bg-primary text-primary-foreground rounded-full shadow-lg"
      @click="showSidebar = !showSidebar"
    >
      <ChevronLeft :class="['w-5 h-5 transition-transform', showSidebar ? '' : 'rotate-180']" />
    </button>

    <!-- Zen Mode: Vertical Activity Bar (left) -->
    <div
      v-if="fullscreenStore.isFullscreen && currentSession"
      class="zen-activity-bar zen-glass zen-toolbar-enter flex flex-col items-center py-3 px-1.5 gap-1 border-r border-border/30 z-10"
    >
      <!-- Session title: first letter avatar -->
      <div
        class="w-8 h-8 rounded-lg bg-primary/20 text-primary flex items-center justify-center text-xs font-bold cursor-pointer shrink-0"
        :title="currentSession.title"
        @click="startHeaderRename"
      >
        {{ currentSession.title.charAt(0).toUpperCase() }}
      </div>

      <!-- Exit fullscreen (top) -->
      <button
        class="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-secondary/50 hover:text-foreground transition-colors shrink-0"
        :title="t('chatView.exitZenMode')"
        @click="fullscreenStore.exit()"
      >
        <Minimize2 class="w-4 h-4" />
      </button>

      <div class="w-6 h-px bg-border/50 my-1 shrink-0"></div>

      <!-- Claude Code toggle (restricted users) -->
      <button
        v-if="['shaerware', 'ivan'].includes(authStore.user?.username ?? '')"
        :class="[
          'w-8 h-8 rounded-lg flex items-center justify-center transition-colors shrink-0',
          cc.isActive.value ? 'bg-green-600/20 text-green-400' : 'text-muted-foreground hover:bg-secondary/50'
        ]"
        :title="cc.isActive.value ? t('chatView.claudeCode.disable') : t('chatView.claudeCode.enable')"
        @click="toggleCcMode()"
      >
        <Terminal class="w-4 h-4" />
      </button>

      <!-- LLM dropdown (non-CC) -->
      <div v-if="!cc.isActive.value" class="zen-llm-anchor relative shrink-0">
        <button
          :class="[
            'w-8 h-8 rounded-lg flex items-center justify-center transition-colors',
            showZenLlmMenu ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:bg-secondary/50'
          ]"
          :title="t('chat.selectLlm')"
          @click.stop="showZenLlmMenu = !showZenLlmMenu"
        >
          <Brain class="w-4 h-4" />
        </button>
        <div
          v-if="showZenLlmMenu"
          class="absolute left-full ml-2 top-0 zen-glass rounded-xl shadow-2xl py-1 z-50 min-w-[180px] animate-scale-in"
          @click.stop
        >
          <button
            :class="[
              'flex items-center gap-2 w-full px-3 py-1.5 text-sm transition-colors text-left',
              selectedLlmBackend === '' ? 'bg-primary/20 text-primary' : 'hover:bg-secondary/30'
            ]"
            @click="selectedLlmBackend = ''; showZenLlmMenu = false"
          >
            <span>{{ t('chat.defaultLlm') }}</span>
            <Check v-if="selectedLlmBackend === ''" class="w-3.5 h-3.5 ml-auto text-primary" />
          </button>
          <button
            v-for="option in availableLlmOptions"
            :key="option.value"
            :class="[
              'flex items-center gap-2 w-full px-3 py-1.5 text-sm transition-colors text-left',
              selectedLlmBackend === option.value ? 'bg-primary/20 text-primary' : 'hover:bg-secondary/30'
            ]"
            @click="selectedLlmBackend = option.value; showZenLlmMenu = false"
          >
            <span>{{ option.label }}</span>
            <Check v-if="selectedLlmBackend === option.value" class="w-3.5 h-3.5 ml-auto text-primary" />
          </button>
        </div>
      </div>

      <!-- RAG collections dropdown (non-CC) -->
      <div v-if="!cc.isActive.value && knowledgeCollections.length" class="relative shrink-0">
        <button
          :class="[
            'w-8 h-8 rounded-lg flex items-center justify-center transition-colors',
            selectedCollectionIds.length > 0 ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:bg-secondary/50'
          ]"
          :title="t('chatView.knowledgeBase')"
          @click="showRagMenu = !showRagMenu"
        >
          <BookOpen class="w-4 h-4" />
          <span
            v-if="selectedCollectionIds.length"
            class="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 text-[9px] font-bold rounded-full bg-primary text-primary-foreground flex items-center justify-center border border-background"
          >{{ selectedCollectionIds.length }}</span>
        </button>
        <div
          v-if="showRagMenu"
          class="absolute left-full ml-2 top-0 zen-glass rounded-xl shadow-2xl py-2 z-50 min-w-[200px] animate-scale-in"
          @click.stop
        >
          <label
            v-for="col in knowledgeCollections"
            :key="col.id"
            class="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-secondary/30 transition-colors cursor-pointer"
          >
            <input v-model="selectedCollectionIds" type="checkbox" :value="col.id" class="rounded border-border w-3.5 h-3.5" />
            <span>{{ col.name }}</span>
          </label>
        </div>
      </div>

      <!-- Share button (non-CC, owner only) -->
      <div v-if="!cc.isActive.value && isSessionOwner && !isSharedWithMe" class="relative shrink-0">
        <button
          class="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-secondary/50 transition-colors"
          :title="t('chatView.shareChat')"
          @click="showShareDialog = true"
        >
          <Share2 class="w-4 h-4" />
          <span
            v-if="(currentSession?.share_count ?? 0) > 0"
            class="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 text-[9px] font-bold rounded-full bg-green-500 text-white flex items-center justify-center border border-background"
          >{{ currentSession!.share_count }}</span>
        </button>
      </div>

      <!-- Fork button (non-CC, read-only) -->
      <button
        v-if="!cc.isActive.value && isReadOnly"
        :disabled="forkSessionMutation.isPending.value"
        class="w-8 h-8 rounded-lg flex items-center justify-center text-blue-400 hover:bg-secondary/50 transition-colors shrink-0"
        :title="t('chatView.forkChat')"
        @click="currentSessionId && forkSessionMutation.mutate(currentSessionId)"
      >
        <Loader2 v-if="forkSessionMutation.isPending.value" class="w-4 h-4 animate-spin" />
        <GitFork v-else class="w-4 h-4" />
      </button>

      <!-- Export dropdown (non-CC) -->
      <div v-if="!cc.isActive.value" class="relative shrink-0">
        <button
          class="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-secondary/50 transition-colors"
          :title="t('chatView.exportChat')"
          @click="showExportMenu = !showExportMenu"
        >
          <Download class="w-4 h-4" />
        </button>
        <div
          v-if="showExportMenu"
          class="absolute left-full ml-2 top-0 zen-glass rounded-xl shadow-2xl py-1 z-50 min-w-[160px] animate-scale-in"
          @click.stop
        >
          <button
            class="w-full px-3 py-1.5 text-sm text-left hover:bg-secondary/30 transition-colors flex items-center gap-2"
            @click="copyChatToClipboard"
          >
            <Copy class="w-3.5 h-3.5" />
            {{ t('chatView.copyChat') }}
          </button>
          <button
            class="w-full px-3 py-1.5 text-sm text-left hover:bg-secondary/30 transition-colors flex items-center gap-2"
            @click="exportChatMarkdown"
          >
            <FileText class="w-3.5 h-3.5" />
            {{ t('chatView.exportMarkdown') }}
          </button>
          <button
            class="w-full px-3 py-1.5 text-sm text-left hover:bg-secondary/30 transition-colors flex items-center gap-2"
            @click="exportChatJson"
          >
            <Download class="w-3.5 h-3.5" />
            {{ t('chatView.exportJson') }}
          </button>
        </div>
      </div>

      <div class="w-6 h-px bg-border/50 my-1 shrink-0"></div>

      <!-- Input position toggle -->
      <button
        class="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-secondary/50 transition-colors shrink-0"
        :title="inputPosition === 'top' ? 'Move input to bottom' : 'Move input to top'"
        @click="toggleInputPosition"
      >
        <ArrowDownToLine v-if="inputPosition === 'top'" class="w-4 h-4" />
        <ArrowUpToLine v-else class="w-4 h-4" />
      </button>

      <!-- Voice mode toggle (non-CC) -->
      <button
        v-if="!cc.isActive.value"
        :class="[
          'w-8 h-8 rounded-lg flex items-center justify-center transition-colors shrink-0',
          voiceMode ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:bg-secondary/50'
        ]"
        :title="voiceMode ? 'Voice mode ON' : 'Voice mode OFF'"
        @click="voiceMode = !voiceMode"
      >
        <Volume2 v-if="voiceMode" class="w-4 h-4" />
        <VolumeX v-else class="w-4 h-4" />
      </button>

      <!-- Branch tree toggle (non-CC) -->
      <button
        v-if="!cc.isActive.value"
        :class="[
          'w-8 h-8 rounded-lg flex items-center justify-center transition-colors shrink-0',
          showBranchTree ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:bg-secondary/50'
        ]"
        :title="t('chatView.branchTree')"
        @click="showBranchTree = !showBranchTree"
      >
        <GitBranch class="w-4 h-4" />
      </button>

      <!-- CC: Working directory dropdown -->
      <div v-if="cc.isActive.value" class="relative shrink-0">
        <button
          :class="[
            'w-8 h-8 rounded-lg flex items-center justify-center transition-colors',
            cc.workingDir.value !== '/opt/ai-secretary' ? 'bg-green-600/20 text-green-400' : 'text-muted-foreground hover:bg-secondary/50'
          ]"
          :title="t('chatView.claudeCode.workDir') + ': ' + cc.workingDir.value"
          @click="showCcDirMenu = !showCcDirMenu"
        >
          <FolderOpen class="w-4 h-4" />
        </button>
        <div
          v-if="showCcDirMenu"
          class="absolute left-full ml-2 top-0 zen-glass rounded-xl shadow-2xl py-1 z-50 min-w-[260px] animate-scale-in"
          @click.stop
        >
          <button
            v-for="proj in ccProjects"
            :key="proj.id ?? proj.path"
            :class="[
              'flex items-center gap-2 w-full px-3 py-1.5 text-sm transition-colors text-left group',
              cc.workingDir.value === proj.path && cc.projectId.value === proj.id ? 'bg-green-600/20 text-green-400' : 'hover:bg-secondary/30'
            ]"
            @click="proj.builtin ? selectCcDir(proj.path) : selectProject(proj)"
          >
            <Server v-if="proj.type === 'ssh'" class="w-3.5 h-3.5 shrink-0 text-blue-400" />
            <FolderOpen v-else class="w-3.5 h-3.5 shrink-0" />
            <span class="font-mono text-xs truncate">{{ proj.name }}</span>
            <span v-if="proj.type === 'ssh'" class="text-[10px] px-1 rounded bg-blue-500/20 text-blue-400">SSH</span>
            <Check v-if="cc.workingDir.value === proj.path && cc.projectId.value === proj.id" class="w-3.5 h-3.5 ml-auto text-green-400" />
            <button
              v-if="proj.id && !proj.builtin"
              class="ml-auto p-0.5 rounded hover:bg-red-500/20 text-muted-foreground hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
              title="Delete project"
              @click.stop="deleteCcProject(proj.id)"
            >
              <Trash2 class="w-3 h-3" />
            </button>
          </button>
          <!-- Add project inline form -->
          <div class="border-t border-border mt-1 pt-1 px-2">
            <button
              v-if="!showCcAddProject"
              class="flex items-center gap-1.5 w-full px-1 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              @click.stop="showCcAddProject = true"
            >
              <Plus class="w-3 h-3" /> Add project
            </button>
            <div v-else class="space-y-1.5 py-1" @click.stop>
              <input v-model="ccNewProject.name" placeholder="Name" class="w-full text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary" />
              <input v-model="ccNewProject.path" placeholder="/path/to/project" class="w-full text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
              <div class="flex gap-1">
                <button
                  :class="['flex-1 text-xs px-2 py-0.5 rounded transition-colors', ccNewProject.type === 'local' ? 'bg-green-600/20 text-green-400' : 'bg-secondary text-muted-foreground']"
                  @click.stop="ccNewProject.type = 'local'"
                >Local</button>
                <button
                  :class="['flex-1 text-xs px-2 py-0.5 rounded transition-colors', ccNewProject.type === 'ssh' ? 'bg-blue-600/20 text-blue-400' : 'bg-secondary text-muted-foreground']"
                  @click.stop="ccNewProject.type = 'ssh'"
                >SSH</button>
              </div>
              <template v-if="ccNewProject.type === 'ssh'">
                <input v-model="ccNewProject.ssh_host" placeholder="Host (e.g. 192.168.1.10)" class="w-full text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
                <div class="flex gap-1">
                  <input v-model="ccNewProject.ssh_user" placeholder="User" class="flex-1 text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
                  <input v-model.number="ccNewProject.ssh_port" placeholder="Port" type="number" class="w-16 text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
                </div>
                <input v-model="ccNewProject.ssh_key_path" placeholder="SSH key path (optional)" class="w-full text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
              </template>
              <div class="flex gap-1">
                <button class="flex-1 text-xs px-2 py-1 rounded bg-green-600/20 text-green-400 hover:bg-green-600/30 transition-colors" @click.stop="addCcProject">Save</button>
                <button class="flex-1 text-xs px-2 py-1 rounded bg-secondary text-muted-foreground hover:bg-secondary/80 transition-colors" @click.stop="showCcAddProject = false; ccNewProject = { name: '', path: '', type: 'local' }">Cancel</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- CC: Context files dropdown -->
      <div v-if="cc.isActive.value && contextFiles.length > 0" class="relative shrink-0">
        <button
          :class="[
            'w-8 h-8 rounded-lg flex items-center justify-center transition-colors',
            cc.pendingContextFiles.value.length > 0 ? 'bg-green-600/20 text-green-400' : 'text-muted-foreground hover:bg-secondary/50'
          ]"
          :title="t('chatView.claudeCode.attachFiles')"
          @click="showCcFilesMenu = !showCcFilesMenu"
        >
          <Paperclip class="w-4 h-4" />
          <span
            v-if="cc.pendingContextFiles.value.length > 0"
            class="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 text-[9px] font-bold rounded-full bg-green-600 text-white flex items-center justify-center border border-background"
          >{{ cc.pendingContextFiles.value.length }}</span>
        </button>
        <div
          v-if="showCcFilesMenu"
          class="absolute left-full ml-2 top-0 zen-glass rounded-xl shadow-2xl py-1 z-50 min-w-[200px] max-w-[300px] animate-scale-in"
          @click.stop
        >
          <label
            v-for="file in contextFiles"
            :key="file.name"
            class="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-secondary/30 transition-colors cursor-pointer"
          >
            <input
              type="checkbox"
              :checked="isCcFileSelected(file.name)"
              class="rounded border-border w-3.5 h-3.5 accent-green-600"
              @change="toggleCcContextFile(file)"
            />
            <span class="truncate text-xs">{{ file.name }}</span>
          </label>
        </div>
      </div>

      <div class="w-6 h-px bg-border/50 my-1 shrink-0"></div>

      <!-- Settings (opens full side panel) -->
      <button
        v-if="!isReadOnly"
        :class="[
          'w-8 h-8 rounded-lg flex items-center justify-center transition-colors shrink-0',
          showSettings ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:bg-secondary/50'
        ]"
        :title="t('chatView.zenSettings')"
        @click="showSettings = !showSettings"
      >
        <Settings2 class="w-4 h-4" />
      </button>

      <!-- Spacer pushes bottom items down -->
      <div class="flex-1"></div>

      <!-- New CC session -->
      <button
        v-if="!isReadOnly && cc.isActive.value"
        class="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-secondary/50 transition-colors shrink-0"
        :title="t('chatView.claudeCode.newSession')"
        @click="cc.newSession()"
      >
        <Plus class="w-4 h-4" />
      </button>

      <!-- Delete chat / Stop CC -->
      <button
        v-if="cc.isActive.value || isSessionOwner"
        class="w-8 h-8 rounded-lg flex items-center justify-center text-red-500 hover:bg-red-500/20 transition-colors shrink-0"
        :title="cc.isActive.value ? t('chatView.claudeCode.disable') : 'Delete chat'"
        @click="cc.isActive.value ? toggleCcMode() : deleteCurrentSession()"
      >
        <Trash2 class="w-4 h-4" />
      </button>

      <div class="w-6 h-px bg-border/50 my-1 shrink-0"></div>

      <!-- Exit fullscreen -->
      <button
        class="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-secondary/50 hover:text-foreground transition-colors shrink-0"
        :title="t('chatView.exitZenMode')"
        @click="fullscreenStore.exit()"
      >
        <Minimize2 class="w-4 h-4" />
      </button>
    </div>

    <!-- Main Chat Area -->
    <div class="flex-1 flex flex-col min-w-0">

      <!-- Chat Header (hidden in zen mode) -->
      <div v-if="currentSession && !fullscreenStore.isFullscreen" class="p-2 sm:p-4 border-b border-border flex items-center justify-between gap-2 bg-card">
        <div class="flex-1 min-w-0">
          <template v-if="editingHeaderTitle">
            <input
              v-model="headerTitleValue"
              class="header-rename-input w-full font-semibold bg-background border border-border rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-primary"
              @keydown.enter="saveHeaderRename"
              @keydown.escape="cancelHeaderRename"
              @blur="saveHeaderRename"
              @click.stop
            />
          </template>
          <template v-else>
            <h2
              class="font-semibold truncate cursor-pointer group/title flex items-center gap-1.5 hover:text-primary transition-colors"
              @click="startHeaderRename"
            >
              {{ currentSession.title }}
              <Edit3 class="w-3.5 h-3.5 opacity-0 group-hover/title:opacity-50 transition-opacity shrink-0" />
            </h2>
          </template>
          <div class="hidden sm:flex items-center gap-3 text-xs text-muted-foreground">
            <span>
              {{ messages.length }} messages
              <span v-if="currentSession.system_prompt" class="ml-1 text-primary">(custom prompt)</span>
            </span>
            <template v-if="tokenUsage">
              <span class="flex items-center gap-1.5">
                {{ formatTokens(tokenUsage.tokens) }} / {{ formatTokens(tokenUsage.context_window) }}
                <span class="inline-flex w-16 h-1.5 bg-secondary rounded-full overflow-hidden">
                  <span
                    :class="[tokenBarColor(tokenUsage.percent), 'h-full rounded-full transition-all']"
                    :style="{ width: Math.min(tokenUsage.percent, 100) + '%' }"
                  />
                </span>
                <span v-if="tokenUsage.percent >= 90" class="text-red-500 font-medium">
                  {{ t('chatView.tokenWarning') }}
                </span>
              </span>
            </template>
          </div>
        </div>
        <div class="flex items-center flex-wrap gap-1 sm:gap-2 shrink-0">
          <!-- Claude Code toggle (restricted users) -->
          <button
            v-if="['shaerware', 'ivan'].includes(authStore.user?.username ?? '')"
            :class="[
              'p-2 rounded-lg border transition-colors',
              cc.isActive.value ? 'border-green-600 bg-green-600 text-white' : 'border-border text-muted-foreground hover:bg-secondary/50'
            ]"
            :title="cc.isActive.value ? t('chatView.claudeCode.disable') : t('chatView.claudeCode.enable')"
            @click="toggleCcMode()"
          >
            <Terminal class="w-4 h-4" />
          </button>
          <!-- LLM provider selector (hidden in Claude Code mode) -->
          <div v-if="!cc.isActive.value" class="flex items-center gap-1">
            <Brain class="w-4 h-4 text-muted-foreground" />
            <select
              v-model="selectedLlmBackend"
              class="px-2 py-1 text-sm bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary border-none cursor-pointer"
              :title="t('chat.selectLlm')"
            >
              <option value="">{{ t('chat.defaultLlm') }}</option>
              <option v-for="option in availableLlmOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </div>
          <!-- RAG collections dropdown -->
          <div v-if="!cc.isActive.value && knowledgeCollections.length" class="relative">
            <button
              :class="[
                'p-2 rounded-lg transition-colors',
                selectedCollectionIds.length > 0 ? 'bg-primary text-primary-foreground' : 'hover:bg-secondary'
              ]"
              :title="t('chatView.knowledgeBase')"
              @click="showRagMenu = !showRagMenu"
            >
              <BookOpen class="w-4 h-4" />
              <span
                v-if="selectedCollectionIds.length"
                class="absolute -top-1 -right-1 w-4 h-4 text-[10px] font-bold rounded-full bg-primary text-primary-foreground flex items-center justify-center border border-background"
              >{{ selectedCollectionIds.length }}</span>
            </button>
            <div
              v-if="showRagMenu"
              class="absolute right-0 top-full mt-1 bg-card border border-border rounded-lg shadow-lg py-1 z-50 min-w-[200px]"
            >
              <label
                v-for="col in knowledgeCollections"
                :key="col.id"
                class="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-secondary transition-colors cursor-pointer"
              >
                <input v-model="selectedCollectionIds" type="checkbox" :value="col.id" class="rounded border-border w-3.5 h-3.5" />
                <span>{{ col.name }}</span>
              </label>
            </div>
          </div>
          <!-- Share button (owner/admin only) -->
          <div v-if="!cc.isActive.value && isSessionOwner && !isSharedWithMe" class="relative">
            <button
              class="p-2 rounded-lg hover:bg-secondary transition-colors"
              :title="t('chatView.shareChat')"
              @click="showShareDialog = true"
            >
              <Share2 class="w-4 h-4" />
              <span
                v-if="(currentSession?.share_count ?? 0) > 0"
                class="absolute -top-1 -right-1 w-4 h-4 text-[10px] font-bold rounded-full bg-green-500 text-white flex items-center justify-center border border-background"
              >{{ currentSession!.share_count }}</span>
            </button>
          </div>
          <!-- Fork button (read-only shared sessions) -->
          <button
            v-if="!cc.isActive.value && isReadOnly"
            :disabled="forkSessionMutation.isPending.value"
            class="p-2 rounded-lg hover:bg-secondary transition-colors text-blue-400"
            :title="t('chatView.forkChat')"
            @click="currentSessionId && forkSessionMutation.mutate(currentSessionId)"
          >
            <Loader2 v-if="forkSessionMutation.isPending.value" class="w-4 h-4 animate-spin" />
            <GitFork v-else class="w-4 h-4" />
          </button>
          <!-- Export chat dropdown (hidden on small screens) -->
          <div v-if="!cc.isActive.value" class="relative hidden sm:block">
            <button
              class="p-2 rounded-lg hover:bg-secondary transition-colors"
              :title="t('chatView.exportChat')"
              @click="showExportMenu = !showExportMenu"
            >
              <Download class="w-4 h-4" />
            </button>
            <div
              v-if="showExportMenu"
              class="absolute right-0 top-full mt-1 bg-card border border-border rounded-lg shadow-lg py-1 z-50 min-w-[160px]"
            >
              <button
                class="w-full px-3 py-1.5 text-sm text-left hover:bg-secondary transition-colors flex items-center gap-2"
                @click="copyChatToClipboard"
              >
                <Copy class="w-3.5 h-3.5" />
                {{ t('chatView.copyChat') }}
              </button>
              <button
                class="w-full px-3 py-1.5 text-sm text-left hover:bg-secondary transition-colors flex items-center gap-2"
                @click="exportChatMarkdown"
              >
                <FileText class="w-3.5 h-3.5" />
                {{ t('chatView.exportMarkdown') }}
              </button>
              <button
                class="w-full px-3 py-1.5 text-sm text-left hover:bg-secondary transition-colors flex items-center gap-2"
                @click="exportChatJson"
              >
                <Download class="w-3.5 h-3.5" />
                {{ t('chatView.exportJson') }}
              </button>
            </div>
          </div>
          <!-- Input position toggle (hidden on small screens) -->
          <button
            class="hidden sm:inline-flex p-2 rounded-lg hover:bg-secondary transition-colors"
            :title="inputPosition === 'top' ? 'Move input to bottom' : 'Move input to top'"
            @click="toggleInputPosition"
          >
            <ArrowDownToLine v-if="inputPosition === 'top'" class="w-4 h-4" />
            <ArrowUpToLine v-else class="w-4 h-4" />
          </button>
          <!-- Voice mode toggle -->
          <button
            v-if="!cc.isActive.value"
            :class="[
              'p-2 rounded-lg transition-colors',
              voiceMode ? 'bg-primary text-primary-foreground' : 'hover:bg-secondary'
            ]"
            :title="voiceMode ? 'Voice mode ON (click to disable)' : 'Voice mode OFF (click to enable)'"
            @click="voiceMode = !voiceMode"
          >
            <Volume2 v-if="voiceMode" class="w-4 h-4" />
            <VolumeX v-else class="w-4 h-4" />
          </button>
          <!-- Branch tree toggle -->
          <button
            v-if="!cc.isActive.value"
            :class="[
              'p-2 rounded-lg transition-colors',
              showBranchTree ? 'bg-primary text-primary-foreground' : 'hover:bg-secondary'
            ]"
            :title="t('chatView.branchTree')"
            @click="showBranchTree = !showBranchTree"
          >
            <GitBranch class="w-4 h-4" />
          </button>
          <button
            v-if="!cc.isActive.value && !isReadOnly"
            :class="[
              'p-2 rounded-lg transition-colors',
              showSettings ? 'bg-primary text-primary-foreground' : 'hover:bg-secondary'
            ]"
            title="Chat settings"
            @click="showSettings = !showSettings"
          >
            <Settings2 class="w-4 h-4" />
          </button>
          <!-- CC: Working directory dropdown -->
          <div v-if="cc.isActive.value" class="relative">
            <button
              :class="[
                'p-2 rounded-lg transition-colors',
                cc.workingDir.value !== '/opt/ai-secretary' ? 'bg-green-600/20 text-green-400' : 'hover:bg-secondary text-muted-foreground'
              ]"
              :title="t('chatView.claudeCode.workDir') + ': ' + cc.workingDir.value"
              @click="showCcDirMenu = !showCcDirMenu"
            >
              <FolderOpen class="w-4 h-4" />
            </button>
            <div
              v-if="showCcDirMenu"
              class="absolute right-0 top-full mt-1 bg-card border border-border rounded-lg shadow-lg py-1 z-50 min-w-[260px]"
              @click.stop
            >
              <button
                v-for="proj in ccProjects"
                :key="proj.id ?? proj.path"
                :class="[
                  'flex items-center gap-2 w-full px-3 py-1.5 text-sm transition-colors text-left group',
                  cc.workingDir.value === proj.path && cc.projectId.value === proj.id ? 'bg-green-600/20 text-green-400' : 'hover:bg-secondary text-foreground'
                ]"
                @click="proj.builtin ? selectCcDir(proj.path) : selectProject(proj)"
              >
                <Server v-if="proj.type === 'ssh'" class="w-3.5 h-3.5 shrink-0 text-blue-400" />
                <FolderOpen v-else class="w-3.5 h-3.5 shrink-0" />
                <span class="font-mono text-xs truncate">{{ proj.name }}</span>
                <span v-if="proj.type === 'ssh'" class="text-[10px] px-1 rounded bg-blue-500/20 text-blue-400">SSH</span>
                <Check v-if="cc.workingDir.value === proj.path && cc.projectId.value === proj.id" class="w-3.5 h-3.5 ml-auto text-green-400" />
                <button
                  v-if="proj.id && !proj.builtin"
                  class="ml-auto p-0.5 rounded hover:bg-red-500/20 text-muted-foreground hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Delete project"
                  @click.stop="deleteCcProject(proj.id)"
                >
                  <Trash2 class="w-3 h-3" />
                </button>
              </button>
              <!-- Add project inline form -->
              <div class="border-t border-border mt-1 pt-1 px-2">
                <button
                  v-if="!showCcAddProject"
                  class="flex items-center gap-1.5 w-full px-1 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  @click.stop="showCcAddProject = true"
                >
                  <Plus class="w-3 h-3" /> Add project
                </button>
                <div v-else class="space-y-1.5 py-1" @click.stop>
                  <input v-model="ccNewProject.name" placeholder="Name" class="w-full text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary" />
                  <input v-model="ccNewProject.path" placeholder="/path/to/project" class="w-full text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
                  <div class="flex gap-1">
                    <button
                      :class="['flex-1 text-xs px-2 py-0.5 rounded transition-colors', ccNewProject.type === 'local' ? 'bg-green-600/20 text-green-400' : 'bg-secondary text-muted-foreground']"
                      @click.stop="ccNewProject.type = 'local'"
                    >Local</button>
                    <button
                      :class="['flex-1 text-xs px-2 py-0.5 rounded transition-colors', ccNewProject.type === 'ssh' ? 'bg-blue-600/20 text-blue-400' : 'bg-secondary text-muted-foreground']"
                      @click.stop="ccNewProject.type = 'ssh'"
                    >SSH</button>
                  </div>
                  <template v-if="ccNewProject.type === 'ssh'">
                    <input v-model="ccNewProject.ssh_host" placeholder="Host (e.g. 192.168.1.10)" class="w-full text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
                    <div class="flex gap-1">
                      <input v-model="ccNewProject.ssh_user" placeholder="User" class="flex-1 text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
                      <input v-model.number="ccNewProject.ssh_port" placeholder="Port" type="number" class="w-16 text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
                    </div>
                    <input v-model="ccNewProject.ssh_key_path" placeholder="SSH key path (optional)" class="w-full text-xs px-2 py-1 rounded bg-secondary border-none focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
                  </template>
                  <div class="flex gap-1">
                    <button class="flex-1 text-xs px-2 py-1 rounded bg-green-600/20 text-green-400 hover:bg-green-600/30 transition-colors" @click.stop="addCcProject">Save</button>
                    <button class="flex-1 text-xs px-2 py-1 rounded bg-secondary text-muted-foreground hover:bg-secondary/80 transition-colors" @click.stop="showCcAddProject = false; ccNewProject = { name: '', path: '', type: 'local' }">Cancel</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <!-- CC: Context files from chat dropdown -->
          <div v-if="cc.isActive.value && contextFiles.length > 0" class="relative">
            <button
              :class="[
                'p-2 rounded-lg transition-colors',
                cc.pendingContextFiles.value.length > 0 ? 'bg-green-600/20 text-green-400' : 'hover:bg-secondary text-muted-foreground'
              ]"
              :title="t('chatView.claudeCode.attachFiles')"
              @click="showCcFilesMenu = !showCcFilesMenu"
            >
              <Paperclip class="w-4 h-4" />
              <span
                v-if="cc.pendingContextFiles.value.length > 0"
                class="absolute -top-1 -right-1 w-4 h-4 text-[10px] font-bold rounded-full bg-green-600 text-white flex items-center justify-center border border-background"
              >{{ cc.pendingContextFiles.value.length }}</span>
            </button>
            <div
              v-if="showCcFilesMenu"
              class="absolute right-0 top-full mt-1 bg-card border border-border rounded-lg shadow-lg py-1 z-50 min-w-[200px] max-w-[300px]"
            >
              <label
                v-for="file in contextFiles"
                :key="file.name"
                class="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-secondary transition-colors cursor-pointer"
              >
                <input
                  type="checkbox"
                  :checked="isCcFileSelected(file.name)"
                  class="rounded border-border w-3.5 h-3.5 accent-green-600"
                  @change="toggleCcContextFile(file)"
                />
                <span class="truncate text-xs">{{ file.name }}</span>
              </label>
            </div>
          </div>
          <!-- CC: Kanban task link -->
          <div v-if="cc.isActive.value" class="relative">
            <button
              :class="[
                'p-2 rounded-lg transition-colors',
                cc.kanbanTaskId.value ? 'bg-green-600/20 text-green-400' : 'hover:bg-secondary text-muted-foreground'
              ]"
              title="Link to Kanban task"
              @click="openCcKanbanMenu()"
            >
              <ListChecks class="w-4 h-4" />
            </button>
            <div
              v-if="showCcKanbanMenu"
              class="absolute right-0 top-full mt-1 bg-card border border-border rounded-lg shadow-lg py-1 z-50 min-w-[220px] max-h-[280px] overflow-y-auto"
              @click.stop
            >
              <button
                v-if="cc.kanbanTaskId.value"
                class="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10 transition-colors"
                @click="unlinkCcKanbanTask()"
              >
                <X class="w-3 h-3" /> Unlink task
              </button>
              <div v-if="!ccKanbanTasks.length" class="px-3 py-2 text-xs text-muted-foreground">No tasks</div>
              <button
                v-for="task in ccKanbanTasks"
                :key="task.id"
                :class="[
                  'flex items-center gap-2 w-full px-3 py-1.5 text-xs transition-colors text-left',
                  cc.kanbanTaskId.value === task.id ? 'bg-green-600/20 text-green-400' : 'hover:bg-secondary'
                ]"
                @click="linkCcToKanbanTask(task)"
              >
                <span class="truncate">{{ task.title }}</span>
                <Check v-if="cc.kanbanTaskId.value === task.id" class="w-3 h-3 ml-auto shrink-0 text-green-400" />
              </button>
            </div>
          </div>
          <!-- New CC session -->
          <button
            v-if="!isReadOnly && cc.isActive.value"
            class="p-2 rounded-lg hover:bg-secondary transition-colors"
            :title="t('chatView.claudeCode.newSession')"
            @click="cc.newSession()"
          >
            <Plus class="w-4 h-4" />
          </button>
          <!-- Delete chat / Stop CC mode -->
          <button
            v-if="cc.isActive.value || isSessionOwner"
            class="p-2 rounded-lg text-red-500 hover:bg-red-500/20 transition-colors"
            :title="cc.isActive.value ? t('chatView.claudeCode.disable') : 'Delete chat'"
            @click="cc.isActive.value ? toggleCcMode() : deleteCurrentSession()"
          >
            <Trash2 class="w-4 h-4" />
          </button>
          <!-- Zen (fullscreen) mode toggle -->
          <button
            class="p-2 rounded-lg hover:bg-secondary transition-colors"
            :title="t('chatView.zenMode')"
            @click="fullscreenStore.enter()"
          >
            <Maximize2 class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- Read-only banner -->
      <div
        v-if="currentSession && isReadOnly"
        class="px-4 py-2 bg-blue-950/50 border-b border-blue-900/50 text-sm text-blue-300 flex items-center gap-2"
      >
        <Users class="w-4 h-4" />
        {{ t('chatView.readOnlyHint') }}
      </div>

      <!-- Input Area: Claude Code mode -->
      <div
        v-if="cc.isActive.value"
        :class="[
          'relative p-4 shrink-0',
          fullscreenStore.isFullscreen ? 'zen-glass' : 'bg-card',
          inputPosition === 'bottom' ? 'border-t border-border order-last' + (fullscreenStore.isFullscreen ? '' : ' pb-24') : 'border-b border-border'
        ]"
      >
        <!-- CC status bar -->
        <div v-if="cc.isConnected.value" class="flex items-center gap-2 mb-2 text-xs text-green-500">
          <span class="w-2 h-2 bg-green-500 rounded-full"></span>
          {{ t('chatView.claudeCode.connected') }}
          <span v-if="cc.currentModel.value" class="text-muted-foreground ml-1">· {{ cc.currentModel.value }}</span>
        </div>
        <div v-if="cc.error.value" class="mb-2 text-xs text-red-500">{{ cc.error.value }}</div>
        <!-- Pasted blocks chips -->
        <div v-if="pastedBlocks.length" class="flex flex-wrap gap-2 mb-2">
          <div
            v-for="block in pastedBlocks"
            :key="block.id"
            class="flex items-center gap-1.5 px-2.5 py-1.5 bg-secondary rounded-lg border border-border text-xs"
          >
            <FileText class="w-3.5 h-3.5 text-green-500 shrink-0" />
            <span class="font-medium text-green-400">{{ block.languageLabel }}</span>
            <span class="text-muted-foreground">{{ t('chatView.pastedLines', { count: block.lineCount }) }}</span>
            <button
              class="ml-1 p-0.5 rounded hover:bg-destructive/20 text-muted-foreground hover:text-destructive transition-colors"
              :title="t('chatView.removePasted')"
              @click="removePastedBlock(block.id)"
            >
              <X class="w-3 h-3" />
            </button>
          </div>
        </div>
        <div class="flex gap-3 items-end">
          <textarea
            ref="messageInputRef"
            v-model="inputMessage"
            :placeholder="t('chatView.claudeCode.placeholder')"
            rows="1"
            class="flex-1 p-3 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 resize-none font-mono text-sm max-h-[288px] overflow-y-auto"
            :disabled="cc.isProcessing.value"
            @keydown.enter.exact.prevent="ccSendMessage"
            @keydown.ctrl.enter.prevent="ccSendMessage"
            @input="onInputAutoResize"
            @paste="onPaste"
          />
          <!-- Abort button (while processing) -->
          <button
            v-if="cc.isProcessing.value"
            class="p-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            :title="t('chatView.claudeCode.abort')"
            @click="cc.abort()"
          >
            <StopCircle class="w-5 h-5" />
          </button>
          <!-- Send button -->
          <button
            v-else
            :disabled="(!inputMessage.trim() && !pastedBlocks.length) || !cc.isConnected.value"
            class="p-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
            @click="ccSendMessage"
          >
            <Send class="w-5 h-5" />
          </button>
        </div>
        <!-- New branch button (yellow, pinned to right edge) -->
        <button
          v-if="currentSessionId"
          :disabled="newBranchMutation.isPending.value"
          class="absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-lg bg-amber-500 hover:bg-amber-600 text-white transition-colors disabled:opacity-50"
          :title="t('chatView.newBranch')"
          @click="startNewBranchAndShowTree"
        >
          <Plus class="w-5 h-5" />
        </button>
      </div>

      <!-- Input Area: Normal chat mode -->
      <div
        v-else-if="currentSession && !isReadOnly"
        :class="[
          'relative p-4 shrink-0',
          fullscreenStore.isFullscreen ? 'zen-glass' : 'bg-card',
          inputPosition === 'bottom' ? 'border-t border-border order-last' + (fullscreenStore.isFullscreen ? '' : ' pb-24') : 'border-b border-border'
        ]"
      >
        <!-- Pending image previews -->
        <div v-if="pendingImages.length" class="flex flex-wrap gap-2 mb-2 max-w-3xl mx-auto">
          <div
            v-for="img in pendingImages"
            :key="img.id"
            class="relative group/img"
          >
            <img
              :src="img.thumb_url"
              :alt="img.original_name"
              class="h-20 rounded-lg border border-border object-cover"
            />
            <button
              class="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-destructive text-white flex items-center justify-center opacity-0 group-hover/img:opacity-100 transition-opacity"
              :title="t('chatView.removeImage')"
              @click="removePendingImage(img.id)"
            >
              <X class="w-3 h-3" />
            </button>
            <div v-if="img.ocr_text" class="absolute bottom-0.5 right-0.5 bg-black/60 text-white text-[10px] px-1 rounded">
              OCR
            </div>
          </div>
        </div>
        <!-- Pasted blocks chips -->
        <div v-if="pastedBlocks.length" class="flex flex-wrap gap-2 mb-2 max-w-3xl mx-auto">
          <div
            v-for="block in pastedBlocks"
            :key="block.id"
            class="flex items-center gap-1.5 px-2.5 py-1.5 bg-secondary rounded-lg border border-border text-xs"
          >
            <FileText class="w-3.5 h-3.5 text-primary shrink-0" />
            <span class="font-medium">{{ block.languageLabel }}</span>
            <span class="text-muted-foreground">{{ t('chatView.pastedLines', { count: block.lineCount }) }}</span>
            <button
              class="ml-1 p-0.5 rounded hover:bg-destructive/20 text-muted-foreground hover:text-destructive transition-colors"
              :title="t('chatView.removePasted')"
              @click="removePastedBlock(block.id)"
            >
              <X class="w-3 h-3" />
            </button>
          </div>
        </div>
        <div
          :class="[
            'flex gap-3 max-w-3xl mx-auto',
            inputPosition === 'bottom' ? 'items-stretch' : 'items-end',
          ]"
        >
          <textarea
            ref="messageInputRef"
            v-model="inputMessage"
            :placeholder="isReadOnly ? t('chatView.readOnlyHint') : 'Type a message...'"
            rows="1"
            class="flex-1 p-3 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none max-h-[288px] overflow-y-auto"
            :disabled="isStreaming || isRecording || isReadOnly"
            @keydown.enter.exact.prevent="sendMessage"
            @keydown.ctrl.enter.prevent="sendMessage"
            @input="onInputAutoResize"
            @paste="onPaste"
          />
          <!-- Image upload button -->
          <button
            :disabled="isStreaming || isUploadingImage || !currentSessionId"
            class="p-3 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors disabled:opacity-50"
            :title="t('chatView.uploadImage')"
            @click="imageInputRef?.click()"
          >
            <Loader2 v-if="isUploadingImage" class="w-5 h-5 animate-spin" />
            <ImagePlus v-else class="w-5 h-5" />
          </button>
          <input
            ref="imageInputRef"
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            multiple
            class="hidden"
            @change="handleImageUpload"
          />
          <!-- Microphone button -->
          <button
            :disabled="isStreaming || isTranscribing"
            :class="[
              'p-3 rounded-lg transition-colors',
              isRecording
                ? 'bg-red-500 text-white animate-pulse'
                : 'bg-secondary hover:bg-secondary/80'
            ]"
            :title="isRecording ? 'Stop recording' : (isTranscribing ? 'Transcribing...' : 'Start voice input')"
            @click="toggleRecording"
          >
            <Loader2 v-if="isTranscribing" class="w-5 h-5 animate-spin" />
            <MicOff v-else-if="isRecording" class="w-5 h-5" />
            <Mic v-else class="w-5 h-5" />
          </button>
          <!-- Send button -->
          <button
            :disabled="(!inputMessage.trim() && !pastedBlocks.length && !pendingImages.length) || isStreaming || isRecording"
            class="p-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
            @click="sendMessage"
          >
            <Send v-if="!isStreaming" class="w-5 h-5" />
            <Loader2 v-else class="w-5 h-5 animate-spin" />
          </button>
        </div>
        <!-- New branch button (yellow, pinned to right edge) -->
        <button
          v-if="currentSessionId"
          :disabled="newBranchMutation.isPending.value"
          class="absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-lg bg-amber-500 hover:bg-amber-600 text-white transition-colors disabled:opacity-50"
          :title="t('chatView.newBranch')"
          @click="startNewBranchAndShowTree"
        >
          <Plus class="w-5 h-5" />
        </button>
        <!-- Recording indicator -->
        <div v-if="isRecording" class="mt-2 flex items-center gap-2 text-sm text-red-500">
          <span class="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
          {{ t('chatView.recording') }}
        </div>
      </div>

      <!-- Messages + Branch Tree row -->
      <div class="flex-1 flex overflow-hidden min-h-0">
      <!-- Messages wrapper (relative for scroll buttons) -->
      <div class="relative flex-1 min-w-0">
      <!-- Messages -->
      <div
        ref="messagesContainer"
        :class="[
          'h-full overflow-y-auto overflow-x-hidden p-4 space-y-4 claude-messages-container',
          fullscreenStore.isFullscreen ? 'zen-messages' : ''
        ]"
        @click="handleMessagesClick"
      >
        <!-- Zen mode: inline session title + new chat button -->
        <div v-if="fullscreenStore.isFullscreen && currentSession" class="text-center mb-4">
          <template v-if="editingHeaderTitle">
            <input
              v-model="headerTitleValue"
              class="header-rename-input text-sm font-medium bg-transparent border-b border-border focus:outline-none focus:border-primary text-center max-w-xs mx-auto"
              @keydown.enter="saveHeaderRename"
              @keydown.escape="cancelHeaderRename"
              @blur="saveHeaderRename"
              @click.stop
            />
          </template>
          <h2
            v-else
            class="text-sm font-medium text-muted-foreground cursor-pointer hover:text-primary transition-colors inline-block"
            @click="startHeaderRename"
          >
            {{ currentSession.title }}
          </h2>
        </div>

        <!-- Claude Code mode messages -->
        <template v-if="cc.isActive.value">
          <div v-if="cc.messages.value.length === 0 && !cc.isProcessing.value" class="h-full flex items-center justify-center text-muted-foreground">
            <div class="text-center">
              <Terminal class="w-12 h-12 mx-auto mb-4 opacity-50 text-green-500" />
              <p class="text-lg font-medium text-green-500">Claude Code</p>
              <p class="text-sm mt-1">{{ t('chatView.claudeCode.welcome') }}</p>
            </div>
          </div>

          <!-- CC Messages -->
          <div
            v-for="(msg, idx) in cc.messages.value"
            :key="idx"
            class="claude-message"
          >
            <!-- Avatar (always left) -->
            <div :class="['claude-avatar', msg.role === 'user' ? 'claude-avatar-user' : '']" :style="msg.role === 'assistant' ? 'background: hsl(var(--primary) / 0.1); color: #22c55e' : ''">
              <Terminal v-if="msg.role === 'assistant'" class="w-3.5 h-3.5" />
              <span v-else>{{ authStore.user?.username?.[0]?.toUpperCase() || 'U' }}</span>
            </div>

            <div :class="['claude-message-content group', msg.role === 'user' ? 'claude-message-user' : '']">
              <!-- Thinking block (collapsible, purple) -->
              <div v-if="msg.thinking" class="mb-2 border border-purple-500/30 rounded-lg overflow-hidden">
                <button
                  class="w-full px-3 py-1.5 flex items-center gap-1.5 text-xs text-purple-400 hover:bg-purple-500/10 transition-colors"
                  @click="toggleThinkingBlock(idx)"
                >
                  <ChevronDown v-if="expandedThinking.has(idx)" class="w-3 h-3" />
                  <ChevronRight v-else class="w-3 h-3" />
                  <Brain class="w-3 h-3" />
                  {{ t('chatView.claudeCode.thinking') }}
                </button>
                <div v-if="expandedThinking.has(idx)" class="px-3 py-2 text-xs text-purple-300/80 whitespace-pre-wrap font-mono border-t border-purple-500/20">{{ msg.thinking }}</div>
              </div>

              <!-- Tool use cards -->
              <div v-if="msg.toolBlocks?.length" class="space-y-1.5 mb-2">
                <div
                  v-for="tool in msg.toolBlocks"
                  :key="tool.tool_use_id"
                  class="border border-border rounded-lg overflow-hidden text-xs"
                >
                  <button
                    class="w-full px-3 py-1.5 flex items-center gap-1.5 hover:bg-secondary/50 transition-colors"
                    @click="tool.collapsed = !tool.collapsed"
                  >
                    <ChevronDown v-if="!tool.collapsed" class="w-3 h-3" />
                    <ChevronRight v-else class="w-3 h-3" />
                    <span class="font-mono font-medium text-green-400">{{ tool.name }}</span>
                    <span v-if="tool.is_error" class="text-red-500 ml-auto">error</span>
                    <Check v-else-if="tool.result !== undefined" class="w-3 h-3 text-green-500 ml-auto" />
                    <Loader2 v-else class="w-3 h-3 animate-spin text-muted-foreground ml-auto" />
                  </button>
                  <div v-if="!tool.collapsed" class="border-t border-border">
                    <div v-if="tool.input" class="px-3 py-2 bg-secondary/30">
                      <div class="text-muted-foreground mb-0.5">Input:</div>
                      <pre class="whitespace-pre-wrap break-all font-mono text-[11px] max-h-40 overflow-y-auto">{{ tool.input }}</pre>
                    </div>
                    <div v-if="tool.result !== undefined" class="px-3 py-2" :class="tool.is_error ? 'bg-red-950/20' : 'bg-green-950/10'">
                      <div class="text-muted-foreground mb-0.5">Result:</div>
                      <pre class="whitespace-pre-wrap break-all font-mono text-[11px] max-h-60 overflow-y-auto">{{ tool.result }}</pre>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Text content -->
              <div v-if="msg.content" class="chat-markdown break-words" v-html="renderMarkdown(msg.content)"></div>
            </div>
          </div>

          <!-- CC Streaming response -->
          <div v-if="cc.isProcessing.value" class="claude-message">
            <div class="claude-avatar" style="background: hsl(var(--primary) / 0.1); color: #22c55e">
              <Terminal class="w-3.5 h-3.5" />
            </div>
            <div class="claude-message-content">
              <!-- Live thinking -->
              <div v-if="cc.thinkingText.value" class="mb-2 text-xs text-purple-400 whitespace-pre-wrap font-mono">
                <Brain class="w-3 h-3 inline mr-1" />
                {{ cc.thinkingText.value }}
              </div>

              <!-- Live tool blocks -->
              <div v-if="cc.currentToolBlocks.value.length" class="space-y-1.5 mb-2">
                <div
                  v-for="tool in cc.currentToolBlocks.value"
                  :key="tool.tool_use_id"
                  class="border border-border rounded-lg overflow-hidden text-xs"
                >
                  <div class="px-3 py-1.5 flex items-center gap-1.5">
                    <span class="font-mono font-medium text-green-400">{{ tool.name }}</span>
                    <Loader2 v-if="!tool.result" class="w-3 h-3 animate-spin text-muted-foreground ml-auto" />
                    <Check v-else class="w-3 h-3 text-green-500 ml-auto" />
                  </div>
                  <div v-if="tool.input" class="px-3 py-2 border-t border-border bg-secondary/30">
                    <pre class="whitespace-pre-wrap break-all font-mono text-[11px] max-h-40 overflow-y-auto">{{ tool.input }}</pre>
                  </div>
                  <div v-if="tool.result" class="px-3 py-2 border-t border-border" :class="tool.is_error ? 'bg-red-950/20' : 'bg-green-950/10'">
                    <pre class="whitespace-pre-wrap break-all font-mono text-[11px] max-h-40 overflow-y-auto">{{ tool.result }}</pre>
                  </div>
                </div>
              </div>

              <!-- Live text stream -->
              <div v-if="cc.streamingText.value" class="chat-markdown break-words" v-html="renderMarkdown(cc.streamingText.value)"></div>

              <!-- Waiting indicator -->
              <div v-if="!cc.streamingText.value && !cc.thinkingText.value && cc.currentToolBlocks.value.length === 0" class="flex items-center gap-1.5">
                <span class="w-2 h-2 bg-green-500/60 rounded-full animate-bounce [animation-delay:0ms]"></span>
                <span class="w-2 h-2 bg-green-500/60 rounded-full animate-bounce [animation-delay:150ms]"></span>
                <span class="w-2 h-2 bg-green-500/60 rounded-full animate-bounce [animation-delay:300ms]"></span>
              </div>
            </div>
          </div>
        </template>

        <!-- Normal chat: no session selected -->
        <template v-else-if="!currentSession">
          <div class="h-full flex items-center justify-center text-muted-foreground">
            <div class="text-center">
              <MessageSquare class="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>{{ t('chatView.selectOrCreate') }}</p>
            </div>
          </div>
        </template>

        <template v-else>
          <!-- Messages -->
          <div
            v-for="message in messages"
            :id="`msg-${message.id}`"
            :key="message.id"
            :class="['claude-message transition-shadow duration-500', message.role === 'user' ? 'claude-message-user' : '']"
          >
            <!-- Avatar (always left) -->
            <div :class="['claude-avatar', message.role === 'user' ? 'claude-avatar-user' : 'claude-avatar-assistant']">
              <Bot v-if="message.role === 'assistant'" class="w-3.5 h-3.5" />
              <span v-else>{{ authStore.user?.username?.[0]?.toUpperCase() || 'U' }}</span>
            </div>

            <!-- Message Content -->
            <div class="claude-message-content group">
              <!-- Editing mode -->
              <div v-if="editingMessageId === message.id" class="space-y-2">
                <textarea
                  v-model="editingContent"
                  data-edit-textarea
                  class="w-full min-h-[80px] p-3 bg-secondary text-foreground rounded resize-none border border-border"
                  style="height: auto; overflow-y: auto;"
                  @keydown.escape="cancelEditing"
                  @keydown.ctrl.enter.prevent="saveEdit"
                  @input="onInputAutoResize"
                />
                <div class="flex gap-2">
                  <button
                    :disabled="editMessageMutation.isPending.value"
                    class="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700"
                    @click="saveEdit"
                  >
                    <Check class="w-3 h-3 inline mr-1" />
                    Save
                  </button>
                  <button
                    class="px-3 py-1 bg-secondary text-foreground rounded text-sm hover:bg-secondary/80"
                    @click="cancelEditing"
                  >
                    <X class="w-3 h-3 inline mr-1" />
                    Cancel
                  </button>
                </div>
              </div>

              <!-- Normal mode -->
              <template v-else>
                <!-- Image attachments -->
                <div v-if="message.metadata?.images?.length" class="flex flex-wrap gap-2 mb-2">
                  <div v-for="img in message.metadata.images" :key="img.id" class="relative group/img">
                    <img
                      :src="img.thumb_url || img.url"
                      :alt="img.original_name || 'image'"
                      class="rounded-lg max-h-48 cursor-pointer hover:opacity-90 transition-opacity"
                      @click="fullscreenImage = img.url"
                    />
                    <div v-if="img.ocr_text" class="absolute bottom-1 right-1 bg-black/60 text-white text-[10px] px-1.5 py-0.5 rounded">
                      OCR
                    </div>
                  </div>
                </div>
                <div class="chat-markdown break-words" v-html="renderMarkdown(message.content, message.id)"></div>
                <div class="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                  <span>{{ formatTime(message.timestamp) }}</span>
                  <span v-if="message.edited" class="italic">(edited)</span>
                  <!-- Version navigation for messages with siblings -->
                  <template v-if="getSiblingInfo(message.id)">
                    <span class="flex items-center gap-1 ml-1">
                      <button
                        class="px-0.5 hover:text-foreground disabled:opacity-30"
                        :disabled="getSiblingInfo(message.id)!.index === 0"
                        @click="switchToSibling(getSiblingInfo(message.id)!.siblings[getSiblingInfo(message.id)!.index - 1])"
                      >&lt;</button>
                      <span>{{ getSiblingInfo(message.id)!.index + 1 }}/{{ getSiblingInfo(message.id)!.total }}</span>
                      <button
                        class="px-0.5 hover:text-foreground disabled:opacity-30"
                        :disabled="getSiblingInfo(message.id)!.index === getSiblingInfo(message.id)!.total - 1"
                        @click="switchToSibling(getSiblingInfo(message.id)!.siblings[getSiblingInfo(message.id)!.index + 1])"
                      >&gt;</button>
                    </span>
                  </template>
                </div>

                <!-- Actions — below content, in normal flow -->
                <div class="flex flex-wrap gap-1 mt-1 -mb-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <!-- TTS button for assistant messages -->
                  <button
                    v-if="message.role === 'assistant'"
                    :disabled="ttsLoading === message.id"
                    class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground"
                    :title="speakingMessageId === message.id && isSpeaking ? 'Stop' : 'Listen'"
                    @click="speakMessage(message.id, message.content)"
                  >
                    <Loader2 v-if="ttsLoading === message.id" class="w-3 h-3 animate-spin" />
                    <Square v-else-if="speakingMessageId === message.id && isSpeaking" class="w-3 h-3 text-primary" />
                    <Volume2 v-else class="w-3 h-3" />
                  </button>
                  <!-- Regenerate button for assistant messages -->
                  <button
                    v-if="message.role === 'assistant' && !isReadOnly"
                    :disabled="regenerateMutation.isPending.value"
                    class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground"
                    title="Regenerate response"
                    @click="regenerateAssistantResponse(message.id)"
                  >
                    <RefreshCw class="w-3 h-3" />
                  </button>
                  <button
                    class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground"
                    :title="t('common.copy')"
                    @click="copyToClipboard(message.content)"
                  >
                    <Copy class="w-3 h-3" />
                  </button>
                  <button
                    class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground"
                    :title="t('chatView.summarizeBranch')"
                    :disabled="summarizingMessageId !== null"
                    @click.stop="summarizeBranch(message.id)"
                  >
                    <Loader2 v-if="summarizingMessageId === message.id" class="w-3 h-3 animate-spin" />
                    <ListChecks v-else class="w-3 h-3" />
                  </button>
                  <!-- Save to context button for assistant messages -->
                  <button
                    v-if="message.role === 'assistant'"
                    class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground"
                    :title="t('chatView.saveToContext')"
                    @click="saveMessageToContext(message)"
                  >
                    <FileOutput class="w-3 h-3" />
                  </button>
                  <!-- Edit button (both user and assistant messages) -->
                  <button
                    v-if="!isReadOnly"
                    class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground"
                    :title="message.role === 'assistant' ? t('chatView.editResponse') : 'Edit'"
                    @click="startEditing(message)"
                  >
                    <Edit3 class="w-3 h-3" />
                  </button>
                  <button
                    v-if="message.role === 'user' && !isReadOnly"
                    :disabled="regenerateMutation.isPending.value"
                    class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground"
                    title="Regenerate response"
                    @click="regenerateResponse(message.id)"
                  >
                    <RefreshCw class="w-3 h-3" />
                  </button>
                  <button
                    v-if="!isReadOnly"
                    class="p-1 rounded hover:bg-secondary text-red-500"
                    title="Delete"
                    @click="deleteMessage(message.id)"
                  >
                    <Trash2 class="w-3 h-3" />
                  </button>
                </div>
              </template>
            </div>
          </div>

          <!-- Optimistic user message (shown immediately before server confirms) -->
          <div v-if="pendingUserContent" class="claude-message claude-message-user">
            <div class="claude-avatar claude-avatar-user">
              <span>{{ authStore.user?.username?.[0]?.toUpperCase() || 'U' }}</span>
            </div>
            <div class="claude-message-content">
              <div class="chat-markdown break-words" v-html="renderMarkdown(pendingUserContent)"></div>
            </div>
          </div>

          <!-- Streaming response -->
          <div v-if="isStreaming && streamingContent" class="claude-message">
            <div class="claude-avatar claude-avatar-assistant">
              <Bot class="w-3.5 h-3.5" />
            </div>
            <div class="claude-message-content">
              <div class="chat-markdown break-words" v-html="renderMarkdown(streamingContent)"></div>
              <div v-if="searchingQuery !== null" class="flex items-center gap-2 text-xs text-muted-foreground mt-2 px-1">
                <Search class="w-3 h-3 animate-pulse" />
                <span>{{ t('chatView.searchingKnowledge', { query: searchingQuery }) }}</span>
              </div>
            </div>
          </div>

          <!-- Thinking indicator (waiting for first chunk) -->
          <div v-if="isStreaming && !streamingContent" class="claude-message">
            <div class="claude-avatar claude-avatar-assistant">
              <Bot class="w-3.5 h-3.5" />
            </div>
            <div class="claude-message-content">
              <div v-if="searchingQuery !== null" class="flex items-center gap-2 text-xs text-muted-foreground px-1">
                <Search class="w-3 h-3 animate-pulse" />
                <span>{{ t('chatView.searchingKnowledge', { query: searchingQuery }) }}</span>
              </div>
              <div v-else class="flex items-center gap-1.5">
                <span class="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce [animation-delay:0ms]"></span>
                <span class="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce [animation-delay:150ms]"></span>
                <span class="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce [animation-delay:300ms]"></span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Floating scroll buttons -->
      <div
        v-if="currentSession && !cc.isActive.value"
        class="absolute right-1 sm:right-3 top-1/2 -translate-y-1/2 z-30 flex flex-col gap-1"
      >
        <button
          class="p-1.5 sm:p-2 rounded-full bg-card/80 backdrop-blur border border-border shadow-md text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          title="Scroll to top"
          @click="scrollToTop"
        >
          <ArrowUpToLine class="w-3.5 h-3.5 sm:w-4 sm:h-4" />
        </button>
        <button
          class="p-1.5 sm:p-2 rounded-full bg-card/80 backdrop-blur border border-border shadow-md text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          title="Scroll to bottom"
          @click="scrollToBottom"
        >
          <ArrowDownToLine class="w-3.5 h-3.5 sm:w-4 sm:h-4" />
        </button>
      </div>
      </div> <!-- /messages wrapper -->

      <!-- Branch Tree Panel -->
      <template v-if="showBranchTree">
        <div
          class="w-1.5 cursor-col-resize hover:bg-primary/30 active:bg-primary/50 transition-colors flex-shrink-0"
          @mousedown="startBranchResize"
          @touchstart="startBranchTouchResize"
        />
        <BranchTree
          :branches="branchTree"
          :session-id="currentSessionId || ''"
          :style="{ width: branchTreeWidth + 'px' }"
          @switch="onBranchSwitch"
          @scroll-to="onBranchScrollTo"
          @new-branch="startNewBranch"
          @close="showBranchTree = false"
          @delete-node="deleteBranchNode"
          @delete-branches="deleteBranches"
        />
      </template>

      <!-- Artifact Panel -->
      <template v-if="showArtifact && activeArtifact">
        <div
          class="hidden md:block w-1.5 cursor-col-resize hover:bg-primary/30 active:bg-primary/50 transition-colors flex-shrink-0"
          @mousedown="startArtifactResize"
          @touchstart="startArtifactTouchResize"
        />
        <!-- Mobile backdrop -->
        <div
          class="md:hidden fixed inset-0 bg-black/50 z-40"
          @click="closeArtifact"
        />
        <ArtifactPanel
          :artifact="activeArtifact"
          class="artifact-panel fixed inset-0 z-50 md:relative md:inset-auto md:z-0 flex-shrink-0 overflow-hidden"
          :style="{ '--artifact-w': artifactWidth + 'px' }"
          @close="closeArtifact"
        />
      </template>

      <!-- Settings Panel (slide-out right / fullscreen on mobile) -->
      <div
        v-if="showSettings"
        class="hidden md:block w-1.5 cursor-col-resize hover:bg-primary/30 active:bg-primary/50 transition-colors flex-shrink-0"
        @mousedown="startSettingsResize"
        @touchstart="startSettingsTouchResize"
      />
      <!-- Mobile backdrop -->
      <div
        v-if="showSettings"
        class="md:hidden fixed inset-0 bg-black/50 z-40"
        @click="showSettings = false"
      />
      <div
        v-if="showSettings"
        class="fixed inset-0 z-50 md:relative md:inset-auto md:z-0 border-l border-border bg-card flex flex-col flex-shrink-0 overflow-hidden settings-panel"
        :style="{ '--settings-w': settingsWidth + 'px' }"
      >
        <!-- Panel header -->
        <div class="p-3 border-b border-border flex items-center justify-between">
          <h3 class="text-xs font-semibold text-muted-foreground uppercase flex items-center gap-1.5">
            <Settings2 class="w-3.5 h-3.5" />
            {{ t('chatView.chatSettings') }}
          </h3>
          <button
            class="p-1 rounded hover:bg-secondary text-muted-foreground transition-colors"
            @click="showSettings = false"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>

        <!-- Tabs -->
        <div class="flex gap-2 px-3 pt-2 border-b border-border">
          <button
            :class="[
              'px-3 py-1.5 text-xs font-medium transition-colors border-b-2 -mb-px',
              settingsTab === 'session'
                ? 'border-primary text-primary'
                : 'border-transparent hover:text-foreground text-muted-foreground'
            ]"
            @click="settingsTab = 'session'"
          >
            <FileText class="w-3.5 h-3.5 inline mr-1" />
            {{ t('chatView.sessionPrompt') }}
          </button>
          <button
            :class="[
              'px-3 py-1.5 text-xs font-medium transition-colors border-b-2 -mb-px',
              settingsTab === 'files'
                ? 'border-primary text-primary'
                : 'border-transparent hover:text-foreground text-muted-foreground'
            ]"
            @click="settingsTab = 'files'"
          >
            <Paperclip class="w-3.5 h-3.5 inline mr-1" />
            {{ t('chatView.contextFiles') }}
            <span v-if="contextFiles.length" class="ml-1 text-[10px] bg-primary/20 px-1 rounded-full">
              {{ contextFiles.length }}
            </span>
          </button>
        </div>

        <!-- Panel content (scrollable, fills remaining height; pb-16 keeps buttons above widget icon) -->
        <div class="flex-1 overflow-y-auto p-3 pb-16 flex flex-col">
          <!-- Session Prompt Tab -->
          <div v-if="settingsTab === 'session'" class="flex flex-col flex-1 gap-3">
            <p class="text-xs text-muted-foreground">
              {{ t('chatView.promptHint') }}
            </p>

            <!-- Textarea fills remaining space -->
            <textarea
              v-model="customPrompt"
              class="flex-1 min-h-[120px] w-full p-3 bg-secondary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none text-sm font-mono"
              :placeholder="t('chatView.promptPlaceholder')"
            />

            <div class="flex justify-end gap-2">
              <button
                class="px-3 py-1.5 text-sm bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
                @click="showSettings = false"
              >
                {{ t('chatView.cancel') }}
              </button>
              <button
                :disabled="updateSessionMutation.isPending.value"
                class="px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
                @click="saveSettings"
              >
                {{ t('chatView.save') }}
              </button>
            </div>
          </div>

          <!-- Context Files Tab -->
          <div v-if="settingsTab === 'files'" class="flex flex-col flex-1 gap-3">
            <p class="text-xs text-muted-foreground">
              {{ t('chatView.contextFilesHint') }}
            </p>

            <!-- Hidden file input -->
            <input
              ref="contextFileInputRef"
              type="file"
              accept=".txt,.md,.json,.csv,.xml,.yaml,.yml,.log,.py,.js,.ts"
              multiple
              class="hidden"
              @change="handleContextFileUpload"
            />

            <!-- File list -->
            <div class="flex-1 overflow-y-auto space-y-2">
              <div v-if="contextFiles.length === 0" class="text-center py-8 text-muted-foreground text-sm">
                {{ t('chatView.noContextFiles') }}
              </div>

              <div
                v-for="(file, idx) in contextFiles"
                :key="idx"
                class="border border-border rounded-lg p-2.5 bg-secondary/30"
              >
                <!-- Editing mode for this file -->
                <template v-if="editingFileIndex === idx">
                  <input
                    v-model="editingFileName"
                    class="w-full px-2 py-1 text-xs bg-secondary rounded border border-border focus:outline-none focus:ring-1 focus:ring-primary mb-2"
                    :placeholder="t('chatView.fileName')"
                  />
                  <textarea
                    v-model="editingFileContent"
                    class="w-full min-h-[100px] p-2 text-xs bg-secondary rounded border border-border focus:outline-none focus:ring-1 focus:ring-primary resize-y font-mono"
                    :placeholder="t('chatView.fileContent')"
                  />
                  <div class="flex justify-end gap-1.5 mt-2">
                    <button
                      class="px-2 py-1 text-xs bg-secondary rounded hover:bg-secondary/80 transition-colors"
                      @click="cancelContextFileEdit"
                    >
                      {{ t('chatView.cancel') }}
                    </button>
                    <button
                      class="px-2 py-1 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors"
                      @click="saveContextFileEdit"
                    >
                      <Check class="w-3 h-3 inline mr-0.5" />
                      OK
                    </button>
                  </div>
                </template>

                <!-- View mode for this file -->
                <template v-else>
                  <div class="flex items-center justify-between mb-1">
                    <span class="text-xs font-medium flex items-center gap-1">
                      <FileText class="w-3.5 h-3.5 text-muted-foreground" />
                      {{ file.name }}
                    </span>
                    <div class="flex gap-1">
                      <button
                        class="p-1 rounded hover:bg-secondary text-muted-foreground transition-colors"
                        title="Редактировать"
                        @click="editContextFile(idx)"
                      >
                        <Edit3 class="w-3 h-3" />
                      </button>
                      <button
                        class="p-1 rounded hover:bg-red-500/10 text-muted-foreground hover:text-red-500 transition-colors"
                        title="Удалить"
                        @click="removeContextFile(idx)"
                      >
                        <X class="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                  <p class="text-xs text-muted-foreground whitespace-pre-wrap line-clamp-3 font-mono">{{ file.content.slice(0, 200) }}{{ file.content.length > 200 ? '...' : '' }}</p>
                </template>
              </div>
            </div>

            <!-- Action buttons -->
            <div class="flex gap-2">
              <button
                class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
                @click="triggerContextFileUpload"
              >
                <Paperclip class="w-3.5 h-3.5" />
                {{ t('chatView.uploadFile') }}
              </button>
              <button
                class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
                @click="addEmptyContextFile"
              >
                <Plus class="w-3.5 h-3.5" />
                {{ t('chatView.emptyFile') }}
              </button>
            </div>

            <div class="flex justify-end gap-2">
              <button
                class="px-3 py-1.5 text-sm bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
                @click="showSettings = false"
              >
                {{ t('chatView.close') }}
              </button>
              <button
                :disabled="saveContextFilesMutation.isPending.value"
                class="px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
                @click="saveContextFiles"
              >
                <Loader2 v-if="saveContextFilesMutation.isPending.value" class="w-4 h-4 inline mr-1 animate-spin" />
                {{ t('chatView.save') }}
              </button>
            </div>
          </div>
        </div>
      </div>
      </div><!-- end Messages + Branch Tree row -->
    </div>

  </div>

  <!-- Share Dialog -->
  <ChatShareDialog
    v-if="currentSessionId"
    :session-id="currentSessionId"
    :open="showShareDialog"
    @close="showShareDialog = false"
  />

  <!-- Fullscreen image viewer -->
  <div
    v-if="fullscreenImage"
    class="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center cursor-pointer"
    @click="fullscreenImage = null"
  >
    <img :src="fullscreenImage" class="max-w-[90vw] max-h-[90vh] object-contain rounded-lg" />
    <button class="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white">
      <X class="w-6 h-6" />
    </button>
  </div>
</template>

<style scoped>
@media (min-width: 768px) {
  .settings-panel {
    width: var(--settings-w);
  }
}

@media (min-width: 768px) {
  .artifact-panel {
    width: var(--artifact-w);
  }
}

/* Zen mode: centered messages (redundant with claude-messages-container but kept for specificity) */
.zen-messages {
  padding-left: 1rem;
  padding-right: 1rem;
}

/* Collapsible code blocks in user messages */
.claude-message-user :deep(.code-block-container) {
  position: relative;
  cursor: pointer;
}
.claude-message-user :deep(.code-block-container:not(.expanded)) pre {
  max-height: 200px;
  overflow: hidden;
}
.claude-message-user :deep(.code-block-container:not(.expanded)) pre::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 60px;
  background: linear-gradient(transparent, hsl(var(--secondary)));
  pointer-events: none;
}
</style>
