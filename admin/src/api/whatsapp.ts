import { api } from './client'

export interface WhatsAppInstance {
  id: string
  name: string
  description?: string
  enabled: boolean
  auto_start: boolean
  // WhatsApp API
  phone_number_id: string
  waba_id?: string
  access_token?: string
  access_token_masked?: string
  verify_token?: string
  app_secret?: string
  // Webhook
  webhook_port: number
  // AI
  llm_backend: string
  system_prompt?: string
  llm_params?: Record<string, unknown>
  // TTS
  tts_enabled: boolean
  tts_engine: string
  tts_voice: string
  tts_preset?: string
  // RAG
  rag_mode?: string
  knowledge_collection_id?: number | null
  knowledge_collection_ids?: number[]
  // Access control
  allowed_phones: string[]
  blocked_phones: string[]
  // Rate limiting
  rate_limit_count?: number | null
  rate_limit_hours?: number | null
  // Status (added by API)
  running?: boolean
  pid?: number
  // Sharing (added by API)
  owner_id?: number | null
  share_count?: number
  is_shared_with_me?: boolean
  share_permission?: string | null
  // Timestamps
  created?: string
  updated?: string
}

export interface WhatsAppStatus {
  running: boolean
  enabled: boolean
  pid: number | null
}

// WhatsApp instances API
export const whatsappInstancesApi = {
  // List instances
  list: (enabledOnly = false) =>
    api.get<{ instances: WhatsAppInstance[] }>(`/admin/whatsapp/instances?enabled_only=${enabledOnly}`),

  // Get instance
  get: (instanceId: string, includeToken = false) =>
    api.get<{ instance: WhatsAppInstance }>(`/admin/whatsapp/instances/${instanceId}?include_token=${includeToken}`),

  // Create instance
  create: (data: Partial<WhatsAppInstance>) =>
    api.post<{ instance: WhatsAppInstance }>('/admin/whatsapp/instances', data),

  // Update instance
  update: (instanceId: string, data: Partial<WhatsAppInstance>) =>
    api.put<{ instance: WhatsAppInstance }>(`/admin/whatsapp/instances/${instanceId}`, data),

  // Delete instance
  delete: (instanceId: string) =>
    api.delete<{ status: string; message: string }>(`/admin/whatsapp/instances/${instanceId}`),

  // Start bot
  start: (instanceId: string) =>
    api.post<{ status: string; pid?: number; instance_id: string }>(`/admin/whatsapp/instances/${instanceId}/start`),

  // Stop bot
  stop: (instanceId: string) =>
    api.post<{ status: string; instance_id: string }>(`/admin/whatsapp/instances/${instanceId}/stop`),

  // Restart bot
  restart: (instanceId: string) =>
    api.post<{ status: string; pid?: number; instance_id: string }>(`/admin/whatsapp/instances/${instanceId}/restart`),

  // Get status
  getStatus: (instanceId: string) =>
    api.get<{ status: WhatsAppStatus }>(`/admin/whatsapp/instances/${instanceId}/status`),

  // Get logs
  getLogs: (instanceId: string, lines = 100) =>
    api.get<{ logs: string }>(`/admin/whatsapp/instances/${instanceId}/logs?lines=${lines}`),

  // Sharing
  getShares: (instanceId: string) =>
    api.get<{ shares: Array<{ id: number; resource_type: string; resource_id: string; user_id: number; permission: string; shared_by: number | null; shared_at: string | null; username: string; display_name: string | null }> }>(`/admin/whatsapp/instances/${instanceId}/shares`),

  shareInstance: (instanceId: string, userId: number, permission: string) =>
    api.post(`/admin/whatsapp/instances/${instanceId}/shares`, { user_id: userId, permission }),

  updateSharePermission: (instanceId: string, userId: number, permission: string) =>
    api.put(`/admin/whatsapp/instances/${instanceId}/shares/${userId}`, { permission }),

  removeShare: (instanceId: string, userId: number) =>
    api.delete(`/admin/whatsapp/instances/${instanceId}/shares/${userId}`),
}
