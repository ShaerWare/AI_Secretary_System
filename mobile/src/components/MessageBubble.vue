<script setup lang="ts">
import { ref, computed } from "vue";
import type { ChatMessage } from "@/api/chat";
import { renderMarkdown } from "@/utils/markdown";

const props = defineProps<{
  message: ChatMessage;
  isStreaming?: boolean;
  isSpeaking?: boolean;
  isAdmin?: boolean;
}>();

const emit = defineEmits<{
  speak: [text: string, id: string];
  stopSpeak: [];
  edit: [messageId: string, content: string];
  saveToContext: [messageId: string, content: string];
  summarizeBranch: [messageId: string];
  deleteBranch: [messageId: string];
  regenerate: [messageId: string];
}>();

const isUser = computed(() => props.message.role === "user");
const isEditing = ref(false);
const editContent = ref("");
const copied = ref(false);

const hasCodeBlock = computed(() => /```/.test(props.message.content));

const renderedContent = computed(() => {
  if (isUser.value) {
    if (hasCodeBlock.value) return renderMarkdown(props.message.content);
    return props.message.content;
  }
  return renderMarkdown(props.message.content);
});

function handleSpeak() {
  if (props.isSpeaking) {
    emit("stopSpeak");
  } else {
    emit("speak", props.message.content, props.message.id);
  }
}

function handleCopy() {
  navigator.clipboard.writeText(props.message.content).then(() => {
    copied.value = true;
    setTimeout(() => (copied.value = false), 1500);
  });
}

function startEdit() {
  editContent.value = props.message.content;
  isEditing.value = true;
}

function saveEdit() {
  isEditing.value = false;
  emit("edit", props.message.id, editContent.value);
}

function cancelEdit() {
  isEditing.value = false;
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
          ? 'bg-amber-600 text-white rounded-br-md'
          : 'bg-stone-800 text-stone-300 rounded-bl-md'
      "
    >
      <!-- Edit mode -->
      <template v-if="isEditing">
        <textarea
          v-model="editContent"
          class="w-full bg-stone-900 text-stone-200 text-sm rounded-lg p-2 border border-stone-600 focus:border-amber-500 focus:outline-none resize-y min-h-[60px]"
          rows="4"
        />
        <div class="flex justify-end gap-2 mt-2">
          <button
            class="text-xs text-stone-400 hover:text-white px-2 py-1 rounded"
            @click="cancelEdit"
          >Отмена</button>
          <button
            class="text-xs text-amber-400 hover:text-amber-300 bg-amber-600/20 px-2 py-1 rounded"
            @click="saveEdit"
          >Сохранить</button>
        </div>
      </template>

      <!-- Normal display -->
      <template v-else>
        <div
          v-if="isUser && hasCodeBlock"
          class="user-markdown break-words"
          v-html="renderedContent"
        />
        <div
          v-else-if="isUser"
          class="whitespace-pre-wrap break-words"
        >
          {{ renderedContent }}
        </div>
        <div
          v-else
          class="markdown-body break-words"
          v-html="renderedContent"
        />

        <!-- Action buttons for assistant messages -->
        <div
          v-if="!isUser && !isStreaming && message.content"
          class="flex items-center gap-0.5 mt-1.5 -mb-1 -mx-1 flex-wrap"
        >
          <!-- TTS -->
          <button
            class="p-1.5 rounded text-stone-500 hover:text-stone-300 transition-colors"
            :title="isSpeaking ? 'Стоп' : 'Озвучить'"
            @click="handleSpeak"
          >
            <svg v-if="!isSpeaking" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            </svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="6" y="4" width="4" height="16" />
              <rect x="14" y="4" width="4" height="16" />
            </svg>
          </button>

          <!-- Copy -->
          <button
            class="p-1.5 rounded transition-colors"
            :class="copied ? 'text-green-400' : 'text-stone-500 hover:text-stone-300'"
            title="Копировать"
            @click="handleCopy"
          >
            <svg v-if="!copied" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </button>

          <!-- Admin-only actions -->
          <template v-if="isAdmin">
            <!-- Edit -->
            <button
              class="p-1.5 rounded text-stone-500 hover:text-stone-300 transition-colors"
              title="Редактировать"
              @click="startEdit"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>

            <!-- Save to context -->
            <button
              class="p-1.5 rounded text-stone-500 hover:text-stone-300 transition-colors"
              title="В контекст"
              @click="$emit('saveToContext', message.id, message.content)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </button>

            <!-- Summarize branch -->
            <button
              class="p-1.5 rounded text-stone-500 hover:text-stone-300 transition-colors"
              title="Суммаризация ветки"
              @click="$emit('summarizeBranch', message.id)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
              </svg>
            </button>

            <!-- Delete branch from here -->
            <button
              class="p-1.5 rounded text-stone-500 hover:text-red-400 transition-colors"
              title="Удалить ветку"
              @click="$emit('deleteBranch', message.id)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          </template>
        </div>

        <!-- Action buttons for user messages -->
        <div
          v-if="isUser && !isStreaming && message.content"
          class="flex items-center justify-end gap-0.5 mt-1.5 -mb-1 -mx-1 flex-wrap"
        >
          <!-- TTS -->
          <button
            class="p-1.5 rounded text-amber-300/50 hover:text-amber-200 transition-colors"
            :title="isSpeaking ? 'Стоп' : 'Озвучить'"
            @click="handleSpeak"
          >
            <svg v-if="!isSpeaking" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            </svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" />
            </svg>
          </button>

          <!-- Copy -->
          <button
            class="p-1.5 rounded transition-colors"
            :class="copied ? 'text-green-400' : 'text-amber-300/50 hover:text-amber-200'"
            title="Копировать"
            @click="handleCopy"
          >
            <svg v-if="!copied" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </button>

          <!-- Admin-only actions -->
          <template v-if="isAdmin">
            <!-- Edit -->
            <button
              class="p-1.5 rounded text-amber-300/50 hover:text-amber-200 transition-colors"
              title="Редактировать"
              @click="startEdit"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>

            <!-- Regenerate response -->
            <button
              class="p-1.5 rounded text-amber-300/50 hover:text-amber-200 transition-colors"
              title="Перегенерировать"
              @click="$emit('regenerate', message.id)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
            </button>

            <!-- Summarize branch -->
            <button
              class="p-1.5 rounded text-amber-300/50 hover:text-amber-200 transition-colors"
              title="Суммаризация ветки"
              @click="$emit('summarizeBranch', message.id)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
              </svg>
            </button>

            <!-- Delete branch from here -->
            <button
              class="p-1.5 rounded text-amber-300/50 hover:text-red-400 transition-colors"
              title="Удалить ветку"
              @click="$emit('deleteBranch', message.id)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* User messages with code blocks: collapsible */
.user-markdown :deep(pre) {
  position: relative;
  max-height: 200px;
  overflow: hidden;
  background: #1c1917;
  border-radius: 0.5rem;
  padding: 0.75rem;
  margin: 0.5rem 0;
  font-size: 0.75rem;
}
.user-markdown :deep(pre)::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 50px;
  background: linear-gradient(transparent, #1c1917);
  pointer-events: none;
}
.user-markdown :deep(pre.expanded) {
  max-height: none;
}
.user-markdown :deep(pre.expanded)::after {
  display: none;
}
.user-markdown :deep(code) {
  font-family: ui-monospace, monospace;
  font-size: 0.75rem;
  color: #d6d3d1;
}
.user-markdown :deep(p) {
  margin: 0.25rem 0;
}
</style>
