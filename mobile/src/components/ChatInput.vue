<script setup lang="ts">
import { ref, computed } from "vue";
import {
  shouldTreatAsPaste,
  createPastedBlock,
  buildMessageContent,
  type PastedBlock,
} from "@/utils/pasteDetect";
import type { ChatImage } from "@/api/chat";

const props = defineProps<{
  disabled?: boolean;
  isStreaming?: boolean;
  pendingFiles?: ChatImage[];
  isUploading?: boolean;
}>();

const emit = defineEmits<{
  send: [content: string];
  stop: [];
  "upload-files": [files: File[]];
  "remove-file": [id: string];
}>();

const input = ref("");
const textarea = ref<HTMLTextAreaElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const pastedBlocks = ref<PastedBlock[]>([]);

const hasContent = computed(() => {
  return (
    input.value.trim().length > 0 ||
    pastedBlocks.value.length > 0 ||
    (props.pendingFiles?.length ?? 0) > 0
  );
});

function handleSend() {
  if (!hasContent.value) return;
  const content = buildMessageContent(input.value.trim(), pastedBlocks.value);
  emit("send", content);
  input.value = "";
  pastedBlocks.value = [];
  if (textarea.value) {
    textarea.value.style.height = "auto";
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

function onPaste(e: ClipboardEvent) {
  const text = e.clipboardData?.getData("text/plain");
  if (!text || !shouldTreatAsPaste(text)) return;
  e.preventDefault();
  pastedBlocks.value.push(createPastedBlock(text));
}

function removePastedBlock(id: string) {
  pastedBlocks.value = pastedBlocks.value.filter((b) => b.id !== id);
}

function triggerFileUpload() {
  fileInputRef.value?.click();
}

function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  if (!input.files?.length) return;
  emit("upload-files", Array.from(input.files));
  input.value = "";
}
</script>

<template>
  <div class="flex-1">
    <!-- Pasted blocks chips -->
    <div v-if="pastedBlocks.length" class="flex flex-wrap gap-2 mb-2">
      <div
        v-for="block in pastedBlocks"
        :key="block.id"
        class="flex items-center gap-1.5 px-2.5 py-1.5 bg-stone-800 rounded-lg border border-stone-700 text-xs"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-amber-500 shrink-0">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><path d="m10 13-2 2 2 2" /><path d="m14 17 2-2-2-2" />
        </svg>
        <span class="font-medium text-amber-400">{{ block.languageLabel }}</span>
        <span class="text-stone-500">{{ block.lineCount }} lines</span>
        <button
          class="ml-1 p-0.5 rounded hover:bg-red-900/30 text-stone-500 hover:text-red-400 transition-colors"
          @click="removePastedBlock(block.id)"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Pending file chips -->
    <div v-if="pendingFiles?.length" class="flex flex-wrap gap-2 mb-2">
      <div
        v-for="file in pendingFiles"
        :key="file.id"
        class="flex items-center gap-1.5 px-2.5 py-1.5 bg-stone-800 rounded-lg border border-stone-700 text-xs"
      >
        <!-- Image thumbnail or document icon -->
        <img
          v-if="file.is_image !== false && file.thumb_url"
          :src="file.thumb_url"
          class="w-5 h-5 rounded object-cover shrink-0"
        />
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-amber-500 shrink-0">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
        </svg>
        <span class="font-medium text-stone-300 max-w-[120px] truncate">{{ file.original_name }}</span>
        <button
          class="ml-0.5 p-0.5 rounded hover:bg-red-900/30 text-stone-500 hover:text-red-400 transition-colors"
          @click="$emit('remove-file', file.id)"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Hidden file input -->
    <input
      ref="fileInputRef"
      type="file"
      accept="image/jpeg,image/png,image/webp,image/gif,.pdf,.xlsx,.xls,.docx,.doc,.txt,.csv,.md,.json,.xml,.html,.log,.yaml,.yml"
      multiple
      class="hidden"
      @change="handleFileChange"
    />

    <div class="flex items-end gap-2">
      <textarea
        ref="textarea"
        v-model="input"
        :disabled="disabled"
        rows="1"
        class="flex-1 resize-none rounded-xl bg-stone-800 border border-stone-700 px-4 py-2.5 text-sm text-stone-300 placeholder-stone-500 focus:outline-none focus:border-amber-500 transition-colors"
        placeholder="Сообщение..."
        @keydown="handleKeydown"
        @input="autoResize"
        @paste="onPaste"
      />

      <!-- File upload button -->
      <button
        :disabled="disabled || isStreaming || isUploading"
        class="shrink-0 w-10 h-10 rounded-xl bg-stone-800 border border-stone-700 hover:border-amber-500 disabled:opacity-50 flex items-center justify-center transition-colors"
        title="Прикрепить файл"
        @click="triggerFileUpload"
      >
        <!-- Spinner while uploading -->
        <svg v-if="isUploading" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-amber-500 animate-spin">
          <path d="M21 12a9 9 0 1 1-6.219-8.56" />
        </svg>
        <!-- Paperclip icon -->
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-stone-400">
          <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
        </svg>
      </button>

      <!-- Stop button (during streaming) -->
      <button
        v-if="isStreaming"
        class="shrink-0 w-10 h-10 rounded-xl bg-red-800 hover:bg-red-900 flex items-center justify-center transition-colors"
        @click="$emit('stop')"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="currentColor"
          class="text-white"
        >
          <rect x="6" y="6" width="12" height="12" rx="1" />
        </svg>
      </button>

      <!-- Send button -->
      <button
        v-else
        :disabled="disabled || !hasContent"
        class="shrink-0 w-10 h-10 rounded-xl bg-amber-600 hover:bg-amber-700 disabled:bg-stone-700 disabled:text-stone-500 flex items-center justify-center transition-colors"
        @click="handleSend"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="text-white"
        >
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>
    </div>
  </div>
</template>
