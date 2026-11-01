# Admin panel frontend

> Part of the project map in [CLAUDE.md](../../CLAUDE.md). Split out of CLAUDE.md verbatim on 2026-10-31; update it in the same PR as the code it describes.

## Frontend Architecture

**Stack**: Vue 3 + Composition API + TypeScript, Vite, Pinia (persisted), Vue Router (hash history), TanStack Vue Query, vue-i18n (ru/en/kk), TailwindCSS + radix-vue, lucide-vue-next. Path alias `@` → `admin/src/`.

**Routing** (`admin/src/router.ts`): `createWebHashHistory`. Routes use `meta` fields: `public` (bypass auth), `localOnly` (hidden in cloud mode), `module` (RBAC module name), `minLevel` (view/edit/manage).

**Stores** (`admin/src/stores/`): Key store `auth.ts` holds JWT, user, `deploymentMode`, `permissions`. Exposes `isAdmin`, `isCloudMode`, `hasModule()`, `canView()`, `canEdit()`, `canManage()`. **Toast API**: `toast.success/error/warning/info(title)` — do NOT use `toast.show()` (different signature: `show(type, title, message?)`). **Confirm API**: `confirm.confirm({ title, message, confirmText, type })` returns `Promise<boolean>` — no `ask()` method.

**API layer** (`admin/src/api/`): `client.ts` provides `api.get/post/put/delete/upload` + `createSSE()` (auto-injects JWT). Domain files build on it. All re-exported from `api/index.ts`.

**Demo mode** (`admin/src/api/client.ts`): a patched `window.fetch` answers API calls with mock data from the domain files in `admin/src/api/demo/`. Two ways in: at build time `VITE_DEMO_MODE=true` (`npm run build -- --mode demo` / `demo-web`, `.env.demo*`) — on from page load; and at **runtime** `activateDemoMode()` — logging in as admin/admin (`stores/auth.ts:login` — that pair **always** goes to the offline demo, on any build, without calling the backend; a real admin account needs another password) or a stored demo token. The runtime path is why the demo module is a lazy `import("./demo/index")` that is present in every production bundle — tell builds apart by the base path, not by grep (see [deployment](deployment.md)).

**Product variant** (`VITE_PRODUCT_VARIANT` env var, defaults to `full`): Set to `lite` to ship a stripped admin panel. Lite variant whitelists `/chat`, `/llm`, `/wiki`, `/finetune` (collections CRUD), `/widget`, `/telegram`, `/whatsapp`, `/mobile-app`, `/settings`, `/users`, `/about`, `/login`, `/invite/*` — everything else is blocked by the router guard and hidden from nav. Scripts: `npm run dev:lite` and `npm run build:lite`. Central helper: `admin/src/config/productVariant.ts` (`IS_LITE`, `isPathAllowed()`).

**Vite base path**: Production `/admin/` (served by FastAPI). Demo/standalone: `/` (via `VITE_BASE_PATH` or `.env.production.local`).
