import { api } from './client'

// Legacy config (for backward compatibility)
export interface TelegramConfig {
  enabled: boolean
  bot_token: string
  bot_token_masked?: string
  api_url: string
  allowed_users: number[]
  admin_users: number[]
  welcome_message: string
  unauthorized_message: string
  error_message: string
  typing_enabled: boolean
}

export interface TelegramStatus {
  running: boolean
  enabled: boolean
  has_token: boolean
  active_sessions: number
  allowed_users_count: number
  admin_users_count: number
  pid: number | null
}

// Action button for Telegram bot
export interface ActionButton {
  id: string
  label: string
  icon?: string
  enabled: boolean
  order: number
  llm_backend?: string  // "vllm", "gemini", or "cloud:provider-id"
  system_prompt?: string
  llm_params?: Record<string, unknown>
}

// Payment product configuration
export interface PaymentProduct {
  id: string
  title: string
  description: string
  price_rub: number   // in kopecks (50000 = 500.00 RUB)
  price_stars: number  // Telegram Stars amount
}

// Payment log entry
export interface PaymentLogEntry {
  id: number
  bot_id: string
  user_id: number
  username?: string
  payment_type: string
  product_id: string
  amount: number
  currency: string
  telegram_payment_id?: string
  provider_payment_id?: string
  status: string
  created?: string
}

// Bot instance types
export interface BotInstance {
  id: string
  name: string
  description?: string
  enabled: boolean
  // Telegram
  bot_token?: string
  bot_token_masked?: string
  api_url?: string
  allowed_users: number[]
  admin_users: number[]
  welcome_message?: string
  unauthorized_message?: string
  error_message?: string
  typing_enabled: boolean
  // AI
  llm_backend: string
  llm_persona: string
  system_prompt?: string
  llm_params?: Record<string, unknown>
  // TTS
  tts_engine: string
  tts_voice: string
  tts_preset?: string
  // Action buttons
  action_buttons: ActionButton[]
  // Payment
  payment_enabled: boolean
  yookassa_provider_token?: string
  yookassa_provider_token_masked?: string
  stars_enabled: boolean
  payment_products: PaymentProduct[]
  payment_success_message?: string
  // YooMoney
  yoomoney_client_id?: string
  yoomoney_client_secret?: string
  yoomoney_redirect_uri?: string
  yoomoney_configured?: boolean
  yoomoney_wallet_id?: string
  // Rate limiting
  rate_limit_count?: number | null
  rate_limit_hours?: number | null
  // Status (added by API)
  running?: boolean
  pid?: number
  // Timestamps
  created?: string
  updated?: string
}

export interface BotInstanceSession {
  bot_id: string
  user_id: number
  chat_session_id: string
  username?: string
  first_name?: string
  last_name?: string
  created?: string
  updated?: string
}

// Legacy API (kept for backward compatibility)
export const telegramApi = {
  getConfig: () =>
    api.get<{ config: TelegramConfig }>('/admin/telegram/config'),

  saveConfig: (config: Partial<TelegramConfig>) =>
    api.post<{ status: string; config: TelegramConfig }>('/admin/telegram/config', config),

  getStatus: () =>
    api.get<{ status: TelegramStatus }>('/admin/telegram/status'),

  start: () =>
    api.post<{ status: string; pid?: number }>('/admin/telegram/start'),

  stop: () =>
    api.post<{ status: string }>('/admin/telegram/stop'),

  restart: () =>
    api.post<{ status: string; pid?: number }>('/admin/telegram/restart'),

  getSessions: () =>
    api.get<{ sessions: Record<string, string> }>('/admin/telegram/sessions'),

  clearSessions: () =>
    api.delete<{ status: string; message: string }>('/admin/telegram/sessions'),
}

// Bot instances API
export const botInstancesApi = {
  // List instances
  list: (enabledOnly = false) =>
    api.get<{ instances: BotInstance[] }>(`/admin/telegram/instances?enabled_only=${enabledOnly}`),

  // Get instance
  get: (instanceId: string, includeToken = false) =>
    api.get<{ instance: BotInstance }>(`/admin/telegram/instances/${instanceId}?include_token=${includeToken}`),

  // Create instance
  create: (data: Partial<BotInstance>) =>
    api.post<{ instance: BotInstance }>('/admin/telegram/instances', data),

  // Update instance
  update: (instanceId: string, data: Partial<BotInstance>) =>
    api.put<{ instance: BotInstance }>(`/admin/telegram/instances/${instanceId}`, data),

  // Delete instance
  delete: (instanceId: string) =>
    api.delete<{ status: string; message: string }>(`/admin/telegram/instances/${instanceId}`),

  // Start bot
  start: (instanceId: string) =>
    api.post<{ status: string; pid?: number; instance_id: string }>(`/admin/telegram/instances/${instanceId}/start`),

  // Stop bot
  stop: (instanceId: string) =>
    api.post<{ status: string; instance_id: string }>(`/admin/telegram/instances/${instanceId}/stop`),

  // Restart bot
  restart: (instanceId: string) =>
    api.post<{ status: string; pid?: number; instance_id: string }>(`/admin/telegram/instances/${instanceId}/restart`),

  // Get status
  getStatus: (instanceId: string) =>
    api.get<{ status: TelegramStatus }>(`/admin/telegram/instances/${instanceId}/status`),

  // Get sessions
  getSessions: (instanceId: string) =>
    api.get<{ sessions: BotInstanceSession[] }>(`/admin/telegram/instances/${instanceId}/sessions`),

  // Clear sessions
  clearSessions: (instanceId: string) =>
    api.delete<{ status: string; message: string }>(`/admin/telegram/instances/${instanceId}/sessions`),

  // Get logs
  getLogs: (instanceId: string, lines = 100) =>
    api.get<{ logs: string }>(`/admin/telegram/instances/${instanceId}/logs?lines=${lines}`),

  // Payments
  getPayments: (instanceId: string, limit = 100) =>
    api.get<{ payments: PaymentLogEntry[] }>(`/admin/telegram/instances/${instanceId}/payments?limit=${limit}`),

  getPaymentStats: (instanceId: string) =>
    api.get<{ stats: { total_count: number; by_currency: Record<string, { count: number; total_amount: number }> } }>(`/admin/telegram/instances/${instanceId}/payments/stats`),
}
