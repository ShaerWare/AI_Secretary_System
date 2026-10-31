# Landing site

> Part of the project map in [CLAUDE.md](../../CLAUDE.md). Split out of CLAUDE.md verbatim on 2026-10-31; update it in the same PR as the code it describes.

## Landing Site (`site/`)

Static marketing site served at `https://ai-sekretar24.ru/` — no build step, no framework. Plain HTML/CSS/JS with i18n: `site/index.html` (ru, canonical), `site/en/index.html`, `site/kk/index.html`. Auto-detects browser language and redirects from root on first visit only (skipped if user already chose a language or arrived from an in-site language page). `site/main.js` handles the language switcher and shared interactions; `site/styles.css` is hand-written, no Tailwind. Deployed independently of admin/mobile — nginx serves `site/` from `/var/www/` directly. Auth CTAs link to `/login` (not `/admin/`).

**Landing lead form** (`site/` → Telegram): the static landing's lead form (`#leadForm`, handled in `site/main.js`) POSTs JSON to `POST /widget/lead` (in `modules/channels/widget/router_public.py`). Mounted under the already nginx-proxied `/widget/` prefix so no new nginx location is needed. The endpoint reads `LEAD_TELEGRAM_BOT_TOKEN` + `LEAD_TELEGRAM_CHAT_ID` from env (no secrets in the static site) and sends an HTML message to the owner's Telegram via `api.telegram.org/bot<token>/sendMessage`. Anti-spam: a hidden `company` honeypot field (CSS `.lead-form__hp`). If the backend is unreachable, the frontend falls back to opening `t.me/ai_sekretar24bot` with a pre-filled message. Locale + page URL are included in the notification.
