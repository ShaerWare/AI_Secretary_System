<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useSettingsStore } from "@/stores/settings";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const settings = useSettingsStore();
const auth = useAuthStore();

const serverUrl = ref("");

onMounted(() => {
  serverUrl.value = settings.serverUrl;
});

async function save() {
  await settings.setServerUrl(serverUrl.value);
  router.back();
}

async function handleLogout() {
  await auth.logout();
  router.replace("/login");
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div
      class="shrink-0 flex items-center gap-3 px-4 py-3 border-b border-slate-800"
    >
      <button
        class="text-slate-400 hover:text-white transition-colors"
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
      <h1 class="text-lg font-semibold text-white">Settings</h1>
    </div>

    <div class="flex-1 overflow-y-auto p-4 space-y-6">
      <!-- Account -->
      <div>
        <h2 class="text-sm font-medium text-slate-400 mb-3 uppercase tracking-wider">
          Account
        </h2>
        <div class="bg-slate-800/50 rounded-xl p-4">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-white font-medium">
                {{ auth.user?.username }}
              </p>
              <p class="text-slate-500 text-sm">
                {{ auth.user?.role }}
              </p>
            </div>
            <button
              class="px-4 py-2 rounded-lg bg-red-600/20 text-red-400 text-sm hover:bg-red-600/30 transition-colors"
              @click="handleLogout"
            >
              Logout
            </button>
          </div>
        </div>
      </div>

      <!-- Server -->
      <div>
        <h2 class="text-sm font-medium text-slate-400 mb-3 uppercase tracking-wider">
          Server
        </h2>
        <div class="bg-slate-800/50 rounded-xl p-4 space-y-3">
          <div>
            <label class="block text-sm text-slate-400 mb-1">URL</label>
            <input
              v-model="serverUrl"
              type="url"
              class="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
            />
          </div>
          <button
            class="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium transition-colors"
            @click="save"
          >
            Save
          </button>
        </div>
      </div>

      <!-- App info -->
      <div>
        <h2 class="text-sm font-medium text-slate-400 mb-3 uppercase tracking-wider">
          About
        </h2>
        <div class="bg-slate-800/50 rounded-xl p-4">
          <p class="text-slate-400 text-sm">AI Secretary Mobile v1.0.0</p>
        </div>
      </div>
    </div>
  </div>
</template>
