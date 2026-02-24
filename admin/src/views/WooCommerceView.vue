<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { woocommerceApi } from '@/api/woocommerce'
import type { WooCommerceConfig, WooCommerceDatasetStatus } from '@/api/woocommerce'
import {
  ShoppingBag,
  Settings2,
  Database,
  Trash2,
  BookOpen,
  CheckCircle,
  XCircle,
  Loader2,
  Save,
  Unplug,
  Plug
} from 'lucide-vue-next'

const { t } = useI18n()
const authStore = useAuthStore()

// State
const config = ref<WooCommerceConfig | null>(null)
const isLoading = ref(false)
const isSaving = ref(false)
const isTesting = ref(false)
const isDatasetSyncing = ref(false)
const toast = ref<{ message: string; type: 'success' | 'error' } | null>(null)

// Form
const form = ref({
  store_url: '',
  consumer_key: '',
  consumer_secret: '',
})

// Dataset
const datasetStatus = ref<WooCommerceDatasetStatus>({
  synced: false,
  collection_id: null,
  documents: 0,
  total_sections: 0,
  last_sync: null,
  files: [],
})

function showToast(message: string, type: 'success' | 'error' = 'success') {
  toast.value = { message, type }
  setTimeout(() => { toast.value = null }, 4000)
}

async function loadConfig() {
  try {
    const result = await woocommerceApi.getConfig()
    config.value = result.config
    if (config.value) {
      form.value.store_url = config.value.store_url || ''
      // Don't overwrite keys — they come back masked
    }
  } catch {
    // Config may not exist yet
  }
}

async function loadDatasetStatus() {
  try {
    datasetStatus.value = await woocommerceApi.datasetStatus()
  } catch {
    // Ignore
  }
}

async function saveConfig() {
  isSaving.value = true
  try {
    const data: Record<string, unknown> = { store_url: form.value.store_url }
    if (form.value.consumer_key) data.consumer_key = form.value.consumer_key
    if (form.value.consumer_secret) data.consumer_secret = form.value.consumer_secret
    const result = await woocommerceApi.saveConfig(data)
    config.value = result.config
    showToast(t('common.saved'))
    form.value.consumer_key = ''
    form.value.consumer_secret = ''
  } catch {
    showToast(t('woocommerce.connectionFail'), 'error')
  } finally {
    isSaving.value = false
  }
}

async function testConnection() {
  isTesting.value = true
  try {
    await woocommerceApi.testConnection()
    showToast(t('woocommerce.connectionOk'))
    await loadConfig()
  } catch {
    showToast(t('woocommerce.connectionFail'), 'error')
  } finally {
    isTesting.value = false
  }
}

async function disconnect() {
  try {
    await woocommerceApi.disconnect()
    config.value = null
    form.value = { store_url: '', consumer_key: '', consumer_secret: '' }
    showToast(t('woocommerce.notConnected'))
    await loadConfig()
  } catch {
    showToast(t('woocommerce.connectionFail'), 'error')
  }
}

async function syncDataset() {
  isDatasetSyncing.value = true
  try {
    const result = await woocommerceApi.datasetSync()
    showToast(
      t('woocommerce.dataset.syncSuccess', {
        products: result.products,
        categories: result.categories,
        orders: result.orders,
      })
    )
    await loadDatasetStatus()
    await loadConfig()
  } catch {
    showToast(t('woocommerce.dataset.syncFail'), 'error')
  } finally {
    isDatasetSyncing.value = false
  }
}

