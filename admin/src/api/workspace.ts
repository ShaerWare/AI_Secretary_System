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

export interface WorkspaceInvite {
  id: number;
  workspace_id: number;
  email: string | null;
  invite_code: string;
  role_name: string;
  created_by: number | null;
  expires_at: string | null;
  used_at: string | null;
  used_by: number | null;
  max_uses: number | null;
  used_count: number;
  is_valid: boolean;
}

export interface InviteInfo {
  workspace_name: string;
  role_name: string;
  expires_at: string | null;
}

export interface AcceptInviteResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: Record<string, unknown>;
}

export const workspaceApi = {
  getInfo: () => api.get<WorkspaceInfo>("/admin/workspace"),

  listMembers: () => api.get<WorkspaceMember[]>("/admin/workspace/members"),

  updateMemberRole: (userId: number, roleName: string) =>
    api.put<WorkspaceMember>(`/admin/workspace/members/${userId}/role`, { role_name: roleName }),

  removeMember: (userId: number) =>
    api.delete<{ message: string }>(`/admin/workspace/members/${userId}`),

  listRoles: () => api.get<RoleInfo[]>("/admin/roles"),

  // Invites
  createInvite: (data: {
    role_name: string;
    email?: string;
    max_uses?: number;
    expires_hours?: number;
  }) => api.post<WorkspaceInvite>("/admin/workspace/invites", data),

  listInvites: () => api.get<WorkspaceInvite[]>("/admin/workspace/invites"),

  deleteInvite: (inviteId: number) =>
    api.delete<{ message: string }>(`/admin/workspace/invites/${inviteId}`),

  getInviteInfo: (code: string) => api.get<InviteInfo>(`/admin/workspace/invites/${code}/info`),

  acceptInvite: (data: {
    invite_code: string;
    username: string;
    password: string;
    display_name?: string;
  }) => api.post<AcceptInviteResponse>("/admin/workspace/invites/accept", data),
};
