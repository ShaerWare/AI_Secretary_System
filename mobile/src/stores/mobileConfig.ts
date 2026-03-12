import { defineStore } from "pinia";
import { ref } from "vue";
import { api } from "@/api/client";

export interface MobileInstanceConfig {
  id: string;
  name: string;
  description?: string;
  llm_backend: string;
  llm_persona: string;
  system_prompt?: string;
  llm_params?: Record<string, unknown>;
  tts_engine: string;
  tts_voice: string;
  tts_preset?: string;
  rag_mode?: string;
  knowledge_collection_ids?: number[];
}

export const useMobileConfigStore = defineStore("mobileConfig", () => {
  const instance = ref<MobileInstanceConfig | null>(null);

  async function load() {
    try {
      const data = await api.get<{
        instance: MobileInstanceConfig | null;
      }>("/admin/mobile/my-config");
      instance.value = data.instance;
    } catch {
      instance.value = null;
    }
  }

  function clear() {
    instance.value = null;
  }

  return { instance, load, clear };
});
