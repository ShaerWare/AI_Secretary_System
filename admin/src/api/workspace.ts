import { api } from "./client";

export interface WorkspaceInfo {
  id: number;
  name: string;
  slug: string;
  owner_id: number | null;
  member_count: number;
  created_at: string;
}

export interface WorkspaceMember {
  id: number;
  workspace_id: number;
  user_id: number;
  role_name: string;
  joined_at: string;
  username?: string;
  display_name?: string;
  email?: string;
  is_active?: boolean;
  last_login?: string | null;
}

export interface RoleInfo {
  id: number;
  name: string;
  display_name: string;
  is_system: boolean;
}

export const workspaceApi = {
  getInfo: () => api.get<WorkspaceInfo>("/admin/workspace"),

  listMembers: () => api.get<WorkspaceMember[]>("/admin/workspace/members"),

  updateMemberRole: (userId: number, roleName: string) =>
    api.put<WorkspaceMember>(`/admin/workspace/members/${userId}/role`, { role_name: roleName }),

  removeMember: (userId: number) =>
    api.delete<{ message: string }>(`/admin/workspace/members/${userId}`),

  listRoles: () => api.get<RoleInfo[]>("/admin/roles"),
};
