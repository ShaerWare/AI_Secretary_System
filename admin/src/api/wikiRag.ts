import { api, getAuthHeaders } from './client'

export interface WikiRagStats {
  sections_indexed: number
  files_indexed: number
  unique_tokens: number
  available: boolean
}

export interface WikiSearchResult {
  title: string
  body: string
  source_file: string
  score: number
}

export interface KnowledgeDocument {
  id: number
  filename: string
  title: string
  source_type: string
  file_size_bytes: number
  section_count: number
  collection_id: number | null
  owner_id: number | null
  created: string | null
  updated: string | null
}

export interface KnowledgeCollection {
  id: number
  name: string
  slug: string
  description: string | null
  enabled: boolean
  document_count: number
  created: string | null
  updated: string | null
}

export const wikiRagApi = {
  // Collections
  getCollections: () =>
    api.get<{ collections: KnowledgeCollection[] }>('/admin/wiki-rag/collections'),

  createCollection: (data: { name: string; slug?: string; description?: string; enabled?: boolean }) =>
    api.post<{ status: string; collection: KnowledgeCollection }>('/admin/wiki-rag/collections', data),

  getCollection: (id: number) =>
    api.get<{ collection: KnowledgeCollection }>(`/admin/wiki-rag/collections/${id}`),

  updateCollection: (id: number, data: { name?: string; description?: string; enabled?: boolean }) =>
    api.put<{ status: string; collection: KnowledgeCollection }>(`/admin/wiki-rag/collections/${id}`, data),

  deleteCollection: (id: number) =>
    api.delete<{ status: string; deleted: string }>(`/admin/wiki-rag/collections/${id}`),

  reloadCollection: (id: number) =>
    api.post<{ status: string; sections_indexed: number; files_indexed: number }>(`/admin/wiki-rag/collections/${id}/reload`),

  // Stats & search
  getStats: () =>
    api.get<{ stats: WikiRagStats; source_files: string[] }>('/admin/wiki-rag/stats'),

  reload: () =>
    api.post<{ status: string; previous_sections: number; current_sections: number; files_indexed: number }>('/admin/wiki-rag/reload'),

  search: (query: string, topK: number = 3, collectionId?: number) =>
    api.post<{ results: WikiSearchResult[]; query: string }>('/admin/wiki-rag/search', {
      query,
      top_k: topK,
      collection_id: collectionId ?? null,
    }),

  // Documents
  getDocuments: (collectionId?: number) => {
    const params = collectionId != null ? `?collection_id=${collectionId}` : ''
    return api.get<{ documents: KnowledgeDocument[]; synced: number }>(`/admin/wiki-rag/documents${params}`)
  },

  uploadDocument: async (file: File, collectionId?: number): Promise<{ status: string; document: KnowledgeDocument }> => {
    const formData = new FormData()
    formData.append('file', file)
    if (collectionId != null) {
      formData.append('collection_id', String(collectionId))
    }

    const response = await fetch('/admin/wiki-rag/documents/upload', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(error.detail || `HTTP error ${response.status}`)
    }

    return response.json()
  },

  getDocument: (id: number) =>
    api.get<{ document: KnowledgeDocument; content_preview: string }>(`/admin/wiki-rag/documents/${id}`),

  updateDocument: (id: number, data: { title?: string; content?: string }) =>
    api.put<{ status: string; document: KnowledgeDocument }>(`/admin/wiki-rag/documents/${id}`, data),

  deleteDocument: (id: number) =>
    api.delete<{ status: string; deleted: string }>(`/admin/wiki-rag/documents/${id}`),
}
