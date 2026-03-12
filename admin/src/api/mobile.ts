import { api } from './client'

export interface MobileAppInstance {
  id: string
  name: string
  description?: string
  enabled: boolean
  // AI
  llm_backend: string
  llm_persona: string
  system_prompt?: string
  llm_params?: Record<string, unknown>
  // TTS
  tts_engine: string
  tts_voice: string
  tts_preset?: string
  // RAG
  rag_mode?: string
  knowledge_collection_id?: number | null
  knowledge_collection_ids?: number[]
  // Rate limiting
  rate_limit_count?: number | null
  rate_limit_hours?: number | null
  // Sharing
  owner_id?: number | null
  share_count?: number
  is_shared_with_me?: boolean
  share_permission?: string | null
  // Timestamps
  created?: string
  updated?: string
}

export const mobileInstancesApi = {
  list: (enabledOnly = false) =>
    api.get<{ instances: MobileAppInstance[] }>(`/admin/mobile/instances?enabled_only=${enabledOnly}`),

  get: (instanceId: string) =>
    api.get<{ instance: MobileAppInstance }>(`/admin/mobile/instances/${instanceId}`),

  create: (data: Partial<MobileAppInstance>) =>
    api.post<{ instance: MobileAppInstance }>('/admin/mobile/instances', data),

  update: (instanceId: string, data: Partial<MobileAppInstance>) =>
    api.put<{ instance: MobileAppInstance }>(`/admin/mobile/instances/${instanceId}`, data),

  delete: (instanceId: string) =>
    api.delete<{ status: string; message: string }>(`/admin/mobile/instances/${instanceId}`),

  // Sharing (user assignment)
  getShares: (instanceId: string) =>
    api.get<{ shares: Array<{ id: number; resource_type: string; resource_id: string; user_id: number; permission: string; shared_by: number | null; shared_at: string | null; username: string; display_name: string | null }> }>(`/admin/mobile/instances/${instanceId}/shares`),

  shareInstance: (instanceId: string, userId: number, permission: string) =>
    api.post(`/admin/mobile/instances/${instanceId}/shares`, { user_id: userId, permission }),

  updateSharePermission: (instanceId: string, userId: number, permission: string) =>
    api.put(`/admin/mobile/instances/${instanceId}/shares/${userId}`, { permission }),

  removeShare: (instanceId: string, userId: number) =>
    api.delete(`/admin/mobile/instances/${instanceId}/shares/${userId}`),

  // Public config (for mobile app)
  getMyConfig: () =>
    api.get<{ instance: MobileAppInstance | null }>('/admin/mobile/my-config'),
}
