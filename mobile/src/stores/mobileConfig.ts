import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { api } from "@/api/client";

export interface MobileInstanceConfig {
  id: string;
  name: string;
  description?: string;
  enabled?: boolean;
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
  // All assistants (mobile instances) assigned to the current user via
  // ResourceShare. Each maps to a private per-user chat session.
  const instances = ref<MobileInstanceConfig[]>([]);
  // The assistant currently in focus (drives streaming instance_id + new-chat
  // inheritance). Null → fall back to the first assigned instance.
  const activeInstanceId = ref<string | null>(null);
  const loaded = ref(false);

  // Backward-compatible single-instance accessor used across the app.
  const instance = computed<MobileInstanceConfig | null>(() => {
    if (activeInstanceId.value) {
      return instances.value.find((i) => i.id === activeInstanceId.value) || null;
    }
    return instances.value[0] || null;
  });

  async function load() {
    try {
      const data = await api.get<{ instances: MobileInstanceConfig[] }>(
        "/admin/mobile/my-instances",
      );
      instances.value = (data.instances || []).filter((i) => i.enabled !== false);
      // Drop a stale active id if the assistant is no longer assigned.
      if (
        activeInstanceId.value &&
        !instances.value.some((i) => i.id === activeInstanceId.value)
      ) {
        activeInstanceId.value = null;
      }
    } catch {
      instances.value = [];
    } finally {
      loaded.value = true;
    }
  }

  // Load once (used on cold start where the store wasn't populated at login).
  async function ensureLoaded() {
    if (!loaded.value) await load();
  }

  function setActive(id: string | null) {
    activeInstanceId.value = id;
  }

  function getById(id: string | null | undefined): MobileInstanceConfig | null {
    if (!id) return null;
    return instances.value.find((i) => i.id === id) || null;
  }

  function clear() {
    instances.value = [];
    activeInstanceId.value = null;
    loaded.value = false;
  }

  return {
    instances,
    activeInstanceId,
    instance,
    loaded,
    load,
    ensureLoaded,
    setActive,
    getById,
    clear,
  };
});
