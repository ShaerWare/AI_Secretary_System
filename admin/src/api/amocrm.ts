import { api } from './client'

// ============== Types ==============

export interface AmoCRMConfig {
  id: number
  subdomain: string | null
  client_id: string | null
  client_secret_masked: string
  redirect_uri: string | null
  is_connected: boolean
  sync_contacts: boolean
  sync_leads: boolean
  sync_tasks: boolean
  auto_create_lead: boolean
  lead_pipeline_id: number | null
  lead_status_id: number | null
  webhook_url: string | null
  last_sync_at: string | null
  contacts_count: number
  leads_count: number
  account_info: Record<string, unknown>
  created: string | null
  updated: string | null
}

export interface AmoCRMStatus {
  connected: boolean
  has_credentials: boolean
  subdomain?: string
  account_info?: Record<string, unknown>
  contacts_count: number
  leads_count: number
  last_sync: string | null
}

export interface AmoCRMSyncLogEntry {
  id: number
  direction: string
  entity_type: string
  entity_id: number | null
  action: string
  details: Record<string, unknown> | null
  status: string
  error_message: string | null
  created: string | null
}

export interface AmoCRMPipelineStatus {
  id: number
  name: string
  sort: number
  color: string
}

export interface AmoCRMPipeline {
  id: number
  name: string
  sort: number
  is_main: boolean
  _embedded: {
    statuses: AmoCRMPipelineStatus[]
  }
}

export interface AmoCRMContact {
  id: number
  name: string
  custom_fields_values: unknown[] | null
}

export interface AmoCRMLead {
  id: number
  name: string
  price: number
  pipeline_id: number
  status_id: number
  responsible_user_id?: number
  created_at?: number
  updated_at?: number
  closest_task_at?: number | null
  _embedded?: {
    contacts?: AmoCRMContact[]
    tags?: { id: number; name: string }[]
  }
}

export interface AmoCRMEvent {
  id: string
  type: string
  entity_id: number
  entity_type: string
  created_at: number
  value_after: unknown[]
  value_before: unknown[]
  account_id: number
}

export interface AmoCRMChat {
  id: string
  contact_id: number
  created_at: number
}

export interface AmoCRMChatMessage {
  id: string
  timestamp: number
  sender: { id: string; name: string }
  receiver: { id: string; name: string }
  message: { type: string; text?: string }
}

// ============== API ==============

export const amocrmApi = {
  // Status & Config
  getStatus: () =>
    api.get<AmoCRMStatus>('/admin/crm/status'),

  getConfig: () =>
    api.get<{ config: AmoCRMConfig }>('/admin/crm/config'),

  saveConfig: (data: Record<string, unknown>) =>
    api.post<{ status: string; config: AmoCRMConfig }>('/admin/crm/config', data),

  // OAuth
  getAuthUrl: () =>
    api.get<{ auth_url: string; redirect_uri: string }>('/admin/crm/auth-url'),

  disconnect: () =>
    api.post<{ status: string }>('/admin/crm/disconnect'),

  testConnection: () =>
    api.post<{ status: string; account: Record<string, unknown> }>('/admin/crm/test'),

  refreshToken: () =>
    api.post<{ status: string; expires_at: string }>('/admin/crm/refresh-token'),

  // Contacts
  getContacts: (page = 1, limit = 50, query?: string) => {
    const params = new URLSearchParams({ page: String(page), limit: String(limit) })
    if (query) params.set('query', query)
    return api.get<{ _embedded: { contacts: AmoCRMContact[] } }>(`/admin/crm/contacts?${params}`)
  },

  createContact: (name: string, custom_fields?: unknown[]) =>
    api.post('/admin/crm/contacts', { name, custom_fields }),

  // Leads
  getLeads: (page = 1, limit = 50, query?: string) => {
    const params = new URLSearchParams({ page: String(page), limit: String(limit) })
    if (query) params.set('query', query)
    return api.get<{ _embedded: { leads: AmoCRMLead[] } }>(`/admin/crm/leads?${params}`)
  },

  getLead: (id: number) =>
    api.get<AmoCRMLead>(`/admin/crm/leads/${id}`),

  updateLead: (id: number, data: Partial<AmoCRMLead>) =>
    api.patch<AmoCRMLead>(`/admin/crm/leads/${id}`, data),

  getLeadsByPipeline: (pipelineId: number) =>
    api.get<{ _embedded: { leads: AmoCRMLead[] } }>(`/admin/crm/leads/by-pipeline/${pipelineId}`),

  getUnsortedLeads: (page = 1, limit = 250) => {
    const params = new URLSearchParams({ page: String(page), limit: String(limit) })
    return api.get<{ _embedded: { leads: AmoCRMLead[] }; total: number }>(`/admin/crm/leads/unsorted?${params}`)
  },

  createLead: (data: {
    name: string
    pipeline_id?: number
    status_id?: number
    contact_id?: number
  }) =>
    api.post('/admin/crm/leads', data),

  addNoteToLead: (leadId: number, text: string) =>
    api.post(`/admin/crm/leads/${leadId}/notes`, { text }),

  // Pipelines
  getPipelines: () =>
    api.get<{ _embedded: { pipelines: AmoCRMPipeline[] } }>('/admin/crm/pipelines'),

  // Events
  getEvents: (page = 1, limit = 50, types?: string) => {
    const params = new URLSearchParams({ page: String(page), limit: String(limit) })
    if (types) params.set('types', types)
    return api.get<{ _embedded: { events: AmoCRMEvent[] } }>(`/admin/crm/events?${params}`)
  },

  // Contact chats
  getContactChats: (contactId: number) =>
    api.get<{ _embedded: { chats: AmoCRMChat[] } }>(`/admin/crm/contacts/${contactId}/chats`),

  // Chat messaging (amojo)
  getChatHistory: (chatId: string, limit = 50, offset = 0) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    return api.get<{ messages: AmoCRMChatMessage[] }>(`/admin/crm/chats/${chatId}/history?${params}`)
  },

  sendChatMessage: (chatId: string, text: string) =>
    api.post<{ status: string }>(`/admin/crm/chats/${chatId}/messages`, { text }),

  // Sync
  sync: () =>
    api.post<{ status: string; contacts_count: number; leads_count: number; synced_at: string }>('/admin/crm/sync'),

  getSyncLog: (limit = 50) =>
    api.get<{ logs: AmoCRMSyncLogEntry[] }>(`/admin/crm/sync-log?limit=${limit}`),
}
