import { createRouter, createWebHashHistory, type RouteRecordRaw } from "vue-router";
import { useAuthStore } from "./stores/auth";
import { IS_LITE } from "./config/variant";

// Lite-included views (always present) — kept as static imports so the main
// app shell loads eagerly, matching pre-lite behaviour.
import ChatView from "./views/ChatView.vue";
import LlmView from "./views/LlmView.vue";
import FaqView from "./views/FaqView.vue";
import WidgetView from "./views/WidgetView.vue";
import TelegramView from "./views/TelegramView.vue";
import WhatsAppView from "./views/WhatsAppView.vue";
import MobileAppView from "./views/MobileAppView.vue";
import SettingsView from "./views/SettingsView.vue";
import LoginView from "./views/LoginView.vue";
import AboutView from "./views/AboutView.vue";
import UsersView from "./views/UsersView.vue";
import InviteView from "./views/InviteView.vue";

// Full-only views: dynamic imports so Rollup tree-shakes them from the lite
// bundle once the `IS_LITE ? [] : fullOnlyRoutes` ternary is constant-folded.
const DashboardView = () => import("./views/DashboardView.vue");
const ServicesView = () => import("./views/ServicesView.vue");
const TtsView = () => import("./views/TtsView.vue");
const FinetuneView = () => import("./views/FinetuneView.vue");
const MonitoringView = () => import("./views/MonitoringView.vue");
const ModelsView = () => import("./views/ModelsView.vue");
const GSMView = () => import("./views/GSMView.vue");
const AuditView = () => import("./views/AuditView.vue");
const UsageView = () => import("./views/UsageView.vue");
const CrmView = () => import("./views/CrmView.vue");
const KanbanView = () => import("./views/KanbanView.vue");
const SalesView = () => import("./views/SalesView.vue");
const WooCommerceView = () => import("./views/WooCommerceView.vue");

const baseRoutes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: LoginView,
    meta: { title: "Login", public: true },
  },
  {
    path: "/",
    redirect: { name: "chat" },
  },
  {
    path: "/chat",
    name: "chat",
    component: ChatView,
    meta: { title: "Chat", icon: "MessageCircle", module: "chat" },
  },
  {
    path: "/llm",
    name: "llm",
    component: LlmView,
    meta: { title: "LLM", icon: "Brain", module: "llm" },
  },
  {
    path: "/wiki",
    name: "wiki",
    component: FaqView,
    meta: { title: "Wiki", icon: "BookOpen", module: "faq" },
  },
  {
    path: "/widget",
    name: "widget",
    component: WidgetView,
    meta: { title: "Widget", icon: "Code2", module: "channels" },
  },
  {
    path: "/telegram",
    name: "telegram",
    component: TelegramView,
    meta: { title: "Telegram", icon: "Send", module: "channels" },
  },
  {
    path: "/whatsapp",
    name: "whatsapp",
    component: WhatsAppView,
    meta: { title: "WhatsApp", icon: "MessageCircle", module: "channels" },
  },
  {
    path: "/mobile-app",
    name: "mobile-app",
    component: MobileAppView,
    meta: { title: "Mobile App", icon: "Smartphone", module: "channels" },
  },
  {
    path: "/settings",
    name: "settings",
    component: SettingsView,
    meta: { title: "Settings", icon: "Settings" },
  },
  {
    path: "/users",
    name: "users",
    component: UsersView,
    meta: { title: "Users", icon: "UserCog", module: "users", minLevel: "view" },
  },
  {
    path: "/invite/:code",
    name: "invite",
    component: InviteView,
    meta: { title: "Invite", public: true },
  },
  {
    path: "/about",
    name: "about",
    component: AboutView,
    meta: { title: "About", icon: "Info" },
  },
];

