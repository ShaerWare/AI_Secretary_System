import { api } from './client'

export interface KanbanTask {
  id: number
  title: string
  description: string | null
  status: string
  is_private: boolean
  assignee: string | null
  created_by: string
  start_date: string | null
  due_date: string | null
  position: number
  tags: string[]
  checklist: ChecklistItem[]
  blockers: number[]
  dependents: number[]
  created: string | null
  updated: string | null
}

export interface ChecklistItem {
  id: number
  task_id: number
  text: string
  is_done: boolean
  position: number
}

export interface TaskCreateData {
  title: string
  description?: string
  assignee?: string
  start_date?: string
  due_date?: string
  tags?: string[]
}

export interface TaskUpdateData {
  title?: string
  description?: string
  status?: string
  assignee?: string
  start_date?: string
  due_date?: string
  tags?: string[]
  is_private?: boolean
}

export const kanbanApi = {
  getTasks: () => api.get<{ tasks: KanbanTask[] }>('/admin/kanban/tasks'),

  createTask: (data: TaskCreateData) =>
    api.post<{ task: KanbanTask }>('/admin/kanban/tasks', data),

  updateTask: (id: number, data: TaskUpdateData) =>
    api.patch<{ task: KanbanTask }>(`/admin/kanban/tasks/${id}`, data),

  deleteTask: (id: number) => api.delete<{ status: string }>(`/admin/kanban/tasks/${id}`),

  reorder: (taskId: number, newStatus: string, newPosition: number) =>
    api.post<{ task: KanbanTask }>('/admin/kanban/reorder', {
      task_id: taskId,
      new_status: newStatus,
      new_position: newPosition,
    }),

  addDependency: (blockerId: number, dependentId: number) =>
    api.post<{ status: string }>('/admin/kanban/dependencies', {
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
}
