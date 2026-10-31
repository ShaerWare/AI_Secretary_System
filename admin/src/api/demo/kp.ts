import type { DemoRoute } from "./types";
import { minutesAgo, nowISO } from "./store";
import type { KpEvent, KpQuote, KpRule, KpSettings, KpStatus } from "../kp";

function dayFromNow(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  return d.toISOString().slice(0, 10);
}

const settings: KpSettings = {
  validity_presets: [1, 2, 3],
  default_valid_days: 3,
  auto_draft: true,
  import_pim_quotes: true,
  send_template:
    "Здравствуйте{contact_comma}! Направляем коммерческое предложение {number} на сумму {total} {currency}. Цены действительны до {valid_until}.\nОткрыть КП: {link}",
  followup_instance_id: "",
  notify_telegram: true,
  notify_chat_id: "",
  notify_whatsapp: true,
  notify_whatsapp_numbers: "",
  notify_whatsapp_instance_id: "",
  tz_offset_hours: 5,
};

function quote(
  partial: Partial<KpQuote> & { id: number; number: string; status: KpStatus }
): KpQuote {
  return {
    pim_id: 1300 + partial.id,
    pim_status: null,
    origin: "assistant",
    customer: { name: "ТОО Демо", contact: "Азамат", phone: "77011234567" },
    items: [
      { sku: "02008001", name: "Кабель КГ-хл 1х70", price: 9483, count: 30, delivery: "5-7 дней" },
      {
        sku: "050600097",
        name: "КГтп 1х25 0,66 кВ",
        price: 2958,
        count: 10,
        delivery: "В наличии",
      },
    ],
    flags: [],
    total: 314070,
    currency: "₸",
    valid_days: 3,
    valid_until: dayFromNow(3),
    request_number: null,
    link: null,
    link_active: null,
    edit_url: null,
    delivery: "whatsapp",
    channel_instance_id: "wa-demo",
    target: "77011234567",
    email: null,
    message:
      "Здравствуйте, Азамат! Направляем коммерческое предложение КП-0021 на сумму 314 070 ₸.\nОткрыть КП: {link}",
    session_id: null,
    outbound_message_id: null,
    reissued_from: null,
    reissued_to: null,
    note: null,
    error: null,
    created_by: "assistant",
    decided_by: null,
    created: minutesAgo(25),
    updated: minutesAgo(25),
    decided_at: null,
    sent_at: null,
    viewed_at: null,
    closed_at: null,
    ...partial,
  };
}

const quotes: KpQuote[] = [
  quote({
    id: 1,
    number: "КП-0021",
    status: "pending",
    flags: ["«Рефлектометр РЕЙС-105»: точного совпадения в каталоге нет — подобрать вручную"],
  }),
  quote({
    id: 2,
    number: "КП-0019",
    status: "viewed",
    origin: "pim",
    customer: { name: "ТОО ЖИГЕРМУНАЙСЕРВИС", contact: "Азамат", phone: "77751528398" },
    total: 897710,
    valid_until: dayFromNow(0),
    link: "https://example.com/cp/demo",
    link_active: true,
    delivery: "link",
    sent_at: minutesAgo(60 * 20),
    viewed_at: minutesAgo(60 * 6),
  }),
  quote({
    id: 3,
    number: "КП-0012",
    status: "expired",
    origin: "pim",
    customer: { name: "ТОО KazGlobalSolution", contact: "Жолдас" },
    total: 282755,
    valid_until: dayFromNow(-2),
    delivery: "link",
    sent_at: minutesAgo(60 * 24 * 4),
  }),
];

const rules: KpRule[] = [
  {
    id: 1,
    name: "Черновик КП ждёт подтверждения",
    trigger: "not_approved",
    offset_hours: 2,
    action: "notify",
    message: "КП {number} ждёт подтверждения уже {hours} ч.",
    enabled: true,
    sort: 0,
  },
  {
    id: 2,
    name: "Клиент не открыл КП",
    trigger: "not_viewed",
    offset_hours: 12,
    action: "notify",
    message: "Клиент «{customer}» не открыл КП {number}.",
    enabled: true,
    sort: 10,
  },
  {
    id: 3,
    name: "КП просмотрено, ответа нет",
    trigger: "viewed_no_reply",
    offset_hours: 12,
    action: "client_message",
    message: "Здравствуйте! Удалось посмотреть КП {number}?",
    enabled: true,
    sort: 20,
  },
  {
    id: 4,
    name: "Срок действия заканчивается",
    trigger: "before_expiry",
    offset_hours: 6,
    action: "client_message",
    message: "Напоминаем: цены в КП {number} действуют до {valid_until}.",
    enabled: true,
    sort: 30,
  },
  {
    id: 5,
    name: "КП истекло — пересчитать",
    trigger: "expired",
    offset_hours: 0,
    action: "notify",
    message: "Срок КП {number} истёк — пересчитайте и перевыпустите.",
    enabled: true,
    sort: 40,
  },
  {
    id: 6,
    name: "Закрыть как проигранное",
    trigger: "expired",
    offset_hours: 72,
    action: "mark_lost",
    message: "",
    enabled: true,
    sort: 50,
  },
];

const events: KpEvent[] = [
  {
    id: 1,
    quote_id: 3,
    rule_id: 5,
    kind: "notify",
    text: "Срок КП КП-0012 истёк — пересчитайте цены и наличие и перевыпустите КП.",
    created: minutesAgo(90),
    acknowledged_by: null,
    acknowledged_at: null,
    number: "КП-0012",
    customer: "ТОО KazGlobalSolution",
  },
];

function counts() {
  const c: Record<string, number> = {};
  for (const q of quotes) c[q.status] = (c[q.status] ?? 0) + 1;
  return c;
}