const fullOnlyRoutes: RouteRecordRaw[] = [
  {
    path: "/dashboard",
    name: "dashboard",
    component: DashboardView,
    meta: { title: "Dashboard", icon: "LayoutDashboard", module: "dashboard", localOnly: true },
  },
  {
    path: "/services",
    name: "services",
    component: ServicesView,
    meta: {
      title: "Services",
      icon: "Server",
      module: "system",
      minLevel: "manage",
      localOnly: true,
    },
  },
  {
    path: "/tts",
    name: "tts",
    component: TtsView,
    meta: { title: "TTS", icon: "Mic", module: "speech", localOnly: true },
  },
  {
    path: "/finetune",
    name: "finetune",
    component: FinetuneView,
    meta: { title: "Fine-tune", icon: "Sparkles", module: "llm" },
  },
  {
    path: "/monitoring",
    name: "monitoring",
    component: MonitoringView,
    meta: { title: "Monitoring", icon: "Activity", module: "system", localOnly: true },
  },
  {
    path: "/models",
    name: "models",
    component: ModelsView,
    meta: {
      title: "Models",
      icon: "HardDrive",
      module: "system",
      minLevel: "manage",
      localOnly: true,
    },
  },
  {
    path: "/gsm",
    name: "gsm",
    component: GSMView,
    meta: { title: "GSM Telephony", icon: "Phone", module: "gsm", localOnly: true },
  },
  {
    path: "/audit",
    name: "audit",
    component: AuditView,
    meta: { title: "Audit", icon: "FileText", module: "audit" },
  },
  {
    path: "/usage",
    name: "usage",
    component: UsageView,
    meta: { title: "Usage", icon: "BarChart3", module: "usage" },
  },
  {
    path: "/crm",
    name: "crm",
    component: CrmView,
    meta: { title: "CRM", icon: "Users", module: "sales" },
  },
  {
    path: "/kanban",
    name: "kanban",
    component: KanbanView,
    meta: { title: "Kanban", icon: "ClipboardList", module: "kanban" },
  },
  {
    path: "/sales",
    name: "sales",
    component: SalesView,
    meta: { title: "Sales", icon: "ShoppingCart", module: "sales" },
  },
  {
    path: "/woocommerce",
    name: "woocommerce",
    component: WooCommerceView,
    meta: { title: "WooCommerce", icon: "ShoppingBag", module: "sales" },
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes: [...baseRoutes, ...(IS_LITE ? [] : fullOnlyRoutes)],
});

const LVL: Record<string, number> = { view: 1, edit: 2, manage: 3 };

// Navigation guard for authentication and authorization
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore();

  // Check if route requires auth
  const isPublicRoute = to.meta.public === true;

  if (!isPublicRoute && !authStore.isAuthenticated) {
    // Check if token is in localStorage but store not initialized
    const token = localStorage.getItem("admin_token");
    if (token && !authStore.isTokenExpired()) {
      // Token exists and valid, check permissions below
    } else {
      // Redirect to login
      next({ name: "login", query: { redirect: to.fullPath } });
      return;
    }
  } else if (to.name === "login" && authStore.isAuthenticated) {
    // Already logged in, redirect to landing page
    next({ name: "chat" });
    return;
  }

  // Chat-only users can only access /chat
  // Use isChatOnlyUser (permission-based) when loaded, fall back to JWT role
  const chatOnly = authStore.isChatOnlyUser
    || (authStore.isAuthenticated && authStore.user?.role !== "admin" && Object.keys(authStore.permissions).length === 0);
  if (!isPublicRoute && chatOnly && to.name !== "chat") {
    next({ name: "chat" });
    return;
  }

  // Check deployment mode (localOnly routes hidden in cloud mode)
  if (to.meta.localOnly && authStore.isCloudMode) {
    next({ name: "chat" });
    return;
  }

  // Module + level check (skip if permissions not loaded yet — avoid redirect loops)
  const mod = to.meta.module as string | undefined;
  if (mod && Object.keys(authStore.permissions).length > 0) {
    const minLvl = (to.meta.minLevel as string) || "view";
    if ((LVL[authStore.permissions[mod]] ?? 0) < (LVL[minLvl] ?? 1)) {
      next({ name: "chat" });
      return;
    }
  }

  next();
});

export default router;
