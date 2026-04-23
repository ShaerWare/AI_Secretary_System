/**
 * Product variant flag. Set via VITE_PRODUCT_VARIANT env var.
 *
 * Vite inlines `import.meta.env.VITE_PRODUCT_VARIANT` at build time, so the
 * `IS_LITE` ternary branches below get constant-folded and Rollup tree-shakes
 * the unused route imports from the lite bundle.
 *
 * Default (no env) = "full" (current behaviour — prod server + local dev).
 * Lite = "lite" (DigiTax build, trimmed UI).
 */
export const PRODUCT_VARIANT =
  (import.meta.env.VITE_PRODUCT_VARIANT as string | undefined) || "full";

export const IS_LITE = PRODUCT_VARIANT === "lite";

/**
 * Paths hidden in lite builds. Used by AccordionNav and App-level shortcuts
 * for runtime UI filtering. Router does build-time tree-shaking separately
 * (see admin/src/router.ts).
 */
export const LITE_HIDDEN_PATHS = new Set<string>([
  "/dashboard",
  "/services",
  "/monitoring",
  "/models",
  "/audit",
  "/usage",
  "/tts",
  "/finetune",
  "/gsm",
  "/sales",
  "/crm",
  "/kanban",
  "/woocommerce",
]);
