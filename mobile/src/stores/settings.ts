import { defineStore } from "pinia";
import { ref } from "vue";

const DEFAULT_SERVER_URL = "https://ai-sekretar24.ru";

export const useSettingsStore = defineStore("settings", () => {
  const serverUrl = ref(DEFAULT_SERVER_URL);
  const isLoaded = ref(false);

  async function load() {
    serverUrl.value = DEFAULT_SERVER_URL;
    isLoaded.value = true;
  }

  async function setServerUrl(_url: string) {
    // Server URL is hardcoded, ignore user input
    serverUrl.value = DEFAULT_SERVER_URL;
  }

  return { serverUrl, isLoaded, load, setServerUrl };
});
