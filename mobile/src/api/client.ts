import { useSettingsStore } from "@/stores/settings";
import { useAuthStore } from "@/stores/auth";

function getBaseUrl(): string {
  return useSettingsStore().serverUrl;
}

function getHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    ...useAuthStore().getAuthHeaders(),
  };
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${getBaseUrl()}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      ...getHeaders(),
      ...options.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 401) {
      useAuthStore().logout();
      throw new Error("Session expired");
    }
    const error = await response
      .json()
      .catch(() => ({ detail: "Request failed" }));
    throw new Error(
      error.detail || `HTTP error ${response.status}`,
    );
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

  delete: <T>(endpoint: string) =>
    request<T>(endpoint, { method: "DELETE" }),

  upload: <T>(endpoint: string, file: File): Promise<T> => {
    const url = `${getBaseUrl()}${endpoint}`;
    const formData = new FormData();
    formData.append("file", file);
    const headers = useAuthStore().getAuthHeaders();
    return fetch(url, {
      method: "POST",
      headers,
      body: formData,
    }).then(async (response) => {
      if (!response.ok) {
        if (response.status === 401) {
          useAuthStore().logout();
          throw new Error("Session expired");
        }
        const error = await response
          .json()
          .catch(() => ({ detail: "Upload failed" }));
        throw new Error(
          error.detail || `HTTP error ${response.status}`,
        );
      }
      return response.json();
    });
  },
};
