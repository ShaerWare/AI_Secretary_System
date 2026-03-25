import { api } from "./client";

export interface CloudProvider {
  id: number;
  name: string;
  provider_type: string;
  model_name: string;
  enabled: boolean;
  is_default: boolean;
}

export interface KnowledgeCollection {
  id: number;
  name: string;
  slug: string;
  description?: string;
  enabled: boolean;
  document_count: number;
}

export interface LlmOption {
  value: string;
  label: string;
  type: "vllm" | "cloud";
}

export interface ShareableUser {
  id: number;
  username: string;
  display_name: string;
  role: string;
}

export interface ChatShare {
  id: number;
  session_id: string;
  user_id: number;
  permission: "read" | "write";
  shared_by: number;
  shared_at: string;
  username: string;
  display_name: string;
  is_default_mobile: boolean;
}

export interface MobileInstance {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  llm_backend: string;
  llm_persona: string;
  system_prompt: string | null;
  rag_mode: string;
  knowledge_collection_ids: number[] | null;
  share_count: number;
}

export interface MobileShare {
  id: number;
  resource_id: string;
  user_id: number;
  permission: "view" | "edit";
  username: string;
  display_name: string;
}

export const adminApi = {
  // LLM providers
  getProviders: () =>
    api.get<{ providers: CloudProvider[] }>(
      "/admin/llm/providers?enabled_only=true",
    ),

  // RAG collections
  getCollections: () =>
    api.get<{ collections: KnowledgeCollection[] }>(
      "/admin/wiki-rag/collections",
    ),

  // Shareable users
  getShareableUsers: () =>
    api.get<{ users: ShareableUser[] }>(
      "/admin/chat/shareable-users",
    ),

  // Chat shares
  getSessionShares: (sessionId: string) =>
    api.get<{ shares: ChatShare[] }>(
      `/admin/chat/sessions/${sessionId}/shares`,
    ),

  shareSession: (sessionId: string, userId: number, permission: "read" | "write" = "read") =>
    api.post<{ share: ChatShare }>(
      `/admin/chat/sessions/${sessionId}/shares`,
      { user_id: userId, permission },
    ),

  removeSessionShare: (sessionId: string, userId: number) =>
    api.delete<{ status: string }>(
      `/admin/chat/sessions/${sessionId}/shares/${userId}`,
    ),

  // Default mobile session
  getDefaultMobileUsers: (sessionId: string) =>
    api.get<{ users: ShareableUser[] }>(
      `/admin/chat/sessions/${sessionId}/default-mobile-users`,
    ),

  setDefaultMobile: (sessionId: string, userIds: number[]) =>
    api.put<{ shares: ChatShare[] }>(
      `/admin/chat/sessions/${sessionId}/default-mobile`,
      { user_ids: userIds },
    ),

  removeDefaultMobile: (sessionId: string, userId: number) =>
    api.delete<{ status: string }>(
      `/admin/chat/sessions/${sessionId}/default-mobile/${userId}`,
    ),

  // Mobile instances
  getMobileInstances: () =>
    api.get<{ instances: MobileInstance[] }>(
      "/admin/mobile/instances",
    ),

  getMobileInstanceShares: (instanceId: string) =>
    api.get<{ shares: MobileShare[] }>(
      `/admin/mobile/instances/${instanceId}/shares`,
    ),

  assignMobileInstance: (instanceId: string, userId: number, permission: "view" | "edit" = "edit") =>
    api.post<{ share: MobileShare }>(
      `/admin/mobile/instances/${instanceId}/shares`,
      { user_id: userId, permission },
    ),

  removeMobileInstanceShare: (instanceId: string, userId: number) =>
    api.delete<{ status: string }>(
      `/admin/mobile/instances/${instanceId}/shares/${userId}`,
    ),
};
