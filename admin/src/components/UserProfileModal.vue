<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { User, Lock, Save, X, Check } from 'lucide-vue-next'
import { googleApi, type GoogleOAuthStatus } from '@/api/google'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { useConfirmStore } from '@/stores/confirm'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const { t } = useI18n()
const authStore = useAuthStore()
const toast = useToastStore()
const confirm = useConfirmStore()

const profileLoading = ref(false)
const profileData = ref<Record<string, string | null>>({})
const displayName = ref('')
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const passwordLoading = ref(false)
const googleStatus = ref<GoogleOAuthStatus>({ connected: false, google_email: null, scopes: [] })
const googleLoading = ref(false)

const roleColors: Record<string, string> = {
  admin: 'bg-red-500/20 text-red-400',
  user: 'bg-blue-500/20 text-blue-400',
  guest: 'bg-gray-500/20 text-gray-400'
}

async function loadProfile() {
  profileLoading.value = true
  try {
    const resp = await fetch('/admin/auth/profile', { headers: authStore.getAuthHeaders() })
    if (resp.ok) {
      profileData.value = await resp.json()
      displayName.value = profileData.value.display_name || ''
    }
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
      body: JSON.stringify({ old_password: oldPassword.value, new_password: newPassword.value })
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

async function loadGoogleStatus() {
  try {
    googleStatus.value = await googleApi.getStatus()
  } catch {
    // optional feature — silent fail
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

function close() { emit('update:modelValue', false) }

onMounted(() => {
  if (props.modelValue) {
    loadProfile()
    loadGoogleStatus()
  }
})

import { watch } from 'vue'
watch(() => props.modelValue, (v) => {
  if (v) {
    loadProfile()
    loadGoogleStatus()
  }
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="modelValue"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      @click.self="close"
    >
      <div class="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <!-- Header -->
        <div class="flex items-center justify-between p-4 border-b border-border sticky top-0 bg-card">
          <h2 class="font-semibold flex items-center gap-2">
            <User class="w-5 h-5" />
            {{ t('profile.title') }}
          </h2>
          <button
            class="p-1.5 rounded-lg hover:bg-secondary text-muted-foreground transition-colors"
            @click="close"
          >
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="p-4 space-y-4">
          <!-- Username + Role -->
          <div class="bg-secondary/30 rounded-xl p-4 space-y-3">
            <div>
              <label class="block text-xs text-muted-foreground mb-1">{{ t('profile.username') }}</label>
              <div class="text-sm font-medium">
                {{ profileData.username || authStore.user?.username }}
              </div>
            </div>
            <div>
              <label class="block text-xs text-muted-foreground mb-1">{{ t('profile.role') }}</label>
              <span
                :class="[
                  'inline-block px-2.5 py-0.5 text-xs rounded-full',
                  roleColors[authStore.user?.role || 'guest']
                ]"
              >
                {{ t(`roles.${authStore.user?.role || 'guest'}`) }}
              </span>
            </div>
          </div>

          <!-- Display Name -->
          <div class="bg-card border border-border rounded-xl p-4">
            <label class="block text-sm text-muted-foreground mb-2">{{ t('profile.displayName') }}</label>
            <div class="flex gap-2">
              <input
                v-model="displayName"
                type="text"
                class="flex-1 px-3 py-2 bg-secondary/50 rounded-lg text-sm border border-border focus:border-primary focus:outline-none"
                :placeholder="t('profile.displayName')"
                :disabled="profileLoading"
              />
              <button
                class="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm hover:bg-primary/90 transition-colors flex items-center gap-1.5 shrink-0"
                @click="saveProfile"
              >
                <Save class="w-4 h-4" />
                {{ t('profile.save') }}
              </button>
            </div>
          </div>

          <!-- Change Password -->
          <div class="bg-card border border-border rounded-xl p-4">
            <h3 class="font-medium flex items-center gap-2 mb-3">
              <Lock class="w-4 h-4" />
              {{ t('profile.changePassword') }}
            </h3>
            <div class="space-y-2">
              <input
                v-model="oldPassword"
                type="password"
                class="w-full px-3 py-2 bg-secondary/50 rounded-lg text-sm border border-border focus:border-primary focus:outline-none"
                :placeholder="t('profile.currentPassword')"
              />
              <input
                v-model="newPassword"
                type="password"
                class="w-full px-3 py-2 bg-secondary/50 rounded-lg text-sm border border-border focus:border-primary focus:outline-none"
                :placeholder="t('profile.newPassword')"
              />
              <input
                v-model="confirmPassword"
                type="password"
                class="w-full px-3 py-2 bg-secondary/50 rounded-lg text-sm border border-border focus:border-primary focus:outline-none"
                :placeholder="t('profile.confirmPassword')"
              />
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
          <div class="bg-card border border-border rounded-xl p-4">
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
      </div>
    </div>
  </Teleport>
</template>
