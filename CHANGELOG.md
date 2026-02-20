# Changelog

All notable changes to AI Secretary System will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Chat Sharing Visual Indicators**: Colored dots (collapsed sidebar) and icons (expanded) to distinguish shared chats — blue for "shared with me", green for "I shared this". Badge counter on Share button matching RAG collections style. Batch `share_count` in `list_sessions` API via single GROUP BY query (#268)
- **Branch Tree Access Control**: Shared users see only the branch that was active at share time. Branch switch endpoint validates visibility. Per-share `branch_message_id` snapshot (#266, #269)
- **FAQ Sections**: Split 11-question FAQ into 3 themed sections (Product, Installation, Pricing & Support) with category menu and back-navigation
- **Usage Tracking & Limits**: Track TTS/STT/LLM usage with configurable limits
  - New models: `UsageLog`, `UsageLimits` in database
  - API endpoints: `/admin/usage/logs`, `/admin/usage/stats`, `/admin/usage/limits`, `/admin/usage/summary`
  - Admin UI: UsageView.vue with dashboard, usage bars, limit configuration
  - Daily/monthly limits with hard/soft enforcement and warning thresholds
- **Responsive Admin Panel**: Mobile-first layout for all screen sizes — collapsible sidebar, responsive headers, adaptive tables
- **News System**: Regex-based `## NEWS` parsing from GitHub PRs/commits for Telegram broadcasts (migrated from LLM generation)
- **Web Role**: New `web` role — same backend access as `user` but frontend hides infrastructure views (Dashboard, Services, vLLM, XTTS, Models, Finetune)
- **Widget Runtime Check**: Embeddable widget auto-hides when instance is disabled via `GET /widget/status`
- **Widget Session Persistence**: Replain-style chat history across page navigations — cookie + localStorage dual storage (30-day TTL), automatic history preloading via `GET /widget/chat/session/{id}`, open/closed state preserved in sessionStorage, `source="widget"` security check on public endpoints
- **Logo Sidebar Toggle**: Click logo to collapse/expand admin sidebar

### Fixed
- **Wiki Button**: Handler now matches both `"📚 Wiki"` and `"📚 Wiki проекта"` button text
- **Multi-Instance Bots**: Fixed crashes and empty responses in multi-instance Telegram bot mode
- **Bridge Auth Header**: Skip empty Authorization header for bridge provider
- **Cloud Mode**: Bridge auto-start, public widget endpoints for cloud-only deployments

### Changed
- **News Config**: Default `NEWS_GITHUB_REPOS` now only watches `ShaerWare/AI_Secretary_System` (removed bridge repo)

### Planned
- GSM Telephony real service (SIM7600E-H serial connection)
- amoCRM Integration
- Internet Restrictions Bypass (whitelist proxies)
- Backup & Restore functionality
- **Kanban + Gantt**: Built-in CRM-lite board with drag & drop, Gantt chart for task planning — as alternative to amoCRM (#270)
- **Google Docs/Sheets in chat context**: OAuth2 integration to attach Google documents as chat context files (#271)
- **Vision & OCR**: Photo recognition in chat — OCR for text extraction, multimodal LLM for image analysis (#272)
- **Notes system**: Markdown notes with tags, search, pinning, and chat message linking (#273)
- **AI → Google Docs/Sheets**: Generate reports and fill spreadsheets from AI responses (#274)

## [1.0.0] - 2026-02-05

### Added

#### Core Features
- **Multi-Voice TTS**: XTTS v2 (voice cloning), OpenVoice v2, Piper (CPU)
- **Speech-to-Text**: Vosk (realtime streaming) + Whisper (batch)
- **Multi-Persona LLM**: Secretary personas (Anna, Marina) with customizable prompts
- **Local LLM**: vLLM with Qwen2.5-7B/Llama-3.1-8B/DeepSeek-7B + LoRA fine-tuning
- **Cloud LLM Providers**: Gemini, Kimi, OpenAI, Claude, DeepSeek, OpenRouter with DB storage
- **Claude Bridge**: CLI-OpenAI bridge for using Claude Code as LLM backend
- **FAQ System**: Instant responses for common questions

#### Admin Panel (Vue 3 PWA)
- 15 tabs with full functionality
- JWT authentication with role-based access
- i18n support (Russian/English)
- 4 themes (Light, Dark, Night-Eyes, System)
- Real-time GPU monitoring with SSE
- Command palette (Ctrl+K)
- Audit logging with export

#### Integrations
- **Multi-Instance Telegram Bots**: Independent settings per bot
- **Multi-Instance Website Widgets**: Embeddable chat widgets
- **Telegram Payments**: YooKassa, YooMoney OAuth, Telegram Stars
- **Sales Bot Features**: Quiz funnels, segmentation, pricing calculator
- **VLESS Proxy**: Gemini routing through xray-core with auto-failover

#### Infrastructure
- Docker Compose deployment (GPU + CPU modes)
- SQLite + Redis database layer
- ~160 API endpoints across 15 modular routers
- OpenAI-compatible API for OpenWebUI integration

#### Security (v1.0.0)
- Rate limiting with slowapi (configurable per endpoint)
- CORS whitelist via environment variable
- Security headers middleware (X-Content-Type-Options, X-Frame-Options, etc.)
- JWT authentication with configurable secrets

#### Developer Experience
- CI/CD with GitHub Actions (lint, type check, security scan)
- Ruff linter + formatter configuration
- MyPy type checking (gradual adoption)
- ESLint + Prettier for Vue/TypeScript
- Pre-commit hooks
- Dependabot for dependency updates

### Changed
- Migrated from JSON files to SQLite database
- Restructured API into modular routers (`app/routers/`)
- Renamed `.env.docker` to `.env.docker.example`

### Security
- Added rate limiting to auth (10/min), chat (30/min), TTS (20/min) endpoints
- Added security headers (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection)
- Configurable CORS origins for production deployment

## [0.9.0] - 2026-01-28

### Added
- CI/CD Pipeline with GitHub Actions
- Code quality tools (ruff, mypy, eslint, prettier)
- Pre-commit hooks
- Telegram action buttons with LLM switching
- Consolidated improvement plan documentation

### Changed
- Removed legacy JSON synchronization code
- Database-first architecture for all data

## [0.8.0] - 2026-01-27

### Added
- Docker Compose deployment
- Multi-instance Telegram bots and widgets
- Cloud LLM providers system
- Voice Mode and Voice Input in chat
- DeepSeek LLM support
- LLM Models UI

### Changed
- Full migration to SQLite + Redis

## [0.7.0] - 2026-01-26

### Added
- SQLite + Redis database layer
- Vosk STT service for realtime recognition
- Chat TTS playback
- Audit logging system

### Changed
- Repository pattern for data access

---

[Unreleased]: https://github.com/ShaerWare/AI_Secretary_System/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/ShaerWare/AI_Secretary_System/releases/tag/v1.0.0
[0.9.0]: https://github.com/ShaerWare/AI_Secretary_System/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/ShaerWare/AI_Secretary_System/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/ShaerWare/AI_Secretary_System/releases/tag/v0.7.0
