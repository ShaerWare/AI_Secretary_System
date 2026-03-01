import { ref } from 'vue'
import {
  createClaudeCodeWs,
  claudeCodeApi,
  type CcWsEvent,
  type CcContextFile,
  type CcSessionSummary,
} from '@/api/claudeCode'

export interface CcMessage {
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  toolBlocks?: CcToolBlock[]
  timestamp: string
}

export interface CcToolBlock {
  tool_use_id: string
  name: string
  input?: string
  result?: string
  is_error?: boolean
  collapsed: boolean
}

// ---- Global singleton state (persists across route changes) ----
const isActive = ref(false)
const isConnected = ref(false)
const isProcessing = ref(false)
const cliSessionId = ref<string | null>(null)
const dbSessionId = ref<string | null>(null)
const streamingText = ref('')
const thinkingText = ref('')
const currentToolBlocks = ref<CcToolBlock[]>([])
const messages = ref<CcMessage[]>([])
const currentModel = ref<string | null>(null)
const error = ref<string | null>(null)
const workingDir = ref('/opt/ai-secretary')
const projectId = ref<number | null>(null)
const pendingContextFiles = ref<CcContextFile[]>([])
const chatSessionId = ref<string | null>(null)
const kanbanTaskId = ref<number | null>(null)

let ws: ReturnType<typeof createClaudeCodeWs> | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempts = 0
const MAX_RECONNECT_ATTEMPTS = 5
const isDemo = import.meta.env.VITE_DEMO_MODE === 'true'

function handleEvent(event: CcWsEvent) {
  error.value = null

  switch (event.type) {
    case 'session_created':
      dbSessionId.value = event.session.id
      // Save user message immediately so it persists even if CLI hangs
      _autoSaveTranscript()
      break

    case 'session_init':
      cliSessionId.value = event.session_id
      if (event.model) currentModel.value = event.model
      isProcessing.value = true
      streamingText.value = ''
      thinkingText.value = ''
      currentToolBlocks.value = []
      break

    case 'text_delta':
      streamingText.value += event.text
      break

    case 'thinking_delta':
      thinkingText.value += event.text
      break

    case 'tool_use_start':
      currentToolBlocks.value.push({
        tool_use_id: event.tool_use_id,
        name: event.name,
        collapsed: true,
      })
      break

    case 'tool_use_input': {
      const block = currentToolBlocks.value.find(b => b.tool_use_id === event.tool_use_id)
      if (block) {
        block.input = typeof event.input === 'string'
          ? event.input
          : JSON.stringify(event.input, null, 2)
      }
      break
    }

    case 'tool_use_input_delta': {
      const lastBlock = currentToolBlocks.value[currentToolBlocks.value.length - 1]
      if (lastBlock) {
        lastBlock.input = (lastBlock.input || '') + event.partial_json
      }
      break
    }

    case 'tool_result': {
      const block = currentToolBlocks.value.find(b => b.tool_use_id === event.tool_use_id)
      if (block) {
        block.result = event.content
        block.is_error = event.is_error
      }
      // Save progress after each tool turn so partial results survive refresh
      _flushMessage()
      _autoSaveTranscript()
      break
    }

    case 'done': {
      _flushMessage()
      if (event.session_id) cliSessionId.value = event.session_id
      isProcessing.value = false
      _autoSaveTranscript()
      break
    }

    case 'error':
      error.value = event.error
      isProcessing.value = false
      if (streamingText.value || currentToolBlocks.value.length) {
        _flushMessage()
      }
      _autoSaveTranscript()
      break

    case 'aborted':
      isProcessing.value = false
      if (streamingText.value || currentToolBlocks.value.length) {
        _flushMessage()
      }
      _autoSaveTranscript()
      break
  }
}

function _flushMessage() {
  if (!streamingText.value && !thinkingText.value && currentToolBlocks.value.length === 0) return
  messages.value.push({
    role: 'assistant',
    content: streamingText.value,
    thinking: thinkingText.value || undefined,
    toolBlocks: currentToolBlocks.value.length > 0
      ? [...currentToolBlocks.value]
      : undefined,
    timestamp: new Date().toISOString(),
  })
  streamingText.value = ''
  thinkingText.value = ''
  currentToolBlocks.value = []
}

function _autoSaveTranscript() {
  if (!dbSessionId.value || messages.value.length === 0 || !ws) return
  try {
    ws.send({
      action: 'save_transcript',
      session_id: dbSessionId.value,
      transcript: JSON.stringify(messages.value),
    })
  } catch {
    // WS might be closed — ignore
  }
}

function connect() {
  if (isDemo) {
    isConnected.value = true
    return
  }
  if (ws) return
  ws = createClaudeCodeWs(handleEvent)
  ws.ws.onopen = () => {
    isConnected.value = true
    error.value = null
    reconnectAttempts = 0
  }
  const origClose = ws.ws.onclose
  ws.ws.onclose = (e) => {
    isConnected.value = false
    if (origClose) (origClose as (ev: CloseEvent) => void)(e)
    ws = null
    // Auto-reconnect if CC mode is still active and not a deliberate close
    if (isActive.value && e.code !== 1000 && e.code !== 4003) {
      _scheduleReconnect()
    }
  }
}

function _scheduleReconnect() {
  if (reconnectTimer) return
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    error.value = `Reconnect failed after ${MAX_RECONNECT_ATTEMPTS} attempts`
    return
  }
  const delay = Math.min(1000 * 2 ** reconnectAttempts, 15000)
  reconnectAttempts++
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    if (isActive.value && !ws) {
      connect()
    }
  }, delay)
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  reconnectAttempts = 0
  if (ws) {
    ws.close()
    ws = null
  }
  isConnected.value = false
  isProcessing.value = false
}

