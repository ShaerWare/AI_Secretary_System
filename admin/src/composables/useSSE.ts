import { ref, onUnmounted, type Ref, shallowRef } from "vue";
import { getAuthHeaders } from "@/api/client";

export function useSSE<T = unknown>(url: string) {
  const data: Ref<T[]> = shallowRef([]);
  const lastData: Ref<T | null> = shallowRef(null);
  const isConnected = ref(false);
  const error = ref<string | null>(null);
  let controller: AbortController | null = null;
  let stopped = false;

  async function connect() {
    if (controller) return;
    stopped = false;

    while (!stopped) {
      controller = new AbortController();
      try {
        const response = await fetch(url, {
          headers: { ...getAuthHeaders(), Accept: "text/event-stream" },
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`SSE connection failed: ${response.status}`);
        }

        isConnected.value = true;
        error.value = null;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!stopped) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const payload = line.slice(6);
              try {
                const parsed = JSON.parse(payload) as T;
                const newData = [...data.value, parsed];
                data.value = newData.length > 1000 ? newData.slice(-500) : newData;
                lastData.value = parsed;
              } catch {
                const newData = [...data.value, payload as T];
                data.value = newData.length > 1000 ? newData.slice(-500) : newData;
                lastData.value = payload as T;
              }
            }
          }
        }
      } catch (e) {
        if (stopped) return;
        isConnected.value = false;
        error.value = "Connection lost";
      }

      controller = null;
      if (!stopped) {
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
  }

  function disconnect() {
    stopped = true;
    if (controller) {
      controller.abort();
      controller = null;
    }
    isConnected.value = false;
  }

  function clear() {
    data.value = [];
    lastData.value = null;
  }

  onUnmounted(() => {
    disconnect();
  });

  return {
    data,
    lastData,
    isConnected,
    error,
    connect,
    disconnect,
    clear,
  };
}
