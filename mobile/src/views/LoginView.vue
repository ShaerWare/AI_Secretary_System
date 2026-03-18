<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";
import { useMobileConfigStore } from "@/stores/mobileConfig";

const router = useRouter();
const auth = useAuthStore();
const settings = useSettingsStore();
const mobileConfig = useMobileConfigStore();

const username = ref("");
const password = ref("");

onMounted(async () => {
  await settings.load();
  await auth.loadToken();
  if (auth.isAuthenticated && !auth.isTokenExpired()) {
    await mobileConfig.load();
    router.replace("/chats");
  }
});

async function handleLogin() {
  const ok = await auth.login(username.value, password.value);
  if (ok) {
    await mobileConfig.load();
    router.replace("/chats");
  }
}
</script>

<template>
  <div
    class="h-full flex flex-col items-center justify-center px-6 bg-gradient-to-b from-stone-950 to-stone-950"
  >
    <!-- Logo -->
    <div class="mb-8 text-center">
      <div class="w-16 h-16 mx-auto mb-4">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="w-full h-full">
          <defs>
            <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#F0A830"/>
              <stop offset="100%" stop-color="#C27010"/>
            </linearGradient>
          </defs>
          <path fill="url(#g)" fill-rule="evenodd" d="M 431.8 217.4 L 484.1 226.3 L 484.1 285.7 L 431.8 294.6 L 407.6 353.0 L 438.3 396.3 L 396.3 438.3 L 353.0 407.6 L 294.6 431.8 L 285.7 484.1 L 226.3 484.1 L 217.4 431.8 L 159.0 407.6 L 115.7 438.3 L 73.7 396.3 L 104.4 353.0 L 80.2 294.6 L 27.9 285.7 L 27.9 226.3 L 80.2 217.4 L 104.4 159.0 L 73.7 115.7 L 115.7 73.7 L 159.0 104.4 L 217.4 80.2 L 226.3 27.9 L 285.7 27.9 L 294.6 80.2 L 353.0 104.4 L 396.3 73.7 L 438.3 115.7 L 407.6 159.0 Z M 341.0 256.0 A 85 85 0 1 0 171.0 256.0 A 85 85 0 1 0 341.0 256.0 Z"/>
        </svg>
      </div>
      <h1 class="text-2xl font-bold text-white">AI Secretary</h1>
      <p class="text-stone-400 text-sm mt-1">Your personal assistant</p>
    </div>

    <!-- Login form -->
    <div class="w-full max-w-sm space-y-4">
      <div>
        <label class="block text-sm text-stone-400 mb-1.5">Username</label>
        <input
          v-model="username"
          type="text"
          autocomplete="username"
          class="w-full rounded-xl bg-stone-800 border border-stone-700 px-4 py-3 text-white placeholder-stone-500 focus:outline-none focus:border-amber-500"
          @keyup.enter="handleLogin"
        />
      </div>
      <div>
        <label class="block text-sm text-stone-400 mb-1.5">Password</label>
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          class="w-full rounded-xl bg-stone-800 border border-stone-700 px-4 py-3 text-white placeholder-stone-500 focus:outline-none focus:border-amber-500"
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
        class="w-full py-3 rounded-xl bg-amber-600 hover:bg-amber-700 disabled:bg-stone-700 disabled:text-stone-500 text-white font-medium transition-colors"
        @click="handleLogin"
      >
        <span v-if="auth.isLoading">Connecting...</span>
        <span v-else>Login</span>
      </button>
    </div>
  </div>
</template>