function find(id: string): KpQuote | undefined {
  return quotes.find((q) => q.id === Number(id));
}

function setStatus(id: string, status: KpStatus) {
  const q = find(id);
  if (q) {
    q.status = status;
    q.updated = nowISO();
    if (status === "sent") {
      q.sent_at = nowISO();
      q.decided_by = "demo";
      q.link = "https://example.com/cp/demo";
    }
  }
  return { quote: q };
}

let nextRuleId = 100;

export const kpRoutes: DemoRoute[] = [
  {
    method: "GET",
    pattern: /^\/admin\/kp\/status$/,
    handler: () => ({ configured: true, ok: true, key_name: "Демо", can_send: true }),
  },
  {
    method: "GET",
    pattern: /^\/admin\/kp\/quotes$/,
    handler: ({ searchParams }) => {
      const status = searchParams.get("status");
      const list = status
        ? quotes.filter((q) => status.split(",").includes(q.status))
        : [...quotes];
      return {
        quotes: list,
        counts: counts(),
        unread_events: events.filter((e) => !e.acknowledged_at).length,
      };
    },
  },
  {
    method: "GET",
    pattern: /^\/admin\/kp\/quotes\/(\d+)$/,
    handler: ({ matches }) => ({ quote: { ...find(matches[1]), events: [] } }),
  },
  {
    method: "PUT",
    pattern: /^\/admin\/kp\/quotes\/(\d+)$/,
    handler: ({ matches, body }) => {
      const q = find(matches[1]);
      if (q) Object.assign(q, body as Partial<KpQuote>);
      return { quote: q };
    },
  },
  {
    method: "POST",
    pattern: /^\/admin\/kp\/quotes\/(\d+)\/approve$/,
    handler: ({ matches }) => setStatus(matches[1], "sent"),
  },
  {
    method: "POST",
    pattern: /^\/admin\/kp\/quotes\/(\d+)\/reject$/,
    handler: ({ matches }) => setStatus(matches[1], "rejected"),
  },
  {
    method: "POST",
    pattern: /^\/admin\/kp\/quotes\/(\d+)\/outcome$/,
    handler: ({ matches, body }) => setStatus(matches[1], (body as { status: KpStatus }).status),
  },
  {
    method: "POST",
    pattern: /^\/admin\/kp\/quotes\/(\d+)\/reissue$/,
    handler: ({ matches }) => {
      const old = find(matches[1]);
      const fresh = quote({
        ...(old as KpQuote),
        id: quotes.length + 1,
        number: `КП-00${30 + quotes.length}`,
        status: "pending",
        valid_until: dayFromNow(3),
        sent_at: null,
        link: null,
      });
      quotes.unshift(fresh);
      if (old) old.status = "superseded";
      return { quote: fresh };
    },
  },
  {
    method: "DELETE",
    pattern: /^\/admin\/kp\/quotes\/(\d+)$/,
    handler: ({ matches }) => {
      const i = quotes.findIndex((q) => q.id === Number(matches[1]));
      if (i >= 0) quotes.splice(i, 1);
      return { status: "ok" };
    },
  },
  {
    method: "POST",
    pattern: /^\/admin\/kp\/quotes$/,
    handler: ({ body }) => {
      const b = body as Partial<KpQuote>;
      const q = quote({
        ...b,
        id: quotes.length + 1,
        number: `КП-00${30 + quotes.length}`,
        status: "pending",
        origin: "manual",
      });
      quotes.unshift(q);
      return { quote: q };
    },
  },
  {
    method: "POST",
    pattern: /^\/admin\/kp\/quotes\/from-dialogue$/,
    handler: () => ({ quote: quotes[0] }),
  },
  {
    method: "POST",
    pattern: /^\/admin\/kp\/sync$/,
    handler: () => ({ ok: true, imported: 0, updated: 0 }),
  },
  { method: "GET", pattern: /^\/admin\/kp\/settings$/, handler: () => settings },
  {
    method: "PUT",
    pattern: /^\/admin\/kp\/settings$/,
    handler: ({ body }) => Object.assign(settings, body as Partial<KpSettings>),
  },
  { method: "GET", pattern: /^\/admin\/kp\/rules$/, handler: () => ({ rules }) },
  {
    method: "POST",
    pattern: /^\/admin\/kp\/rules$/,
    handler: ({ body }) => {
      const r = { ...(body as Omit<KpRule, "id">), id: nextRuleId++ };
      rules.push(r);
      return { rule: r };
    },
  },
  {
    method: "PUT",
    pattern: /^\/admin\/kp\/rules\/(\d+)$/,
    handler: ({ matches, body }) => {
      const r = rules.find((x) => x.id === Number(matches[1]));
      if (r) Object.assign(r, body as Partial<KpRule>);
      return { rule: r };
    },
  },
  {
    method: "DELETE",
    pattern: /^\/admin\/kp\/rules\/(\d+)$/,
    handler: ({ matches }) => {
      const i = rules.findIndex((x) => x.id === Number(matches[1]));
      if (i >= 0) rules.splice(i, 1);
      return { status: "ok" };
    },
  },
  {
    method: "GET",
    pattern: /^\/admin\/kp\/events$/,
    handler: ({ searchParams }) => ({
      events:
        searchParams.get("unread") === "true" ? events.filter((e) => !e.acknowledged_at) : events,
    }),
  },
  {
    method: "POST",
    pattern: /^\/admin\/kp\/events\/(\d+)\/ack$/,
    handler: ({ matches }) => {
      const e = events.find((x) => x.id === Number(matches[1]));
      if (e) {
        e.acknowledged_at = nowISO();
        e.acknowledged_by = "demo";
      }
      return { event: e };
    },
  },
];
