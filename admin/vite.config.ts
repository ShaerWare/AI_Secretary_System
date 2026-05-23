import { fileURLToPath, URL } from 'node:url'
import { readFileSync, statSync } from 'node:fs'
import { extname, resolve } from 'node:path'
import { defineConfig, loadEnv, type PluginOption } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * Dev-only: serve site/ landing on /, /en/, /kk/ + its assets — same as nginx does in prod.
 * SPA stays on /admin/*. No effect on production build (vite build emits only the SPA).
 */
function landingDevPlugin(): PluginOption {
  const siteRoot = resolve(__dirname, '..', 'site')
  const mime: Record<string, string> = {
    '.html': 'text/html; charset=utf-8',
    '.css':  'text/css; charset=utf-8',
    '.js':   'application/javascript; charset=utf-8',
    '.svg':  'image/svg+xml',
    '.xml':  'application/xml; charset=utf-8',
    '.txt':  'text/plain; charset=utf-8',
    '.png':  'image/png',
    '.jpg':  'image/jpeg',
    '.webp': 'image/webp',
    '.ico':  'image/x-icon',
  }
  // Files under site/ root that should be reachable as /<name>. Anything not in this
  // set (e.g. /admin/, /v1/, /health, HMR) falls through to Vite / existing proxies.
  const rootAssets = new Set(['styles.css', 'main.js', 'favicon.svg', 'robots.txt', 'sitemap.xml'])

  function tryServe(reqPath: string): { body: Buffer; type: string } | null {
    // Normalize: strip query/hash, decode, drop leading slash.
    const clean = decodeURIComponent(reqPath.split('?')[0].split('#')[0])
    let rel: string | null = null
    if (clean === '/' || clean === '/index.html') rel = 'index.html'
    else if (clean === '/en' || clean === '/en/' || clean === '/en/index.html') rel = 'en/index.html'
    else if (clean === '/kk' || clean === '/kk/' || clean === '/kk/index.html') rel = 'kk/index.html'
    else if (clean.startsWith('/')) {
      const name = clean.slice(1)
      if (rootAssets.has(name)) rel = name
    }
    if (!rel) return null
    const full = resolve(siteRoot, rel)
    if (!full.startsWith(siteRoot)) return null // path traversal guard
    try {
      const st = statSync(full)
      if (!st.isFile()) return null
      return { body: readFileSync(full), type: mime[extname(full).toLowerCase()] || 'application/octet-stream' }
    } catch {
      return null
    }
  }

  return {
    name: 'landing-dev-serve',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url || req.method !== 'GET') return next()
        // Anything under /admin/, /v1/, /health, /webhooks → let proxy / SPA handle it.
        if (/^\/(admin|v1|health|webhooks|@vite|@id|@fs|node_modules|src)(\/|$|\?)/.test(req.url)) return next()
        const hit = tryServe(req.url)
        if (!hit) return next()
        res.statusCode = 200
        res.setHeader('Content-Type', hit.type)
        res.setHeader('Cache-Control', 'no-store')
        res.end(hit.body)
      })
    },
  }
}

// API path segments that should be proxied to the orchestrator.
// Everything else under /admin/ is served by Vite (SPA, HMR, assets).
const apiSegments = [
  'auth', 'chat', 'wiki-rag', 'telegram', 'whatsapp', 'widget', 'mobile',
  'faq', 'roles', 'workspace', 'backup', 'legal', 'llm', 'tts', 'stt',
  'services', 'voices', 'voice', 'models', 'logs', 'finetune', 'tts-finetune',
  'gsm', 'kanban', 'claude-code', 'github-webhook', 'github-repos', 'audit',
  'usage', 'monitor', 'deployment-mode', 'amocrm', 'woocommerce', 'bot-sales',
  'resource-shares', 'yoomoney', 'google',
]
const apiRegex = new RegExp(`^/admin/(${apiSegments.join('|')})(/|$)`)

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const isDemo = env.VITE_DEMO_MODE === 'true'

  return {
    plugins: [vue(), landingDevPlugin()],
    base: env.VITE_BASE_PATH || (isDemo ? '/' : '/admin/'),
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    server: {
      port: 5173,
      proxy: {
        '/admin': {
          target: 'http://localhost:8002',
          changeOrigin: true,
          bypass(req) {
            // Only proxy known API paths; let Vite handle SPA, assets, HMR
            if (!req.url || !apiRegex.test(req.url)) {
              return req.url
            }
          }
        },
        '/v1': {
          target: 'http://localhost:8002',
          changeOrigin: true
        },
        '/health': {
          target: 'http://localhost:8002',
          changeOrigin: true
        },
        '/webhooks': {
          target: 'http://localhost:8002',
          changeOrigin: true
        }
      }
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor': ['vue', 'vue-router', 'pinia'],
            'ui': ['radix-vue', 'lucide-vue-next'],
            'charts': ['chart.js', 'vue-chartjs'],
            'gantt': ['frappe-gantt']
          }
        }
      }
    }
  }
})
