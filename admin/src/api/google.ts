import { api } from './client'

export interface GoogleOAuthStatus {
  connected: boolean
  google_email: string | null
  scopes: string[]
}

export const googleApi = {
  getAuthUrl: () =>
    api.get<{ auth_url: string }>('/admin/google/auth-url'),

  getStatus: () =>
    api.get<GoogleOAuthStatus>('/admin/google/status'),

  disconnect: () =>
    api.post<{ status: string }>('/admin/google/disconnect'),
}
