import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { Preferences } from "@capacitor/preferences";
import { useSettingsStore } from "./settings";

export interface User {
  id: number;
  username: string;
  role: string;
  workspace_id: number;
}

const TOKEN_KEY = "auth_token";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(null);
  const user = ref<User | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  const isAuthenticated = computed(() => !!token.value);

  async function loadToken() {
    const { value } = await Preferences.get({ key: TOKEN_KEY });
    if (value) {
      token.value = value;
      try {
        const parts = value.split(".");
        const payload = JSON.parse(atob(parts[1] ?? ""));
        user.value = {
          id: payload.user_id || 0,
          username: payload.sub,
          role: payload.role,
          workspace_id: payload.workspace_id || 1,
        };
      } catch {
        token.value = null;
        await Preferences.remove({ key: TOKEN_KEY });
      }
    }
  }

  async function login(
    username: string,
    password: string,
  ): Promise<boolean> {
    const settings = useSettingsStore();
    isLoading.value = true;
    error.value = null;

    try {
      const response = await fetch(
        `${settings.serverUrl}/admin/auth/login`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        },
      );

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        error.value =
          data.detail || `Error ${response.status}`;
        return false;
      }

      const data = await response.json();
      token.value = data.access_token;
      await Preferences.set({
        key: TOKEN_KEY,
        value: data.access_token,
      });

      const payload = JSON.parse(
        atob(data.access_token.split(".")[1]),
      );
      user.value = {
        id: payload.user_id || 0,
        username: payload.sub,
        role: payload.role,
        workspace_id: payload.workspace_id || 1,
      };

      return true;
    } catch {
      error.value = "Connection error";
      return false;
    } finally {
      isLoading.value = false;
    }
  }

  async function logout() {
    token.value = null;
    user.value = null;
    await Preferences.remove({ key: TOKEN_KEY });
  }

  function isTokenExpired(): boolean {
    if (!token.value) return true;
    try {
      const parts = token.value.split(".");
      const payload = JSON.parse(atob(parts[1] ?? ""));
      return payload.exp * 1000 < Date.now();
    } catch {
      return true;
    }
  }

  function getAuthHeaders(): Record<string, string> {
    if (token.value) {
      return { Authorization: `Bearer ${token.value}` };
    }
    return {};
  }

  return {
    token,
    user,
    isLoading,
    error,
    isAuthenticated,
    loadToken,
    login,
    logout,
    isTokenExpired,
    getAuthHeaders,
  };
});
