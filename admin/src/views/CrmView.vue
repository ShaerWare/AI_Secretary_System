<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import {
  Users,
  Building2,
  Link2,
  Settings2,
  AlertCircle,
  ExternalLink,
  RefreshCw,
  Check,
  X as XIcon,
  Save,
  ArrowDownUp,
  Clock,
  LayoutDashboard,
  Table2,
  MessageSquare,
  BookOpen,
  Database,
  Trash2,
} from 'lucide-vue-next'
import { amocrmApi } from '@/api/amocrm'
import type { AmoCRMSyncLogEntry, CRMDatasetStatus } from '@/api/amocrm'
import { useAuthStore } from '@/stores'
import CrmKanban from '@/components/CrmKanban.vue'
import CrmDeals from '@/components/CrmDeals.vue'
import CrmInbox from '@/components/CrmInbox.vue'

const { t } = useI18n()
const route = useRoute()

// Tab management
const activeTab = ref('settings')

const tabs = computed(() => {
  const list = [
    { id: 'settings', label: t('crm.tabs.settings'), icon: Settings2 },
  ]
  if (isConnected.value) {
    list.push(
      { id: 'kanban', label: t('crm.tabs.kanban'), icon: LayoutDashboard },
      { id: 'deals', label: t('crm.tabs.deals'), icon: Table2 },
      { id: 'inbox', label: t('crm.tabs.inbox'), icon: MessageSquare },
    )
  }
  return list
})

// amoCRM integration state
const isConnected = ref(false)
const isLoading = ref(false)
const isSyncing = ref(false)
const isSaving = ref(false)
const toast = ref<{ message: string; type: 'success' | 'error' } | null>(null)

// Settings form
const settings = ref({
  subdomain: '',
  clientId: '',
  clientSecret: '',
  redirectUri: window.location.origin + '/admin/crm/oauth-redirect',
  syncContacts: true,
  syncLeads: true,
  syncTasks: false,
  autoCreateLead: true,
  leadPipelineId: '',
  leadStatusId: '',
  amojoBaseUrl: 'https://amojo.amocrm.ru',
  amojoScopeId: '',
  amojoChannelSecret: '',
})

// Stats
const stats = ref({
  contacts: 0,
  leads: 0,
  lastSync: null as string | null
})

// Account info
const accountInfo = ref<Record<string, unknown>>({})

// Sync log
const syncLogs = ref<AmoCRMSyncLogEntry[]>([])
const showSyncLog = ref(false)

// Auth store for role checks
const authStore = useAuthStore()

// CRM Dataset state
const datasetStatus = ref<CRMDatasetStatus>({
  synced: false,
  collection_id: null,
  documents: 0,
  total_sections: 0,
  last_sync: null,
  files: [],
})
const isDatasetSyncing = ref(false)

function showToast(message: string, type: 'success' | 'error' = 'success') {
  toast.value = { message, type }
  setTimeout(() => { toast.value = null }, 3000)
}

// Track whether secret is saved on server (masked)
const clientSecretSaved = ref(false)

async function loadConfig() {
  try {
    const resp = await amocrmApi.getConfig()
    const config = resp.config as unknown as Record<string, unknown>
    if (config && config.subdomain) {
      settings.value.subdomain = (config.subdomain as string) || ''
      settings.value.clientId = (config.client_id as string) || ''
      settings.value.redirectUri = (config.redirect_uri as string) || window.location.origin + '/admin/crm/oauth-redirect'
      settings.value.syncContacts = (config.sync_contacts as boolean) ?? true
      settings.value.syncLeads = (config.sync_leads as boolean) ?? true
      settings.value.syncTasks = (config.sync_tasks as boolean) ?? false
      settings.value.autoCreateLead = (config.auto_create_lead as boolean) ?? true
      settings.value.leadPipelineId = config.lead_pipeline_id ? String(config.lead_pipeline_id) : ''
      settings.value.leadStatusId = config.lead_status_id ? String(config.lead_status_id) : ''
      settings.value.amojoBaseUrl = (config.amojo_base_url as string) || 'https://amojo.amocrm.ru'
      settings.value.amojoScopeId = (config.amojo_scope_id as string) || ''
      isConnected.value = (config.is_connected as boolean) || false
      stats.value.contacts = (config.contacts_count as number) || 0
      stats.value.leads = (config.leads_count as number) || 0
      stats.value.lastSync = (config.last_sync_at as string) || null
      accountInfo.value = (config.account_info as Record<string, unknown>) || {}
      clientSecretSaved.value = !!config.client_secret_masked
    }
  } catch {
    // Config not yet created — expected on first load
  }
}

