import { api } from './client'

// Legacy config (for backward compatibility)
export interface WidgetConfig {
  enabled: boolean
  title: string
  greeting: string
  placeholder: string
  placeholder_color?: string
  placeholder_font?: string
  primary_color: string
  button_icon?: string
  position: 'left' | 'right'
  allowed_domains: string[]
  tunnel_url: string
}

// Widget instance type
export interface WidgetInstance {
  id: string
  name: string
  description?: string
  enabled: boolean
  // Appearance
  title: string
  greeting?: string
  placeholder: string
  placeholder_color?: string
  placeholder_font?: string
  primary_color: string
  button_icon?: string
  position: 'left' | 'right'
  // Access
  allowed_domains: string[]
  tunnel_url?: string
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
  // Sharing (added by API)
  owner_id?: number | null
  share_count?: number
  is_shared_with_me?: boolean
  share_permission?: string | null
  // Timestamps
  created?: string
  updated?: string
}

// Legacy API (kept for backward compatibility)
export const widgetApi = {
  getConfig: () =>
    api.get<{ config: WidgetConfig }>('/admin/widget/config'),

  saveConfig: (config: WidgetConfig) =>
    api.post<{ status: string; config: WidgetConfig }>('/admin/widget/config', config),
}

// Widget instances API
export const widgetInstancesApi = {
  // List instances
  list: (enabledOnly = false) =>
    api.get<{ instances: WidgetInstance[] }>(`/admin/widget/instances?enabled_only=${enabledOnly}`),

  // Get instance
  get: (instanceId: string) =>
    api.get<{ instance: WidgetInstance }>(`/admin/widget/instances/${instanceId}`),

  // Create instance
  create: (data: Partial<WidgetInstance>) =>
    api.post<{ instance: WidgetInstance }>('/admin/widget/instances', data),

  // Update instance
  update: (instanceId: string, data: Partial<WidgetInstance>) =>
    api.put<{ instance: WidgetInstance }>(`/admin/widget/instances/${instanceId}`, data),

  // Delete instance
  delete: (instanceId: string) =>
    api.delete<{ status: string; message: string }>(`/admin/widget/instances/${instanceId}`),

  // Sharing
  getShares: (instanceId: string) =>
    api.get<{ shares: Array<{ id: number; resource_type: string; resource_id: string; user_id: number; permission: string; shared_by: number | null; shared_at: string | null; username: string; display_name: string | null }> }>(`/admin/widget/instances/${instanceId}/shares`),

  shareInstance: (instanceId: string, userId: number, permission: string) =>
    api.post(`/admin/widget/instances/${instanceId}/shares`, { user_id: userId, permission }),

  updateSharePermission: (instanceId: string, userId: number, permission: string) =>
    api.put(`/admin/widget/instances/${instanceId}/shares/${userId}`, { permission }),

  removeShare: (instanceId: string, userId: number) =>
    api.delete(`/admin/widget/instances/${instanceId}/shares/${userId}`),
}
