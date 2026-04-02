// Demo mode interceptor — loaded async but awaited before first API call
// Can be activated at build time (VITE_DEMO_MODE) or at runtime (admin/admin login)
let demoReady: Promise<void> | null =
  import.meta.env.VITE_DEMO_MODE === "true"
    ? import("./demo/index").then(({ setupDemoInterceptor }) =>
        setupDemoInterceptor(),
      )
    : null;

let demoActive = import.meta.env.VITE_DEMO_MODE === "true";

// Activate demo mode at runtime (e.g. admin/admin login on production)
export function activateDemoMode(): Promise<void> {
  if (demoActive) return demoReady!;
  demoActive = true;
  demoReady = import("./demo/index").then(({ setupDemoInterceptor }) =>
    setupDemoInterceptor(),
  );
  return demoReady;
}

export function isDemoActive(): boolean {
  return demoActive;
}

// Deactivate demo mode (on logout) — interceptor will pass through to real backend
export function deactivateDemoMode(): void {
  demoActive = false;
  demoReady = null;
}

// Auto-activate demo if page reloads with a demo token in localStorage
function checkDemoToken(): boolean {
  const token = localStorage.getItem("admin_token");
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.demo === true;
  } catch {
    return false;
  }
}

if (!demoActive && checkDemoToken()) {
  activateDemoMode();
}

// Base API client
const BASE_URL = "";

export interface ApiResponse<T> {
  data?: T;
  error?: string;
  status: "ok" | "error";
}

// Get auth headers from localStorage
export function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem("admin_token");
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  if (demoReady) await demoReady;
  const url = `${BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || `HTTP error ${response.status}`);
  }

  return response.json();
}

export const api = {
  get: <T>(endpoint: string) => request<T>(endpoint),

  post: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, {
      method: "POST",
      body: data ? JSON.stringify(data) : undefined,
    }),

  put: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, {
      method: "PUT",
      body: data ? JSON.stringify(data) : undefined,
    }),

  patch: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, {
      method: "PATCH",
      body: data ? JSON.stringify(data) : undefined,
    }),

  delete: <T>(endpoint: string) => request<T>(endpoint, { method: "DELETE" }),

  upload: async <T>(endpoint: string, file: File): Promise<T> => {
    if (demoReady) await demoReady;
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${BASE_URL}${endpoint}`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(error.detail || `HTTP error ${response.status}`);
    }

    return response.json();
  },
};

// SSE helper with generic type support (fetch-based to send JWT)
export function createSSE<T = unknown>(endpoint: string, onMessage: (data: T) => void) {
  // In demo mode, use polling via fetch instead of real SSE
  if (demoActive) {
    let stopped = false;
    const poll = async () => {
      if (demoReady) await demoReady;
      while (!stopped) {
        try {
          const res = await fetch(`${BASE_URL}${endpoint}`);
          if (res.ok) {
            const data = await res.json();
            onMessage(data as T);
          }
        } catch {
          // ignore
        }
        await new Promise((r) => setTimeout(r, 3000));
      }
    };
    poll();
    return {
      close: () => {
        stopped = true;
      },
      eventSource: null as unknown as EventSource,
    };
  }

  // Real mode: fetch-based SSE with JWT auth
  const controller = new AbortController();
  let stopped = false;

  const connect = async () => {
    while (!stopped) {
      try {
        const response = await fetch(`${BASE_URL}${endpoint}`, {
          headers: { ...getAuthHeaders(), Accept: "text/event-stream" },
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`SSE connection failed: ${response.status}`);
        }

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
                onMessage(JSON.parse(payload) as T);
              } catch {
                onMessage(payload as T);
              }
            }
          }
        }
      } catch (e) {
        if (stopped) return;
        console.error("SSE error, reconnecting in 3s:", e);
      }

      if (!stopped) {
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
  };

  connect();

  return {
    close: () => {
      stopped = true;
      controller.abort();
    },
    eventSource: null as unknown as EventSource,
  };
}
