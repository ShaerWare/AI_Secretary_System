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

  // Drive RAG projects
  driveRagProjects: () =>
    api.get<GoogleDriveProject[]>('/admin/google-drive/projects'),

  driveResolve: (link: string) =>
    api.get<GoogleDriveFile>(`/admin/google/drive/resolve?link=${encodeURIComponent(link)}`),

  createDriveRagProject: (data: CreateDriveSource) =>
    api.post<GoogleDriveProject>('/admin/google-drive/projects', data),

  updateDriveRagProject: (id: number, data: { name?: string; auto_sync?: boolean; file_ids?: string[] }) =>
    api.patch<GoogleDriveProject>(`/admin/google-drive/projects/${id}`, data),

  syncDriveRagProject: (id: number) =>
    api.post<{ status: string }>(`/admin/google-drive/projects/${id}/sync`),

  deleteDriveRagProject: (id: number) =>
    api.delete<{ status: string }>(`/admin/google-drive/projects/${id}`),
}

export interface GoogleDriveProject {
  id: number
  name: string
  user_id: number
  folder_id: string
  folder_name: string | null
  collection_id: number | null
  sync_status: string
  sync_error: string | null
  last_synced: string | null
  file_count: number
  total_size_bytes: number
  purpose: DriveSourcePurpose
  file_ids: string[]
  auto_sync: boolean
  sync_report: DriveSyncReport | null
  last_checked: string | null
  workspace_id: number
  created: string | null
  updated: string | null
}

export type DriveSourcePurpose = 'rag' | 'prices' | 'both'

export interface CreateDriveSource {
  name: string
  folder_id: string
  folder_name?: string
  purpose: DriveSourcePurpose
  file_ids: string[]
  auto_sync: boolean
}

export interface DriveSupplierMatch {
  key: string
  name: string
  price_file?: { pattern: string | string[]; files: string[] }
  stock_file?: { pattern: string | string[]; files: string[] }
}

export interface DriveSyncReport {
  missing: string[]
  skipped: { name: string; reason: string }[]
  prices?: {
    suppliers: DriveSupplierMatch[]
    unmatched: string[]
    ambiguous?: string[]
    installed: string[]
    archived: string[]
    conflicts: string[]
    duplicates: string[]
  }
  rag?: { documents: number; skipped: { name: string; reason: string }[] }
  parsed?: { supplier: string; rows?: number; offers?: number; error?: string }[]
}
