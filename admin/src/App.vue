<script setup lang="ts">
import { RouterView, useRoute, useRouter } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import {
  Settings,
  Menu,
  X,
  Search,
  LogOut,
  User,
  Languages,
  PanelLeftClose,
  MessageCircle,
  Maximize2
} from 'lucide-vue-next'
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from './stores/auth'
import { useSearchStore } from './stores/search'
import { useThemeStore } from './stores/theme'
import { useChatFullscreenStore } from './stores/chatFullscreen'
import { useResizablePanel } from './composables/useResizablePanel'
import { setLocale, getLocale } from './plugins/i18n'
import ToastContainer from './components/ToastContainer.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import SearchPalette from './components/SearchPalette.vue'
import ThemeToggle from './components/ThemeToggle.vue'
import ErrorBoundary from './components/ErrorBoundary.vue'
import AccordionNav from './components/AccordionNav.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const searchStore = useSearchStore()
const themeStore = useThemeStore()
const chatFullscreenStore = useChatFullscreenStore()

const isFullscreenChat = computed(() => chatFullscreenStore.isFullscreen && route.name === 'chat')

const sidebarOpen = ref(false)
const mobileMenuOpen = ref(false)
const isMobile = ref(false)

const { width: mainSidebarWidth, startResize: startMainSidebarResize } =
  useResizablePanel('main-sidebar-width', 256, 180, 400, 'right')

