<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore, type UserRole } from '../stores/auth'
import { ChevronDown } from 'lucide-vue-next'
import {
  LayoutDashboard,
  Activity,
  Server,
  FileText,
  Brain,
  Mic,
  AudioLines,
  Sparkles,
  MessageCircle,
  Send,
  Code2,
  Phone,
  MessageSquare,
  ShoppingCart,
  Users,
  Settings,
  Info
} from 'lucide-vue-next'
import { markRaw } from 'vue'
import WhatsAppIcon from './WhatsAppIcon.vue'
const WhatsApp = markRaw(WhatsAppIcon)

const props = defineProps<{
  collapsed: boolean
}>()

const { t } = useI18n()
const route = useRoute()
const authStore = useAuthStore()

const ROLE_LEVEL: Record<UserRole, number> = { guest: 0, web: 1, user: 1, admin: 2 }

function isVisibleForRole(item: { minRole?: UserRole; excludeRoles?: UserRole[]; localOnly?: boolean }): boolean {
  const userRole = authStore.user?.role || 'guest'
  if (item.excludeRoles?.includes(userRole)) return false
  if (item.localOnly && authStore.isCloudMode) return false
  if (!item.minRole) return true
  return ROLE_LEVEL[userRole] >= ROLE_LEVEL[item.minRole]
}

// Navigation groups with items
const allNavGroups = computed(() => [
  {
    id: 'monitoring',
    nameKey: 'nav.group.monitoring',
    icon: Activity,
    items: [
      { path: '/', nameKey: 'nav.dashboard', icon: LayoutDashboard, excludeRoles: ['web', 'user'] as UserRole[], localOnly: true },
      { path: '/monitoring', nameKey: 'nav.monitoring', icon: Activity, minRole: 'admin' as UserRole, localOnly: true },
      { path: '/services', nameKey: 'nav.services', icon: Server, minRole: 'admin' as UserRole, localOnly: true },
      { path: '/audit', nameKey: 'nav.audit', icon: FileText, minRole: 'admin' as UserRole },
    ]
  },
  {
    id: 'ai',
    nameKey: 'nav.group.ai',
    icon: Brain,
    items: [
      { path: '/llm', nameKey: 'nav.llm', icon: Brain, minRole: 'user' as UserRole },
      { path: '/tts', nameKey: 'nav.tts', icon: Mic, minRole: 'user' as UserRole, excludeRoles: ['web'] as UserRole[], localOnly: true },
      { path: '/models', nameKey: 'nav.models', icon: AudioLines, minRole: 'admin' as UserRole, localOnly: true },
      { path: '/finetune', nameKey: 'nav.finetune', icon: Sparkles, minRole: 'user' as UserRole },
    ]
  },
  {
    id: 'channels',
    nameKey: 'nav.group.channels',
    icon: MessageCircle,
    items: [
      { path: '/telegram', nameKey: 'nav.telegram', icon: Send, minRole: 'user' as UserRole },
      { path: '/whatsapp', nameKey: 'nav.whatsapp', icon: WhatsApp, minRole: 'user' as UserRole },
      { path: '/widget', nameKey: 'nav.widget', icon: Code2, minRole: 'user' as UserRole },
      { path: '/gsm', nameKey: 'nav.gsm', icon: Phone, minRole: 'admin' as UserRole, localOnly: true },
    ]
  },
  {
    id: 'business',
    nameKey: 'nav.group.business',
    icon: ShoppingCart,
    items: [
      { path: '/faq', nameKey: 'nav.faq', icon: MessageSquare },
      { path: '/sales', nameKey: 'nav.sales', icon: ShoppingCart, minRole: 'user' as UserRole },
      { path: '/crm', nameKey: 'nav.crm', icon: Users, minRole: 'user' as UserRole },
    ]
  },
  {
    id: 'system',
    nameKey: 'nav.group.system',
    icon: Settings,
    items: [
      { path: '/settings', nameKey: 'common.settings', icon: Settings, minRole: 'user' as UserRole },
      { path: '/about', nameKey: 'nav.about', icon: Info },
    ]
  }
])

