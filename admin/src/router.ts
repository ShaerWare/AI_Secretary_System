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
import KanbanView from './views/KanbanView.vue'
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
      meta: { title: 'Dashboard', icon: 'LayoutDashboard', module: 'dashboard', localOnly: true }
    },
    {
      path: '/chat',
      name: 'chat',
      component: ChatView,
      meta: { title: 'Chat', icon: 'MessageCircle', module: 'chat' }
    },
    {
      path: '/services',
      name: 'services',
      component: ServicesView,
      meta: { title: 'Services', icon: 'Server', module: 'system', minLevel: 'manage', localOnly: true }
    },
    {
      path: '/llm',
      name: 'llm',
      component: LlmView,
      meta: { title: 'LLM', icon: 'Brain', module: 'llm' }
    },
    {
      path: '/tts',
      name: 'tts',
      component: TtsView,
      meta: { title: 'TTS', icon: 'Mic', module: 'speech', localOnly: true }
    },
    {
      path: '/wiki',
      name: 'wiki',
      component: FaqView,
      meta: { title: 'Wiki', icon: 'BookOpen', module: 'faq' }
    },
    {
      path: '/finetune',
      name: 'finetune',
      component: FinetuneView,
      meta: { title: 'Fine-tune', icon: 'Sparkles', module: 'llm' }
    },
    {
      path: '/monitoring',
      name: 'monitoring',
      component: MonitoringView,
      meta: { title: 'Monitoring', icon: 'Activity', module: 'system', localOnly: true }
    },
    {
      path: '/models',
      name: 'models',
      component: ModelsView,
      meta: { title: 'Models', icon: 'HardDrive', module: 'system', minLevel: 'manage', localOnly: true }
    },
    {
      path: '/widget',
      name: 'widget',
      component: WidgetView,
      meta: { title: 'Widget', icon: 'Code2', module: 'channels' }
    },
    {
      path: '/telegram',
      name: 'telegram',
      component: TelegramView,
      meta: { title: 'Telegram', icon: 'Send', module: 'channels' }
    },
    {
      path: '/whatsapp',
      name: 'whatsapp',
      component: WhatsAppView,
      meta: { title: 'WhatsApp', icon: 'MessageCircle', module: 'channels' }
    },
    {
      path: '/gsm',
      name: 'gsm',
      component: GSMView,
      meta: { title: 'GSM Telephony', icon: 'Phone', module: 'gsm', localOnly: true }
    },
    {
      path: '/audit',
      name: 'audit',
      component: AuditView,
      meta: { title: 'Audit', icon: 'FileText', module: 'audit' }
    },
    {
      path: '/usage',
      name: 'usage',
      component: UsageView,
      meta: { title: 'Usage', icon: 'BarChart3', module: 'usage' }
    },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsView,
      meta: { title: 'Settings', icon: 'Settings' }
    },
    {
      path: '/crm',
      name: 'crm',
      component: CrmView,
      meta: { title: 'CRM', icon: 'Users', module: 'sales' }
    },
    {
      path: '/kanban',
      name: 'kanban',
      component: KanbanView,
      meta: { title: 'Kanban', icon: 'ClipboardList', module: 'kanban' }
    },
    {
      path: '/sales',
      name: 'sales',
      component: SalesView,
      meta: { title: 'Sales', icon: 'ShoppingCart', module: 'sales' }
    },
    {
      path: '/about',
      name: 'about',
      component: AboutView,
      meta: { title: 'About', icon: 'Info' }
    }
  ]
})

const LVL: Record<string, number> = { view: 1, edit: 2, manage: 3 }

// Navigation guard for authentication and authorization
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  // Check if route requires auth
  const isPublicRoute = to.meta.public === true

  if (!isPublicRoute && !authStore.isAuthenticated) {
    // Check if token is in localStorage but store not initialized
    const token = localStorage.getItem('admin_token')
    if (token && !authStore.isTokenExpired()) {
      // Token exists and valid, check permissions below
    } else {
      // Redirect to login
      next({ name: 'login', query: { redirect: to.fullPath } })
      return
    }
  } else if (to.name === 'login' && authStore.isAuthenticated) {
    // Already logged in, redirect to landing page
    const landing = authStore.hasModule('dashboard') && !authStore.isCloudMode ? 'dashboard' : 'chat'
    next({ name: landing })
    return
  }

  // Check deployment mode (localOnly routes hidden in cloud mode)
  if (to.meta.localOnly && authStore.isCloudMode) {
    next({ name: 'chat' })
    return
  }

  // Module + level check (skip if permissions not loaded yet — avoid redirect loops)
  const mod = to.meta.module as string | undefined
  if (mod && Object.keys(authStore.permissions).length > 0) {
    const minLvl = (to.meta.minLevel as string) || 'view'
    if ((LVL[authStore.permissions[mod]] ?? 0) < (LVL[minLvl] ?? 1)) {
      const landing = authStore.hasModule('dashboard') && !authStore.isCloudMode ? 'dashboard' : 'chat'
      next({ name: landing })
      return
    }
  }

  next()
})

export default router