async function connectAmoCRM() {
  isLoading.value = true
  try {
    // Save credentials first
    await amocrmApi.saveConfig({
      subdomain: settings.value.subdomain,
      client_id: settings.value.clientId,
      client_secret: settings.value.clientSecret,
      redirect_uri: settings.value.redirectUri,
      sync_contacts: settings.value.syncContacts,
      sync_leads: settings.value.syncLeads,
      sync_tasks: settings.value.syncTasks,
      auto_create_lead: settings.value.autoCreateLead,
    })

    // Get OAuth URL and redirect
    const resp = await amocrmApi.getAuthUrl()
    window.location.href = resp.auth_url
  } catch {
    showToast(t('crm.connectionFail'), 'error')
    isLoading.value = false
  }
}

async function disconnectAmoCRM() {
  try {
    await amocrmApi.disconnect()
    isConnected.value = false
    stats.value = { contacts: 0, leads: 0, lastSync: null }
    accountInfo.value = {}
    activeTab.value = 'settings'
  } catch {
    showToast(t('crm.connectionFail'), 'error')
  }
}

async function testConnection() {
  isLoading.value = true
  try {
    const resp = await amocrmApi.testConnection()
    if (resp.account) {
      accountInfo.value = resp.account
    }
    showToast(t('crm.connectionOk'))
  } catch {
    showToast(t('crm.connectionFail'), 'error')
  } finally {
    isLoading.value = false
  }
}

async function saveSettings() {
  isSaving.value = true
  try {
    const data: Record<string, unknown> = {
      subdomain: settings.value.subdomain,
      client_id: settings.value.clientId,
      redirect_uri: settings.value.redirectUri,
      sync_contacts: settings.value.syncContacts,
      sync_leads: settings.value.syncLeads,
      sync_tasks: settings.value.syncTasks,
      auto_create_lead: settings.value.autoCreateLead,
      lead_pipeline_id: settings.value.leadPipelineId ? Number(settings.value.leadPipelineId) : null,
      lead_status_id: settings.value.leadStatusId ? Number(settings.value.leadStatusId) : null,
      amojo_base_url: settings.value.amojoBaseUrl,
      amojo_scope_id: settings.value.amojoScopeId || null,
    }
    // Only send secrets if user entered new ones
    if (settings.value.clientSecret) {
      data.client_secret = settings.value.clientSecret
    }
    if (settings.value.amojoChannelSecret) {
      data.amojo_channel_secret = settings.value.amojoChannelSecret
    }
    await amocrmApi.saveConfig(data)
    showToast(t('crm.settingsSaved'))
  } catch {
    showToast(t('crm.connectionFail'), 'error')
  } finally {
    isSaving.value = false
  }
}

async function syncNow() {
  isSyncing.value = true
  try {
    const resp = await amocrmApi.sync()
    stats.value.contacts = resp.contacts_count
    stats.value.leads = resp.leads_count
    stats.value.lastSync = resp.synced_at
    showToast(t('crm.syncSuccess'))
  } catch {
    showToast(t('crm.connectionFail'), 'error')
  } finally {
    isSyncing.value = false
  }
}

