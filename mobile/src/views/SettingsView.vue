<script setup lang="ts">
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const auth = useAuthStore();

async function handleLogout() {
  await auth.logout();
  router.replace("/login");
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div
      class="shrink-0 flex items-center gap-3 px-4 py-3 border-b border-stone-800"
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
      <h1 class="text-lg font-semibold text-white">Настройки</h1>
    </div>

    <div class="flex-1 overflow-y-auto p-4 space-y-6">
      <!-- Account -->
      <div>
        <h2 class="text-sm font-medium text-stone-400 mb-3 uppercase tracking-wider">
          Аккаунт
        </h2>
        <div class="bg-stone-800/50 rounded-xl p-4">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-white font-medium">
                {{ auth.user?.username }}
              </p>
              <p class="text-stone-500 text-sm">
                {{ auth.user?.role }}
              </p>
            </div>
            <button
              class="px-4 py-2 rounded-lg bg-red-800/20 text-red-400 text-sm hover:bg-red-800/30 transition-colors"
              @click="handleLogout"
            >
              Выйти
            </button>
          </div>
        </div>
      </div>

      <!-- App info -->
      <div>
        <h2 class="text-sm font-medium text-stone-400 mb-3 uppercase tracking-wider">
          О приложении
        </h2>
        <div class="bg-stone-800/50 rounded-xl p-4">
          <p class="text-stone-400 text-sm">AI Секретарь v1.0.0</p>
        </div>
      </div>
    </div>
  </div>
</template>
