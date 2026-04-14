<script setup lang="ts">
import { ref } from "vue";
import type { ContextFile } from "@/api/chat";

const props = defineProps<{
  files: ContextFile[];
}>();

const emit = defineEmits<{
  update: [files: ContextFile[]];
  upload: [];
}>();

const editingIndex = ref<number | null>(null);
const editingName = ref("");
const editingContent = ref("");
const expandedIndex = ref<number | null>(null);

function startEdit(index: number) {
  const file = props.files[index];
  if (!file) return;
  editingIndex.value = index;
  editingName.value = file.name;
  editingContent.value = file.content;
}

function saveEdit() {
  if (editingIndex.value === null) return;
  const next = props.files.slice();
  next[editingIndex.value] = {
    name: editingName.value || "untitled.txt",
    content: editingContent.value,
  };
  emit("update", next);
  editingIndex.value = null;
  editingName.value = "";
  editingContent.value = "";
}

function cancelEdit() {
  if (editingIndex.value !== null) {
    const file = props.files[editingIndex.value];
    if (file && !file.content && editingContent.value === "") {
      const next = props.files.slice();
      next.splice(editingIndex.value, 1);
      emit("update", next);
    }
  }
  editingIndex.value = null;
  editingName.value = "";
  editingContent.value = "";
}

function removeFile(index: number) {
  const next = props.files.slice();
  next.splice(index, 1);
  emit("update", next);
  if (editingIndex.value === index) editingIndex.value = null;
  if (expandedIndex.value === index) expandedIndex.value = null;
}

function addEmpty() {
  const next = props.files.slice();
  const idx = next.length + 1;
  next.push({ name: `file_${idx}.txt`, content: "" });
  emit("update", next);
  editingIndex.value = next.length - 1;
  editingName.value = next[next.length - 1]!.name;
  editingContent.value = "";
}

function toggleExpand(index: number) {
  expandedIndex.value = expandedIndex.value === index ? null : index;
}
</script>

<template>
  <div class="flex flex-col min-h-0">
    <div class="shrink-0 px-3 py-2 flex items-center justify-between gap-2">
      <span class="text-xs text-stone-400 uppercase tracking-wide font-medium">
        Файлы ({{ files.length }})
      </span>
      <div class="flex items-center gap-2">
        <button
          class="text-xs text-amber-400 hover:text-amber-300 transition-colors"
          @click="addEmpty"
        >+ Пустой</button>
        <button
          class="text-xs text-amber-400 hover:text-amber-300 transition-colors"
          @click="emit('upload')"
        >+ Файл</button>
      </div>
    </div>

    <div
      v-if="!files.length && editingIndex === null"
      class="px-3 py-3 text-sm text-stone-500"
    >
      Нет прикреплённых файлов
    </div>

    <div class="flex-1 overflow-y-auto pb-2">
      <div
        v-for="(file, index) in files"
        :key="index"
        class="border-b border-stone-800/60"
      >
        <div v-if="editingIndex === index" class="px-3 py-2 space-y-2 bg-stone-800/40">
          <input
            v-model="editingName"
            type="text"
            placeholder="имя файла"
            class="w-full bg-stone-950 text-stone-200 text-xs rounded-lg px-2 py-1.5 border border-stone-700 focus:border-amber-500 focus:outline-none"
          />
          <textarea
            v-model="editingContent"
            placeholder="Содержимое файла..."
            class="w-full bg-stone-950 text-stone-200 text-xs font-mono rounded-lg p-2 border border-stone-700 focus:border-amber-500 focus:outline-none resize-y min-h-[140px]"
            rows="8"
          />
          <div class="flex justify-end gap-2">
            <button
              class="text-xs text-stone-400 hover:text-white px-3 py-1.5 rounded"
              @click="cancelEdit"
            >Отмена</button>
            <button
              class="text-xs text-amber-400 hover:text-amber-300 bg-amber-600/20 px-3 py-1.5 rounded"
              @click="saveEdit"
            >Сохранить</button>
          </div>
        </div>

        <div v-else>
          <div class="flex items-center gap-2 px-3 py-1.5 hover:bg-stone-800/50">
            <button
              class="shrink-0 text-stone-500 hover:text-stone-300 transition-transform"
              :class="expandedIndex === index ? 'rotate-90' : ''"
              :title="expandedIndex === index ? 'Свернуть' : 'Раскрыть'"
              @click="toggleExpand(index)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-stone-500 shrink-0">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <button
              class="text-xs text-stone-300 truncate flex-1 text-left hover:text-amber-300"
              :title="file.name"
              @click="toggleExpand(index)"
            >{{ file.name }}</button>
            <span class="text-[10px] text-stone-500 shrink-0">
              {{ Math.round(file.content.length / 1024) || '<1' }}KB
            </span>
            <button
              class="p-1 text-stone-500 hover:text-amber-300 transition-colors"
              title="Редактировать"
              @click="startEdit(index)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>
            <button
              class="p-1 text-stone-500 hover:text-red-400 transition-colors"
              title="Удалить"
              @click="removeFile(index)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
          <pre
            v-if="expandedIndex === index"
            class="mx-3 mb-2 p-2 text-[11px] font-mono text-stone-300 bg-stone-950 rounded border border-stone-800 max-h-48 overflow-auto whitespace-pre-wrap break-words"
          >{{ file.content || '(пусто)' }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
