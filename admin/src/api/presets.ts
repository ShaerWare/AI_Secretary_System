import { api } from './client'

export interface PresetCollection {
  id: number
  slug: string
  name: string
}

export interface AssistantPreset {
  slug: string
  name: string
  description: string
  icon: string
  system_prompt: string | null
  rag_mode: string | null
  collections: PresetCollection[]
  knowledge_collection_ids: number[]
  ready: boolean
}

export const presetsApi = {
  list: () => api.get<{ presets: AssistantPreset[] }>('/admin/chat/assistant-presets'),
}
