<script setup lang="ts">
import { ref } from "vue";

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

function handleSend() {
  const content = input.value.trim();
  if (!content) return;
  emit("send", content);
  input.value = "";
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
</script>

<template>
  <div
    class="border-t border-slate-800 bg-slate-900/95 backdrop-blur px-4 py-3 safe-bottom"
  >
    <div class="flex items-end gap-2">
      <textarea
        ref="textarea"
        v-model="input"
        :disabled="disabled"
        rows="1"
        class="flex-1 resize-none rounded-xl bg-slate-800 border border-slate-700 px-4 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
        placeholder="Message..."
        @keydown="handleKeydown"
        @input="autoResize"
      />

      <!-- Stop button (during streaming) -->
      <button
        v-if="isStreaming"
        class="shrink-0 w-10 h-10 rounded-xl bg-red-600 hover:bg-red-700 flex items-center justify-center transition-colors"
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
        :disabled="disabled || !input.trim()"
        class="shrink-0 w-10 h-10 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-700 disabled:text-slate-500 flex items-center justify-center transition-colors"
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
