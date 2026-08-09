<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { presetsApi, type AssistantPreset } from '@/api/presets'
import { Scale, Calculator, Search, Bot, Edit3, X } from 'lucide-vue-next'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (e: 'select', preset: AssistantPreset): void
  (e: 'close'): void
}>()

const presets = ref<AssistantPreset[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function loadPresets() {
  loading.value = true
  error.value = null
  try {
    const resp = await presetsApi.list()
    presets.value = resp.presets
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось загрузить'
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (now) => {
    if (now && !presets.value.length) loadPresets()
  },
)

onMounted(() => {
  if (props.open) loadPresets()
})

const visiblePresets = computed(() => presets.value.filter((p) => p.ready))

const iconMap = {
  scale: Scale,
  calculator: Calculator,
  search: Search,
  bot: Bot,
  edit: Edit3,
} as const

function getIcon(name: string) {
  return iconMap[name as keyof typeof iconMap] || Bot
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
    @click.self="emit('close')"
  >
    <div
      class="w-full max-w-2xl max-h-[80vh] flex flex-col bg-stone-900 border border-stone-700 rounded-2xl shadow-2xl overflow-hidden"
    >
      <!-- Header -->
      <div class="shrink-0 flex items-center justify-between px-5 py-4 border-b border-stone-800">
        <div>
          <h2 class="text-lg font-semibold text-white">Новый ассистент</h2>
          <p class="text-xs text-stone-400 mt-0.5">
            Выберите тематику — к ассистенту автоматически прикрепятся коллекции на эту тему
          </p>
        </div>
        <button
          class="text-stone-500 hover:text-white transition-colors p-1"
          @click="emit('close')"
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Body -->
      <div class="flex-1 overflow-y-auto p-4">
        <div v-if="loading" class="flex items-center justify-center py-12">
          <div
            class="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"
          />
        </div>
        <div v-else-if="error" class="flex flex-col items-center justify-center py-12 text-center">
          <p class="text-red-400 text-sm mb-3">{{ error }}</p>
          <button
            class="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm transition-colors"
            @click="loadPresets"
          >
            Повторить
          </button>
        </div>
        <div v-else class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            v-for="p in visiblePresets"
            :key="p.slug"
            class="flex items-start gap-3 p-4 rounded-xl bg-stone-800/60 hover:bg-stone-700/80 active:bg-stone-700 border border-stone-700/50 hover:border-amber-600/40 transition-all text-left group"
            @click="emit('select', p)"
          >
            <div
              class="shrink-0 w-11 h-11 rounded-lg bg-amber-600/15 text-amber-400 flex items-center justify-center group-hover:bg-amber-600/25 transition-colors"
            >
              <component :is="getIcon(p.icon)" class="w-5 h-5" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium text-white">{{ p.name }}</div>
              <div class="text-xs text-stone-400 mt-1 line-clamp-2">{{ p.description }}</div>
              <div v-if="p.collections.length > 0" class="text-[11px] text-amber-500/80 mt-2">
                {{ p.collections.length }}
                {{ p.collections.length === 1 ? 'коллекция' : 'коллекций' }}
              </div>
              <div v-else-if="p.slug === 'custom'" class="text-[11px] text-stone-500 mt-2">
                Без коллекций — настроить позже
              </div>
            </div>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
