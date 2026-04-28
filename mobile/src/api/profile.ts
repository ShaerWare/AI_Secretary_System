import { api } from "./client";

export interface UserProfile {
  username: string;
  display_name: string | null;
  role: string;
  email?: string | null;
}

export interface GoogleOAuthStatus {
  connected: boolean;
  google_email: string | null;
  scopes: string[];
}

export const profileApi = {
  getProfile: () => api.get<UserProfile>("/admin/auth/profile"),

  updateDisplayName: (displayName: string | null) =>
    api.put<UserProfile>("/admin/auth/profile", {
      display_name: displayName,
    }),

  changePassword: (oldPassword: string, newPassword: string) =>
    api.post<{ status: string }>("/admin/auth/change-password", {
      old_password: oldPassword,
      new_password: newPassword,
    }),
};

export const googleApi = {
  getStatus: () => api.get<GoogleOAuthStatus>("/admin/google/status"),

  getAuthUrl: () => api.get<{ auth_url: string }>("/admin/google/auth-url"),

  disconnect: () => api.post<{ status: string }>("/admin/google/disconnect"),
};
