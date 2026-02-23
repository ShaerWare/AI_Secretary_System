<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Download,
  Upload,
  History,
  Trash2,
  Shield,
  Languages,
  Palette,
  Bell,
  Database,
  ChevronRight,
  Check,
  X,
  User,
  Lock,
  Save
} from 'lucide-vue-next'
import { useExportImport } from '@/composables/useExportImport'
import { useAuditStore } from '@/stores/audit'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useToastStore } from '@/stores/toast'
import { useConfirmStore } from '@/stores/confirm'
import { setLocale, getLocale } from '@/plugins/i18n'

const { t } = useI18n()
const { isExporting, exportFaq, exportPresets, exportFullConfig, handleImport } = useExportImport()
const auditStore = useAuditStore()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const toast = useToastStore()
const confirm = useConfirmStore()

const activeTab = ref<'profile' | 'general' | 'export' | 'audit'>('profile')

// Profile state
const profileLoading = ref(false)
const profileData = ref<Record<string, string | null>>({})
const displayName = ref('')
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const passwordLoading = ref(false)

const roleColors: Record<string, string> = {
  admin: 'bg-red-500/20 text-red-400',
  user: 'bg-blue-500/20 text-blue-400',
  guest: 'bg-gray-500/20 text-gray-400'
}

async function loadProfile() {
  profileLoading.value = true
  try {
    const resp = await fetch('/admin/auth/profile', {
      headers: authStore.getAuthHeaders()
    })
    if (resp.ok) {
      profileData.value = await resp.json()
      displayName.value = profileData.value.display_name || ''
    }
  } catch {
    // ignore
  } finally {
    profileLoading.value = false
  }
}

async function saveProfile() {
  try {
    const resp = await fetch('/admin/auth/profile', {
      method: 'PUT',
      headers: { ...authStore.getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName.value || null })
    })
    if (resp.ok) {
      toast.success(t('profile.profileUpdated'))
      await loadProfile()
    } else {
      const data = await resp.json()
      toast.error(data.detail || 'Error')
    }
  } catch {
    toast.error('Connection error')
  }
}

async function changePassword() {
  if (newPassword.value !== confirmPassword.value) {
    toast.error(t('profile.passwordMismatch'))
    return
  }
  passwordLoading.value = true
  try {
    const resp = await fetch('/admin/auth/change-password', {
      method: 'POST',
      headers: { ...authStore.getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        old_password: oldPassword.value,
        new_password: newPassword.value
      })
    })
    if (resp.ok) {
      toast.success(t('profile.passwordChanged'))
      oldPassword.value = ''
      newPassword.value = ''
      confirmPassword.value = ''
    } else {
      const data = await resp.json()
      toast.error(data.detail || 'Error')
    }
  } catch {
    toast.error('Connection error')
  } finally {
    passwordLoading.value = false
  }
}

onMounted(() => {
  loadProfile()
})

