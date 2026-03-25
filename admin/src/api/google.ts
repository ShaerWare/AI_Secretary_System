import { api } from './client'

export interface GoogleOAuthStatus {
  connected: boolean
  google_email: string | null
  scopes: string[]
}

export interface GoogleDriveFile {
  id: string
  name: string
  mimeType: string
  modifiedTime: string | null
  size: string | null
  isFolder: boolean
}

export interface GoogleDriveListResponse {
  files: GoogleDriveFile[]
  nextPageToken?: string
}

export interface GoogleDocContent {
  title: string
  text: string
  id: string
}

export interface GoogleSheetContent {
  title: string
  sheet: string
  sheets: string[]
  markdown: string
  rows: number
  id: string
}

export const googleApi = {
  // OAuth
  getAuthUrl: () =>
    api.get<{ auth_url: string }>('/admin/google/auth-url'),

  getStatus: () =>
    api.get<GoogleOAuthStatus>('/admin/google/status'),

  disconnect: () =>
    api.post<{ status: string }>('/admin/google/disconnect'),

  // Drive
  driveList: (folderId = 'root', query?: string, pageToken?: string) => {
    const params = new URLSearchParams({ folder_id: folderId })
    if (query) params.set('query', query)
    if (pageToken) params.set('page_token', pageToken)
    return api.get<GoogleDriveListResponse>(`/admin/google/drive/files?${params}`)
  },

  driveSearch: (query: string) =>
    api.get<GoogleDriveListResponse>(`/admin/google/drive/search?query=${encodeURIComponent(query)}`),

  // File content
  getFileContent: (fileId: string, mimeType: string, sheetName?: string) => {
    const params = new URLSearchParams({ mime_type: mimeType })
    if (sheetName) params.set('sheet_name', sheetName)
    return api.get<GoogleDocContent | GoogleSheetContent>(
      `/admin/google/drive/file/${fileId}/content?${params}`
    )
  },
}
