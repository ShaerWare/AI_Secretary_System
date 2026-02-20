import { api } from './client'

// ============== Types ==============

export interface ClaudeCodeSession {
  id: string
  cli_session_id: string | null
  title: string
  owner_id: number
  status: 'active' | 'completed' | 'error' | 'aborted'
  model: string | null
  total_turns: number
  max_turns: number
  working_directory: string
  created: string
  updated: string
}

/** Events sent FROM server TO client over WebSocket */
export type CcWsEvent =
  | { type: 'session_created'; session: ClaudeCodeSession }
  | { type: 'session_init'; session_id: string; model: string; tools: string[]; mcp_servers: string[] }
  | { type: 'text_delta'; text: string }
  | { type: 'thinking_delta'; text: string }
  | { type: 'tool_use_start'; tool_use_id: string; name: string }
  | { type: 'tool_use_input'; tool_use_id: string; name: string; input: unknown }
  | { type: 'tool_use_input_delta'; partial_json: string }
  | { type: 'tool_result'; tool_use_id: string; content: string; is_error: boolean }
  | { type: 'done'; session_id: string; cost_usd: number | null; duration_ms: number | null; result: string }
  | { type: 'error'; error: string }
  | { type: 'aborted' }

/** Commands sent FROM client TO server over WebSocket */
export type CcWsCommand =
  | { action: 'start'; prompt: string }
  | { action: 'message'; prompt: string; session_id?: string; cli_session_id?: string }
  | { action: 'abort' }

// ============== WebSocket ==============

export function createClaudeCodeWs(onEvent: (event: CcWsEvent) => void) {
  const token = localStorage.getItem('admin_token') || ''
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${proto}//${window.location.host}/admin/claude-code/ws?token=${token}`

  const ws = new WebSocket(url)

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as CcWsEvent
      onEvent(data)
    } catch {
      console.warn('Claude Code WS: invalid JSON', event.data)
    }
  }

  ws.onerror = () => {
    onEvent({ type: 'error', error: 'WebSocket connection error' })
  }

  ws.onclose = (event) => {
    if (event.code !== 1000) {
      onEvent({ type: 'error', error: event.reason || `Connection closed (${event.code})` })
    }
  }

  function send(cmd: CcWsCommand) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(cmd))
    }
  }

  function close() {
    ws.close()
  }

  return { ws, send, close }
}

// ============== REST ==============

export const claudeCodeApi = {
  listSessions: () =>
    api.get<{ sessions: ClaudeCodeSession[] }>('/admin/claude-code/sessions'),

  getSession: (id: string) =>
    api.get<{ session: ClaudeCodeSession }>(`/admin/claude-code/sessions/${id}`),

  deleteSession: (id: string) =>
    api.delete<{ status: string }>(`/admin/claude-code/sessions/${id}`),
}
