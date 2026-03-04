<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
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
  BookOpen,
  ShoppingCart,
  ShoppingBag,
  Users,
  Settings,
  Info,
  UserCog
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

const LVL: Record<string, number> = { view: 1, edit: 2, manage: 3 }

function isVisible(item: { module?: string; minLevel?: string; localOnly?: boolean }): boolean {
  if (item.localOnly && authStore.isCloudMode) return false
  if (!item.module) return true
  const min = item.minLevel || 'view'
  return (LVL[authStore.permissions[item.module]] ?? 0) >= (LVL[min] ?? 1)
}

// Navigation groups with items
const allNavGroups = computed(() => [
  {
    id: 'monitoring',
    nameKey: 'nav.group.monitoring',
    icon: Activity,
    items: [
      { path: '/', nameKey: 'nav.dashboard', icon: LayoutDashboard, module: 'dashboard', localOnly: true },
      { path: '/monitoring', nameKey: 'nav.monitoring', icon: Activity, module: 'system', localOnly: true },
      { path: '/services', nameKey: 'nav.services', icon: Server, module: 'system', minLevel: 'manage', localOnly: true },
      { path: '/audit', nameKey: 'nav.audit', icon: FileText, module: 'audit' },
    ]
  },
  {
    id: 'ai',
    nameKey: 'nav.group.ai',
    icon: Brain,
    items: [
      { path: '/llm', nameKey: 'nav.llm', icon: Brain, module: 'llm' },
      { path: '/tts', nameKey: 'nav.tts', icon: Mic, module: 'speech', localOnly: true },
      { path: '/models', nameKey: 'nav.models', icon: AudioLines, module: 'system', minLevel: 'manage', localOnly: true },
      { path: '/finetune', nameKey: 'nav.finetune', icon: Sparkles, module: 'llm' },
    ]
  },
  {
    id: 'channels',
    nameKey: 'nav.group.channels',
    icon: MessageCircle,
    items: [
      { path: '/telegram', nameKey: 'nav.telegram', icon: Send, module: 'channels' },
      { path: '/whatsapp', nameKey: 'nav.whatsapp', icon: WhatsApp, module: 'channels' },
      { path: '/widget', nameKey: 'nav.widget', icon: Code2, module: 'channels' },
      { path: '/gsm', nameKey: 'nav.gsm', icon: Phone, module: 'gsm', localOnly: true },
    ]
  },
  {
    id: 'business',
    nameKey: 'nav.group.business',
    icon: ShoppingCart,
    items: [
      { path: '/sales', nameKey: 'nav.sales', icon: ShoppingCart, module: 'sales' },
      { path: '/crm', nameKey: 'nav.crm', icon: Users, module: 'sales' },
      { path: '/woocommerce', nameKey: 'nav.woocommerce', icon: ShoppingBag, module: 'sales' },
    ]
  },
  {
    id: 'system',
    nameKey: 'nav.group.system',
    icon: Settings,
    items: [
      { path: '/users', nameKey: 'nav.users', icon: UserCog, module: 'users' },
      { path: '/wiki', nameKey: 'nav.wiki', icon: BookOpen, module: 'faq' },
      { path: '/settings', nameKey: 'common.settings', icon: Settings },
      { path: '/about', nameKey: 'nav.about', icon: Info },
    ]
  }
])

// Filtered nav groups based on user role
const navGroups = computed(() =>
  allNavGroups.value
    .map(group => ({
      ...group,
      items: group.items.filter(item => isVisible(item))
    }))
    .filter(group => group.items.length > 0)
)

// Expanded groups state (persisted in localStorage)
const expandedGroups = ref<Set<string>>(new Set())

// Load from localStorage on mount — default: all collapsed
onMounted(() => {
  const saved = localStorage.getItem('nav_expanded_groups')
  if (saved) {
    try {
      expandedGroups.value = new Set(JSON.parse(saved))
    } catch {
      // keep empty — all collapsed
    }
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

// No auto-expand on route change — user controls accordion state

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
        <template v-if="isGroupExpanded(group.id)">
          <div class="h-px flex-1 bg-border" />
        </template>
        <template v-else>
          <component :is="group.icon" class="w-5 h-5 shrink-0" />
          <span class="flex-1 ml-3 text-left font-medium truncate">
            {{ t(group.nameKey) }}
          </span>
        </template>
        <ChevronDown
          :class="[
            'w-4 h-4 shrink-0 transition-transform duration-200',
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

      <!-- Collapsed mode: group icon as toggle, items expand below -->
      <template v-if="collapsed">
        <button
          :title="t(group.nameKey)"
          :class="[
            'flex items-center justify-center w-full p-2 rounded-lg transition-colors',
            'text-muted-foreground hover:bg-secondary/50 hover:text-foreground',
            hasActiveItem(group) ? 'bg-primary/10 text-primary' : ''
          ]"
          @click="toggleGroup(group.id)"
        >
          <div v-if="isGroupExpanded(group.id)" class="h-px w-5 bg-border" />
          <component :is="group.icon" v-else class="w-5 h-5" />
        </button>
        <div
          :class="[
            'overflow-hidden transition-all duration-200 ease-in-out',
            isGroupExpanded(group.id) ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'
          ]"
        >
          <div class="space-y-0.5 py-1">
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
              <component :is="item.icon" class="w-4 h-4" />
            </RouterLink>
          </div>
        </div>
      </template>
    </template>
  </nav>
</template>
