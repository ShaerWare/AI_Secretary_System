import { api } from "./client";

// ============== Types ==============

export type OutboundStatus = "pending" | "sent" | "rejected" | "failed";
export type OutboundMode = "auto" | "approval";

export interface OutboundMessage {
  id: number;
  channel: string;
  instance_id: string;
  target: string;
  session_id: string | null;
  client_text: string | null;
  draft_text: string;
  text: string;
  edited: boolean;
  status: OutboundStatus | "sending";
  ack_sent: boolean;
  error: string | null;
  created: string | null;
  updated: string | null;
  decided_by: string | null;
  decided_at: string | null;
  sent_at: string | null;
}

export interface OutboundList {
  messages: OutboundMessage[];
  counts: Record<OutboundStatus, number>;
}

export interface OutboundInstanceConfig {
  mode: OutboundMode;
  ack_text: string;
}

export interface OutboundSettings {
  instances: Record<string, OutboundInstanceConfig>;
  unanswered_minutes: number;
  pending_alert_minutes: number;
}

export interface UnansweredConversation {
  session_id: string;
  target: string;
  waiting_seconds: number;
  preview: string;
}

export interface ChannelSummary {
  key: string;
  name: string;
  approval: boolean;
  conversations_72h: number;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  unanswered_count: number;
  unanswered: UnansweredConversation[];
}

export interface WhatsAppChannelSummary extends ChannelSummary {
  instance_id: string;
  enabled: boolean;
  provider: string;
  mode: OutboundMode;
  ack_text: string;
  bot_running: boolean;
  bot_uptime_seconds: number | null;
  bridge_status: string | null;
  bridge_error: string | null;
  bridge_connected_at: string | null;
}

export interface MonitorAlert {
  level: "error" | "warning";
  text: string;
}

export interface OutboundMonitor {
  status: "ok" | "warning" | "error";
  checked_at: string;
  alerts: MonitorAlert[];
  queue: {
    pending: number;
    oldest_pending_seconds: number | null;
    failed: number;
    sent_today: number;
  };
  whatsapp: WhatsAppChannelSummary[];
  channels: ChannelSummary[];
  crm: {
    connected: boolean;
    subdomain: string | null;
    auto_create_lead: boolean;
    last_sync_at: string | null;
  };
  settings: { unanswered_minutes: number; pending_alert_minutes: number };
}

// ============== API ==============

export const outboundApi = {
  list: (status?: string, limit = 50, offset = 0) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set("status", status);
    return api.get<OutboundList>(`/admin/outbound/messages?${params}`);
  },

  update: (id: number, text: string) =>
    api.put<{ message: OutboundMessage }>(`/admin/outbound/messages/${id}`, { text }),

  approve: (id: number, text?: string) =>
    api.post<{ message: OutboundMessage }>(`/admin/outbound/messages/${id}/approve`, { text }),

  reject: (id: number) =>
    api.post<{ message: OutboundMessage }>(`/admin/outbound/messages/${id}/reject`),

  remove: (id: number) => api.delete<{ status: string }>(`/admin/outbound/messages/${id}`),

  getSettings: () => api.get<OutboundSettings>("/admin/outbound/settings"),

  saveSettings: (data: Partial<OutboundSettings>) =>
    api.put<OutboundSettings>("/admin/outbound/settings", data),

  monitor: () => api.get<OutboundMonitor>("/admin/outbound/monitor"),
};
