<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useAuthStore } from "@/stores/auth";
import {
  profileApi,
  googleApi,
  type UserProfile,
  type GoogleOAuthStatus,
} from "@/api/profile";

const props = defineProps<{
  // Re-load profile/google status when this prop changes (e.g. when panel toggles open).
  active?: boolean;
}>();

const emit = defineEmits<{
  (e: "logout"): void;
}>();

const auth = useAuthStore();

const profile = ref<UserProfile | null>(null);
const profileLoading = ref(false);
const displayName = ref("");
const displaySaving = ref(false);
const displayMessage = ref<{ type: "ok" | "err"; text: string } | null>(null);

const oldPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const passwordSaving = ref(false);
const passwordMessage = ref<{ type: "ok" | "err"; text: string } | null>(null);

const googleStatus = ref<GoogleOAuthStatus>({
  connected: false,
  google_email: null,
  scopes: [],
});
const googleLoading = ref(false);
const googleMessage = ref<{ type: "ok" | "err"; text: string } | null>(null);

async function loadProfile() {
  profileLoading.value = true;
  try {
    profile.value = await profileApi.getProfile();
    displayName.value = profile.value?.display_name || "";
  } catch {
    // best-effort
  } finally {
    profileLoading.value = false;
  }
}

async function loadGoogleStatus() {
  try {
    googleStatus.value = await googleApi.getStatus();
  } catch {
    // optional feature
  }
}

async function refreshAll() {
  await Promise.all([loadProfile(), loadGoogleStatus()]);
}

async function saveDisplayName() {
  displaySaving.value = true;
  displayMessage.value = null;
  try {
    const updated = await profileApi.updateDisplayName(
      displayName.value.trim() || null,
    );
    profile.value = updated;
    displayMessage.value = { type: "ok", text: "Сохранено" };
    setTimeout(() => (displayMessage.value = null), 2500);
  } catch (e) {
    displayMessage.value = {
      type: "err",
      text: (e as Error).message || "Ошибка",
    };
  } finally {
    displaySaving.value = false;
  }
}

async function changePassword() {
  passwordMessage.value = null;
  if (!oldPassword.value || !newPassword.value || !confirmPassword.value) {
    passwordMessage.value = { type: "err", text: "Заполните все поля" };
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    passwordMessage.value = { type: "err", text: "Пароли не совпадают" };
    return;
  }
  if (newPassword.value.length < 6) {
    passwordMessage.value = {
      type: "err",
      text: "Пароль слишком короткий (мин. 6 символов)",
    };
    return;
  }
  passwordSaving.value = true;
  try {
    await profileApi.changePassword(oldPassword.value, newPassword.value);
    oldPassword.value = "";
    newPassword.value = "";
    confirmPassword.value = "";
    passwordMessage.value = { type: "ok", text: "Пароль изменён" };
    setTimeout(() => (passwordMessage.value = null), 2500);
  } catch (e) {
    passwordMessage.value = {
      type: "err",
      text: (e as Error).message || "Ошибка",
    };
  } finally {
    passwordSaving.value = false;
  }
}

async function connectGoogle() {
  googleLoading.value = true;
  googleMessage.value = null;
  try {
    const { auth_url } = await googleApi.getAuthUrl();
    window.open(auth_url, "_system");
    googleMessage.value = {
      type: "ok",
      text: "Открыт браузер. Когда закончите — обновите.",
    };
  } catch (e) {
    googleMessage.value = {
      type: "err",
      text: (e as Error).message || "Не удалось открыть",
    };
  } finally {
    googleLoading.value = false;
  }
}

async function disconnectGoogle() {
  if (!confirm("Отключить Google-аккаунт?")) return;
  googleLoading.value = true;
  googleMessage.value = null;
  try {
    await googleApi.disconnect();
    googleStatus.value = { connected: false, google_email: null, scopes: [] };
    googleMessage.value = { type: "ok", text: "Отключён" };
    setTimeout(() => (googleMessage.value = null), 2500);
  } catch (e) {
    googleMessage.value = {
      type: "err",
      text: (e as Error).message || "Ошибка",
    };
  } finally {
    googleLoading.value = false;
  }
}

onMounted(refreshAll);

watch(
  () => props.active,
  (now) => {
    if (now) refreshAll();
  },
);
</script>

