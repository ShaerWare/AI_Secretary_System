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
];
