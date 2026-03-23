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
import { useRoute, useRouter } from 'vue-router'
import { useExportImport } from '@/composables/useExportImport'
import { googleApi, type GoogleOAuthStatus } from '@/api/google'
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

// Google OAuth
const route = useRoute()
const router = useRouter()
const googleStatus = ref<GoogleOAuthStatus>({ connected: false, google_email: null, scopes: [] })
const googleLoading = ref(false)

async function loadGoogleStatus() {
  try {
    googleStatus.value = await googleApi.getStatus()
  } catch {
    // ignore
  }
}

async function connectGoogle() {
  googleLoading.value = true
  try {
    const { auth_url } = await googleApi.getAuthUrl()
    window.location.href = auth_url
  } catch {
    toast.error('Failed to start Google auth')
    googleLoading.value = false
  }
}

async function disconnectGoogle() {
  const ok = await confirm.confirm({
    title: t('google.disconnectTitle'),
    message: t('google.disconnectConfirm'),
    confirmText: t('google.disconnect'),
    type: 'danger'
  })
  if (!ok) return
  try {
    await googleApi.disconnect()
    googleStatus.value = { connected: false, google_email: null, scopes: [] }
    toast.success(t('google.disconnected'))
  } catch {
    toast.error('Error')
  }
}

onMounted(() => {
  loadProfile()
  loadGoogleStatus()
  // Handle OAuth callback redirect
  if (route.query.google === 'connected') {
    toast.success(t('google.connected'))
    router.replace({ query: {} })
    loadGoogleStatus()
  } else if (route.query.google === 'error') {
    toast.error(t('google.connectionFailed'))
    router.replace({ query: {} })
  }
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

      <!-- Google Account -->
      <div class="bg-card rounded-xl border border-border p-4">
        <h3 class="font-medium mb-3 flex items-center gap-2">
          <svg class="w-5 h-5" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
          Google
        </h3>
        <div v-if="googleStatus.connected" class="space-y-2">
          <div class="flex items-center gap-2 text-sm">
            <Check class="w-4 h-4 text-green-400" />
            <span>{{ t('google.connectedAs', { email: googleStatus.google_email }) }}</span>
          </div>
          <div class="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
            <span v-if="googleStatus.scopes.some(s => s.includes('drive'))" class="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400">Drive</span>
            <span v-if="googleStatus.scopes.some(s => s.includes('documents'))" class="px-2 py-0.5 rounded-full bg-green-500/10 text-green-400">Docs</span>
            <span v-if="googleStatus.scopes.some(s => s.includes('spreadsheets'))" class="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400">Sheets</span>
            <span v-if="googleStatus.scopes.some(s => s.includes('gmail'))" class="px-2 py-0.5 rounded-full bg-red-500/10 text-red-400">Gmail</span>
          </div>
          <button
            class="mt-2 px-3 py-1.5 text-sm bg-destructive/20 text-destructive rounded-lg hover:bg-destructive/30 transition-colors"
            @click="disconnectGoogle"
          >
            {{ t('google.disconnect') }}
          </button>
        </div>
        <div v-else>
          <p class="text-sm text-muted-foreground mb-3">{{ t('google.connectDescription') }}</p>
          <button
            :disabled="googleLoading"
            class="flex items-center gap-2 px-4 py-2 bg-white text-gray-700 rounded-lg hover:bg-gray-100 transition-colors font-medium text-sm border border-gray-300"
            @click="connectGoogle"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
            {{ t('google.connectButton') }}
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
