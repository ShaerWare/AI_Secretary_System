import { api, getAuthHeaders } from "./client";

// ============== Types ==============

export type KpStatus =
  | "pending"
  | "sending"
  | "sent"
  | "viewed"
  | "clarification"
  | "accepted"
  | "expired"
  | "lost"
  | "rejected"
  | "superseded"
  | "failed";

export type KpDelivery = "whatsapp" | "email" | "link";

export type KpTrigger =
  | "not_approved"
  | "not_viewed"
  | "viewed_no_reply"
  | "before_expiry"
  | "expired";

export type KpAction = "notify" | "client_message" | "mark_lost";

export interface KpItem {
  sku: string;
  name: string;
  price: number | null;
  count: number;
  delivery: string;
}

export interface KpCustomer {
  name?: string;
  contact?: string;
  phone?: string;
  email?: string;
  bin?: string;
}

export interface KpEvent {
  id: number;
  quote_id: number;
  rule_id: number | null;
  kind: string;
  text: string;
  created: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  number?: string | null;
  customer?: string | null;
}

export interface KpQuote {
  id: number;
  pim_id: number | null;
  number: string | null;
  status: KpStatus;
  pim_status: string | null;
  origin: "assistant" | "manual" | "pim";
  customer: KpCustomer;
  items: KpItem[];
  flags: string[];
  total: number | null;
  currency: string | null;
  valid_days: number | null;
  valid_until: string | null;
  request_number: string | null;
  link: string | null;
  link_active: boolean | null;
  edit_url: string | null;
  delivery: KpDelivery;
  channel_instance_id: string | null;
  target: string | null;
  email: string | null;
  message: string | null;
  session_id: string | null;
  outbound_message_id: number | null;
  reissued_from: number | null;
  reissued_to: number | null;
  note: string | null;
  error: string | null;
  created_by: string | null;
  decided_by: string | null;
  created: string | null;
  updated: string | null;
  decided_at: string | null;
  sent_at: string | null;
  viewed_at: string | null;
  closed_at: string | null;
  events?: KpEvent[];
}

export interface KpList {
  quotes: KpQuote[];
  counts: Record<string, number>;
  unread_events: number;
}

export interface KpSettings {
  validity_presets: number[];
  default_valid_days: number;
  auto_draft: boolean;
  import_pim_quotes: boolean;
  send_template: string;
  followup_instance_id: string;
  notify_telegram: boolean;
  notify_chat_id: string;
  tz_offset_hours: number;
}

export interface KpRule {
  id: number;
  name: string;
  trigger: KpTrigger;
  offset_hours: number;
  action: KpAction;
  message: string | null;
  enabled: boolean;
  sort: number;
}

export interface KpPimStatus {
  configured: boolean;
  ok: boolean;
  error?: string;
  key_name?: string;
  can_send?: boolean;
  account_id?: number;
}

export interface KpCreatePayload {
  customer: KpCustomer;
  items: Array<Pick<KpItem, "sku" | "name" | "count" | "delivery"> & { price: number }>;
  valid_days?: number;
  delivery: KpDelivery;
  channel_instance_id?: string;
  target?: string;
  email?: string;
  message?: string;
  request_number?: string;
  note?: string;
}

// ============== API ==============

export const kpApi = {
  status: () => api.get<KpPimStatus>("/admin/kp/status"),

  list: (status?: string, limit = 100) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (status) params.set("status", status);
    return api.get<KpList>(`/admin/kp/quotes?${params}`);
  },

  get: (id: number) => api.get<{ quote: KpQuote }>(`/admin/kp/quotes/${id}`),

  create: (data: KpCreatePayload) => api.post<{ quote: KpQuote }>("/admin/kp/quotes", data),

  fromDialogue: (sessionId: string) =>
    api.post<{ quote: KpQuote }>("/admin/kp/quotes/from-dialogue", { session_id: sessionId }),

  update: (id: number, data: Partial<KpCreatePayload>) =>
    api.put<{ quote: KpQuote }>(`/admin/kp/quotes/${id}`, data),

  approve: (id: number, text?: string) =>
    api.post<{ quote: KpQuote }>(`/admin/kp/quotes/${id}/approve`, { text }),

  reject: (id: number, note = "") =>
    api.post<{ quote: KpQuote }>(`/admin/kp/quotes/${id}/reject`, { note }),

  reissue: (id: number, validDays?: number, refreshPrices = false) =>
    api.post<{ quote: KpQuote }>(`/admin/kp/quotes/${id}/reissue`, {
      valid_days: validDays,
      refresh_prices: refreshPrices,
    }),

  outcome: (id: number, status: "accepted" | "lost", note = "") =>
    api.post<{ quote: KpQuote }>(`/admin/kp/quotes/${id}/outcome`, { status, note }),

  remove: (id: number) => api.delete<{ status: string }>(`/admin/kp/quotes/${id}`),

  sync: () => api.post<Record<string, unknown>>("/admin/kp/sync"),

  getSettings: () => api.get<KpSettings>("/admin/kp/settings"),

  saveSettings: (data: Partial<KpSettings>) => api.put<KpSettings>("/admin/kp/settings", data),

  rules: () => api.get<{ rules: KpRule[] }>("/admin/kp/rules"),

  createRule: (data: Omit<KpRule, "id">) => api.post<{ rule: KpRule }>("/admin/kp/rules", data),

  updateRule: (id: number, data: Partial<KpRule>) =>
    api.put<{ rule: KpRule }>(`/admin/kp/rules/${id}`, data),

  deleteRule: (id: number) => api.delete<{ status: string }>(`/admin/kp/rules/${id}`),

  events: (unread = false) =>
    api.get<{ events: KpEvent[] }>(`/admin/kp/events?unread=${unread ? "true" : "false"}`),

  ackEvent: (id: number) => api.post<{ event: KpEvent }>(`/admin/kp/events/${id}/ack`),

  /** PDF needs the auth header, so it is fetched and opened as a blob. */
  openPdf: async (id: number) => {
    const resp = await fetch(`/admin/kp/quotes/${id}/pdf`, { headers: getAuthHeaders() });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const url = URL.createObjectURL(await resp.blob());
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
};
