import { ref, onUnmounted } from 'vue'
import {
  createClaudeCodeWs,
  type CcWsEvent,
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

export function useClaudeCode() {
  // State
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

  // WebSocket connection
  let ws: ReturnType<typeof createClaudeCodeWs> | null = null

  const isDemo = import.meta.env.VITE_DEMO_MODE === 'true'

  function handleEvent(event: CcWsEvent) {
    error.value = null

    switch (event.type) {
      case 'session_created':
        dbSessionId.value = event.session.id
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
        // Append to last tool block's input
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
        break
      }

      case 'done': {
        // Flush current streaming into a message
        _flushMessage()
        if (event.session_id) cliSessionId.value = event.session_id
        isProcessing.value = false
        break
      }

      case 'error':
        error.value = event.error
        isProcessing.value = false
        // Flush any partial content
        if (streamingText.value || currentToolBlocks.value.length) {
          _flushMessage()
        }
        break

      case 'aborted':
        isProcessing.value = false
        if (streamingText.value || currentToolBlocks.value.length) {
          _flushMessage()
        }
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
    }
    const origClose = ws.ws.onclose
    ws.ws.onclose = (e) => {
      isConnected.value = false
      if (origClose) (origClose as (ev: CloseEvent) => void)(e)
      ws = null
    }
  }

  function disconnect() {
    if (ws) {
      ws.close()
      ws = null
    }
    isConnected.value = false
    isProcessing.value = false
  }

  function toggle() {
    if (isActive.value) {
      isActive.value = false
      disconnect()
      // Reset state
      messages.value = []
      streamingText.value = ''
      thinkingText.value = ''
      currentToolBlocks.value = []
      cliSessionId.value = null
      dbSessionId.value = null
      currentModel.value = null
      error.value = null
    } else {
      isActive.value = true
      connect()
    }
  }

  function sendMessage(prompt: string) {
    if (!prompt.trim()) return

    // Add user message
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
      // Continue existing session
      ws.send({
        action: 'message',
        prompt,
        session_id: dbSessionId.value || undefined,
        cli_session_id: cliSessionId.value,
      })
    } else {
      // Start new session
      ws.send({ action: 'start', prompt })
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

  // Demo simulation
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

  onUnmounted(() => {
    disconnect()
  })

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
    toggle,
    connect,
    disconnect,
    sendMessage,
    abort,
  }
}
