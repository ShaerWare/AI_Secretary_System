import type { DemoRoute } from "./types";
import { minutesAgo } from "./store";
import type { ClientMemorySettings, ClientProfile } from "../clients";

const settings: ClientMemorySettings = {
  instances: { "whatsapp:wa-demo": true },
  idle_minutes: 30,
};

const profiles: ClientProfile[] = [
  {
    id: 1,
    channel: "whatsapp",
    external_id: "wa-demo:77011234567",
    display_name: "Азамат, ТОО «Каспий Монтаж»",
    card_md:
      "**Кто:** Азамат, снабженец\n**Компания и город:** ТОО «Каспий Монтаж», Атырау\n**Что спрашивал:** АВР на 630А, 3P; контакторы 18А с катушкой 220В — 12 шт.\n**Договорённости:** 2026-10-30 обещали уточнить срок поставки АВР\n**Открыто:** ждёт КП на контакторы",
    manager_notes: "Работает через тендеры, просит счёт с БИН заранее.",
    last_message_at: minutesAgo(95),
    last_session_id: "chat_demo_wa_1",
    sessions: ["chat_demo_wa_1"],
    created: minutesAgo(60 * 24 * 3),
    updated: minutesAgo(60),
  },
];

export const clientsRoutes: DemoRoute[] = [
  {
    method: "GET",
    pattern: /^\/admin\/clients\/settings$/,
    handler: () => settings,
  },
  {
    method: "PUT",
    pattern: /^\/admin\/clients\/settings$/,
    handler: ({ body }) => Object.assign(settings, body as Partial<ClientMemorySettings>),
  },
  {
    method: "GET",
    pattern: /^\/admin\/clients$/,
    handler: ({ searchParams }) => {
      const q = (searchParams.get("q") || "").toLowerCase();
      return {
        profiles: q
          ? profiles.filter((p) =>
              `${p.display_name} ${p.external_id} ${p.card_md}`.toLowerCase().includes(q)
            )
          : profiles,
      };
    },
  },
  {
    method: "PUT",
    pattern: /^\/admin\/clients\/(\d+)$/,
    handler: ({ matches, body }) => {
      const p = profiles.find((x) => x.id === Number(matches[1]));
      if (p) Object.assign(p, body as Partial<ClientProfile>);
      return p;
    },
  },
  {
    method: "DELETE",
    pattern: /^\/admin\/clients\/(\d+)$/,
    handler: ({ matches }) => {
      const i = profiles.findIndex((x) => x.id === Number(matches[1]));
      if (i >= 0) profiles.splice(i, 1);
      return { status: "ok" };
    },
  },
  {
    method: "POST",
    pattern: /^\/admin\/clients\/refresh$/,
    handler: () => profiles[0],
  },
];