async function loadSyncLog() {
  showSyncLog.value = !showSyncLog.value
  if (showSyncLog.value) {
    try {
      const resp = await amocrmApi.getSyncLog()
      syncLogs.value = resp.logs
    } catch {
      syncLogs.value = []
    }
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString()
}

// CRM Dataset functions
async function loadDatasetStatus() {
  try {
    datasetStatus.value = await amocrmApi.datasetStatus()
  } catch {
    // Ignore — dataset may not exist yet
  }
}

async function syncDataset() {
  isDatasetSyncing.value = true
  try {
    const result = await amocrmApi.datasetSync()
    showToast(t('crm.dataset.syncSuccess', { leads: result.leads_total, files: result.files_written }))
    await loadDatasetStatus()
  } catch {
    showToast(t('crm.dataset.syncFail'), 'error')
  } finally {
    isDatasetSyncing.value = false
  }
}

async function clearDataset() {
  try {
    await amocrmApi.datasetClear()
    showToast(t('crm.dataset.clearSuccess'))
    await loadDatasetStatus()
  } catch {
    showToast(t('crm.dataset.syncFail'), 'error')
  }
}

onMounted(async () => {
  await loadConfig()
  await loadDatasetStatus()

  // Check for OAuth redirect result
  const query = route.query
  if (query.connected === 'true') {
    showToast(t('crm.connectedSuccess'))
    await loadConfig()
  } else if (query.error) {
    showToast(String(query.error), 'error')
  }

  // Default to kanban tab if connected
  if (isConnected.value) {
    activeTab.value = 'kanban'
  }
})
</script>

<template>
  <div class="space-y-6">
    <!-- Toast -->
    <Transition name="fade">
      <div
        v-if="toast"
        :class="[
          'fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium',
          toast.type === 'success' ? 'bg-green-500/90 text-white' : 'bg-red-500/90 text-white'
        ]"
      >
        {{ toast.message }}
      </div>
    </Transition>

    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="p-2 rounded-lg bg-blue-500/20">
          <Users class="w-6 h-6 text-blue-500" />
        </div>
        <div>
          <h1 class="text-2xl font-bold">{{ t('crm.title') }}</h1>
          <p class="text-muted-foreground">{{ t('crm.description') }}</p>
        </div>
      </div>
    </div>

    <!-- Tab Bar -->
    <div class="flex gap-1 border-b border-border">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px',
          activeTab === tab.id
            ? 'border-primary text-primary'
            : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
        ]"
        @click="activeTab = tab.id"
      >
        <component :is="tab.icon" class="w-4 h-4" />
        {{ tab.label }}
      </button>
    </div>

    <!-- Tab Content: Settings -->
    <div v-if="activeTab === 'settings'">
      <!-- Connection Status Card -->
      <div class="card p-6">
        <div class="flex items-center justify-between mb-6">
          <div class="flex items-center gap-3">
            <Building2 class="w-8 h-8 text-blue-500" />
            <div>
              <h2 class="text-lg font-semibold">amoCRM</h2>
              <p class="text-sm text-muted-foreground">{{ t('crm.amoDescription') }}</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span
              :class="[
                'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium',
                isConnected
                  ? 'bg-green-500/20 text-green-400'
                  : 'bg-yellow-500/20 text-yellow-400'
              ]"
            >
              <span :class="['w-2 h-2 rounded-full', isConnected ? 'bg-green-400' : 'bg-yellow-400']" />
              {{ isConnected ? t('crm.connected') : t('crm.notConnected') }}
            </span>
          </div>
        </div>

        <!-- Setup hint (only when not connected) -->
        <div v-if="!isConnected" class="p-4 rounded-lg bg-secondary/50 border border-border mb-6">
          <div class="flex gap-3">
            <AlertCircle class="w-5 h-5 text-yellow-400 shrink-0 mt-0.5" />
            <div>
              <p class="text-sm font-medium">{{ t('crm.setupRequired') }}</p>
              <p class="text-sm text-muted-foreground mt-1">{{ t('crm.setupDescription') }}</p>
            </div>
          </div>
        </div>

        <!-- Account Info (when connected) -->
        <div v-if="isConnected && accountInfo.name" class="p-3 rounded-lg bg-blue-500/10 border border-blue-500/20 mb-4">
          <div class="text-sm">
            <span class="text-muted-foreground">{{ t('crm.accountName') }}:</span>
            <span class="ml-2 font-medium">{{ accountInfo.name }}</span>
          </div>
        </div>

        <!-- Stats (when connected) -->
        <div v-if="isConnected" class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div class="p-4 rounded-lg bg-secondary/50">
            <div class="text-2xl font-bold">{{ stats.contacts }}</div>
            <div class="text-sm text-muted-foreground">{{ t('crm.contacts') }}</div>
          </div>
          <div class="p-4 rounded-lg bg-secondary/50">
            <div class="text-2xl font-bold">{{ stats.leads }}</div>
            <div class="text-sm text-muted-foreground">{{ t('crm.leads') }}</div>
          </div>
          <div class="p-4 rounded-lg bg-secondary/50">
            <div class="text-sm text-muted-foreground">{{ t('crm.lastSync') }}</div>
            <div class="text-sm font-medium">{{ stats.lastSync ? formatDate(stats.lastSync) : t('crm.never') }}</div>
          </div>
        </div>

        <!-- Credentials Form (always visible) -->
        <div class="space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('crm.subdomain') }}</label>
              <div class="flex">
                <input
                  v-model="settings.subdomain"
                  type="text"
                  placeholder="your-company"
                  class="input rounded-r-none flex-1"
                />
                <span class="inline-flex items-center px-3 bg-secondary border border-l-0 border-border rounded-r-lg text-sm text-muted-foreground">
                  .amocrm.ru
                </span>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('crm.clientId') }}</label>
              <input
                v-model="settings.clientId"
                type="text"
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                class="input w-full"
              />
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('crm.clientSecret') }}</label>
              <input
                v-model="settings.clientSecret"
                type="password"
                :placeholder="clientSecretSaved ? '••••••• (saved)' : '...'"
                class="input w-full"
              />
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('crm.redirectUri') }}</label>
              <input
                v-model="settings.redirectUri"
                type="text"
                readonly
                class="input w-full bg-secondary/50 cursor-not-allowed"
              />
            </div>
          </div>

          <!-- Sync Settings -->
          <div v-if="isConnected" class="pt-4 border-t border-border">
            <h3 class="font-medium flex items-center gap-2 mb-3">
              <Settings2 class="w-4 h-4" />
              {{ t('crm.syncSettings') }}
            </h3>

            <div class="space-y-3">
              <label class="flex items-center gap-3">
                <input v-model="settings.syncContacts" type="checkbox" class="checkbox" />
                <span>{{ t('crm.syncContactsLabel') }}</span>
              </label>
              <label class="flex items-center gap-3">
                <input v-model="settings.syncLeads" type="checkbox" class="checkbox" />
                <span>{{ t('crm.syncLeadsLabel') }}</span>
              </label>
              <label class="flex items-center gap-3">
                <input v-model="settings.autoCreateLead" type="checkbox" class="checkbox" />
                <span>{{ t('crm.autoCreateLeadLabel') }}</span>
              </label>
            </div>
          </div>

          <!-- Amojo (Inbox) Settings -->
          <div v-if="isConnected" class="pt-4 border-t border-border">
            <h3 class="font-medium flex items-center gap-2 mb-3">
              <MessageSquare class="w-4 h-4" />
              {{ t('crm.inbox.settingsTitle') }}
            </h3>
            <p class="text-sm text-muted-foreground mb-3">{{ t('crm.inbox.settingsHint') }}</p>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium mb-1.5">Amojo Base URL</label>
                <input
                  v-model="settings.amojoBaseUrl"
                  type="text"
                  placeholder="https://amojo.amocrm.ru"
                  class="input w-full"
                />
              </div>
              <div>
                <label class="block text-sm font-medium mb-1.5">Scope ID</label>
                <input
                  v-model="settings.amojoScopeId"
                  type="text"
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  class="input w-full"
                />
              </div>
              <div class="md:col-span-2">
                <label class="block text-sm font-medium mb-1.5">Channel Secret</label>
                <input
                  v-model="settings.amojoChannelSecret"
                  type="password"
                  placeholder="Channel secret key..."
                  class="input w-full"
                />
              </div>
            </div>
          </div>

          <!-- Save / Connect buttons -->
          <div class="flex justify-end gap-2 pt-4">
            <button :disabled="isSaving" class="btn btn-secondary" @click="saveSettings">
              <Save v-if="!isSaving" class="w-4 h-4 mr-2" />
              <RefreshCw v-else class="w-4 h-4 mr-2 animate-spin" />
              {{ t('crm.saveSettings') }}
            </button>
            <button
              v-if="!isConnected"
              :disabled="!settings.subdomain || !settings.clientId || (!settings.clientSecret && !clientSecretSaved) || isLoading"
              class="btn btn-primary"
              @click="connectAmoCRM"
            >
              <Link2 v-if="!isLoading" class="w-4 h-4 mr-2" />
              <RefreshCw v-else class="w-4 h-4 mr-2 animate-spin" />
              {{ t('crm.connect') }}
            </button>
          </div>
        </div>

        <!-- Actions (when connected) -->
        <div v-if="isConnected" class="flex justify-between pt-6 border-t border-border mt-6">
          <button class="btn btn-ghost text-red-400 hover:bg-red-500/10" @click="disconnectAmoCRM">
            <XIcon class="w-4 h-4 mr-2" />
            {{ t('crm.disconnect') }}
          </button>
          <div class="flex gap-2">
            <button :disabled="isSyncing" class="btn btn-secondary" @click="syncNow">
              <ArrowDownUp :class="['w-4 h-4 mr-2', isSyncing && 'animate-spin']" />
              {{ isSyncing ? t('crm.syncing') : t('crm.syncNow') }}
            </button>
            <button :disabled="isLoading" class="btn btn-secondary" @click="testConnection">
              <RefreshCw :class="['w-4 h-4 mr-2', isLoading && 'animate-spin']" />
              {{ t('crm.testConnection') }}
            </button>
            <a
              :href="`https://${settings.subdomain}.amocrm.ru`"
              target="_blank"
              class="btn btn-primary"
            >
              <ExternalLink class="w-4 h-4 mr-2" />
              {{ t('crm.openAmoCRM') }}
            </a>
          </div>
        </div>
      </div>

      <!-- Sync Log -->
      <div class="card p-6 mt-6">
        <button class="flex items-center gap-2 font-semibold w-full text-left" @click="loadSyncLog">
          <Clock class="w-5 h-5" />
          {{ t('crm.syncLog') }}
          <span class="text-muted-foreground text-sm ml-auto">{{ showSyncLog ? '▲' : '▼' }}</span>
        </button>

        <div v-if="showSyncLog" class="mt-4">
          <div v-if="syncLogs.length === 0" class="text-sm text-muted-foreground py-4 text-center">
            {{ t('crm.never') }}
          </div>
          <div v-else class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-border text-left">
                  <th class="pb-2 pr-4">{{ t('crm.status') }}</th>
                  <th class="pb-2 pr-4">Direction</th>
                  <th class="pb-2 pr-4">Type</th>
                  <th class="pb-2 pr-4">Action</th>
                  <th class="pb-2">Date</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="log in syncLogs" :key="log.id" class="border-b border-border/50">
                  <td class="py-2 pr-4">
                    <span
                      :class="[
                        'inline-block w-2 h-2 rounded-full',
                        log.status === 'success' ? 'bg-green-400' : 'bg-red-400'
                      ]"
                    />
                  </td>
                  <td class="py-2 pr-4 text-muted-foreground">{{ log.direction }}</td>
                  <td class="py-2 pr-4">{{ log.entity_type }}</td>
                  <td class="py-2 pr-4">{{ log.action }}</td>
                  <td class="py-2 text-muted-foreground">{{ formatDate(log.created) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- CRM Dataset (Knowledge Base Sync) -->
      <div v-if="isConnected" class="card p-6 mt-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-semibold flex items-center gap-2">
            <BookOpen class="w-5 h-5" />
            {{ t('crm.dataset.title') }}
          </h3>
          <div class="flex gap-2">
            <button
              :disabled="isDatasetSyncing"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              @click="syncDataset"
            >
              <Database :class="['w-4 h-4', isDatasetSyncing && 'animate-spin']" />
              {{ isDatasetSyncing ? t('crm.dataset.syncing') : t('crm.dataset.syncButton') }}
            </button>
            <button
              v-if="datasetStatus.synced && authStore.isAdmin"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg hover:bg-destructive/10 text-destructive"
              @click="clearDataset"
            >
              <Trash2 class="w-4 h-4" />
              {{ t('crm.dataset.clear') }}
            </button>
          </div>
        </div>

        <p class="text-sm text-muted-foreground mb-3">{{ t('crm.dataset.description') }}</p>

        <div v-if="datasetStatus.synced" class="grid grid-cols-3 gap-4">
          <div class="p-3 rounded-lg bg-secondary/50">
            <div class="text-lg font-bold">{{ datasetStatus.documents }}</div>
            <div class="text-xs text-muted-foreground">{{ t('crm.dataset.documents') }}</div>
          </div>
          <div class="p-3 rounded-lg bg-secondary/50">
            <div class="text-lg font-bold">{{ datasetStatus.total_sections }}</div>
            <div class="text-xs text-muted-foreground">{{ t('crm.dataset.sections') }}</div>
          </div>
          <div class="p-3 rounded-lg bg-secondary/50">
            <div class="text-sm">{{ datasetStatus.last_sync ? formatDate(datasetStatus.last_sync) : '—' }}</div>
            <div class="text-xs text-muted-foreground">{{ t('crm.dataset.lastSync') }}</div>
          </div>
        </div>
        <div v-else class="text-sm text-muted-foreground italic">
          {{ t('crm.dataset.notSynced') }}
        </div>
      </div>

      <!-- Features -->
      <div class="card p-6 mt-6">
        <h3 class="font-semibold mb-4">{{ t('crm.plannedFeatures') }}</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div class="flex items-start gap-3 p-3 rounded-lg bg-secondary/30">
            <Check class="w-5 h-5 text-green-400 shrink-0 mt-0.5" />
            <div>
              <div class="font-medium">{{ t('crm.feature.oauth') }}</div>
              <div class="text-sm text-muted-foreground">{{ t('crm.feature.oauthDesc') }}</div>
            </div>
          </div>
          <div class="flex items-start gap-3 p-3 rounded-lg bg-secondary/30">
            <Check class="w-5 h-5 text-green-400 shrink-0 mt-0.5" />
            <div>
              <div class="font-medium">{{ t('crm.feature.contacts') }}</div>
              <div class="text-sm text-muted-foreground">{{ t('crm.feature.contactsDesc') }}</div>
            </div>
          </div>
          <div class="flex items-start gap-3 p-3 rounded-lg bg-secondary/30">
            <Check class="w-5 h-5 text-green-400 shrink-0 mt-0.5" />
            <div>
              <div class="font-medium">{{ t('crm.feature.leads') }}</div>
              <div class="text-sm text-muted-foreground">{{ t('crm.feature.leadsDesc') }}</div>
            </div>
          </div>
          <div class="flex items-start gap-3 p-3 rounded-lg bg-secondary/30">
            <Check class="w-5 h-5 text-green-400 shrink-0 mt-0.5" />
            <div>
              <div class="font-medium">{{ t('crm.feature.webhook') }}</div>
              <div class="text-sm text-muted-foreground">{{ t('crm.feature.webhookDesc') }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab Content: Kanban -->
    <CrmKanban v-if="activeTab === 'kanban'" :subdomain="settings.subdomain" :currency="(accountInfo.currency as string) || 'RUB'" />

    <!-- Tab Content: Deals -->
    <CrmDeals v-if="activeTab === 'deals'" :subdomain="settings.subdomain" :currency="(accountInfo.currency as string) || 'RUB'" />

    <!-- Tab Content: Inbox -->
    <CrmInbox v-if="activeTab === 'inbox'" />
  </div>
</template>
