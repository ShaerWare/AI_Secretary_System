import type { DemoRoute } from "./types";

const demoMembers = [
  {
    id: 1,
    workspace_id: 1,
    user_id: 1,
    role_name: "owner",
    joined_at: "2025-01-15T10:00:00",
    username: "admin",
    display_name: "Администратор",
    email: "admin@example.com",
    is_active: true,
    last_login: "2026-02-24T09:30:00",
  },
  {
    id: 2,
    workspace_id: 1,
    user_id: 2,
    role_name: "operator",
    joined_at: "2025-03-10T14:00:00",
    username: "operator1",
    display_name: "Оператор Мария",
    email: "maria@example.com",
    is_active: true,
    last_login: "2026-02-23T18:45:00",
  },
  {
    id: 3,
    workspace_id: 1,
    user_id: 3,
    role_name: "viewer",
    joined_at: "2025-06-20T09:00:00",
    username: "demo",
    display_name: "Демо пользователь",
    email: "demo@example.com",
    is_active: true,
    last_login: "2026-02-20T12:00:00",
  },
  {
    id: 4,
    workspace_id: 1,
    user_id: 4,
    role_name: "operator",
    joined_at: "2025-09-01T11:30:00",
    username: "ivan",
    display_name: "Иван Петров",
    email: "ivan@example.com",
    is_active: false,
    last_login: "2026-01-15T08:00:00",
  },
];

const demoRoles = [
  { id: 1, name: "owner", display_name: "Владелец", is_system: true },
  { id: 2, name: "admin", display_name: "Администратор", is_system: true },
  { id: 3, name: "operator", display_name: "Оператор", is_system: true },
  { id: 4, name: "viewer", display_name: "Наблюдатель", is_system: true },
];

interface DemoInvite {
  id: number;
  workspace_id: number;
  email: string | null;
  invite_code: string;
  role_name: string;
  created_by: number;
  expires_at: string | null;
  used_at: string | null;
  used_by: number | null;
  max_uses: number | null;
  used_count: number;
  is_valid: boolean;
}

let nextInviteId = 2;
const demoInvites: DemoInvite[] = [
  {
    id: 1,
    workspace_id: 1,
    email: null,
    invite_code: "demo-invite-abc123",
    role_name: "operator",
    created_by: 1,
    expires_at: "2026-03-01T10:00:00",
    used_at: null,
    used_by: null,
    max_uses: 5,
    used_count: 1,
    is_valid: true,
  },
];

export const workspaceRoutes: DemoRoute[] = [
  // GET /admin/workspace
  {
    method: "GET",
    pattern: /^\/admin\/workspace$/,
    handler: () => ({
      id: 1,
      name: "Default",
      slug: "default",
      owner_id: 1,
      member_count: demoMembers.length,
      created_at: "2025-01-15T10:00:00",
    }),
  },
  // GET /admin/workspace/members
  {
    method: "GET",
    pattern: /^\/admin\/workspace\/members$/,
    handler: () => [...demoMembers],
  },
  // PUT /admin/workspace/members/:id/role
  {
    method: "PUT",
    pattern: /^\/admin\/workspace\/members\/(\d+)\/role$/,
    handler: ({ matches, body }) => {
      const userId = parseInt(matches[1]);
      const { role_name } = body as { role_name: string };
      const member = demoMembers.find((m) => m.user_id === userId);
      if (!member) throw new Error("Member not found");
      if (member.user_id === 1) throw new Error("Cannot change the workspace owner's role");
      member.role_name = role_name;
      return { ...member };
    },
  },
  // DELETE /admin/workspace/members/:id
  {
    method: "DELETE",
    pattern: /^\/admin\/workspace\/members\/(\d+)$/,
    handler: ({ matches }) => {
      const userId = parseInt(matches[1]);
      const idx = demoMembers.findIndex((m) => m.user_id === userId);
      if (idx === -1) throw new Error("Member not found");
      if (demoMembers[idx].user_id === 1) throw new Error("Cannot remove the workspace owner");
      demoMembers.splice(idx, 1);
      return { message: "Member removed" };
    },
  },
  // GET /admin/roles (reuse for role dropdown)
  {
    method: "GET",
    pattern: /^\/admin\/roles$/,
    handler: () => [...demoRoles],
  },
  // POST /admin/workspace/invites
  {
    method: "POST",
    pattern: /^\/admin\/workspace\/invites$/,
    handler: ({ body }) => {
      const { role_name, email, max_uses, expires_hours } = body as {
        role_name: string;
        email?: string;
        max_uses?: number;
        expires_hours?: number;
      };
      const invite = {
        id: nextInviteId++,
        workspace_id: 1,
        email: email || null,
        invite_code: `demo-invite-${Date.now().toString(36)}`,
        role_name,
        created_by: 1,
        expires_at: expires_hours
          ? new Date(Date.now() + expires_hours * 3600000).toISOString()
          : null,
        used_at: null,
        used_by: null,
        max_uses: max_uses || null,
        used_count: 0,
        is_valid: true,
      };
      demoInvites.push(invite);
      return invite;
    },
  },
  // GET /admin/workspace/invites
  {
    method: "GET",
    pattern: /^\/admin\/workspace\/invites$/,
    handler: () => [...demoInvites],
  },
  // DELETE /admin/workspace/invites/:id
  {
    method: "DELETE",
    pattern: /^\/admin\/workspace\/invites\/(\d+)$/,
    handler: ({ matches }) => {
      const id = parseInt(matches[1]);
      const idx = demoInvites.findIndex((i) => i.id === id);
      if (idx === -1) throw new Error("Invite not found");
      demoInvites.splice(idx, 1);
      return { message: "Invite deleted" };
    },
  },
  // GET /admin/workspace/invites/:code/info (public)
  {
    method: "GET",
    pattern: /^\/admin\/workspace\/invites\/([^/]+)\/info$/,
    handler: ({ matches }) => {
      const code = matches[1];
      const invite = demoInvites.find((i) => i.invite_code === code);
      if (!invite || !invite.is_valid) throw new Error("Invite not found or expired");
      return {
        workspace_name: "Default",
        role_name: invite.role_name,
        expires_at: invite.expires_at,
      };
    },
  },
  // POST /admin/workspace/invites/accept (public)
  {
    method: "POST",
    pattern: /^\/admin\/workspace\/invites\/accept$/,
    handler: ({ body }) => {
      const { invite_code, username, display_name } = body as {
        invite_code: string;
        username: string;
        password: string;
        display_name?: string;
      };
      const invite = demoInvites.find((i) => i.invite_code === invite_code);
      if (!invite || !invite.is_valid) throw new Error("Invite is invalid or expired");
      invite.used_count++;
      return {
        access_token: "demo-token",
        token_type: "bearer",
        expires_in: 86400,
        user: {
          id: 100,
          username,
          display_name: display_name || username,
          role: "user",
        },
      };
    },
  },
];
