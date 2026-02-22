<script setup lang="ts">
import { ref, onMounted, defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ClipboardList,
  Plus,
  RefreshCw,
  LayoutGrid,
  ChartGantt,
  Github,
  ChevronDown,
  FolderOpen,
  Settings,
} from 'lucide-vue-next'
import { useKanbanStore } from '@/stores/kanban'
import { useAuthStore } from '@/stores/auth'
import { useConfirmStore } from '@/stores/confirm'
import { useToastStore } from '@/stores/toast'
import type { KanbanTask, TaskCreateData, TaskUpdateData } from '@/api'
import KanbanBoard from '@/components/kanban/KanbanBoard.vue'
import KanbanTaskForm from '@/components/kanban/KanbanTaskForm.vue'
import KanbanCardDetail from '@/components/kanban/KanbanCardDetail.vue'
import KanbanProjectForm from '@/components/kanban/KanbanProjectForm.vue'

const KanbanRoadmap = defineAsyncComponent(
  () => import('@/components/kanban/KanbanRoadmap.vue'),
)

const { t } = useI18n()
const kanbanStore = useKanbanStore()
const authStore = useAuthStore()
const confirmStore = useConfirmStore()
const toast = useToastStore()

const showForm = ref(false)
const editingTask = ref<KanbanTask | null>(null)
const showDetail = ref(false)
const detailTask = ref<KanbanTask | null>(null)

// Project selector
const showProjectSelect = ref(false)
const showProjectForm = ref(false)
const editingProject = ref<(typeof kanbanStore.projects)[0] | null>(null)

onMounted(async () => {
  await kanbanStore.fetchProjects()
  kanbanStore.fetchTasks()
})

function openCreate() {
  editingTask.value = null
  showForm.value = true
}

function openDetail(task: KanbanTask) {
  detailTask.value = kanbanStore.tasks.find((t) => t.id === task.id) || task
  showDetail.value = true
}

function openProjectCreate() {
  editingProject.value = null
  showProjectForm.value = true
  showProjectSelect.value = false
}

function openProjectEdit() {
  if (kanbanStore.currentProject) {
    editingProject.value = kanbanStore.currentProject
    showProjectForm.value = true
    showProjectSelect.value = false
  }
}

