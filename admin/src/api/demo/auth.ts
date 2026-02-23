import type { DemoRoute } from './types'

const demoRole = import.meta.env.VITE_DEMO_ROLE || 'admin'
const demoDeploymentMode = import.meta.env.VITE_DEMO_DEPLOYMENT_MODE || 'full'

const ALL_MODULES = [
  'dashboard', 'chat', 'llm', 'speech', 'faq', 'channels',
  'gsm', 'system', 'audit', 'usage', 'settings', 'users',
  'sales', 'kanban', 'roles', 'billing',
]

function getDemoPermissions(): Record<string, string> {
  if (demoRole === 'admin') {
    return Object.fromEntries(ALL_MODULES.map(m => [m, 'manage']))
  }
  if (demoRole === 'user' || demoRole === 'web') {
    // operator: edit on core modules, view on read-only modules
    return {
      chat: 'edit', llm: 'edit', faq: 'edit', channels: 'edit',
      sales: 'edit', kanban: 'edit', settings: 'edit', usage: 'edit',
      audit: 'view', system: 'view', dashboard: 'view',
    }
  }
  // guest / viewer
  return {
    chat: 'view', faq: 'view', dashboard: 'view',
    audit: 'view', usage: 'view', kanban: 'view', sales: 'view',
  }
}

function createDemoToken(username: string): { access_token: string } {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = btoa(JSON.stringify({
    sub: username,
    role: demoRole,
    workspace_id: 1,
    exp: Math.floor(Date.now() / 1000) + 86400,
    iat: Math.floor(Date.now() / 1000),
    demo: true,
  }))
  const signature = btoa('demo-signature')
  return { access_token: `${header}.${payload}.${signature}` }
}

export const authRoutes: DemoRoute[] = [
  {
    method: 'POST',
    pattern: /^\/admin\/auth\/login$/,
    handler: ({ body }) => {
      const { username, password } = body as { username: string; password: string }
      if (
        (username === 'admin' && password === 'admin') ||
        (username === 'demo' && password === 'demo')
      ) {
        return createDemoToken(username)
      }
      throw new Error('Invalid credentials')
    },
  },
  {
    method: 'POST',
    pattern: /^\/admin\/auth\/logout$/,
    handler: () => ({ status: 'ok' }),
  },
  {
    method: 'POST',
    pattern: /^\/admin\/auth\/refresh$/,
    handler: () => createDemoToken('admin'),
  },
  {
    method: 'GET',
    pattern: /^\/admin\/auth\/me$/,
    handler: () => ({
      username: 'admin',
      role: demoRole,
      workspace_id: 1,
      deployment_mode: demoDeploymentMode,
    }),
  },
  {
    method: 'GET',
    pattern: /^\/admin\/deployment-mode$/,
    handler: () => ({ mode: demoDeploymentMode }),
  },
  {
    method: 'GET',
    pattern: /^\/admin\/auth\/permissions$/,
    handler: () => getDemoPermissions(),
  },
]
