import { defineStore } from "pinia";
import { ref } from "vue";
import { Preferences } from "@capacitor/preferences";

const STORAGE_KEY = "server_url";

export const useSettingsStore = defineStore("settings", () => {
  const serverUrl = ref("");
  const isLoaded = ref(false);

  async function load() {
    const { value } = await Preferences.get({ key: STORAGE_KEY });
    serverUrl.value = value || "";
    isLoaded.value = true;
  }

  async function setServerUrl(url: string) {
    // Normalize: strip trailing slash
    const normalized = url.replace(/\/+$/, "");
    serverUrl.value = normalized;
    await Preferences.set({ key: STORAGE_KEY, value: normalized });
  }

  return { serverUrl, isLoaded, load, setServerUrl };
});