async function handleCreate(data: TaskCreateData) {
  try {
    await kanbanStore.createTask(data)
    showForm.value = false
    toast.success(t('kanban.taskCreated'))
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleUpdate(id: number, data: TaskUpdateData) {
  try {
    await kanbanStore.updateTask(id, data)
    showForm.value = false
    toast.success(t('kanban.taskUpdated'))
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleDetailUpdate(id: number, data: Record<string, unknown>) {
  try {
    await kanbanStore.updateTask(id, data as TaskUpdateData)
    detailTask.value = kanbanStore.tasks.find((t) => t.id === id) || null
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleDelete(id: number) {
  const confirmed = await confirmStore.confirmDelete(
    kanbanStore.tasks.find((t) => t.id === id)?.title || '',
    t('kanban.task'),
  )
  if (!confirmed) return
  try {
    await kanbanStore.deleteTask(id)
    showDetail.value = false
    toast.success(t('kanban.taskDeleted'))
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleDateChange(taskId: number, startDate: string, endDate: string) {
  try {
    await kanbanStore.updateTask(taskId, { start_date: startDate, due_date: endDate })
    toast.success(t('kanban.taskUpdated'))
  } catch (e) {
    toast.error((e as Error).message)
    await kanbanStore.fetchTasks()
  }
}

function handleGanttClick(taskId: number) {
  const task = kanbanStore.tasks.find((t) => t.id === taskId)
  if (task) openDetail(task)
}

async function handleReorder(taskId: number, newStatus: string, newPosition: number) {
  try {
    await kanbanStore.reorderTask(taskId, newStatus, newPosition)
  } catch (e) {
    toast.error((e as Error).message)
    await kanbanStore.fetchTasks()
  }
}

async function handleAddChecklist(taskId: number, text: string) {
  try {
    await kanbanStore.addChecklistItem(taskId, text)
    detailTask.value = kanbanStore.tasks.find((t) => t.id === taskId) || null
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleToggleChecklist(itemId: number) {
  try {
    await kanbanStore.toggleChecklistItem(itemId)
    if (detailTask.value) {
      detailTask.value = kanbanStore.tasks.find((t) => t.id === detailTask.value!.id) || null
    }
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleDeleteChecklist(itemId: number) {
  try {
    await kanbanStore.deleteChecklistItem(itemId)
    if (detailTask.value) {
      detailTask.value = kanbanStore.tasks.find((t) => t.id === detailTask.value!.id) || null
    }
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleAddDependency(blockerId: number, dependentId: number) {
  try {
    await kanbanStore.addDependency(blockerId, dependentId)
    if (detailTask.value) {
      detailTask.value = kanbanStore.tasks.find((t) => t.id === detailTask.value!.id) || null
    }
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleRemoveDependency(blockerId: number, dependentId: number) {
  try {
    await kanbanStore.removeDependency(blockerId, dependentId)
    if (detailTask.value) {
      detailTask.value = kanbanStore.tasks.find((t) => t.id === detailTask.value!.id) || null
    }
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleSync() {
  if (!kanbanStore.currentProject) return
  try {
    const result = await kanbanStore.syncProject(kanbanStore.currentProject.id)
    toast.success(
      `${t('kanban.syncSuccess')}: ${result.created} ${t('kanban.created')}, ${result.updated} ${t('kanban.updated')}`,
    )
  } catch (e) {
    toast.error(t('kanban.syncFailed'))
  }
}

async function handleProjectCreate(data: Record<string, unknown>) {
  try {
    await kanbanStore.createProject(data as unknown as Parameters<typeof kanbanStore.createProject>[0])
    showProjectForm.value = false
    toast.success(t('kanban.projectCreated'))
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleProjectUpdate(id: number, data: Record<string, unknown>) {
  try {
    await kanbanStore.updateProject(
      id,
      data as Parameters<typeof kanbanStore.updateProject>[1],
    )
    showProjectForm.value = false
    toast.success(t('kanban.projectUpdated'))
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleProjectDelete(id: number) {
  const project = kanbanStore.projects.find((p) => p.id === id)
  const confirmed = await confirmStore.confirmDelete(project?.name || '', t('kanban.project'))
  if (!confirmed) return
  try {
    await kanbanStore.deleteProject(id)
    showProjectForm.value = false
    toast.success(t('kanban.projectDeleted'))
  } catch (e) {
    toast.error((e as Error).message)
  }
}

function selectProject(id: number | null) {
  kanbanStore.selectProject(id)
  showProjectSelect.value = false
}
</script>

<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
          <ClipboardList class="w-5 h-5 text-primary" />
        </div>
        <div>
          <h1 class="text-2xl font-bold">{{ t('kanban.title') }}</h1>
        </div>

        <!-- Project selector -->
        <div class="relative ml-2">
          <button
            class="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
            @click="showProjectSelect = !showProjectSelect"
          >
            <Github v-if="kanbanStore.currentProject" class="w-4 h-4" />
            <FolderOpen v-else class="w-4 h-4" />
            <span class="max-w-[200px] truncate">
              {{ kanbanStore.currentProject?.name || t('kanban.localTasks') }}
            </span>
            <ChevronDown class="w-3 h-3" />
          </button>
          <div
            v-if="showProjectSelect"
            class="absolute top-full left-0 mt-1 bg-card border border-border rounded-lg shadow-lg z-10 min-w-[240px]"
          >
            <button
              class="w-full text-left px-4 py-2 hover:bg-secondary/50 first:rounded-t-lg text-sm flex items-center gap-2"
              :class="{ 'bg-secondary/30': kanbanStore.selectedProjectId === null }"
              @click="selectProject(null)"
            >
              <FolderOpen class="w-4 h-4 text-muted-foreground" />
              {{ t('kanban.localTasks') }}
            </button>
            <button
              v-for="project in kanbanStore.projects"
              :key="project.id"
              class="w-full text-left px-4 py-2 hover:bg-secondary/50 text-sm flex items-center gap-2"
              :class="{ 'bg-secondary/30': kanbanStore.selectedProjectId === project.id }"
              @click="selectProject(project.id)"
            >
              <Github class="w-4 h-4 text-muted-foreground" />
              <span class="truncate">{{ project.name }}</span>
              <span class="text-xs text-muted-foreground ml-auto">
                {{ project.github_owner }}/{{ project.github_repo }}
              </span>
            </button>
            <div v-if="authStore.isAdmin" class="border-t border-border">
              <button
                class="w-full text-left px-4 py-2 hover:bg-secondary/50 last:rounded-b-lg text-sm text-primary flex items-center gap-2"
                @click="openProjectCreate"
              >
                <Plus class="w-4 h-4" />
                {{ t('kanban.addProject') }}
              </button>
            </div>
          </div>
        </div>

        <!-- Edit project button -->
        <button
          v-if="kanbanStore.currentProject && authStore.isAdmin"
          class="p-1.5 rounded-lg hover:bg-muted transition-colors text-muted-foreground"
          :title="t('kanban.editProject')"
          @click="openProjectEdit"
        >
          <Settings class="w-4 h-4" />
        </button>
      </div>
      <div class="flex items-center gap-2">
        <!-- Sync button (GitHub projects only) -->
        <button
          v-if="kanbanStore.currentProject && !authStore.isGuest"
          class="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
          :disabled="kanbanStore.syncing"
          @click="handleSync"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': kanbanStore.syncing }" />
          {{ t('kanban.syncGithub') }}
        </button>

        <!-- View toggle -->
        <div class="flex rounded-lg border border-border overflow-hidden">
          <button
            class="flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors"
            :class="
              kanbanStore.activeView === 'kanban'
                ? 'bg-primary text-primary-foreground'
                : 'bg-card text-muted-foreground hover:bg-muted'
            "
            @click="kanbanStore.activeView = 'kanban'"
          >
            <LayoutGrid class="w-4 h-4" />
            {{ t('kanban.viewKanban') }}
          </button>
          <button
            class="flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors"
            :class="
              kanbanStore.activeView === 'roadmap'
                ? 'bg-primary text-primary-foreground'
                : 'bg-card text-muted-foreground hover:bg-muted'
            "
            @click="kanbanStore.activeView = 'roadmap'"
          >
            <ChartGantt class="w-4 h-4" />
            {{ t('kanban.viewRoadmap') }}
          </button>
        </div>

        <button
          class="p-2 rounded-lg border border-border hover:bg-muted transition-colors"
          :disabled="kanbanStore.loading"
          @click="kanbanStore.fetchTasks()"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': kanbanStore.loading }" />
        </button>
        <button
          v-if="!authStore.isGuest"
          class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          @click="openCreate"
        >
          <Plus class="w-4 h-4" />
          {{ t('kanban.create') }}
        </button>
      </div>
    </div>

    <!-- Kanban Board -->
    <KanbanBoard
      v-if="kanbanStore.activeView === 'kanban'"
      :tasks-by-status="kanbanStore.tasksByStatus"
      :loading="kanbanStore.loading"
      :disabled="authStore.isGuest"
      :is-github-project="!!kanbanStore.currentProject"
      @reorder="handleReorder"
      @click-task="openDetail"
      @create-task="openCreate"
    />

    <!-- Gantt Roadmap -->
    <KanbanRoadmap
      v-else
      :tasks="kanbanStore.ganttTasks"
      :loading="kanbanStore.loading"
      :disabled="authStore.isGuest"
      @click-task="handleGanttClick"
      @date-change="handleDateChange"
    />

    <!-- Modals -->
    <KanbanTaskForm
      :visible="showForm"
      :task="editingTask"
      @close="showForm = false"
      @create="handleCreate"
      @update="handleUpdate"
    />

    <KanbanCardDetail
      :visible="showDetail"
      :task="detailTask"
      :all-tasks="kanbanStore.tasks"
      :current-project="kanbanStore.currentProject"
      @close="showDetail = false"
      @update="handleDetailUpdate"
      @delete="handleDelete"
      @add-checklist="handleAddChecklist"
      @toggle-checklist="handleToggleChecklist"
      @delete-checklist="handleDeleteChecklist"
      @add-dependency="handleAddDependency"
      @remove-dependency="handleRemoveDependency"
    />

    <KanbanProjectForm
      :visible="showProjectForm"
      :project="editingProject"
      @close="showProjectForm = false"
      @create="handleProjectCreate"
      @update="handleProjectUpdate"
      @delete="handleProjectDelete"
    />
  </div>

  <!-- Click-away for project selector -->
  <Teleport to="body">
    <div
      v-if="showProjectSelect"
      class="fixed inset-0 z-[5]"
      @click="showProjectSelect = false"
    />
  </Teleport>
</template>
