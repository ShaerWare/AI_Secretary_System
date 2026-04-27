import { api } from './client'

export interface RSSFeed {
  id: number
  name: string
  url: string
  collection_id: number | null
  enabled: boolean
  fetch_full_text: boolean
  verify_ssl: boolean
  last_synced: string | null
  last_error: string | null
  sync_status: string
  item_count: number
  workspace_id: number
  created: string | null
  updated: string | null
}

export interface RSSFeedItem {
  id: number
  feed_id: number
  guid: string
  title: string
  link: string | null
  document_id: number | null
  pub_date: string | null
  created: string | null
}

export interface RSSFeedCreate {
  name: string
  url: string
  collection_id: number
  fetch_full_text?: boolean
  verify_ssl?: boolean
  enabled?: boolean
}

export interface RSSFeedUpdate {
  name?: string
  url?: string
  collection_id?: number
  fetch_full_text?: boolean
  verify_ssl?: boolean
  enabled?: boolean
}

export const rssFeedsApi = {
  list: (collectionId?: number) =>
    api.get<{ feeds: RSSFeed[] }>(
      collectionId !== undefined
        ? `/admin/rss/feeds?collection_id=${collectionId}`
        : '/admin/rss/feeds',
    ),

  create: (data: RSSFeedCreate) => api.post<RSSFeed>('/admin/rss/feeds', data),

  update: (id: number, data: RSSFeedUpdate) =>
    api.patch<RSSFeed>(`/admin/rss/feeds/${id}`, data),

  remove: (id: number) => api.delete<{ status: string }>(`/admin/rss/feeds/${id}`),

  syncOne: (id: number) =>
    api.post<{ status: string; feed_id: number }>(`/admin/rss/feeds/${id}/sync`),

  syncAll: () => api.post<{ status: string }>('/admin/rss/sync-all'),

  items: (id: number, limit = 50) =>
    api.get<{ feed_id: number; items: RSSFeedItem[] }>(
      `/admin/rss/feeds/${id}/items?limit=${limit}`,
    ),
}
