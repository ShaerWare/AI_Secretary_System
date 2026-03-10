<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";

const router = useRouter();
const auth = useAuthStore();
const settings = useSettingsStore();

const serverUrl = ref("");
const username = ref("");
const password = ref("");
const step = ref<"server" | "login">("server");

onMounted(async () => {
  await settings.load();
  if (settings.serverUrl) {
    serverUrl.value = settings.serverUrl;
    step.value = "login";
  }
  await auth.loadToken();
  if (auth.isAuthenticated && !auth.isTokenExpired()) {
    router.replace("/chats");
  }
});

async function setServer() {
  const url = serverUrl.value.trim();
  if (!url) return;
  await settings.setServerUrl(url);
  step.value = "login";
}

async function handleLogin() {
  const ok = await auth.login(username.value, password.value);
  if (ok) {
    router.replace("/chats");
  }
}

function changeServer() {
  step.value = "server";
}
</script>

<template>
  <div
    class="h-full flex flex-col items-center justify-center px-6 bg-gradient-to-b from-slate-900 to-slate-950"
  >
    <!-- Logo -->
    <div class="mb-8 text-center">
      <div
        class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-indigo-600 flex items-center justify-center"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="white"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path
            d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
          />
        </svg>
      </div>
      <h1 class="text-2xl font-bold text-white">AI Secretary</h1>
      <p class="text-slate-400 text-sm mt-1">Your personal assistant</p>
    </div>

    <!-- Server URL step -->
    <div v-if="step === 'server'" class="w-full max-w-sm space-y-4">
      <div>
        <label class="block text-sm text-slate-400 mb-1.5">Server URL</label>
        <input
          v-model="serverUrl"
          type="url"
          placeholder="https://your-server.com"
          class="w-full rounded-xl bg-slate-800 border border-slate-700 px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          @keyup.enter="setServer"
        />
      </div>
      <button
        :disabled="!serverUrl.trim()"
        class="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-700 disabled:text-slate-500 text-white font-medium transition-colors"
        @click="setServer"
      >
        Continue
      </button>
    </div>

    <!-- Login step -->
    <div v-else class="w-full max-w-sm space-y-4">
      <button
        class="text-sm text-slate-400 hover:text-slate-300 mb-2"
        @click="changeServer"
      >
        {{ settings.serverUrl }}
      </button>

      <div>
        <label class="block text-sm text-slate-400 mb-1.5">Username</label>
        <input
          v-model="username"
          type="text"
          autocomplete="username"
          class="w-full rounded-xl bg-slate-800 border border-slate-700 px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          @keyup.enter="handleLogin"
        />
      </div>
      <div>
        <label class="block text-sm text-slate-400 mb-1.5">Password</label>
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          class="w-full rounded-xl bg-slate-800 border border-slate-700 px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          @keyup.enter="handleLogin"
        />
      </div>

      <div
        v-if="auth.error"
        class="text-red-400 text-sm text-center"
      >
        {{ auth.error }}
      </div>

      <button
        :disabled="auth.isLoading || !username || !password"
        class="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-700 disabled:text-slate-500 text-white font-medium transition-colors"
        @click="handleLogin"
      >
        <span v-if="auth.isLoading">Connecting...</span>
        <span v-else>Login</span>
      </button>
    </div>
  </div>
</template>