// Filtered nav groups based on user role
const navGroups = computed(() =>
  allNavGroups.value
    .map(group => ({
      ...group,
      items: group.items.filter(item => isVisibleForRole(item))
    }))
    .filter(group => group.items.length > 0)
)

// Expanded groups state (persisted in localStorage)
const expandedGroups = ref<Set<string>>(new Set())

// Load from localStorage on mount
onMounted(() => {
  const saved = localStorage.getItem('nav_expanded_groups')
  if (saved) {
    try {
      expandedGroups.value = new Set(JSON.parse(saved))
    } catch {
      // Default: expand group containing current route
      expandActiveGroup()
    }
  } else {
    expandActiveGroup()
  }
})

// Save to localStorage when changed
watch(expandedGroups, (val) => {
  localStorage.setItem('nav_expanded_groups', JSON.stringify([...val]))
}, { deep: true })

// Expand group containing active route
function expandActiveGroup() {
  for (const group of navGroups.value) {
    if (group.items.some(item => item.path === route.path)) {
      expandedGroups.value.add(group.id)
      break
    }
  }
}

// Auto-expand when route changes
watch(() => route.path, () => {
  for (const group of navGroups.value) {
    if (group.items.some(item => item.path === route.path)) {
      expandedGroups.value.add(group.id)
      break
    }
  }
})

function toggleGroup(groupId: string) {
  if (expandedGroups.value.has(groupId)) {
    expandedGroups.value.delete(groupId)
  } else {
    expandedGroups.value.add(groupId)
  }
  // Trigger reactivity
  expandedGroups.value = new Set(expandedGroups.value)
}

function isGroupExpanded(groupId: string) {
  return expandedGroups.value.has(groupId)
}

function isItemActive(path: string) {
  return route.path === path
}

function hasActiveItem(group: typeof navGroups.value[0]) {
  return group.items.some(item => item.path === route.path)
}
</script>

<template>
  <nav class="flex-1 p-2 space-y-1 overflow-y-auto">
    <template v-for="group in navGroups" :key="group.id">
      <!-- Group Header (hidden when sidebar is collapsed) -->
      <button
        v-if="!collapsed"
        :class="[
          'flex items-center w-full px-3 py-2 rounded-lg transition-all duration-200',
          'text-muted-foreground hover:bg-secondary/50 hover:text-foreground',
          hasActiveItem(group) ? 'bg-primary/10 text-primary' : ''
        ]"
        @click="toggleGroup(group.id)"
      >
        <component :is="group.icon" class="w-5 h-5 shrink-0" />
        <span class="flex-1 ml-3 text-left font-medium truncate">
          {{ t(group.nameKey) }}
        </span>
        <ChevronDown
          :class="[
            'w-4 h-4 transition-transform duration-200',
            isGroupExpanded(group.id) ? 'rotate-180' : ''
          ]"
        />
      </button>

      <!-- Group Items (collapsible) -->
      <div
        v-if="!collapsed"
        :class="[
          'overflow-hidden transition-all duration-200 ease-in-out',
          isGroupExpanded(group.id) ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'
        ]"
      >
        <div class="pl-4 space-y-0.5 py-1">
          <RouterLink
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            :class="[
              'flex items-center gap-3 px-3 py-2 rounded-lg transition-colors',
              isItemActive(item.path)
                ? 'bg-secondary text-foreground font-medium'
                : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground'
            ]"
          >
            <component :is="item.icon" class="w-4 h-4 shrink-0" />
            <span class="truncate text-sm">{{ t(item.nameKey) }}</span>
          </RouterLink>
        </div>
      </div>

      <!-- Collapsed mode: show items on hover via tooltip or just icons -->
      <template v-if="collapsed">
        <RouterLink
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          :title="t(item.nameKey)"
          :class="[
            'flex items-center justify-center p-2 rounded-lg transition-colors',
            isItemActive(item.path)
              ? 'bg-secondary text-foreground'
              : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground'
          ]"
        >
          <component :is="item.icon" class="w-5 h-5" />
        </RouterLink>
      </template>
    </template>
  </nav>
</template>