// Check if mobile
function checkMobile() {
  isMobile.value = window.innerWidth < 768
  if (isMobile.value) {
    sidebarOpen.value = false
  }
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

// Hide external chat widget on /chat page, show everywhere else
// Widget loads async (deferred script + await fetch), so poll until it appears
// Uses inline style (display:none) instead of CSS class because the widget's
// own !important rules on .ai-chat-button override class-based hiding
function setWidgetVisibility(widget: HTMLElement, hide: boolean) {
  widget.style.display = hide ? 'none' : ''
}
let widgetFound = false
watch(
  () => route.name,
  () => {
    const widget = document.querySelector('.ai-chat-widget') as HTMLElement | null
    if (widget) {
      setWidgetVisibility(widget, route.name === 'chat')
      widgetFound = true
    }
    mobileMenuOpen.value = false
  },
  { immediate: true },
)
const widgetPoll = setInterval(() => {
  const widget = document.querySelector('.ai-chat-widget') as HTMLElement | null
  if (widget) {
    setWidgetVisibility(widget, route.name === 'chat')
    widgetFound = true
  }
  if (widgetFound) clearInterval(widgetPoll)
}, 500)
onUnmounted(() => clearInterval(widgetPoll))

// Page title from route meta
const currentTitle = computed(() => {
  const meta = route.meta as { title?: string }
  return meta?.title || 'Admin'
})

const isLoginPage = computed(() => route.name === 'login')

const queryClient = useQueryClient()

function handleLogout() {
  authStore.logout()
  queryClient.clear()
  router.push('/login')
}

function toggleLocale() {
  const order = ['ru', 'en', 'kk'] as const
  const idx = order.indexOf(getLocale())
  const newLocale = order[(idx + 1) % order.length]
  setLocale(newLocale)
}

const localeLabel: Record<string, string> = { ru: 'RU', en: 'EN', kk: 'ҚАЗ' }
const localeTitle: Record<string, string> = { ru: 'Переключить язык', en: 'Switch language', kk: 'Тілді ауыстыру' }
</script>

<template>
  <ErrorBoundary>
    <!-- Login Page (no sidebar) -->
    <template v-if="isLoginPage">
      <RouterView />
    </template>

    <!-- Main App Layout -->
    <template v-else>
      <div class="flex h-screen overflow-hidden bg-background">
        <!-- Mobile Overlay -->
        <div
          v-if="mobileMenuOpen && isMobile && !isFullscreenChat"
          class="fixed inset-0 bg-black/50 z-40 md:hidden"
          @click="mobileMenuOpen = false"
        />

        <!-- Sidebar -->
        <aside
          v-if="!isFullscreenChat"
          :class="[
            'flex flex-col bg-card border-r border-border z-50 flex-shrink-0',
            isMobile ? 'fixed inset-y-0 left-0 transition-all duration-300' : '',
            isMobile && !mobileMenuOpen ? '-translate-x-full' : 'translate-x-0',
            isMobile ? 'w-64' : '',
            !isMobile && !sidebarOpen ? 'w-16' : ''
          ]"
          :style="!isMobile && sidebarOpen ? { width: mainSidebarWidth + 'px' } : undefined"
        >
          <!-- Logo -->
          <div class="flex items-center justify-between h-16 px-4 border-b border-border">
            <div :class="['flex items-center gap-3', !sidebarOpen && !isMobile ? 'cursor-pointer' : '']" @click="!sidebarOpen && !isMobile && (sidebarOpen = true)">
              <div class="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
                <Settings class="w-5 h-5 text-primary" />
              </div>
              <span v-if="sidebarOpen || isMobile" class="font-semibold text-lg">AI Secretary</span>
            </div>
            <button
              v-if="!isMobile && sidebarOpen"
              class="p-2 rounded-lg border border-border text-muted-foreground hover:bg-secondary/50 transition-colors"
              @click="sidebarOpen = false"
            >
              <PanelLeftClose class="w-4 h-4" />
            </button>
            <button
              v-if="isMobile"
              class="p-1 rounded-lg hover:bg-secondary/50 text-muted-foreground"
              @click="mobileMenuOpen = false"
            >
              <X class="w-5 h-5" />
            </button>
          </div>

          <!-- Chat shortcut -->
          <div v-if="sidebarOpen || isMobile" class="p-2">
            <router-link
              to="/chat"
              class="flex items-center gap-2 w-full px-3 py-2 text-sm rounded-lg transition-colors"
              :class="route.path === '/chat' ? 'bg-primary/10 text-primary' : 'text-muted-foreground bg-secondary/50 hover:bg-secondary'"
              @click="isMobile && (mobileMenuOpen = false)"
            >
              <MessageCircle class="w-4 h-4" />
              <span class="flex-1 text-left">{{ t('nav.chat') }}</span>
            </router-link>
          </div>
          <div v-else class="p-2">
            <router-link
              to="/chat"
              class="flex items-center justify-center w-full p-2 rounded-lg transition-colors"
              :class="route.path === '/chat' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-secondary/50'"
            >
              <MessageCircle class="w-5 h-5" />
            </router-link>
          </div>

          <!-- Navigation -->
          <AccordionNav :collapsed="!sidebarOpen && !isMobile" />

          <!-- User & Toggle -->
          <div class="p-2 border-t border-border space-y-1">
            <!-- User info -->
            <div
              v-if="(sidebarOpen || isMobile) && authStore.user"
              class="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground"
            >
              <User class="w-4 h-4" />
              <span class="truncate">{{ authStore.user.username }}</span>
              <span
                :class="[
                  'px-1.5 py-0.5 text-[10px] rounded-full leading-tight',
                  authStore.user.role === 'admin' ? 'bg-red-500/20 text-red-400' :
                  authStore.user.role === 'user' ? 'bg-blue-500/20 text-blue-400' :
                  authStore.user.role === 'web' ? 'bg-green-500/20 text-green-400' :
                  'bg-gray-500/20 text-gray-400'
                ]"
              >
                {{ t(`roles.${authStore.user.role}`) }}
              </span>
            </div>

            <!-- Logout -->
            <button
              :class="[
                'flex items-center w-full px-3 py-2 rounded-lg text-muted-foreground hover:bg-red-500/10 hover:text-red-400 transition-colors',
                sidebarOpen || isMobile ? 'gap-3' : 'justify-center'
              ]"
              @click="handleLogout"
            >
              <LogOut class="w-5 h-5" />
              <span v-if="sidebarOpen || isMobile">{{ t('nav.logout') }}</span>
            </button>

            <!-- Toggle Button (desktop only) -->
            <button
              v-if="!isMobile"
              class="flex items-center justify-center w-full p-2 rounded-lg text-muted-foreground hover:bg-secondary/50 hover:text-foreground transition-colors"
              @click="sidebarOpen = !sidebarOpen"
            >
              <Menu v-if="!sidebarOpen" class="w-5 h-5" />
              <X v-else class="w-5 h-5" />
            </button>
          </div>
        </aside>

        <!-- Sidebar resize handle (desktop only) -->
        <div
          v-if="sidebarOpen && !isMobile && !isFullscreenChat"
          class="w-1 cursor-col-resize hover:bg-primary/30 active:bg-primary/50 transition-colors flex-shrink-0"
          @mousedown="startMainSidebarResize"
        />

        <!-- Main Content -->
        <main class="flex-1 flex flex-col overflow-hidden">
          <!-- Header -->
          <header v-if="!isFullscreenChat" class="flex items-center justify-between h-16 px-4 md:px-6 border-b border-border bg-card">
            <div class="flex items-center gap-3">
              <!-- Mobile Menu Button -->
              <button
                v-if="isMobile"
                class="p-2 -ml-2 rounded-lg hover:bg-secondary/50 text-muted-foreground"
                @click="mobileMenuOpen = true"
              >
                <Menu class="w-5 h-5" />
              </button>
              <h1 class="text-lg md:text-xl font-semibold truncate">{{ currentTitle }}</h1>
            </div>
            <div class="flex items-center gap-2 md:gap-4">
              <!-- Zen mode (chat page only) -->
              <button
                v-if="route.name === 'chat'"
                class="p-2 rounded-lg hover:bg-secondary/50 text-muted-foreground hover:text-foreground transition-colors"
                :title="t('chatView.zenMode')"
                @click="chatFullscreenStore.enter()"
              >
                <Maximize2 class="w-4 h-4" />
              </button>

              <!-- Language Toggle -->
              <button
                class="flex items-center gap-1 px-2 py-1.5 rounded-lg hover:bg-secondary/50 text-muted-foreground hover:text-foreground transition-colors text-sm font-medium"
                :title="localeTitle[getLocale()]"
                @click="toggleLocale"
              >
                <Languages class="w-4 h-4" />
                <span>{{ localeLabel[getLocale()] }}</span>
              </button>

              <!-- Theme Toggle -->
              <ThemeToggle />

              <!-- Search -->
              <button
                class="p-2 rounded-lg hover:bg-secondary/50 text-muted-foreground hover:text-foreground transition-colors"
                :title="t('nav.search') + ' (⌘K)'"
                @click="searchStore.open"
              >
                <Search class="w-4 h-4" />
              </button>
            </div>
          </header>

          <!-- Content -->
          <div :class="['flex-1', ['chat', 'kanban'].includes(route.name as string) ? 'overflow-hidden' : 'overflow-auto p-4 md:p-6']">
            <RouterView />
          </div>
        </main>
      </div>
    </template>

    <!-- Global Components -->
    <ToastContainer />
    <ConfirmDialog />
    <SearchPalette />
  </ErrorBoundary>
</template>

<style>
/* Page transition animations */
.page-enter-active,
.page-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* Fade transition for modals */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Slide transition for sidebar */
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(-100%);
}

/* Scale transition for cards */
.scale-enter-active,
.scale-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.scale-enter-from,
.scale-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

/* Smooth hover effects */
.hover-lift {
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.hover-lift:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

/* Focus visible styles */
*:focus-visible {
  outline: 2px solid hsl(var(--ring));
  outline-offset: 2px;
}

/* Responsive text sizing */
@media (max-width: 640px) {
  .text-responsive-sm { font-size: 0.75rem; }
  .text-responsive-base { font-size: 0.875rem; }
  .text-responsive-lg { font-size: 1rem; }
  .text-responsive-xl { font-size: 1.125rem; }
}
</style>
