// In-memory store for demo mode session persistence
// Data persists during the browser session but resets on reload

interface StoreState {
  faq: Record<string, string>
  chatSessions: ChatSessionData[]
  botInstances: BotInstanceData[]
  whatsappInstances: WhatsAppInstanceData[]
  widgetInstances: WidgetInstanceData[]
  cloudProviders: CloudProviderData[]
  llmPresets: LlmPresetData[]
  auditLogs: AuditLogData[]
  usageLimits: UsageLimitData[]
  customTtsPresets: Record<string, Record<string, number>>
  initialized: boolean
}

export interface WhatsAppInstanceData {
  id: string
  name: string
  description?: string
  enabled: boolean
  auto_start: boolean
  phone_number_id: string
  waba_id?: string
  access_token_masked?: string
  verify_token?: string
  app_secret?: string
  webhook_port: number
  llm_backend: string
  system_prompt?: string
  tts_enabled: boolean
  tts_engine: string
  tts_voice: string
  tts_preset?: string
  rag_mode?: string
  knowledge_collection_id?: number | null
  knowledge_collection_ids?: number[]
  allowed_phones: string[]
  blocked_phones: string[]
  rate_limit_count?: number | null
  rate_limit_hours?: number | null
  running?: boolean
  pid?: number
  created?: string
  updated?: string
}

export interface ChatSessionData {
  id: string
  title: string
  messages: ChatMessageData[]
  system_prompt?: string
  pinned: boolean
  context_files?: { name: string; content: string }[]
  source: 'admin' | 'telegram' | 'widget' | 'whatsapp' | null
  source_id?: string
  created: string
  updated: string
}

export interface ChatMessageData {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  edited?: boolean
}

export interface BotInstanceData {
  id: string
  name: string
  description?: string
  enabled: boolean
  bot_token_masked?: string
  api_url?: string
  allowed_users: number[]
  admin_users: number[]
  welcome_message?: string
  unauthorized_message?: string
  error_message?: string
  typing_enabled: boolean
  llm_backend: string
  llm_persona: string
  system_prompt?: string
  tts_engine: string
  tts_voice: string
  tts_preset?: string
  rag_mode?: string
  knowledge_collection_id?: number | null
  knowledge_collection_ids?: number[]
  action_buttons: ActionButtonData[]
  payment_enabled: boolean
  stars_enabled: boolean
  payment_products: PaymentProductData[]
  payment_success_message?: string
  yoomoney_configured?: boolean
  running?: boolean
  pid?: number
  created?: string
  updated?: string
}

export interface ActionButtonData {
  id: string
  label: string
  icon?: string
  enabled: boolean
  order: number
  llm_backend?: string
  system_prompt?: string
}

export interface PaymentProductData {
  id: string
  title: string
  description: string
  price_rub: number
  price_stars: number
}

export interface WidgetInstanceData {
  id: string
  name: string
  description?: string
  enabled: boolean
  title: string
  greeting?: string
  placeholder: string
  placeholder_color?: string
  placeholder_font?: string
  primary_color: string
  button_icon?: string
  button_size?: number
  button_offset_bottom?: number
  button_offset_side?: number
  position: 'left' | 'right'
  allowed_domains: string[]
  tunnel_url?: string
  llm_backend: string
  llm_persona: string
  system_prompt?: string
  tts_engine: string
  tts_voice: string
  tts_preset?: string
  rag_mode?: string
  knowledge_collection_id?: number | null
  knowledge_collection_ids?: number[]
  created?: string
  updated?: string
}

export interface CloudProviderData {
  id: string
  name: string
  provider_type: string
  api_key_masked?: string
  base_url?: string | null
  model_name: string
  enabled: boolean
  is_default: boolean
  config?: Record<string, unknown>
  description?: string | null
  created?: string
  updated?: string
}

export interface LlmPresetData {
  id: string
  name: string
  description?: string | null
  system_prompt?: string | null
  temperature: number
  max_tokens: number
  top_p: number
  repetition_penalty: number
  is_default: boolean
  enabled: boolean
  created?: string
  updated?: string
}

export interface AuditLogData {
  id: number
  timestamp: string
  action: string
  resource: string
  resource_id: string | null
  user_id: string | null
  user_ip: string | null
  details: string | null
}

export interface UsageLimitData {
  id: number
  service_type: string
  limit_type: string
  limit_value: number
  warning_threshold: number
  hard_limit: boolean
  enabled: boolean
  created?: string
  updated?: string
}

const store: StoreState = {
  faq: {},
  chatSessions: [],
  botInstances: [],
  whatsappInstances: [],
  widgetInstances: [],
  cloudProviders: [],
  llmPresets: [],
  auditLogs: [],
  usageLimits: [],
  customTtsPresets: {},
  initialized: false,
}

export function getStore(): StoreState {
  return store
}

export function initStore(initialData: Partial<StoreState>) {
  if (store.initialized) return
  Object.assign(store, initialData, { initialized: true })
}

export function generateId(): string {
  return Math.random().toString(36).substring(2, 10)
}

export function nowISO(): string {
  return new Date().toISOString()
}

export function daysAgo(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString()
}

export function minutesAgo(n: number): string {
  const d = new Date()
  d.setMinutes(d.getMinutes() - n)
  return d.toISOString()
}
