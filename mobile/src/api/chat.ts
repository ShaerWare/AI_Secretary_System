import { api } from "./client";
import { useSettingsStore } from "@/stores/settings";
import { useAuthStore } from "@/stores/auth";
import { useMobileConfigStore } from "@/stores/mobileConfig";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  parent_id?: string | null;
  is_active?: boolean;
}

export interface TokenUsage {
  tokens: number;
  context_window: number;
  percent: number;
  trimmed?: boolean;
}

export interface ContextFile {
  name: string;
  content: string;
}

export interface BranchNode {
  id: string;
  role: string;
  content_preview: string;
  is_active: boolean;
  children: BranchNode[];
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  system_prompt?: string;
  source?: string | null;
  source_id?: string | null;
  rag_mode?: string | null;
  knowledge_collection_id?: number | null;
  knowledge_collection_ids?: number[] | string | null;
  context_files?: ContextFile[];
  web_search_enabled?: boolean;
  created: string;
  updated: string;
  token_usage?: TokenUsage;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  message_count: number;
  last_message?: string;
  source?: string | null;
  created: string;
  updated: string;
  is_shared_with_me?: boolean;
  share_permission?: string;
  share_count?: number;
}

export interface StreamChunk {
  type: string;
  content?: string;
  message?: ChatMessage;
  token_usage?: TokenUsage;
  query?: string;
  name?: string;
  found?: boolean;
}

export const chatApi = {
  listSessions: () =>
    api.get<{ sessions: ChatSessionSummary[] }>(
      "/admin/chat/sessions",
    ),

  getSession: (id: string) =>
    api.get<{ session: ChatSession }>(
      `/admin/chat/sessions/${id}`,
    ),

  createSession: (title?: string) => {
    const config = useMobileConfigStore();
    const instanceId = config.instance?.id;
    return api.post<{ session: ChatSession }>("/admin/chat/sessions", {
      title,
      source: "mobile",
      source_id: instanceId || undefined,
      system_prompt: config.instance?.system_prompt || undefined,
    });
  },

  deleteSession: (id: string) =>
    api.delete<{ status: string }>(`/admin/chat/sessions/${id}`),

  updateSession: (
    id: string,
    data: {
      title?: string;
      system_prompt?: string;
      context_files?: ContextFile[];
      web_search_enabled?: boolean;
      source?: string;
      source_id?: string;
      rag_mode?: string;
      knowledge_collection_ids?: number[];
      [key: string]: unknown;
    },
  ) =>
    api.put<{ session: ChatSession }>(
      `/admin/chat/sessions/${id}`,
      data,
    ),

  deleteMessage: (sessionId: string, messageId: string) =>
    api.delete<{ status: string }>(
      `/admin/chat/sessions/${sessionId}/messages/${messageId}`,
    ),

  editMessage: (sessionId: string, messageId: string, content: string) =>
    api.put<{ message: ChatMessage }>(
      `/admin/chat/sessions/${sessionId}/messages/${messageId}`,
      { content },
    ),

  summarizeBranch: (sessionId: string, messageId: string) =>
    api.post<{ summary: string }>(
      `/admin/chat/sessions/${sessionId}/messages/${messageId}/summarize`,
    ),

  // Branches
  getBranches: (sessionId: string) =>
    api.get<{ branches: BranchNode[] }>(
      `/admin/chat/sessions/${sessionId}/branches`,
    ),

  switchBranch: (sessionId: string, messageId: string) =>
    api.post<{ status: string; session: ChatSession }>(
      `/admin/chat/sessions/${sessionId}/branches/switch`,
      { message_id: messageId },
    ),

  newBranch: (sessionId: string) =>
    api.post<{ status: string; session: ChatSession }>(
      `/admin/chat/sessions/${sessionId}/branches/new`,
    ),

  regenerateResponse: (sessionId: string, messageId: string) =>
    api.post<{ status: string }>(
      `/admin/chat/sessions/${sessionId}/messages/${messageId}/regenerate`,
    ),

  streamMessage: (
    sessionId: string,
    content: string,
    onChunk: (data: StreamChunk) => void,
    overrides?: Record<string, unknown>,
  ) => {
    const settings = useSettingsStore();
    const auth = useAuthStore();
    const config = useMobileConfigStore();
    const controller = new AbortController();

    const body: Record<string, unknown> = { content };
    if (config.instance?.id) {
      body.mobile_instance_id = config.instance.id;
    }
    if (overrides) {
      Object.assign(body, overrides);
    }

    fetch(
      `${settings.serverUrl}/admin/chat/sessions/${sessionId}/stream`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...auth.getAuthHeaders(),
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      },
    )
      .then(async (response) => {
        if (!response.ok) throw new Error("Stream failed");

        const reader = response.body?.getReader();
        if (!reader) return;

        const decoder = new TextDecoder();
        let buffer = "";
        let receivedDone = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              if (data === "[DONE]") {
                receivedDone = true;
                onChunk({ type: "done" });
              } else {
                try {
                  const parsed = JSON.parse(data);
                  if (
                    parsed.type === "done" ||
                    parsed.type === "assistant_message" ||
                    parsed.type === "error"
                  ) {
                    receivedDone = true;
                  }
                  onChunk(parsed);
                } catch {
                  // Ignore parse errors
                }
              }
            }
          }
        }

        if (!receivedDone) {
          onChunk({
            type: "error",
            content: "Stream ended unexpectedly",
          });
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          onChunk({ type: "error", content: e.message });
        }
      });

    return { abort: () => controller.abort() };
  },

  getMyDefaultMobileSession: () =>
    api.get<{ session_id: string | null }>(
      "/admin/chat/my-default-mobile-session",
    ),
};
