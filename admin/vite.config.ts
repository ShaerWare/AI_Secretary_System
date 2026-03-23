import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

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
    plugins: [vue()],
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
