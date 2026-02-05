import { api } from './client'

// Types
export interface UsageLog {
  id: number
  timestamp: string
  service_type: 'tts' | 'stt' | 'llm'
  action: string
  source?: string | null
  source_id?: string | null
  units_consumed: number
  cost_usd?: number | null
  details?: Record<string, unknown> | null
}

export interface UsageStats {
  period_days: number
  from_date: string
  by_service: Record<
    string,
    {
      units: number
      requests: number
      cost_usd: number
    }
  >
  by_source: Record<
    string,
    {
      units: number
      requests: number
    }
  >
  daily: Array<{
    date: string
    units: number
    requests: number
    cost_usd: number
  }>
}

export interface UsageLimit {
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

export interface UsageSummary {
  summary: Record<
    string,
    {
      daily: {
        used: number
        limit: number | null
        percent: number
      }
      monthly: {
        used: number
        limit: number | null
        percent: number
      }
    }
  >
}

export interface UsageQueryParams {
  service_type?: string
  action?: string
  source?: string
  from_date?: string
  to_date?: string
  limit?: number
  offset?: number
}

export interface UsageCheckResult {
  service_type: string
  limit_type: string
  current_usage: number
  within_limits: boolean
  warnings: string[]
  blocked: boolean
  limits: Array<{
    limit_type: string
    limit_value: number
    current_usage: number
    usage_percent: number
    hard_limit: boolean
  }>
}

// Usage API
export const usageApi = {
  // Logs
  getLogs: (params?: UsageQueryParams) => {
    const query = new URLSearchParams()
    if (params?.service_type) query.set('service_type', params.service_type)
    if (params?.action) query.set('action', params.action)
    if (params?.source) query.set('source', params.source)
    if (params?.from_date) query.set('from_date', params.from_date)
    if (params?.to_date) query.set('to_date', params.to_date)
    if (params?.limit) query.set('limit', params.limit.toString())
    if (params?.offset) query.set('offset', params.offset.toString())

    const queryStr = query.toString()
    return api.get<{ logs: UsageLog[]; count: number }>(
      `/admin/usage/logs${queryStr ? '?' + queryStr : ''}`
    )
  },

  getStats: (serviceType?: string, periodDays?: number) => {
    const query = new URLSearchParams()
    if (serviceType) query.set('service_type', serviceType)
    if (periodDays) query.set('period_days', periodDays.toString())

    const queryStr = query.toString()
    return api.get<{ stats: UsageStats }>(`/admin/usage/stats${queryStr ? '?' + queryStr : ''}`)
  },

  getSummary: () => api.get<UsageSummary>('/admin/usage/summary'),

  // Limits
  getLimits: (enabledOnly: boolean = true) =>
    api.get<{ limits: UsageLimit[] }>(`/admin/usage/limits?enabled_only=${enabledOnly}`),

  getLimit: (serviceType: string, limitType: string) =>
    api.get<{ limit: UsageLimit }>(`/admin/usage/limits/${serviceType}/${limitType}`),

  setLimit: (
    serviceType: string,
    limitType: string,
    limitValue: number,
    hardLimit: boolean = false,
    warningThreshold: number = 80
  ) =>
    api.post<{ limit: UsageLimit }>('/admin/usage/limits', {
      service_type: serviceType,
      limit_type: limitType,
      limit_value: limitValue,
      hard_limit: hardLimit,
      warning_threshold: warningThreshold,
    }),

  deleteLimit: (serviceType: string, limitType: string) =>
    api.delete<{ status: string }>(`/admin/usage/limits/${serviceType}/${limitType}`),

  // Check usage
  checkUsage: (serviceType: string, limitType: string = 'daily') =>
    api.get<UsageCheckResult>(`/admin/usage/check/${serviceType}?limit_type=${limitType}`),

  // Maintenance
  cleanup: (days: number = 90) =>
    api.post<{ status: string; deleted: number; retention_days: number }>(
      `/admin/usage/cleanup?days=${days}`
    ),

  // Log usage (for internal use)
  logUsage: (data: {
    service_type: string
    action: string
    units_consumed?: number
    source?: string
    source_id?: string
    cost_usd?: number
    details?: Record<string, unknown>
  }) => api.post<{ log: UsageLog }>('/admin/usage/log', data),
}
