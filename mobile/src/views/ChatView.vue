<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { chatApi, type ChatMessage, type StreamChunk } from "@/api/chat";
import { useTts } from "@/composables/useTts";
import MessageBubble from "@/components/MessageBubble.vue";
import ChatInput from "@/components/ChatInput.vue";

const route = useRoute();
const router = useRouter();
const tts = useTts();

const sessionId = computed(() => route.params.id as string);
const title = ref("Chat");
const messages = ref<ChatMessage[]>([]);
const isLoading = ref(false);
const isStreaming = ref(false);
const streamingContent = ref("");
const error = ref<string | null>(null);
const messagesContainer = ref<HTMLElement | null>(null);

let abortStream: (() => void) | null = null;

async function loadSession() {
  isLoading.value = true;
  error.value = null;
  try {
    const data = await chatApi.getSession(sessionId.value);
    title.value = data.session.title || "Chat";
    messages.value = data.session.messages.filter(
      (m) => m.is_active !== false,
    );
    await scrollToBottom();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load";
  } finally {
    isLoading.value = false;
  }
}

async function sendMessage(content: string) {
  // Add user message optimistically
  const userMsg: ChatMessage = {
    id: "temp-" + Date.now(),
    role: "user",
    content,
    timestamp: new Date().toISOString(),
  };
  messages.value.push(userMsg);
  await scrollToBottom();

  // Start streaming
  isStreaming.value = true;
  streamingContent.value = "";

  const { abort } = chatApi.streamMessage(
    sessionId.value,
    content,
    (chunk: StreamChunk) => {
      switch (chunk.type) {
        case "chunk":
          streamingContent.value += chunk.content || "";
          scrollToBottom();
          break;
        case "assistant_message":
          if (chunk.message) {
            // Replace temp user message with real one if available
            messages.value.push(chunk.message);
            streamingContent.value = "";
            isStreaming.value = false;
            scrollToBottom();
          }
          break;
        case "user_message":
          if (chunk.message) {
            // Replace optimistic user message
            const idx = messages.value.findIndex(
              (m) => m.id === userMsg.id,
            );
            if (idx >= 0) messages.value[idx] = chunk.message;
          }
          break;
        case "tool_start":
          streamingContent.value += "\n_Searching..._\n";
          break;
        case "done":
          isStreaming.value = false;
          streamingContent.value = "";
          break;
        case "error":
          isStreaming.value = false;
          streamingContent.value = "";
          error.value = chunk.content || "Stream error";
          break;
      }
    },
  );

  abortStream = abort;
}

function stopStreaming() {
  if (abortStream) {
    abortStream();
    abortStream = null;
  }
  isStreaming.value = false;
  if (streamingContent.value) {
    messages.value.push({
      id: "partial-" + Date.now(),
      role: "assistant",
      content: streamingContent.value,
      timestamp: new Date().toISOString(),
    });
    streamingContent.value = "";
  }
}

async function scrollToBottom() {
  await nextTick();
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop =
      messagesContainer.value.scrollHeight;
  }
}

// Watch streaming content for auto-scroll
watch(streamingContent, () => {
  scrollToBottom();
});

onMounted(loadSession);
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div
      class="shrink-0 flex items-center gap-3 px-4 py-3 border-b border-stone-800 bg-stone-950/95 backdrop-blur"
    >
      <button
        class="text-stone-400 hover:text-white transition-colors"
        @click="router.back()"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
      <h1 class="text-sm font-medium text-white truncate flex-1">
        {{ title }}
      </h1>
    </div>

    <!-- Messages -->
    <div
      ref="messagesContainer"
      class="flex-1 overflow-y-auto py-4"
    >
      <!-- Loading -->
      <div
        v-if="isLoading"
        class="flex items-center justify-center h-32"
      >
        <div
          class="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"
        />
      </div>

      <!-- Error -->
      <div
        v-if="error"
        class="mx-4 mb-3 p-3 rounded-xl bg-red-900/30 border border-red-800/50 text-red-400 text-sm"
      >
        {{ error }}
      </div>

      <!-- Message list -->
      <template v-if="!isLoading">
        <MessageBubble
          v-for="msg in messages"
          :key="msg.id"
          :message="msg"
          :is-speaking="tts.speakingMessageId.value === msg.id"
          @speak="tts.speak($event, msg.id)"
          @stop-speak="tts.stop()"
        />

        <!-- Streaming message -->
        <MessageBubble
          v-if="isStreaming && streamingContent"
          :message="{
            id: 'streaming',
            role: 'assistant',
            content: streamingContent,
            timestamp: new Date().toISOString(),
          }"
          :is-streaming="true"
        />

        <!-- Typing indicator -->
        <div
          v-if="isStreaming && !streamingContent"
          class="flex justify-start px-4 mb-3"
        >
          <div
            class="bg-stone-800 rounded-2xl rounded-bl-md px-4 py-3 flex gap-1"
          >
            <div
              class="w-2 h-2 rounded-full bg-slate-500 animate-bounce"
              style="animation-delay: 0ms"
            />
            <div
              class="w-2 h-2 rounded-full bg-slate-500 animate-bounce"
              style="animation-delay: 150ms"
            />
            <div
              class="w-2 h-2 rounded-full bg-slate-500 animate-bounce"
              style="animation-delay: 300ms"
            />
          </div>
        </div>
      </template>
    </div>

    <!-- Input -->
    <ChatInput
      :disabled="isLoading"
      :is-streaming="isStreaming"
      @send="sendMessage"
      @stop="stopStreaming"
    />
  </div>
</template>
