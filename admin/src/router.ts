import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import DashboardView from './views/DashboardView.vue'
import ChatView from './views/ChatView.vue'
import ServicesView from './views/ServicesView.vue'
import LlmView from './views/LlmView.vue'
import TtsView from './views/TtsView.vue'
import FaqView from './views/FaqView.vue'
import FinetuneView from './views/FinetuneView.vue'
import MonitoringView from './views/MonitoringView.vue'
import ModelsView from './views/ModelsView.vue'
import WidgetView from './views/WidgetView.vue'
import TelegramView from './views/TelegramView.vue'
import WhatsAppView from './views/WhatsAppView.vue'
import GSMView from './views/GSMView.vue'
import AuditView from './views/AuditView.vue'
import UsageView from './views/UsageView.vue'
import SettingsView from './views/SettingsView.vue'
import LoginView from './views/LoginView.vue'
import CrmView from './views/CrmView.vue'
import SalesView from './views/SalesView.vue'
import AboutView from './views/AboutView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { title: 'Login', public: true }
    },
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
      meta: { title: 'Dashboard', icon: 'LayoutDashboard', excludeRoles: ['web'], localOnly: true }
    },
    {
      path: '/chat',
      name: 'chat',
      component: ChatView,
      meta: { title: 'Chat', icon: 'MessageCircle' }
    },
    {
      path: '/services',
      name: 'services',
      component: ServicesView,
      meta: { title: 'Services', icon: 'Server', minRole: 'user', excludeRoles: ['web'], localOnly: true }
    },
    {
      path: '/llm',
      name: 'llm',
      component: LlmView,
      meta: { title: 'LLM', icon: 'Brain', minRole: 'user' }
    },
    {
      path: '/tts',
      name: 'tts',
      component: TtsView,
      meta: { title: 'TTS', icon: 'Mic', minRole: 'user', excludeRoles: ['web'], localOnly: true }
    },
    {
      path: '/faq',
      name: 'faq',
      component: FaqView,
      meta: { title: 'FAQ', icon: 'MessageSquare' }
    },
    {
      path: '/finetune',
      name: 'finetune',
      component: FinetuneView,
      meta: { title: 'Fine-tune', icon: 'Sparkles' }
    },
    {
      path: '/monitoring',
      name: 'monitoring',
      component: MonitoringView,
      meta: { title: 'Monitoring', icon: 'Activity', minRole: 'user', excludeRoles: ['web'], localOnly: true }
    },
    {
      path: '/models',
      name: 'models',
      component: ModelsView,
      meta: { title: 'Models', icon: 'HardDrive', minRole: 'admin', localOnly: true }
    },
    {
      path: '/widget',
      name: 'widget',
      component: WidgetView,
      meta: { title: 'Widget', icon: 'Code2', minRole: 'user' }
    },
    {
      path: '/telegram',
      name: 'telegram',
      component: TelegramView,
      meta: { title: 'Telegram', icon: 'Send', minRole: 'user' }
    },
    {
      path: '/whatsapp',
      name: 'whatsapp',
      component: WhatsAppView,
      meta: { title: 'WhatsApp', icon: 'MessageCircle', minRole: 'user' }
    },
    {
      path: '/gsm',
      name: 'gsm',
      component: GSMView,
      meta: { title: 'GSM Telephony', icon: 'Phone', minRole: 'admin', localOnly: true }
    },
    {
      path: '/audit',
      name: 'audit',
      component: AuditView,
      meta: { title: 'Audit', icon: 'FileText', minRole: 'user', excludeRoles: ['web'] }
    },
    {
      path: '/usage',
      name: 'usage',
      component: UsageView,
      meta: { title: 'Usage', icon: 'BarChart3', minRole: 'user', excludeRoles: ['web'] }
    },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsView,
      meta: { title: 'Settings', icon: 'Settings', minRole: 'user' }
    },
    {
      path: '/crm',
      name: 'crm',
      component: CrmView,
      meta: { title: 'CRM', icon: 'Users', minRole: 'user', excludeRoles: ['web'] }
    },
    {
      path: '/sales',
      name: 'sales',
      component: SalesView,
      meta: { title: 'Sales', icon: 'ShoppingCart', minRole: 'user' }
    },
    {
      path: '/about',
      name: 'about',
      component: AboutView,
      meta: { title: 'About', icon: 'Info' }
    }
  ]
})

// Role level mapping for route guards
const ROLE_LEVEL: Record<string, number> = { guest: 0, web: 1, user: 1, admin: 2 }

// Navigation guard for authentication and authorization
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  // Check if route requires auth
  const isPublicRoute = to.meta.public === true

  if (!isPublicRoute && !authStore.isAuthenticated) {
    // Check if token is in localStorage but store not initialized
    const token = localStorage.getItem('admin_token')
    if (token && !authStore.isTokenExpired()) {
      // Token exists and valid, check role below
    } else {
      // Redirect to login
      next({ name: 'login', query: { redirect: to.fullPath } })
      return
    }
  } else if (to.name === 'login' && authStore.isAuthenticated) {
    // Already logged in, redirect to landing page
    const landing = authStore.isWeb ? 'chat' : 'dashboard'
    next({ name: landing })
    return
  }

  const userRole = authStore.user?.role || 'guest'

  // Check excludeRoles (e.g. 'web' excluded from dashboard, services)
  const excludeRoles = to.meta.excludeRoles as string[] | undefined
  if (excludeRoles?.includes(userRole)) {
    next({ name: 'chat' })
    return
  }

  // Check deployment mode (localOnly routes hidden in cloud mode)
  if (to.meta.localOnly && authStore.isCloudMode) {
    next({ name: 'chat' })
    return
  }

  // Check role-based access
  const minRole = to.meta.minRole as string | undefined
  if (minRole) {
    if (ROLE_LEVEL[userRole] < ROLE_LEVEL[minRole]) {
      // Insufficient role, redirect to landing page
      const landing = userRole === 'web' ? 'chat' : 'dashboard'
      next({ name: landing })
      return
    }
  }

  next()
})

export default router
