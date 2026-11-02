# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report them privately through GitHub: **[Security → Report a vulnerability](https://github.com/ShaerWare/AI_Secretary_System/security/advisories/new)**. Include the affected component, steps to reproduce and the impact you see. English or Russian is fine.

We aim to acknowledge reports within 3 days and to agree on a fix and disclosure timeline with you.

## Supported versions

Only the latest `main` gets security fixes.

## Hardening notes for self-hosters

- In the admin panel, `admin` / `admin` always opens the offline demo. Create real accounts with `scripts/manage_users.py` and use strong passwords.
- Set `ADMIN_JWT_SECRET` explicitly; an auto-generated one changes on restart.
- With cloud LLM providers, prompts, RAG context and messages leave your server. See the privacy table in [docs/REFERENCE.ru.md](docs/REFERENCE.ru.md#data-privacy-конфиденциальность-данных).
- Keep `.env` (API keys, bot tokens, `WHATSAPP_BRIDGE_TOKEN`) out of version control.
