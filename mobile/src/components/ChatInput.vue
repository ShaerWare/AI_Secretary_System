<script setup lang="ts">
import { ref } from "vue";
import {
  shouldTreatAsPaste,
  createPastedBlock,
  buildMessageContent,
  type PastedBlock,
} from "@/utils/pasteDetect";

defineProps<{
  disabled?: boolean;
  isStreaming?: boolean;
}>();

const emit = defineEmits<{
  send: [content: string];
  stop: [];
}>();

const input = ref("");
const textarea = ref<HTMLTextAreaElement | null>(null);
const pastedBlocks = ref<PastedBlock[]>([]);

function handleSend() {
  const hasText = input.value.trim().length > 0;
  const hasPaste = pastedBlocks.value.length > 0;
  if (!hasText && !hasPaste) return;
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
</script>

<template>
  <div
    class="border-t border-stone-800 bg-stone-950/95 backdrop-blur px-4 py-3 safe-bottom"
  >
    <!-- Pasted blocks chips -->
    <div v-if="pastedBlocks.length" class="flex flex-wrap gap-2 mb-2">
      <div
        v-for="block in pastedBlocks"
        :key="block.id"
        class="flex items-center gap-1.5 px-2.5 py-1.5 bg-stone-800 rounded-lg border border-stone-700 text-xs"
      >
        <!-- file-code icon -->
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-amber-500 shrink-0">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><path d="m10 13-2 2 2 2" /><path d="m14 17 2-2-2-2" />
        </svg>
        <span class="font-medium text-amber-400">{{ block.languageLabel }}</span>
        <span class="text-stone-500">{{ block.lineCount }} lines</span>
        <button
          class="ml-1 p-0.5 rounded hover:bg-red-900/30 text-stone-500 hover:text-red-400 transition-colors"
          @click="removePastedBlock(block.id)"
        >
          <!-- X icon -->
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>

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
        :disabled="disabled || (!input.trim() && !pastedBlocks.length)"
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
