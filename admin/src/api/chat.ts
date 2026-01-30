import { api, createSSE } from './client'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  edited?: boolean
}

export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  system_prompt?: string
  source?: 'admin' | 'telegram' | 'widget' | null
  source_id?: string
  created: string
  updated: string
}

export interface ChatSessionSummary {
  id: string
  title: string
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

  createSession: (title?: string, systemPrompt?: string, source?: string) =>
    api.post<{ session: ChatSession }>('/admin/chat/sessions', {
      title,
      system_prompt: systemPrompt,
      source,
    }),

  updateSession: (sessionId: string, data: { title?: string; system_prompt?: string }) =>
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

  // Streaming chat
  streamMessage: (
    sessionId: string,
    content: string,
    onChunk: (data: { type: string; content?: string; message?: ChatMessage }) => void
  ) => {
    const controller = new AbortController()

    fetch(`/admin/chat/sessions/${sessionId}/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
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
