import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type UserRole = 'admin' | 'user' | 'web' | 'guest'

export interface User {
  id: number
  username: string
  role: UserRole
  workspace_id: number
}

// Check if we're in dev mode (Vite sets this)
const isDev = import.meta.env.DEV
const isDemo = import.meta.env.VITE_DEMO_MODE === 'true'

export type DeploymentMode = 'full' | 'cloud' | 'local'

const LEVEL_ORDER: Record<string, number> = { view: 1, edit: 2, manage: 3 }

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('admin_token'))
  const user = ref<User | null>(null)
  const deploymentMode = ref<DeploymentMode>('full')
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const permissions = ref<Record<string, string>>({})

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => canManage('users'))
  const isCloudMode = computed(() => deploymentMode.value === 'cloud')
  const isChatOnlyUser = computed(() => {
    if (Object.keys(permissions.value).length === 0) return false
    return !isAdmin.value
  })

  function hasModule(module: string): boolean {
    return module in permissions.value
  }
  function canView(module: string): boolean {
    return (LEVEL_ORDER[permissions.value[module]] ?? 0) >= 1
  }
  function canEdit(module: string): boolean {
    return (LEVEL_ORDER[permissions.value[module]] ?? 0) >= 2
  }
  function canManage(module: string): boolean {
    return (LEVEL_ORDER[permissions.value[module]] ?? 0) >= 3
  }

  // Fetch deployment mode from backend
  async function fetchDeploymentMode() {
    try {
      const response = await fetch('/admin/deployment-mode')
      if (response.ok) {
        const data = await response.json()
        deploymentMode.value = data.mode || 'full'
      }
    } catch {
      // Default to full if backend unreachable
    }
  }

  // Fetch permissions from backend
  async function fetchPermissions() {
    try {
      const resp = await fetch('/admin/auth/permissions', { headers: getAuthHeaders() })
      if (resp.ok) {
        permissions.value = await resp.json()
      } else if (resp.status === 401) {
        // Token invalid/expired/session revoked — force logout
        logout()
      }
    } catch { /* default empty */ }
  }

  // Initialize from localStorage
  if (token.value) {
    try {
      const payload = JSON.parse(atob(token.value.split('.')[1]))
      user.value = {
        id: payload.user_id || 0,
        username: payload.sub,
        role: payload.role,
        workspace_id: payload.workspace_id || 1,
      }
      // Fetch deployment mode and permissions on init
      fetchDeploymentMode()
      fetchPermissions()
    } catch {
      token.value = null
      localStorage.removeItem('admin_token')
    }
  }

  // Create a mock JWT for dev mode when backend is unavailable
  function createDevToken(username: string): string {
    const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
    const payload = btoa(JSON.stringify({
      sub: username,
      user_id: 0,
      role: import.meta.env.VITE_DEMO_ROLE || 'admin',
      workspace_id: 1,
      exp: Math.floor(Date.now() / 1000) + 86400, // 24 hours
      iat: Math.floor(Date.now() / 1000),
      dev: true
    }))
    const signature = btoa('dev-signature')
    return `${header}.${payload}.${signature}`
  }

  async function login(username: string, password: string): Promise<boolean> {
    isLoading.value = true
    error.value = null

    try {
      const response = await fetch('/admin/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      })

      if (!response.ok) {
        const data = await response.json()
        error.value = data.detail || 'Invalid credentials'
        return false
      }

      const data = await response.json()
      token.value = data.access_token
      localStorage.setItem('admin_token', data.access_token)

      // Decode JWT payload
      const payload = JSON.parse(atob(data.access_token.split('.')[1]))
      user.value = {
        id: payload.user_id || 0,
        username: payload.sub,
        role: payload.role,
        workspace_id: payload.workspace_id || 1,
      }

      // Fetch deployment mode and permissions from backend
      await fetchDeploymentMode()
      await fetchPermissions()

      return true
    } catch (e) {
      // In dev mode, allow login without backend
      if ((isDev || isDemo) && ((username === 'admin' && password === 'admin') || (username === 'demo' && password === 'demo'))) {
        console.warn('⚠️ Dev/Demo mode: Backend unavailable, using mock authentication')
        const devToken = createDevToken(username)
        token.value = devToken
        localStorage.setItem('admin_token', devToken)
        user.value = { id: 0, username, role: (import.meta.env.VITE_DEMO_ROLE || 'admin') as UserRole, workspace_id: 1 }
        error.value = null
        return true
      }

      error.value = 'Connection error - Backend not running'
      return false
    } finally {
      isLoading.value = false
    }
  }

  function logout() {
    token.value = null
    user.value = null
    permissions.value = {}
    localStorage.removeItem('admin_token')
  }

  function getAuthHeaders(): Record<string, string> {
    if (token.value) {
      return { 'Authorization': `Bearer ${token.value}` }
    }
    return {}
  }

  // Check if token is expired
  function isTokenExpired(): boolean {
    if (!token.value) return true
    try {
      const payload = JSON.parse(atob(token.value.split('.')[1]))
      return payload.exp * 1000 < Date.now()
    } catch {
      return true
    }
  }

  return {
    token,
    user,
    deploymentMode,
    isLoading,
    error,
    permissions,
    isAuthenticated,
    isAdmin,
    isCloudMode,
    isChatOnlyUser,
    hasModule,
    canView,
    canEdit,
    canManage,
    login,
    logout,
    getAuthHeaders,
    isTokenExpired
  }
})
