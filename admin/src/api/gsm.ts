import { api } from './client'

// ============== Types ==============

export type ModuleState =
  | 'disconnected'
  | 'initializing'
  | 'ready'
  | 'incoming_call'
  | 'in_call'
  | 'error'

export type CallDirection = 'incoming' | 'outgoing'
export type CallState = 'ringing' | 'active' | 'completed' | 'missed' | 'failed'

export interface GSMStatus {
  state: ModuleState
  signal_strength?: number | null
  signal_percent?: number | null
  sim_status?: string | null
  network_name?: string | null
  network_registered: boolean
  phone_number?: string | null
  at_port: string
  audio_port: string
  module_info?: string | null
  last_error?: string | null
  mock_mode?: boolean
  network_mode?: string | null
}

export interface GSMConfig {
  // Ports
  at_port: string
  audio_port: string
  baud_rate: number

  // Auto-answer
  auto_answer: boolean
  auto_answer_rings: number

  // Number filtering
  allowed_numbers: string[]
  blocked_numbers: string[]

  // Messages
  greeting_message: string
  goodbye_message: string
  busy_message: string

  // Timeouts
  silence_timeout: number
  max_call_duration: number

  // SMS
  sms_enabled: boolean
  sms_notify_number: string
  sms_missed_call_template: string
  sms_voicemail_template: string

  // LLM
  llm_backend: string
  llm_persona: string

  // TTS
  tts_voice: string
  tts_preset: string
}

export interface CallInfo {
  id: string
  direction: CallDirection
  state: CallState
  caller_number: string
  started_at: string
  answered_at?: string | null
  ended_at?: string | null
  duration_seconds?: number | null
  transcript_preview?: string | null
  sms_sent: boolean
}

export interface ActiveCall {
  id: string
  direction: CallDirection
  caller_number: string
  started_at: string
  duration_seconds: number
  transcript: Array<{ role: string; text: string; ts: string }>
}

export interface SMSMessage {
  id: number
  direction: string
  number: string
  text: string
  sent_at: string
  status: string
}

export interface ATCommandResponse {
  command: string
  response: string[]
  success: boolean
  error?: string | null
}

export interface SerialPorts {
  usb_ports: string[]
  acm_ports: string[]
  total: number
}

export interface Conversation {
  number: string
  last_message: string
  last_direction: string
  last_time: string | null
  message_count: number
  call_count: number
}

export interface ConversationDetail {
  number: string
  messages: SMSMessage[]
  calls: CallInfo[]
}

// ============== API ==============

export const gsmApi = {
  // Status
  getStatus: () => api.get<GSMStatus>('/admin/gsm/status'),

  initialize: () =>
    api.post<{ status: string; message: string }>('/admin/gsm/initialize'),

  // Config
  getConfig: () => api.get<GSMConfig>('/admin/gsm/config'),

  updateConfig: (config: Partial<GSMConfig>) =>
    api.put<GSMConfig>('/admin/gsm/config', config),

  // Calls
  listCalls: (params?: { limit?: number; offset?: number; state?: CallState }) => {
    const query = new URLSearchParams()
    if (params?.limit) query.set('limit', params.limit.toString())
    if (params?.offset) query.set('offset', params.offset.toString())
    if (params?.state) query.set('state', params.state)
    const qs = query.toString()
    return api.get<{ calls: CallInfo[]; total: number; limit: number; offset: number }>(
      `/admin/gsm/calls${qs ? `?${qs}` : ''}`
    )
  },

  getActiveCall: () => api.get<ActiveCall | null>('/admin/gsm/calls/active'),

  getCall: (callId: string) => api.get<CallInfo>(`/admin/gsm/calls/${callId}`),

  answerCall: () =>
    api.post<{ status: string; message: string }>('/admin/gsm/calls/answer'),

  hangupCall: () =>
    api.post<{ status: string; message: string }>('/admin/gsm/calls/hangup'),

  dialNumber: (number: string) =>
    api.post<{ status: string; message: string }>('/admin/gsm/calls/dial', { number }),

  // SMS
  listSMS: (params?: { limit?: number; offset?: number }) => {
    const query = new URLSearchParams()
    if (params?.limit) query.set('limit', params.limit.toString())
    if (params?.offset) query.set('offset', params.offset.toString())
    const qs = query.toString()
    return api.get<{ messages: SMSMessage[]; total: number; limit: number; offset: number }>(
      `/admin/gsm/sms${qs ? `?${qs}` : ''}`
    )
  },

  sendSMS: (number: string, text: string) =>
    api.post<{ status: string; message: string }>('/admin/gsm/sms', { number, text }),

  readModemSMS: () =>
    api.post<{ status: string; count: number; messages: SMSMessage[] }>(
      '/admin/gsm/sms/read-modem',
    ),

  clearModemSMS: () =>
    api.post<{ status: string; message: string }>('/admin/gsm/sms/clear-modem'),

  // DTMF
  sendDTMF: (digits: string) =>
    api.post<{ status: string; message: string }>('/admin/gsm/dtmf', { digits }),

  // Conversations
  listConversations: (params?: { limit?: number; offset?: number }) => {
    const query = new URLSearchParams()
    if (params?.limit) query.set('limit', params.limit.toString())
    if (params?.offset) query.set('offset', params.offset.toString())
    const qs = query.toString()
    return api.get<{
      conversations: Conversation[]
      total: number
      limit: number
      offset: number
    }>(`/admin/gsm/conversations${qs ? `?${qs}` : ''}`)
  },

  getConversation: (number: string) =>
    api.get<ConversationDetail>(`/admin/gsm/conversations/${encodeURIComponent(number)}`),

  // Debug
  executeAT: (command: string, timeout = 5.0) =>
    api.post<ATCommandResponse>('/admin/gsm/at', { command, timeout }),

  listPorts: () => api.get<SerialPorts>('/admin/gsm/ports'),
}