<template>
  <div class="flex flex-col">
    <!-- Account info (read-only) -->
    <div class="px-3 py-2 border-b border-stone-800 flex items-center gap-3">
      <div class="w-9 h-9 rounded-full bg-amber-600/20 text-amber-400 flex items-center justify-center text-sm font-medium shrink-0">
        {{ (profile?.display_name || profile?.username || auth.user?.username || "?").substring(0, 1).toUpperCase() }}
      </div>
      <div class="flex-1 min-w-0">
        <p class="text-sm text-white truncate">{{ profile?.display_name || profile?.username || auth.user?.username }}</p>
        <p class="text-[10px] uppercase tracking-wide text-stone-500">{{ profile?.role || auth.user?.role }}</p>
      </div>
      <button
        class="p-1.5 rounded-lg text-stone-400 hover:text-amber-400 transition-colors shrink-0"
        title="Обновить"
        @click="refreshAll"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
      </button>
    </div>

    <!-- Display name -->
    <div class="px-3 py-2.5 border-b border-stone-800 space-y-2">
      <p class="text-[10px] uppercase tracking-wide text-stone-500">Никнейм</p>
      <input
        v-model="displayName"
        type="text"
        class="w-full px-2.5 py-1.5 bg-stone-900 border border-stone-700 rounded text-white text-sm placeholder-stone-500 outline-none focus:border-amber-500"
        placeholder="Как к вам обращаться"
        :disabled="profileLoading"
      />
      <button
        class="w-full px-3 py-1.5 rounded bg-amber-600 text-white text-xs hover:bg-amber-500 transition-colors disabled:opacity-50"
        :disabled="displaySaving"
        @click="saveDisplayName"
      >
        {{ displaySaving ? "Сохранение..." : "Сохранить" }}
      </button>
      <p
        v-if="displayMessage"
        class="text-[11px]"
        :class="displayMessage.type === 'ok' ? 'text-emerald-400' : 'text-red-400'"
      >{{ displayMessage.text }}</p>
    </div>

    <!-- Change password -->
    <div class="px-3 py-2.5 border-b border-stone-800 space-y-2">
      <p class="text-[10px] uppercase tracking-wide text-stone-500">Смена пароля</p>
      <input
        v-model="oldPassword"
        type="password"
        autocomplete="current-password"
        class="w-full px-2.5 py-1.5 bg-stone-900 border border-stone-700 rounded text-white text-sm placeholder-stone-500 outline-none focus:border-amber-500"
        placeholder="Текущий пароль"
      />
      <input
        v-model="newPassword"
        type="password"
        autocomplete="new-password"
        class="w-full px-2.5 py-1.5 bg-stone-900 border border-stone-700 rounded text-white text-sm placeholder-stone-500 outline-none focus:border-amber-500"
        placeholder="Новый пароль"
      />
      <input
        v-model="confirmPassword"
        type="password"
        autocomplete="new-password"
        class="w-full px-2.5 py-1.5 bg-stone-900 border border-stone-700 rounded text-white text-sm placeholder-stone-500 outline-none focus:border-amber-500"
        placeholder="Повторите новый"
      />
      <button
        class="w-full px-3 py-1.5 rounded bg-amber-600 text-white text-xs hover:bg-amber-500 transition-colors disabled:opacity-50"
        :disabled="passwordSaving"
        @click="changePassword"
      >
        {{ passwordSaving ? "Сохранение..." : "Изменить пароль" }}
      </button>
      <p
        v-if="passwordMessage"
        class="text-[11px]"
        :class="passwordMessage.type === 'ok' ? 'text-emerald-400' : 'text-red-400'"
      >{{ passwordMessage.text }}</p>
    </div>

    <!-- Google -->
    <div class="px-3 py-2.5 border-b border-stone-800 space-y-2">
      <p class="text-[10px] uppercase tracking-wide text-stone-500">Google (Drive, Docs, Sheets, Gmail)</p>
      <template v-if="googleStatus.connected">
        <div class="flex items-center gap-2">
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          <p class="text-sm text-white truncate flex-1 min-w-0">{{ googleStatus.google_email }}</p>
        </div>
        <div class="flex flex-wrap gap-1 text-[9px]">
          <span v-if="googleStatus.scopes.some((s) => s.includes('drive'))" class="px-1.5 py-0.5 rounded-full bg-blue-500/15 text-blue-300">Drive</span>
          <span v-if="googleStatus.scopes.some((s) => s.includes('documents'))" class="px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300">Docs</span>
          <span v-if="googleStatus.scopes.some((s) => s.includes('spreadsheets'))" class="px-1.5 py-0.5 rounded-full bg-green-500/15 text-green-300">Sheets</span>
          <span v-if="googleStatus.scopes.some((s) => s.includes('gmail'))" class="px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-300">Gmail</span>
        </div>
        <button
          class="w-full px-3 py-1.5 rounded bg-red-800/20 text-red-300 text-xs hover:bg-red-800/30 transition-colors disabled:opacity-50"
          :disabled="googleLoading"
          @click="disconnectGoogle"
        >Отключить Google</button>
      </template>
      <template v-else>
        <p class="text-stone-400 text-xs">Подключите Google, чтобы ассистент мог читать ваши Drive / Docs / Sheets.</p>
        <button
          class="w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded bg-white text-stone-800 text-xs font-medium hover:bg-stone-100 transition-colors disabled:opacity-50"
          :disabled="googleLoading"
          @click="connectGoogle"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          {{ googleLoading ? "Открытие..." : "Подключить Google" }}
        </button>
      </template>
      <p
        v-if="googleMessage"
        class="text-[11px]"
        :class="googleMessage.type === 'ok' ? 'text-emerald-400' : 'text-red-400'"
      >{{ googleMessage.text }}</p>
    </div>

    <!-- Logout -->
    <div class="px-3 py-2.5">
      <button
        class="w-full px-3 py-2 rounded-lg bg-red-800/20 text-red-300 text-sm font-medium hover:bg-red-800/30 transition-colors flex items-center justify-center gap-2"
        @click="emit('logout')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <polyline points="16 17 21 12 16 7" />
          <line x1="21" y1="12" x2="9" y2="12" />
        </svg>
        Выйти из аккаунта
      </button>
    </div>
  </div>
</template>
