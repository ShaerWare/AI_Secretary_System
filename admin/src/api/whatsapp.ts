import { api } from './client'

export interface WhatsAppInstance {
  id: string
  name: string
  description?: string
  enabled: boolean
  auto_start: boolean
  // Transport: 'cloud' = Meta Cloud API, 'bridge' = self-hosted (phone linked by QR)
  provider?: 'cloud' | 'bridge'
  bridge_url?: string | null
  bridge_token?: string
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

/** Link state of a self-hosted bridge session (one linked phone). */
export interface BridgeSessionState {
  session_id: string
  status: 'idle' | 'starting' | 'qr' | 'pairing' | 'connected' | 'disconnected' | 'logged_out'
  phone: string | null
  /** data-URL of the QR to scan; present only while status === 'qr' */
  qr: string | null
  /** 8-character code to type on the phone; present only while status === 'pairing' */
  pairing_code: string | null
  pairing_phone: string | null
  last_error: string | null
  connected_at: string | null
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

  // Self-hosted bridge: QR linking of a phone
  /** Omit pairingPhone to link by QR; pass digits to link by code instead. */
  bridgeStart: (instanceId: string, pairingPhone?: string) =>
    api.post<BridgeSessionState>(
      `/admin/whatsapp/instances/${instanceId}/bridge/start`,
      pairingPhone ? { pairing_phone: pairingPhone } : {},
    ),

  bridgeStatus: (instanceId: string) =>
    api.get<BridgeSessionState>(`/admin/whatsapp/instances/${instanceId}/bridge/status`),

  bridgeStop: (instanceId: string) =>
    api.post<BridgeSessionState>(`/admin/whatsapp/instances/${instanceId}/bridge/stop`),

  bridgeLogout: (instanceId: string) =>
    api.post<BridgeSessionState>(`/admin/whatsapp/instances/${instanceId}/bridge/logout`),

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