function _resetState() {
  messages.value = []
  streamingText.value = ''
  thinkingText.value = ''
  currentToolBlocks.value = []
  cliSessionId.value = null
  dbSessionId.value = null
  currentModel.value = null
  error.value = null
  projectId.value = null
  pendingContextFiles.value = []
  chatSessionId.value = null
  kanbanTaskId.value = null
}

/** Activate / deactivate Claude Code mode */
function toggle() {
  if (isActive.value) {
    // Save transcript before deactivating
    _autoSaveTranscript()
    // Deactivate: abort if running, disconnect, reset
    if (isProcessing.value && ws) {
      ws.send({ action: 'abort' })
    }
    isActive.value = false
    disconnect()
    _resetState()
  } else {
    isActive.value = true
    connect()
  }
}

/** Stop current session and start fresh (keeps CC mode active) */
function newSession() {
  _autoSaveTranscript()
  if (isProcessing.value && ws) {
    ws.send({ action: 'abort' })
  }
  _resetState()
  // Reconnect if WS dropped
  if (!ws && !isDemo) {
    connect()
  }
}

function sendMessage(prompt: string) {
  if (!prompt.trim()) return

  messages.value.push({
    role: 'user',
    content: prompt,
    timestamp: new Date().toISOString(),
  })

  isProcessing.value = true
  streamingText.value = ''
  thinkingText.value = ''
  currentToolBlocks.value = []
  error.value = null

  if (isDemo) {
    _demoSimulate()
    return
  }

  if (!ws) {
    error.value = 'Not connected'
    isProcessing.value = false
    return
  }

  if (cliSessionId.value) {
    ws.send({
      action: 'message',
      prompt,
      session_id: dbSessionId.value || undefined,
      cli_session_id: cliSessionId.value,
    })
  } else {
    // First message — include cwd/project_id, context files, and link IDs
    const startCmd: Record<string, unknown> = {
      action: 'start',
      prompt,
      cwd: workingDir.value,
    }
    if (projectId.value) {
      startCmd.project_id = projectId.value
    }
    if (chatSessionId.value) {
      startCmd.chat_session_id = chatSessionId.value
    }
    if (kanbanTaskId.value) {
      startCmd.kanban_task_id = kanbanTaskId.value
    }
    if (pendingContextFiles.value.length > 0) {
      startCmd.context_files = pendingContextFiles.value
      pendingContextFiles.value = [] // clear after sending
    }
    ws.send(startCmd as never)
  }
}

/**
 * Load a previously saved CC session by its DB id.
 * Fetches transcript from backend, populates messages, and activates CC mode.
 */
async function loadSession(sessionId: string) {
  if (isProcessing.value) return

  // Save current session before switching
  _autoSaveTranscript()
  _resetState()

  try {
    const result = await claudeCodeApi.getSessionTranscript(sessionId)
    const session = result.session

    dbSessionId.value = session.id
    cliSessionId.value = session.cli_session_id
    currentModel.value = session.model
    chatSessionId.value = session.chat_session_id
    kanbanTaskId.value = session.kanban_task_id

    // Parse saved transcript
    if (session.events_json) {
      try {
        const parsed = JSON.parse(session.events_json) as CcMessage[]
        messages.value = parsed
      } catch {
        // Corrupted transcript — start fresh
      }
    }

    // Activate CC mode + connect WS if needed
    if (!isActive.value) {
      isActive.value = true
    }
    if (!ws && !isDemo) {
      connect()
    }
  } catch {
    error.value = 'Failed to load session'
  }
}

function abort() {
  if (isDemo) {
    isProcessing.value = false
    _flushMessage()
    return
  }
  if (ws) {
    ws.send({ action: 'abort' })
  }
}

function _demoSimulate() {
  const steps = [
    { delay: 200, fn: () => handleEvent({ type: 'session_init', session_id: 'demo-session-1', model: 'claude-opus-4-6', tools: ['Bash', 'Read', 'Write'], mcp_servers: [] }) },
    { delay: 400, fn: () => handleEvent({ type: 'thinking_delta', text: 'Let me analyze this request...' }) },
    { delay: 800, fn: () => handleEvent({ type: 'text_delta', text: 'I\'ll help you with that. ' }) },
    { delay: 1000, fn: () => handleEvent({ type: 'text_delta', text: 'Let me check the relevant files.' }) },
    { delay: 1200, fn: () => handleEvent({ type: 'tool_use_start', tool_use_id: 'tool-1', name: 'Read' }) },
    { delay: 1400, fn: () => handleEvent({ type: 'tool_use_input', tool_use_id: 'tool-1', name: 'Read', input: { file_path: '/opt/ai-secretary/orchestrator.py' } }) },
    { delay: 1800, fn: () => handleEvent({ type: 'tool_result', tool_use_id: 'tool-1', content: 'File contents displayed (156 lines)', is_error: false }) },
    { delay: 2200, fn: () => handleEvent({ type: 'text_delta', text: '\n\nI\'ve reviewed the file. Everything looks good!' }) },
    { delay: 2600, fn: () => handleEvent({ type: 'done', session_id: 'demo-session-1', cost_usd: null, duration_ms: 2400, result: '' }) },
  ]

  steps.forEach(({ delay, fn }) => setTimeout(fn, delay))
}

// ---- Public composable (returns same global refs every time) ----
export function useClaudeCode() {
  return {
    isActive,
    isConnected,
    isProcessing,
    cliSessionId,
    dbSessionId,
    streamingText,
    thinkingText,
    currentToolBlocks,
    messages,
    currentModel,
    error,
    workingDir,
    projectId,
    pendingContextFiles,
    chatSessionId,
    kanbanTaskId,
    toggle,
    newSession,
    connect,
    disconnect,
    sendMessage,
    loadSession,
    abort,
  }
}
