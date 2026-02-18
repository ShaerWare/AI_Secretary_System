import { api, createSSE, getAuthHeaders } from './client'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  edited?: boolean
  parent_id?: string | null
  is_active?: boolean
}

export interface SiblingInfo {
  index: number
  total: number
  siblings: string[]
}

export interface BranchNode {
  id: string
  role: string
  content_preview: string
  is_active: boolean
  children: BranchNode[]
}

export interface TokenUsage {
  tokens: number
  context_window: number
  percent: number
  trimmed?: boolean
}

export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  system_prompt?: string
  pinned?: boolean
  context_files?: { name: string; content: string }[]
  source?: 'admin' | 'telegram' | 'widget' | null
  source_id?: string
  created: string
  updated: string
  sibling_info?: Record<string, SiblingInfo>
  token_usage?: TokenUsage
}

export interface ChatSessionSummary {
  id: string
  title: string
  pinned?: boolean
  message_count: number
  last_message?: string
  source?: 'admin' | 'telegram' | 'widget' | null
  source_id?: string
  created: string
  updated: string
}

export interface GroupedSessions {
  admin: ChatSessionSummary[]
  telegram: ChatSessionSummary[]
  widget: ChatSessionSummary[]
  unknown: ChatSessionSummary[]
}

// Chat API
export const chatApi = {
  // Sessions
  listSessions: () =>
    api.get<{ sessions: ChatSessionSummary[] }>('/admin/chat/sessions'),

  listSessionsGrouped: () =>
    api.get<{ sessions: GroupedSessions; grouped: true }>('/admin/chat/sessions?group_by=source'),

  getSession: (sessionId: string) =>
    api.get<{ session: ChatSession }>(`/admin/chat/sessions/${sessionId}`),

  createSession: (title?: string, systemPrompt?: string, source?: string, sourceId?: string) =>
    api.post<{ session: ChatSession }>('/admin/chat/sessions', {
      title,
      system_prompt: systemPrompt,
      source,
      source_id: sourceId,
    }),

  updateSession: (sessionId: string, data: { title?: string; system_prompt?: string; pinned?: boolean; context_files?: { name: string; content: string }[] }) =>
    api.put<{ session: ChatSession }>(`/admin/chat/sessions/${sessionId}`, data),

  deleteSession: (sessionId: string) =>
    api.delete<{ status: string }>(`/admin/chat/sessions/${sessionId}`),

  bulkDeleteSessions: (sessionIds: string[]) =>
    api.post<{ status: string; deleted: number }>('/admin/chat/sessions/bulk-delete', {
      session_ids: sessionIds,
    }),

  // Messages
  sendMessage: (sessionId: string, content: string) =>
    api.post<{ message: ChatMessage; response: ChatMessage }>(
      `/admin/chat/sessions/${sessionId}/messages`,
      { content }
    ),

  editMessage: (sessionId: string, messageId: string, content: string) =>
    api.put<{ message: ChatMessage; response?: ChatMessage }>(
      `/admin/chat/sessions/${sessionId}/messages/${messageId}`,
      { content }
    ),

  deleteMessage: (sessionId: string, messageId: string) =>
    api.delete<{ status: string }>(
      `/admin/chat/sessions/${sessionId}/messages/${messageId}`
    ),

  regenerateResponse: (sessionId: string, messageId: string) =>
    api.post<{ response: ChatMessage }>(
      `/admin/chat/sessions/${sessionId}/messages/${messageId}/regenerate`
    ),

  summarizeBranch: (sessionId: string, messageId: string) =>
    api.post<{ summary: string }>(
      `/admin/chat/sessions/${sessionId}/messages/${messageId}/summarize`
    ),

  // Branches
  getBranches: (sessionId: string) =>
    api.get<{ branches: BranchNode[] }>(`/admin/chat/sessions/${sessionId}/branches`),

  switchBranch: (sessionId: string, messageId: string) =>
    api.post<{ status: string; session: ChatSession }>(
      `/admin/chat/sessions/${sessionId}/branches/switch`,
      { message_id: messageId }
    ),

  newBranchFromScratch: (sessionId: string) =>
    api.post<{ status: string; session: ChatSession }>(
      `/admin/chat/sessions/${sessionId}/branches/new`
    ),

  // Streaming chat
  streamMessage: (
    sessionId: string,
    content: string,
    onChunk: (data: { type: string; content?: string; message?: ChatMessage; token_usage?: TokenUsage }) => void,
    llmOverride?: { llm_backend?: string; system_prompt?: string },
    widgetInstanceId?: string
  ) => {
    const controller = new AbortController()

    const body: Record<string, unknown> = { content }
    if (llmOverride) {
      body.llm_override = llmOverride
    }
    if (widgetInstanceId) {
      body.widget_instance_id = widgetInstanceId
    }

    fetch(`/admin/chat/sessions/${sessionId}/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error('Stream failed')

      const reader = response.body?.getReader()
      if (!reader) return

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') {
              onChunk({ type: 'done' })
            } else {
              try {
                const parsed = JSON.parse(data)
                onChunk(parsed)
              } catch {
                // Ignore parse errors
              }
            }
          }
        }
      }
    }).catch((e) => {
      if (e.name !== 'AbortError') {
        onChunk({ type: 'error', content: e.message })
      }
    })

    return { abort: () => controller.abort() }
  },

  // Get default system prompt
  getDefaultPrompt: () =>
    api.get<{ prompt: string; persona: string }>('/admin/llm/prompt'),
}