// Format date for display
function formatDate(date: Date): string {
  return new Intl.DateTimeFormat(getLocale(), {
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(date)
}

// Action badge colors
const actionColors: Record<string, string> = {
  create: 'bg-green-500/20 text-green-400',
  update: 'bg-blue-500/20 text-blue-400',
  delete: 'bg-red-500/20 text-red-400',
  start: 'bg-emerald-500/20 text-emerald-400',
  stop: 'bg-orange-500/20 text-orange-400',
  login: 'bg-purple-500/20 text-purple-400',
  logout: 'bg-gray-500/20 text-gray-400',
  export: 'bg-cyan-500/20 text-cyan-400',
  import: 'bg-yellow-500/20 text-yellow-400'
}

async function clearAuditLog() {
  const confirmed = await confirm.confirm({
    title: 'Clear Audit Log',
    message: 'This will permanently delete all audit log entries. This action cannot be undone.',
    confirmText: 'Clear All',
    cancelText: 'Cancel',
    type: 'danger'
  })

  if (confirmed) {
    auditStore.clear()
    toast.success('Audit log cleared')
  }
}

function downloadAuditLog() {
  const json = auditStore.exportLog()
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `audit-log-${Date.now()}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  toast.success('Audit log exported')
}

const localeLabelMap: Record<string, string> = { ru: 'Русский', en: 'English', kk: 'Қазақша' }

function toggleLocale() {
  const order = ['ru', 'en', 'kk'] as const
  const idx = order.indexOf(getLocale())
  const newLocale = order[(idx + 1) % order.length]
  setLocale(newLocale)
  toast.success(`Language: ${localeLabelMap[newLocale]}`)
}
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6 animate-fade-in">
    <!-- Page Header -->
    <div>
      <h1 class="text-2xl font-bold">{{ t('common.settings') }}</h1>
      <p class="text-muted-foreground mt-1">Configure your admin panel preferences</p>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 bg-secondary/50 p-1 rounded-lg w-fit tab-bar-scroll max-w-full whitespace-nowrap">
      <button
        v-for="tab in ['profile', 'general', 'export', 'audit'] as const"
        :key="tab"
        :class="[
          'px-4 py-2 text-sm rounded-md transition-colors capitalize',
          activeTab === tab
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground'
        ]"
        @click="activeTab = tab"
      >
        {{ tab === 'profile' ? t('profile.title') : tab }}
      </button>
    </div>

    <!-- Profile -->
    <div v-if="activeTab === 'profile'" class="space-y-4">
      <!-- User Info -->
      <div class="bg-card rounded-xl border border-border p-6">
        <h3 class="font-semibold flex items-center gap-2 mb-4">
          <User class="w-5 h-5" />
          {{ t('profile.title') }}
        </h3>

        <div class="space-y-4">
          <!-- Username (read-only) -->
          <div>
            <label class="block text-sm text-muted-foreground mb-1">{{ t('profile.username') }}</label>
            <div class="px-3 py-2 bg-secondary/50 rounded-lg text-sm">
              {{ profileData.username || authStore.user?.username }}
            </div>
          </div>

          <!-- Role (read-only) -->
          <div>
            <label class="block text-sm text-muted-foreground mb-1">{{ t('profile.role') }}</label>
            <span
              :class="[
                'inline-block px-3 py-1 text-sm rounded-full',
                roleColors[authStore.user?.role || 'guest']
              ]"
            >
              {{ t(`roles.${authStore.user?.role || 'guest'}`) }}
            </span>
          </div>

          <!-- Display Name -->
          <div v-if="authStore.canEdit('settings')">
            <label class="block text-sm text-muted-foreground mb-1">{{ t('profile.displayName') }}</label>
            <div class="flex gap-2">
              <input
                v-model="displayName"
                type="text"
                class="flex-1 px-3 py-2 bg-secondary/50 rounded-lg text-sm border border-border focus:border-primary focus:outline-none"
                :placeholder="t('profile.displayName')"
              />
              <button
                class="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm hover:bg-primary/90 transition-colors flex items-center gap-1"
                @click="saveProfile"
              >
                <Save class="w-4 h-4" />
                {{ t('profile.save') }}
              </button>
            </div>
          </div>

          <!-- Registration date -->
          <div v-if="profileData.created" class="flex gap-8 text-sm text-muted-foreground">
            <div>
              <span class="font-medium">{{ t('profile.created') }}:</span>
              {{ new Date(profileData.created).toLocaleDateString(getLocale()) }}
            </div>
            <div v-if="profileData.last_login">
              <span class="font-medium">{{ t('profile.lastLogin') }}:</span>
              {{ new Date(profileData.last_login).toLocaleString(getLocale()) }}
            </div>
          </div>

          <!-- Guest notice -->
          <div v-if="!authStore.canEdit('settings')" class="text-sm text-muted-foreground italic">
            {{ t('profile.guestReadOnly') }}
          </div>
        </div>
      </div>

      <!-- Change Password -->
      <div v-if="authStore.canEdit('settings')" class="bg-card rounded-xl border border-border p-6">
        <h3 class="font-semibold flex items-center gap-2 mb-4">
          <Lock class="w-5 h-5" />
          {{ t('profile.changePassword') }}
        </h3>

        <div class="space-y-3 max-w-md">
          <div>
            <label class="block text-sm text-muted-foreground mb-1">{{ t('profile.currentPassword') }}</label>
            <input
              v-model="oldPassword"
              type="password"
              class="w-full px-3 py-2 bg-secondary/50 rounded-lg text-sm border border-border focus:border-primary focus:outline-none"
            />
          </div>
          <div>
            <label class="block text-sm text-muted-foreground mb-1">{{ t('profile.newPassword') }}</label>
            <input
              v-model="newPassword"
              type="password"
              class="w-full px-3 py-2 bg-secondary/50 rounded-lg text-sm border border-border focus:border-primary focus:outline-none"
            />
          </div>
          <div>
            <label class="block text-sm text-muted-foreground mb-1">{{ t('profile.confirmPassword') }}</label>
            <input
              v-model="confirmPassword"
              type="password"
              class="w-full px-3 py-2 bg-secondary/50 rounded-lg text-sm border border-border focus:border-primary focus:outline-none"
            />
          </div>
          <button
            :disabled="passwordLoading || !oldPassword || !newPassword || !confirmPassword"
            class="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-2"
            @click="changePassword"
          >
            <Lock class="w-4 h-4" />
            {{ t('profile.changePassword') }}
          </button>
        </div>
      </div>
    </div>

    <!-- General Settings -->
    <div v-if="activeTab === 'general'" class="space-y-4">
      <!-- Language -->
      <div class="bg-card rounded-xl border border-border p-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
              <Languages class="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <h3 class="font-medium">Language</h3>
              <p class="text-sm text-muted-foreground">Choose interface language</p>
            </div>
          </div>
          <button
            class="px-4 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
            @click="toggleLocale"
          >
            {{ localeLabelMap[getLocale()] || getLocale().toUpperCase() }}
          </button>
        </div>
      </div>

      <!-- Theme -->
      <div class="bg-card rounded-xl border border-border p-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
              <Palette class="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <h3 class="font-medium">Theme</h3>
              <p class="text-sm text-muted-foreground">Choose color theme</p>
            </div>
          </div>
          <div class="flex gap-2">
            <button
              v-for="theme in themeStore.themes"
              :key="theme.value"
              :class="[
                'px-3 py-2 rounded-lg text-sm transition-colors',
                themeStore.theme === theme.value
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary hover:bg-secondary/80'
              ]"
              @click="themeStore.setTheme(theme.value)"
            >
              {{ t(`themes.${theme.value}`) }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Export/Import Settings -->
    <div v-if="activeTab === 'export'" class="space-y-4">
      <!-- Export Options -->
      <div class="bg-card rounded-xl border border-border">
        <div class="p-4 border-b border-border">
          <h3 class="font-semibold flex items-center gap-2">
            <Download class="w-5 h-5" />
            {{ t('common.export') }}
          </h3>
        </div>
        <div class="p-4 space-y-3">
          <button
            :disabled="isExporting"
            class="flex items-center justify-between w-full p-4 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors disabled:opacity-50"
            @click="exportFullConfig"
          >
            <div class="flex items-center gap-3">
              <Database class="w-5 h-5 text-indigo-400" />
              <div class="text-left">
                <p class="font-medium">Full Configuration</p>
                <p class="text-sm text-muted-foreground">Export FAQ, presets, and LLM params</p>
              </div>
            </div>
            <ChevronRight class="w-5 h-5 text-muted-foreground" />
          </button>

          <button
            :disabled="isExporting"
            class="flex items-center justify-between w-full p-4 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors disabled:opacity-50"
            @click="exportFaq"
          >
            <div class="flex items-center gap-3">
              <Database class="w-5 h-5 text-green-400" />
              <div class="text-left">
                <p class="font-medium">FAQ Only</p>
                <p class="text-sm text-muted-foreground">Export FAQ responses</p>
              </div>
            </div>
            <ChevronRight class="w-5 h-5 text-muted-foreground" />
          </button>

          <button
            :disabled="isExporting"
            class="flex items-center justify-between w-full p-4 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors disabled:opacity-50"
            @click="exportPresets"
          >
            <div class="flex items-center gap-3">
              <Database class="w-5 h-5 text-purple-400" />
              <div class="text-left">
                <p class="font-medium">TTS Presets</p>
                <p class="text-sm text-muted-foreground">Export custom voice presets</p>
              </div>
            </div>
            <ChevronRight class="w-5 h-5 text-muted-foreground" />
          </button>
        </div>
      </div>

      <!-- Import -->
      <div class="bg-card rounded-xl border border-border">
        <div class="p-4 border-b border-border">
          <h3 class="font-semibold flex items-center gap-2">
            <Upload class="w-5 h-5" />
            {{ t('common.import') }}
          </h3>
        </div>
        <div class="p-4">
          <button
            class="flex items-center justify-center gap-2 w-full p-4 rounded-lg border-2 border-dashed border-border hover:border-primary hover:bg-primary/5 transition-colors"
            @click="handleImport"
          >
            <Upload class="w-5 h-5" />
            <span>Click to select configuration file (.json)</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Audit Log -->
    <div v-if="activeTab === 'audit'" class="space-y-4">
      <div class="bg-card rounded-xl border border-border">
        <div class="flex items-center justify-between p-4 border-b border-border">
          <h3 class="font-semibold flex items-center gap-2">
            <History class="w-5 h-5" />
            Audit Log
          </h3>
          <div class="flex gap-2">
            <button
              class="flex items-center gap-2 px-3 py-1.5 text-sm bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
              @click="downloadAuditLog"
            >
              <Download class="w-4 h-4" />
              Export
            </button>
            <button
              class="flex items-center gap-2 px-3 py-1.5 text-sm bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors"
              @click="clearAuditLog"
            >
              <Trash2 class="w-4 h-4" />
              Clear
            </button>
          </div>
        </div>

        <div class="max-h-[600px] overflow-auto">
          <div v-if="auditStore.entries.length === 0" class="p-8 text-center text-muted-foreground">
            No audit entries yet
          </div>

          <div v-else class="divide-y divide-border">
            <div
              v-for="entry in auditStore.entries"
              :key="entry.id"
              class="p-4 hover:bg-secondary/30 transition-colors"
            >
              <div class="flex items-start justify-between gap-4">
                <div class="flex items-start gap-3 min-w-0">
                  <span
                    :class="[
                      'px-2 py-0.5 text-xs rounded-full capitalize shrink-0',
                      actionColors[entry.action] || 'bg-gray-500/20 text-gray-400'
                    ]"
                  >
                    {{ entry.action }}
                  </span>
                  <div class="min-w-0">
                    <p class="font-medium truncate">{{ entry.resource }}</p>
                    <p v-if="entry.details" class="text-sm text-muted-foreground truncate">
                      {{ entry.details }}
                    </p>
                  </div>
                </div>
                <div class="text-right shrink-0">
                  <p class="text-sm text-muted-foreground">{{ entry.user }}</p>
                  <p class="text-xs text-muted-foreground">{{ formatDate(entry.timestamp) }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
