import { ref, onMounted, onUnmounted, computed } from "vue";
import { createSSE, getAuthHeaders } from "@/api/client";

export interface GpuMetrics {
  memoryPercent: number;
  utilization: number;
  temperature?: number;
  name?: string;
}

export interface MetricsHistory {
  gpu: {
    memory: number[];
    utilization: number[];
  };
  requests: {
    total: number[];
    latency: number[];
  };
  timestamps: string[];
}

const MAX_HISTORY = 60; // 5 minutes at 5s interval

export function useRealtimeMetrics(intervalMs = 5000) {
  const gpuMetrics = ref<GpuMetrics | null>(null);
  const history = ref<MetricsHistory>({
    gpu: { memory: [], utilization: [] },
    requests: { total: [], latency: [] },
    timestamps: [],
  });
  const isConnected = ref(false);
  const error = ref<string | null>(null);

  let intervalId: number | null = null;
  let sseHandle: { close: () => void } | null = null;

  // Try SSE first, fallback to polling
  function connectSSE() {
    try {
      sseHandle = createSSE("/admin/monitor/gpu/stream", (data: unknown) => {
        updateMetrics(data);
        isConnected.value = true;
        error.value = null;
      });

      // SSE errors will cause reconnection inside createSSE.
      // If after 10s we have no data, fall back to polling.
      setTimeout(() => {
        if (!gpuMetrics.value && !intervalId) {
          sseHandle?.close();
          sseHandle = null;
          startPolling();
        }
      }, 10000);
    } catch {
      startPolling();
    }
  }

  function startPolling() {
    if (intervalId) return;

    const poll = async () => {
      try {
        const response = await fetch("/admin/monitor/gpu", {
          headers: getAuthHeaders(),
        });
        if (response.ok) {
          const data = await response.json();
          updateMetrics(data);
          isConnected.value = true;
          error.value = null;
        }
      } catch {
        isConnected.value = false;
        error.value = "Failed to fetch metrics";
      }
    };

    poll(); // Initial fetch
    intervalId = window.setInterval(poll, intervalMs);
  }

  function updateMetrics(data: any) {
    const gpu = data?.gpus?.[0] || data;

    if (gpu) {
      const memPercent =
        gpu.allocated_gb && gpu.total_memory_gb
          ? Math.round((gpu.allocated_gb / gpu.total_memory_gb) * 100)
          : gpu.memory_percent || 0;

      gpuMetrics.value = {
        memoryPercent: memPercent,
        utilization: gpu.utilization_percent || gpu.utilization || 0,
        temperature: gpu.temperature_c || gpu.temperature,
        name: gpu.name,
      };

      // Update history
      history.value.gpu.memory.push(memPercent);
      history.value.gpu.utilization.push(gpuMetrics.value.utilization);
      history.value.timestamps.push(new Date().toISOString());

      // Trim to max size
      if (history.value.gpu.memory.length > MAX_HISTORY) {
        history.value.gpu.memory.shift();
        history.value.gpu.utilization.shift();
        history.value.timestamps.shift();
      }
    }
  }

  function disconnect() {
    if (sseHandle) {
      sseHandle.close();
      sseHandle = null;
    }
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
    isConnected.value = false;
  }

  onMounted(() => {
    connectSSE();
  });

  onUnmounted(() => {
    disconnect();
  });

  // Computed sparkline data
  const memorySparkline = computed(() => history.value.gpu.memory.slice(-20));
  const utilizationSparkline = computed(() => history.value.gpu.utilization.slice(-20));

  return {
    gpuMetrics,
    history,
    isConnected,
    error,
    memorySparkline,
    utilizationSparkline,
    disconnect,
  };
}
