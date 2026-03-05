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
  source?: 'admin' | 'telegram' | 'widget' | 'whatsapp' | null
  source_id?: string
  owner_id?: number | null
  rag_mode?: string | null
  knowledge_collection_ids?: number[] | null
  created: string
  updated: string
  sibling_info?: Record<string, SiblingInfo>
  token_usage?: TokenUsage
  is_shared_with_me?: boolean
  share_permission?: string
  share_count?: number
}

export interface ChatSessionSummary {
  id: string
  title: string
  pinned?: boolean
  message_count: number
  last_message?: string
  source?: 'admin' | 'telegram' | 'widget' | 'whatsapp' | null
  source_id?: string
  owner_id?: number | null
  created: string
  updated: string
  is_shared_with_me?: boolean
  share_permission?: string
  share_count?: number
}

export interface ChatShare {
  id: number
  session_id: string
  user_id: number
  permission: string
  shared_by: number | null
  shared_at: string
  username: string
  display_name: string | null
}

export interface ShareableUser {
  id: number
  username: string
  display_name: string | null
  role: string
}

export interface GroupedSessions {
  admin: ChatSessionSummary[]
  telegram: ChatSessionSummary[]
  widget: ChatSessionSummary[]
  whatsapp: ChatSessionSummary[]
  unknown: ChatSessionSummary[]
}

// Chat API
export const chatApi = {
  // Sessions
  listSessions: (source?: string, excludeSource?: string) => {
    const params = new URLSearchParams()
    if (source) params.set('source', source)
    if (excludeSource) params.set('exclude_source', excludeSource)
    const qs = params.toString()
    return api.get<{ sessions: ChatSessionSummary[] }>(`/admin/chat/sessions${qs ? `?${qs}` : ''}`)
  },

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

  updateSession: (sessionId: string, data: { title?: string; system_prompt?: string; pinned?: boolean; context_files?: { name: string; content: string }[]; rag_mode?: string; knowledge_collection_ids?: number[] }) =>
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
      let receivedDone = false

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
              receivedDone = true
              onChunk({ type: 'done' })
            } else {
              try {
                const parsed = JSON.parse(data)
                if (parsed.type === 'done' || parsed.type === 'assistant_message' || parsed.type === 'error') {
                  receivedDone = true
                }
                onChunk(parsed)
              } catch {
                // Ignore parse errors
              }
            }
          }
        }
      }

      // Stream ended without a terminal event — treat as error
      if (!receivedDone) {
        onChunk({ type: 'error', content: 'Stream ended unexpectedly' })
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

  // Sharing
  getShares: (sessionId: string) =>
    api.get<{ shares: ChatShare[] }>(`/admin/chat/sessions/${sessionId}/shares`),

  shareSession: (sessionId: string, userId: number, permission: string = 'read') =>
    api.post<{ share: ChatShare }>(`/admin/chat/sessions/${sessionId}/shares`, {
      user_id: userId,
      permission,
    }),

  updateSharePermission: (sessionId: string, userId: number, permission: string) =>
    api.put<{ status: string }>(`/admin/chat/sessions/${sessionId}/shares/${userId}`, {
      permission,
    }),

  removeShare: (sessionId: string, userId: number) =>
    api.delete<{ status: string }>(`/admin/chat/sessions/${sessionId}/shares/${userId}`),

  forkSession: (sessionId: string, title?: string) =>
    api.post<{ session: ChatSession }>(`/admin/chat/sessions/${sessionId}/fork`, { title }),

  getShareableUsers: () =>
    api.get<{ users: ShareableUser[] }>('/admin/chat/shareable-users'),
}