async function clearDataset() {
  try {
    await woocommerceApi.datasetClear()
    showToast(t('woocommerce.dataset.clearSuccess'))
    await loadDatasetStatus()
  } catch {
    showToast(t('woocommerce.dataset.syncFail'), 'error')
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return dateStr
}

onMounted(async () => {
  isLoading.value = true
  await Promise.all([loadConfig(), loadDatasetStatus()])
  isLoading.value = false
})
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6">
    <!-- Toast -->
    <Transition name="fade">
      <div
        v-if="toast"
        :class="[
          'fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm',
          toast.type === 'error' ? 'bg-destructive text-destructive-foreground' : 'bg-primary text-primary-foreground'
        ]"
      >
        {{ toast.message }}
      </div>
    </Transition>

    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <ShoppingBag class="w-7 h-7 text-primary" />
        <div>
          <h1 class="text-2xl font-bold">{{ t('woocommerce.title') }}</h1>
          <p class="text-sm text-muted-foreground">{{ t('woocommerce.description') }}</p>
        </div>
      </div>
      <div v-if="config?.is_connected" class="flex items-center gap-2 text-sm text-green-500">
        <CheckCircle class="w-4 h-4" />
        {{ t('woocommerce.connected') }}
      </div>
      <div v-else class="flex items-center gap-2 text-sm text-muted-foreground">
        <XCircle class="w-4 h-4" />
        {{ t('woocommerce.notConnected') }}
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex items-center justify-center py-12">
      <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
    </div>

    <template v-else>
      <!-- Connection Settings -->
      <div class="card p-6">
        <h3 class="font-semibold flex items-center gap-2 mb-4">
          <Settings2 class="w-5 h-5" />
          {{ t('woocommerce.tabs.settings') }}
        </h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('woocommerce.storeUrl') }}</label>
            <input
              v-model="form.store_url"
              type="url"
              :placeholder="t('woocommerce.storeUrlPlaceholder')"
              class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
            />
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('woocommerce.consumerKey') }}</label>
              <input
                v-model="form.consumer_key"
                type="password"
                :placeholder="config?.consumer_key_masked || 'ck_...'"
                class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
              />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('woocommerce.consumerSecret') }}</label>
              <input
                v-model="form.consumer_secret"
                type="password"
                :placeholder="config?.consumer_secret_masked || 'cs_...'"
                class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
              />
            </div>
          </div>

          <div class="flex gap-2 pt-2">
            <button
              :disabled="isSaving"
              class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg bg-secondary hover:bg-secondary/80"
              @click="saveConfig"
            >
              <Save class="w-4 h-4" />
              {{ t('woocommerce.save') }}
            </button>
            <button
              :disabled="isTesting || !config?.consumer_key_masked"
              class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              @click="testConnection"
            >
              <Plug :class="['w-4 h-4', isTesting && 'animate-spin']" />
              {{ t('woocommerce.testConnection') }}
            </button>
            <button
              v-if="config?.is_connected"
              class="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg hover:bg-destructive/10 text-destructive"
              @click="disconnect"
            >
              <Unplug class="w-4 h-4" />
              {{ t('woocommerce.disconnect') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Dataset Sync Card -->
      <div v-if="config?.is_connected" class="card p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-semibold flex items-center gap-2">
            <BookOpen class="w-5 h-5" />
            {{ t('woocommerce.dataset.title') }}
          </h3>
          <div class="flex gap-2">
            <button
              :disabled="isDatasetSyncing"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              @click="syncDataset"
            >
              <Database :class="['w-4 h-4', isDatasetSyncing && 'animate-spin']" />
              {{ isDatasetSyncing ? t('woocommerce.dataset.syncing') : t('woocommerce.dataset.syncButton') }}
            </button>
            <button
              v-if="datasetStatus.synced && authStore.canManage('sales')"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg hover:bg-destructive/10 text-destructive"
              @click="clearDataset"
            >
              <Trash2 class="w-4 h-4" />
              {{ t('woocommerce.dataset.clear') }}
            </button>
          </div>
        </div>

        <p class="text-sm text-muted-foreground mb-3">{{ t('woocommerce.dataset.description') }}</p>

        <div v-if="datasetStatus.synced" class="space-y-3">
          <!-- Stats from config (products, categories, orders) -->
          <div class="grid grid-cols-3 gap-4">
            <div class="p-3 rounded-lg bg-secondary/50">
              <div class="text-lg font-bold">{{ config?.products_count ?? 0 }}</div>
              <div class="text-xs text-muted-foreground">{{ t('woocommerce.dataset.products') }}</div>
            </div>
            <div class="p-3 rounded-lg bg-secondary/50">
              <div class="text-lg font-bold">{{ config?.categories_count ?? 0 }}</div>
              <div class="text-xs text-muted-foreground">{{ t('woocommerce.dataset.categories') }}</div>
            </div>
            <div class="p-3 rounded-lg bg-secondary/50">
              <div class="text-lg font-bold">{{ config?.orders_count ?? 0 }}</div>
              <div class="text-xs text-muted-foreground">{{ t('woocommerce.dataset.orders') }}</div>
            </div>
          </div>
          <!-- Stats from dataset (documents, sections, last sync) -->
          <div class="grid grid-cols-3 gap-4">
            <div class="p-3 rounded-lg bg-secondary/50">
              <div class="text-lg font-bold">{{ datasetStatus.documents }}</div>
              <div class="text-xs text-muted-foreground">{{ t('woocommerce.dataset.documents') }}</div>
            </div>
            <div class="p-3 rounded-lg bg-secondary/50">
              <div class="text-lg font-bold">{{ datasetStatus.total_sections }}</div>
              <div class="text-xs text-muted-foreground">{{ t('woocommerce.dataset.sections') }}</div>
            </div>
            <div class="p-3 rounded-lg bg-secondary/50">
              <div class="text-sm">{{ formatDate(datasetStatus.last_sync) }}</div>
              <div class="text-xs text-muted-foreground">{{ t('woocommerce.dataset.lastSync') }}</div>
            </div>
          </div>
        </div>
        <div v-else class="text-sm text-muted-foreground italic">
          {{ t('woocommerce.dataset.notSynced') }}
        </div>
      </div>
    </template>
  </div>
</template>
