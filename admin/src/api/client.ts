// Demo mode interceptor — loaded async but awaited before first API call
const demoReady: Promise<void> | null =
  import.meta.env.VITE_DEMO_MODE === "true"
    ? import("./demo/index").then(({ setupDemoInterceptor }) => setupDemoInterceptor())
    : null;

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

// SSE helper with generic type support
export function createSSE<T = unknown>(endpoint: string, onMessage: (data: T) => void) {
  // In demo mode, use polling via fetch instead of real EventSource
  if (import.meta.env.VITE_DEMO_MODE === "true") {
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

  const eventSource = new EventSource(`${BASE_URL}${endpoint}`);

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as T;
      onMessage(data);
    } catch {
      onMessage(event.data as T);
    }
  };

  eventSource.onerror = () => {
    console.error("SSE error");
  };

  return {
    close: () => eventSource.close(),
    eventSource,
  };
}
