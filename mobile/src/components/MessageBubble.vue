<script setup lang="ts">
import { computed } from "vue";
import type { ChatMessage } from "@/api/chat";
import { renderMarkdown } from "@/utils/markdown";

const props = defineProps<{
  message: ChatMessage;
  isStreaming?: boolean;
  isSpeaking?: boolean;
}>();

const emit = defineEmits<{
  speak: [text: string, id: string];
  stopSpeak: [];
}>();

const isUser = computed(() => props.message.role === "user");

const renderedContent = computed(() => {
  if (isUser.value) return props.message.content;
  return renderMarkdown(props.message.content);
});

function handleSpeak() {
  if (props.isSpeaking) {
    emit("stopSpeak");
  } else {
    emit("speak", props.message.content, props.message.id);
  }
}
</script>

<template>
  <div
    class="flex mb-3 px-4"
    :class="isUser ? 'justify-end' : 'justify-start'"
  >
    <div
      class="max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed"
      :class="
        isUser
          ? 'bg-indigo-600 text-white rounded-br-md'
          : 'bg-slate-800 text-slate-200 rounded-bl-md'
      "
    >
      <div
        v-if="isUser"
        class="whitespace-pre-wrap break-words"
      >
        {{ renderedContent }}
      </div>
      <div
        v-else
        class="markdown-body break-words"
        v-html="renderedContent"
      />

      <!-- TTS button for assistant messages -->
      <div
        v-if="!isUser && !isStreaming && message.content"
        class="flex justify-end mt-1 -mb-1"
      >
        <button
          class="p-1 text-slate-500 hover:text-slate-300 transition-colors"
          @click="handleSpeak"
        >
          <svg
            v-if="!isSpeaking"
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
          </svg>
          <svg
            v-else
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect x="6" y="4" width="4" height="16" />
            <rect x="14" y="4" width="4" height="16" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>
