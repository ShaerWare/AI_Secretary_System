import { api } from "./client";

export interface KanbanProject {
  id: number;
  name: string;
  github_owner: string;
  github_repo: string;
  has_token: boolean;
  webhook_secret_set: boolean;
  label_mapping: Record<string, string>;
  sync_enabled: boolean;
  last_synced: string | null;
  created: string | null;
  updated: string | null;
}

export interface KanbanTask {
  id: number;
  title: string;
  description: string | null;
  status: string;
  is_private: boolean;
  assignee: string | null;
  created_by: string;
  owner_id: number | null;
  start_date: string | null;
  due_date: string | null;
  position: number;
  tags: string[];
  project_id: number | null;
  github_issue_number: number | null;
  checklist: ChecklistItem[];
  blockers: number[];
  dependents: number[];
  created: string | null;
  updated: string | null;
}

export interface ChecklistItem {
  id: number;
  task_id: number;
  text: string;
  is_done: boolean;
  position: number;
}

export interface TaskCreateData {
  title: string;
  description?: string;
  status?: string;
  assignee?: string;
  start_date?: string;
  due_date?: string;
  tags?: string[];
}

export interface TaskUpdateData {
  title?: string;
  description?: string;
  status?: string;
  assignee?: string;
  start_date?: string;
  due_date?: string;
  tags?: string[];
  is_private?: boolean;
}

export interface ProjectCreateData {
  name: string;
  github_owner: string;
  github_repo: string;
  github_token?: string;
  webhook_secret?: string;
  label_mapping?: Record<string, string>;
  sync_enabled?: boolean;
}

export interface ProjectUpdateData {
  name?: string;
  github_owner?: string;
  github_repo?: string;
  github_token?: string;
  webhook_secret?: string;
  label_mapping?: Record<string, string>;
  sync_enabled?: boolean;
}

export const kanbanApi = {
  // Projects
  getProjects: () => api.get<{ projects: KanbanProject[] }>("/admin/kanban/projects"),

  createProject: (data: ProjectCreateData) =>
    api.post<{ project: KanbanProject }>("/admin/kanban/projects", data),

  updateProject: (id: number, data: ProjectUpdateData) =>
    api.patch<{ project: KanbanProject }>(`/admin/kanban/projects/${id}`, data),

  deleteProject: (id: number) => api.delete<{ status: string }>(`/admin/kanban/projects/${id}`),

  syncProject: (id: number) =>
    api.post<{ created: number; updated: number; total: number }>(
      `/admin/kanban/projects/${id}/sync`
    ),

  // Tasks
  getTasks: (projectId?: number | null) => {
    const params = projectId != null ? `?project_id=${projectId}` : "";
    return api.get<{ tasks: KanbanTask[] }>(`/admin/kanban/tasks${params}`);
  },

  createTask: (data: TaskCreateData) => api.post<{ task: KanbanTask }>("/admin/kanban/tasks", data),

  updateTask: (id: number, data: TaskUpdateData) =>
    api.patch<{ task: KanbanTask }>(`/admin/kanban/tasks/${id}`, data),

  deleteTask: (id: number) => api.delete<{ status: string }>(`/admin/kanban/tasks/${id}`),

  reorder: (taskId: number, newStatus: string, newPosition: number) =>
    api.post<{ task: KanbanTask }>("/admin/kanban/reorder", {
      task_id: taskId,
      new_status: newStatus,
      new_position: newPosition,
    }),

  addDependency: (blockerId: number, dependentId: number) =>
    api.post<{ status: string }>("/admin/kanban/dependencies", {
      blocker_id: blockerId,
      dependent_id: dependentId,
    }),

  removeDependency: (blockerId: number, dependentId: number) =>
    api.delete<{ status: string }>(
      `/admin/kanban/dependencies?blocker_id=${blockerId}&dependent_id=${dependentId}`
    ),

  addChecklistItem: (taskId: number, text: string, position: number = 0) =>
    api.post<{ item: ChecklistItem }>(`/admin/kanban/tasks/${taskId}/checklist`, {
      text,
      position,
    }),

  toggleChecklistItem: (itemId: number) =>
    api.patch<{ item: ChecklistItem }>(`/admin/kanban/checklist/${itemId}/toggle`),

  deleteChecklistItem: (itemId: number) =>
    api.delete<{ status: string }>(`/admin/kanban/checklist/${itemId}`),
};
