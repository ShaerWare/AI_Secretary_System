import { api } from './client'

// ============== Types ==============

export interface WooCommerceConfig {
  id: number
  store_url: string
  consumer_key_masked?: string
  consumer_secret_masked?: string
  is_connected: boolean
  sync_enabled: boolean
  last_sync_at: string | null
  products_count: number
  categories_count: number
  orders_count: number
  created: string | null
  updated: string | null
}

export interface WooCommerceStoreInfo {
  store_name: string
  description: string
  wc_version: string
  url: string
}

export interface WooCommerceDatasetStatus {
  synced: boolean
  collection_id: number | null
  collection_name?: string
  documents: number
  total_sections: number
  last_sync: string | null
  files: string[]
}

export interface WooCommerceDatasetSyncResult {
  status: string
  products: number
  categories: number
  orders: number
  files_written: number
  files_removed: number
  collection_id: number
  synced_at: string
}

// ============== API ==============

export const woocommerceApi = {
  // Config
  getConfig: () =>
    api.get<{ config: WooCommerceConfig | null }>('/admin/woocommerce/config'),

  saveConfig: (data: Record<string, unknown>) =>
    api.post<{ status: string; config: WooCommerceConfig }>('/admin/woocommerce/config', data),

  testConnection: () =>
    api.post<{ status: string; store_info: WooCommerceStoreInfo }>('/admin/woocommerce/test'),

  disconnect: () =>
    api.post<{ status: string }>('/admin/woocommerce/disconnect'),

  // Dataset
  datasetSync: () =>
    api.post<WooCommerceDatasetSyncResult>('/admin/woocommerce/dataset-sync'),

  datasetStatus: () =>
    api.get<WooCommerceDatasetStatus>('/admin/woocommerce/dataset-status'),

  datasetClear: () =>
    api.delete<{ status: string; files_removed: number }>('/admin/woocommerce/dataset'),
}
