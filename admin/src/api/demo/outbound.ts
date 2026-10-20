import type { DemoRoute } from "./types";
import { minutesAgo, nowISO } from "./store";
import type { OutboundMessage, OutboundSettings } from "../outbound";

const INSTANCE = "wa-demo";
const KEY = `whatsapp:${INSTANCE}`;

const settings: OutboundSettings = {
  instances: { [KEY]: { mode: "approval", ack_text: "" } },
  unanswered_minutes: 10,
  pending_alert_minutes: 30,
};

const messages: OutboundMessage[] = [
  {
    id: 1,
    channel: "whatsapp",
    instance_id: INSTANCE,
    target: "77011234567",
    session_id: null,
    client_text: "Здравствуйте, есть автомат АВР на 630А в наличии?",
    draft_text:
      "Здравствуйте! Да, есть ввод резерва АВР NXZM-630S/3B 3P 630A — 36 шт. на складе. Подготовить коммерческое предложение?",
    text: "Здравствуйте! Да, есть ввод резерва АВР NXZM-630S/3B 3P 630A — 36 шт. на складе. Подготовить коммерческое предложение?",
    edited: false,
    status: "pending",
    ack_sent: true,
    error: null,
    created: minutesAgo(4),
    updated: minutesAgo(4),
    decided_by: null,
    decided_at: null,
    sent_at: null,
  },
  {
    id: 2,
    channel: "whatsapp",
    instance_id: INSTANCE,
    target: "77029876543",
    session_id: null,
    client_text: "Сколько стоит доставка в Атырау?",
    draft_text:
      "Доставку в Атырау рассчитаем по весу заказа — пришлите, пожалуйста, список позиций.",
    text: "Доставку в Атырау рассчитаем по весу заказа — пришлите, пожалуйста, список позиций.",
    edited: false,
    status: "pending",
    ack_sent: true,
    error: null,
    created: minutesAgo(12),
    updated: minutesAgo(12),
    decided_by: null,
    decided_at: null,
    sent_at: null,
  },
  {
    id: 3,
    channel: "whatsapp",
    instance_id: INSTANCE,
    target: "77055550000",
    session_id: null,
    client_text: "Нужен контактор 18А",
    draft_text: "Есть контактор NC1-1810 18А.",
    text: "Есть контактор NC1-1810 18А, катушка 220В. Цена 6 237 ₸.",
    edited: true,
    status: "sent",
    ack_sent: true,
    error: null,
    created: minutesAgo(90),
    updated: minutesAgo(85),
    decided_by: "admin",
    decided_at: minutesAgo(85),
    sent_at: minutesAgo(85),
  },
];

function counts() {
  const c = { pending: 0, sent: 0, rejected: 0, failed: 0 };
  for (const m of messages) {
    if (m.status === "sending") c.failed++;
    else c[m.status]++;
  }
  return c;
}

function decide(id: number, status: "sent" | "rejected", text?: string) {
  const m = messages.find((x) => x.id === id);
  if (!m) return { message: null };
  if (text) {
    m.text = text;
    m.edited = m.text !== m.draft_text;
  }
  m.status = status;
  m.decided_by = "demo";
  m.decided_at = nowISO();
  if (status === "sent") m.sent_at = nowISO();
  return { message: m };
}

export const outboundRoutes: DemoRoute[] = [
  {
    method: "GET",
    pattern: /^\/admin\/outbound\/messages$/,
    handler: ({ searchParams }) => {
      const status = searchParams.get("status");
      const list = status
        ? messages.filter((m) => status.split(",").includes(m.status))
        : [...messages];
      return { messages: list, counts: counts() };
    },
  },
  {
    method: "PUT",
    pattern: /^\/admin\/outbound\/messages\/(\d+)$/,
    handler: ({ matches, body }) => {
      const m = messages.find((x) => x.id === Number(matches[1]));
      if (m) {
        m.text = (body as { text: string }).text;
        m.edited = m.text !== m.draft_text;
      }
      return { message: m };
    },
  },
  {
    method: "POST",
    pattern: /^\/admin\/outbound\/messages\/(\d+)\/approve$/,
    handler: ({ matches, body }) =>
      decide(Number(matches[1]), "sent", (body as { text?: string } | null)?.text),
  },
  {
    method: "POST",
    pattern: /^\/admin\/outbound\/messages\/(\d+)\/reject$/,
    handler: ({ matches }) => decide(Number(matches[1]), "rejected"),
  },
  {
    method: "DELETE",
    pattern: /^\/admin\/outbound\/messages\/(\d+)$/,
    handler: ({ matches }) => {
      const i = messages.findIndex((x) => x.id === Number(matches[1]));
      if (i >= 0) messages.splice(i, 1);
      return { status: "ok" };
    },
  },
  {
    method: "GET",
    pattern: /^\/admin\/outbound\/settings$/,
    handler: () => settings,
  },
  {
    method: "PUT",
    pattern: /^\/admin\/outbound\/settings$/,
    handler: ({ body }) => {
      Object.assign(settings, body as Partial<OutboundSettings>);
      return settings;
    },
  },
  {
    method: "GET",
    pattern: /^\/admin\/outbound\/monitor$/,
    handler: () => {
      const pending = messages.filter((m) => m.status === "pending");
      const cfg = settings.instances[KEY] ?? { mode: "auto", ack_text: "" };
      return {
        status: pending.length ? "warning" : "ok",
        checked_at: nowISO(),
        alerts: [],
        queue: {
          pending: pending.length,
          oldest_pending_seconds: pending.length ? 12 * 60 : null,
          failed: 0,
          sent_today: messages.filter((m) => m.status === "sent").length,
        },
        whatsapp: [
          {
            key: KEY,
            name: "Demo WhatsApp",
            approval: cfg.mode === "approval",
            conversations_72h: 7,
            last_inbound_at: minutesAgo(4),
            last_outbound_at: minutesAgo(85),
            unanswered_count: 0,
            unanswered: [],
            instance_id: INSTANCE,
            enabled: true,
            provider: "bridge",
            mode: cfg.mode,
            ack_text: cfg.ack_text,
            bot_running: true,
            bot_uptime_seconds: 3 * 3600,
            bridge_status: "connected",
            bridge_error: null,
            bridge_connected_at: minutesAgo(180),
          },
        ],
        channels: [
          {
            key: "telegram",
            name: "telegram",
            approval: false,
            conversations_72h: 3,
            last_inbound_at: minutesAgo(240),
            last_outbound_at: minutesAgo(239),
            unanswered_count: 0,
            unanswered: [],
          },
          {
            key: "widget",
            name: "widget",
            approval: false,
            conversations_72h: 12,
            last_inbound_at: minutesAgo(30),
            last_outbound_at: minutesAgo(30),
            unanswered_count: 0,
            unanswered: [],
          },
        ],
        crm: {
          connected: true,
          subdomain: "ai-sekretar-demo",
          auto_create_lead: true,
          last_sync_at: minutesAgo(35),
        },
        settings: {
          unanswered_minutes: settings.unanswered_minutes,
          pending_alert_minutes: settings.pending_alert_minutes,
        },
      };
    },
  },
];
