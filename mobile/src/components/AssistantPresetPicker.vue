<script setup lang="ts">
import { ref, watch, computed } from "vue";
import { presetsApi, type AssistantPreset } from "@/api/presets";

const props = defineProps<{ active?: boolean }>();
const emit = defineEmits<{
  (e: "select", preset: AssistantPreset): void;
  (e: "close"): void;
}>();

const presets = ref<AssistantPreset[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

async function loadPresets() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await presetsApi.list();
    presets.value = resp.presets;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Не удалось загрузить наборы";
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.active,
  (now) => {
    if (now && !presets.value.length) loadPresets();
  },
  { immediate: true },
);

const visiblePresets = computed(() =>
  // The "custom" preset (empty collections) always renders. Other presets
  // render only when they resolved at least one collection — so empty
  // categories on a fresh DB don't clutter the picker.
  presets.value.filter((p) => p.ready),
);

function pick(p: AssistantPreset) {
  emit("select", p);
}

// Lucide-like inline icons keyed by name from backend (icons keep file
// small — no need to ship the full lucide package for one screen).
const iconPaths: Record<string, string> = {
  scale:
    '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
  calculator:
    '<rect width="16" height="20" x="4" y="2" rx="2"/><line x1="8" x2="16" y1="6" y2="6"/><line x1="16" x2="16" y1="14" y2="18"/><path d="M16 10h.01"/><path d="M12 10h.01"/><path d="M8 10h.01"/><path d="M12 14h.01"/><path d="M8 14h.01"/><path d="M12 18h.01"/><path d="M8 18h.01"/>',
  search:
    '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  bot:
    '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>',
  edit:
    '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>',
};

function iconSvg(name: string): string {
  return iconPaths[name] || iconPaths.bot!;
}
</script>

<template>
  <div class="h-full flex flex-col bg-stone-900">
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <div class="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
    </div>
    <div v-else-if="error" class="flex-1 flex flex-col items-center justify-center px-4 text-center">
      <p class="text-red-400 text-sm mb-3">{{ error }}</p>
      <button
        class="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm transition-colors"
        @click="loadPresets"
      >
        Повторить
      </button>
    </div>
    <div v-else class="flex-1 overflow-y-auto">
      <p class="px-4 pt-3 pb-2 text-xs text-stone-500">
        Выберите тематику — к новому ассистенту автоматически прикрепятся коллекции на эту тему.
      </p>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 px-3 pb-4">
        <button
          v-for="p in visiblePresets"
          :key="p.slug"
          class="flex items-start gap-3 p-3 rounded-xl bg-stone-800/60 hover:bg-stone-700/60 active:bg-stone-700 border border-stone-700/50 transition-colors text-left"
          @click="pick(p)"
        >
          <div
            class="shrink-0 w-10 h-10 rounded-lg bg-amber-600/15 text-amber-400 flex items-center justify-center"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              v-html="iconSvg(p.icon)"
            />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-white">{{ p.name }}</div>
            <div class="text-xs text-stone-400 mt-0.5 line-clamp-2">{{ p.description }}</div>
            <div v-if="p.collections.length > 0" class="text-[10px] text-stone-500 mt-1">
              {{ p.collections.length }} {{ p.collections.length === 1 ? "коллекция" : "коллекций" }}
            </div>
            <div v-else-if="p.slug === 'custom'" class="text-[10px] text-stone-500 mt-1">
              Без коллекций
            </div>
          </div>
        </button>
      </div>
    </div>
  </div>
</template>
