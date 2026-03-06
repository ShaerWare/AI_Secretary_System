import { api } from './client'

export interface Voice {
  id: string
  name: string
  engine: string
  description: string
  available: boolean
  samples_count?: number
  default?: boolean
}

export interface VoiceConfig {
  engine: string
  voice: string
}

export interface XttsParams {
  temperature: number
  repetition_penalty: number
  top_k: number
  top_p: number
  speed: number
  gpt_cond_len: number
  gpt_cond_chunk_len: number
}

export interface TtsPreset {
  display_name: string
  temperature: number
  repetition_penalty: number
  top_k: number
  top_p: number
  speed: number
}

// TTS API
export const ttsApi = {
  // Voices
  getVoices: () =>
    api.get<{ voices: Voice[]; current: VoiceConfig }>('/admin/voices'),

  getCurrentVoice: () =>
    api.get<VoiceConfig>('/admin/voice'),

  setVoice: (voice: string) =>
    api.post<{ status: string; engine: string; voice: string }>('/admin/voice', { voice }),

  testVoice: (voice: string) => {
    const token = localStorage.getItem('admin_token')
    return fetch(`/admin/voice/test`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ voice }),
    }).then(res => {
      if (!res.ok) throw new Error('Test failed')
      return res.blob()
    })
  },

  // XTTS Params
  getXttsParams: () =>
    api.get<{ default_preset: string; current_params: XttsParams }>('/admin/tts/xtts/params'),

  setXttsParams: (params: Partial<XttsParams>) =>
    api.post<{ status: string; params: Partial<XttsParams> }>('/admin/tts/xtts/params', params),

  // Piper Params
  getPiperParams: () =>
    api.get<{ speed: number; voices: Record<string, unknown> }>('/admin/tts/piper/params'),

  setPiperParams: (speed: number) =>
    api.post<{ status: string; speed: number }>('/admin/tts/piper/params', { speed }),

  // Presets
  getBuiltinPresets: () =>
    api.get<{ presets: Record<string, TtsPreset>; current: string }>('/admin/tts/presets'),

  setPreset: (preset: string) =>
    api.post<{ status: string; preset: string }>('/admin/tts/preset', { preset }),

  getCustomPresets: () =>
    api.get<{ presets: Record<string, Partial<XttsParams>> }>('/admin/tts/presets/custom'),

  createCustomPreset: (name: string, params: Partial<XttsParams>) =>
    api.post<{ status: string; preset: string }>('/admin/tts/presets/custom', { name, params }),

  updateCustomPreset: (name: string, params: Partial<XttsParams>) =>
    api.put<{ status: string; preset: string }>(`/admin/tts/presets/custom/${name}`, { name, params }),

  deleteCustomPreset: (name: string) =>
    api.delete<{ status: string; deleted: string }>(`/admin/tts/presets/custom/${name}`),

  // Cache
  getCacheStats: () =>
    api.get<{ cache_size: number; active_sessions: number }>('/admin/tts/cache'),

  clearCache: () =>
    api.delete<{ status: string; cleared_items: number }>('/admin/tts/cache'),

  // Test synthesis - returns audio blob for playback
  testSynthesize: (text: string, preset = 'natural') => {
    const token = localStorage.getItem('admin_token')
    return fetch(`/admin/tts/test`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ text, preset }),
    }).then(res => {
      if (!res.ok) throw new Error('Synthesis failed')
      return res.blob()
    })
  },
}
