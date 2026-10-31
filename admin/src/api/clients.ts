import { api } from "./client";

// ============== Types ==============

export interface ClientProfile {
  id: number;
  channel: string;
  /** "<instance>:<phone>" for WhatsApp. */
  external_id: string;
  display_name: string;
  /** Written by the assistant after each dialogue; editable. */
  card_md: string;
  /** Written by people only — the assistant never rewrites it. */
  manager_notes: string;
  last_message_at: string | null;
  last_session_id: string | null;
  sessions: string[];
  created: string | null;
  updated: string | null;
}

export interface ClientMemorySettings {
  /** "whatsapp:<instance_id>" → memory on/off. */
  instances: Record<string, boolean>;
  idle_minutes: number;
}

// ============== API ==============

export const clientsApi = {
  list: (q = "", limit = 100) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (q) params.set("q", q);
    return api.get<{ profiles: ClientProfile[] }>(`/admin/clients?${params}`);
  },

  update: (
    id: number,
    data: Partial<Pick<ClientProfile, "display_name" | "manager_notes" | "card_md">>
  ) => api.put<ClientProfile>(`/admin/clients/${id}`, data),

  remove: (id: number) => api.delete<{ status: string }>(`/admin/clients/${id}`),

  refresh: (sessionId: string) =>
    api.post<ClientProfile>("/admin/clients/refresh", { session_id: sessionId }),

  getSettings: () => api.get<ClientMemorySettings>("/admin/clients/settings"),

  saveSettings: (data: Partial<ClientMemorySettings>) =>
    api.put<ClientMemorySettings>("/admin/clients/settings", data),
};
