import { api } from './client'

// ============== Types ==============

export interface GitHubRepoProject {
  id: number
  name: string
  github_owner: string
  github_repo: string
  has_token: boolean
  branch: string
  collection_id: number | null
  sync_status: 'idle' | 'syncing' | 'error'
  sync_error: string | null
  last_synced: string | null
  last_commit_sha: string | null
  include_patterns: string[]
  exclude_patterns: string[]
  file_count: number
  total_size_bytes: number
  workspace_id: number
  created: string | null
  updated: string | null
}

export interface GitHubProjectCreateData {
  name: string
  github_owner: string
  github_repo: string
  github_token?: string
  branch?: string
  include_patterns?: string[]
  exclude_patterns?: string[]
}

export interface GitHubProjectUpdateData {
  name?: string
  github_token?: string
  branch?: string
  include_patterns?: string[]
  exclude_patterns?: string[]
}

export interface GitHubProjectSyncResult {
  status: string
  changed: boolean
  commit_sha: string
  files_indexed?: number
  total_size_bytes?: number
  synced_at?: string
  message?: string
}

export interface GitHubProjectStatus {
  sync_status: string
  sync_error: string | null
  last_synced: string | null
  last_commit_sha: string | null
  file_count: number
  total_size_bytes: number
}

// ============== API ==============

export const githubReposApi = {
  listProjects: () =>
    api.get<{ projects: GitHubRepoProject[] }>('/admin/github-repos/projects'),

  createProject: (data: GitHubProjectCreateData) =>
    api.post<{ status: string; project: GitHubRepoProject; files_indexed: number; collection_id: number }>(
      '/admin/github-repos/projects',
      data,
    ),

  getProject: (id: number) =>
    api.get<{ project: GitHubRepoProject }>(`/admin/github-repos/projects/${id}`),

  updateProject: (id: number, data: GitHubProjectUpdateData) =>
    api.put<{ status: string; project: GitHubRepoProject }>(
      `/admin/github-repos/projects/${id}`,
      data,
    ),

  deleteProject: (id: number) =>
    api.delete<{ status: string }>(`/admin/github-repos/projects/${id}`),

  syncProject: (id: number) =>
    api.post<GitHubProjectSyncResult>(`/admin/github-repos/projects/${id}/sync`),

  getProjectStatus: (id: number) =>
    api.get<GitHubProjectStatus>(`/admin/github-repos/projects/${id}/status`),
}
