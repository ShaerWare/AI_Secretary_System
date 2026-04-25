// Product variant flag — configures which admin features/routes are
// exposed at build time. Set via `VITE_PRODUCT_VARIANT` env var.
//
// - `full` (default) — all modules visible. Matches the historical
//   admin panel used on ai-sekretar24.ru.
// - `lite` — strictly a subset: chat, LLM providers, RAG (wiki +
//   collection CRUD in finetune), website widget, Telegram, WhatsApp,
//   mobile app, account settings, users (for inviting teammates),
//   plus auxiliary routes (login, invite, about, root). Every other
//   route is removed from navigation and blocked by the router guard.
//
// Used from `router.ts` (navigation guard), `AccordionNav.vue` (menu
// filter), and `App.vue` (top shortcut for /kanban).

export type ProductVariant = 'full' | 'lite'

export const PRODUCT_VARIANT: ProductVariant =
  (import.meta.env.VITE_PRODUCT_VARIANT as ProductVariant) || 'full'

export const IS_LITE = PRODUCT_VARIANT === 'lite'

// Whitelist of paths the lite variant is allowed to render. Exact
// matches + prefix matches against this set (for /chat/:id, /users/:id,
// /invite/:code etc.).
const LITE_ALLOWED_PATHS: readonly string[] = [
  '/',
  '/login',
  '/chat',
  '/llm',
  '/wiki',
  '/finetune',
  '/widget',
  '/telegram',
  '/whatsapp',
  '/mobile-app',
  '/settings',
  '/users',
  '/about',
  '/invite',
] as const

export function isPathAllowed(path: string): boolean {
  if (!IS_LITE) return true
  if (path === '/') return true
  for (const allowed of LITE_ALLOWED_PATHS) {
    if (allowed === '/') continue
    if (path === allowed) return true
    if (path.startsWith(allowed + '/')) return true
  }
  return false
}
