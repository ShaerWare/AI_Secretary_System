<script setup lang="ts">
import { ref, watch, onMounted, defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ClipboardList,
  Plus,
  RefreshCw,
  LayoutGrid,
  ChartGantt,
  Github,
  ChevronLeft,
  FolderOpen,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  Database,
} from 'lucide-vue-next'
import { useKanbanStore } from '@/stores/kanban'
import { useAuthStore } from '@/stores/auth'
import { useConfirmStore } from '@/stores/confirm'
import { useToastStore } from '@/stores/toast'
import { kanbanApi } from '@/api'
import { useSidebarCollapse } from '@/composables/useSidebarCollapse'
import { useResizablePanel } from '@/composables/useResizablePanel'
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
const createStatus = ref<string | undefined>(undefined)
const showDetail = ref(false)
const detailTask = ref<KanbanTask | null>(null)

// Project form
const showProjectForm = ref(false)
const editingProject = ref<(typeof kanbanStore.projects)[0] | null>(null)

// Sidebar
const { collapsed: sidebarCollapsed, toggle: toggleSidebarCollapse } = useSidebarCollapse('kanban-sidebar-collapsed')
const { width: sidebarWidth, startResize: startSidebarResize, startTouchResize: startSidebarTouchResize } = useResizablePanel('kanban-sidebar-width', 288, 220, 440, 'right')
const showSidebar = ref(true)

onMounted(async () => {
  await kanbanStore.fetchProjects()
  kanbanStore.fetchTasks()
})

function openCreate(status?: string) {
  editingTask.value = null
  createStatus.value = status
  showForm.value = true
}

function openDetail(task: KanbanTask) {
  detailTask.value = kanbanStore.tasks.find((t) => t.id === task.id) || task
  showDetail.value = true
}

function openProjectCreate() {
  editingProject.value = null
  showProjectForm.value = true
}

function openProjectEdit(project: (typeof kanbanStore.projects)[0]) {
  editingProject.value = project
  showProjectForm.value = true
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
  } catch {
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
}

// ============== Dataset (RAG Knowledge Base) ==============
const datasetSyncing = ref(false)
const datasetStatus = ref<{ synced: boolean; documents: number; sections: number } | null>(null)

async function fetchDatasetStatus() {
  if (!kanbanStore.currentProject) {
    datasetStatus.value = null
    return
  }
  try {
    datasetStatus.value = await kanbanApi.datasetStatus(kanbanStore.currentProject.id)
  } catch {
    datasetStatus.value = null
  }
}

async function handleDatasetSync() {
  if (!kanbanStore.currentProject) return
  datasetSyncing.value = true
  try {
    const result = await kanbanApi.datasetSync(kanbanStore.currentProject.id)
    toast.success(
      `${t('kanban.dataset.syncSuccess')}: ${result.tasks} ${t('kanban.dataset.tasks')}, ${result.documents} ${t('kanban.dataset.files')}`,
    )
    await fetchDatasetStatus()
  } catch {
    toast.error(t('kanban.dataset.syncFailed'))
  } finally {
    datasetSyncing.value = false
  }
}

async function handleDatasetClear() {
  if (!kanbanStore.currentProject) return
  const confirmed = await confirmStore.confirm({
    title: t('kanban.dataset.clear'),
    message: t('kanban.dataset.clearConfirm'),
    confirmText: t('kanban.dataset.clear'),
    type: 'danger',
  })
  if (!confirmed) return
  try {
    await kanbanApi.datasetClear(kanbanStore.currentProject.id)
    toast.success(t('kanban.dataset.clearSuccess'))
    datasetStatus.value = null
  } catch {
    toast.error(t('kanban.dataset.clearFailed'))
  }
}

watch(() => kanbanStore.selectedProjectId, () => {
  fetchDatasetStatus()
})
</script>

<template>
  <div class="flex h-full">
    <!-- Sidebar: Board List -->
    <div
      :class="[
        'border-r border-border bg-card flex flex-col transition-all flex-shrink-0',
        showSidebar ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
        'fixed md:relative inset-y-0 left-0 z-40 md:z-0',
        sidebarCollapsed ? 'w-full md:!w-14' : 'w-full'
      ]"
      :style="!sidebarCollapsed ? { width: sidebarWidth + 'px' } : undefined"
    >
      <!-- Collapsed mode (desktop only) -->
      <template v-if="sidebarCollapsed">
        <div class="hidden md:flex flex-col items-center gap-1 p-2 border-b border-border">
          <button
            class="p-2 rounded-lg border border-border text-muted-foreground hover:bg-secondary/50 transition-colors"
            :title="t('kanban.expandSidebar')"
            @click="toggleSidebarCollapse"
          >
            <PanelLeftOpen class="w-4 h-4" />
          </button>
          <button
            v-if="authStore.canManage('kanban')"
            class="p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            :title="t('kanban.addProject')"
            @click="openProjectCreate"
          >
            <Plus class="w-4 h-4" />
          </button>
        </div>

        <!-- Collapsed boards list -->
        <div class="hidden md:block flex-1 overflow-y-auto">
          <!-- Local tasks -->
          <button
            :title="t('kanban.localTasks')"
            :class="[
              'w-full flex items-center justify-center py-2 transition-colors',
              kanbanStore.selectedProjectId === null
                ? 'bg-primary/10 border-l-2 border-l-primary'
                : 'hover:bg-secondary/50'
            ]"
            @click="selectProject(null)"
          >
            <div class="w-8 h-8 rounded-lg border border-border flex items-center justify-center">
              <FolderOpen class="w-4 h-4 text-muted-foreground" />
            </div>
          </button>
          <!-- Projects -->
          <button
            v-for="project in kanbanStore.projects"
            :key="project.id"
            :title="project.name"
            :class="[
              'w-full flex items-center justify-center py-2 transition-colors',
              kanbanStore.selectedProjectId === project.id
                ? 'bg-primary/10 border-l-2 border-l-primary'
                : 'hover:bg-secondary/50'
            ]"
            @click="selectProject(project.id)"
          >
            <div class="w-8 h-8 rounded-lg border border-border flex items-center justify-center">
              <Github class="w-4 h-4 text-muted-foreground" />
            </div>
          </button>
        </div>
      </template>

      <!-- Expanded mode -->
      <template v-else>
        <!-- Header -->
        <div class="p-4 border-b border-border flex items-center justify-between">
          <h2 class="font-semibold flex items-center gap-2">
            <ClipboardList class="w-5 h-5" />
            {{ t('kanban.title') }}
          </h2>
          <div class="flex items-center gap-1">
            <button
              v-if="authStore.canManage('kanban')"
              class="p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
              :title="t('kanban.addProject')"
              @click="openProjectCreate"
            >
              <Plus class="w-4 h-4" />
            </button>
            <button
              class="hidden md:inline-flex p-2 rounded-lg border border-border text-muted-foreground hover:bg-secondary/50 transition-colors"
              :title="t('kanban.collapseSidebar')"
              @click="toggleSidebarCollapse"
            >
              <PanelLeftClose class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Board list -->
        <div class="flex-1 overflow-y-auto">
          <!-- Local tasks board -->
          <div
            class="px-3 py-2.5 cursor-pointer border-b border-border group hover:bg-secondary/50 transition-colors flex items-center gap-3"
            :class="{ 'bg-primary/10 border-l-2 border-l-primary': kanbanStore.selectedProjectId === null }"
            @click="selectProject(null)"
          >
            <div class="w-8 h-8 rounded-lg bg-secondary/50 flex items-center justify-center flex-shrink-0">
              <FolderOpen class="w-4 h-4 text-muted-foreground" />
            </div>
            <div class="min-w-0 flex-1">
              <div class="font-medium text-sm truncate">{{ t('kanban.localTasks') }}</div>
            </div>
          </div>

          <!-- GitHub project boards -->
          <div
            v-for="project in kanbanStore.projects"
            :key="project.id"
            class="px-3 py-2.5 cursor-pointer border-b border-border group hover:bg-secondary/50 transition-colors flex items-center gap-3"
            :class="{ 'bg-primary/10 border-l-2 border-l-primary': kanbanStore.selectedProjectId === project.id }"
            @click="selectProject(project.id)"
          >
            <div class="w-8 h-8 rounded-lg bg-secondary/50 flex items-center justify-center flex-shrink-0">
              <Github class="w-4 h-4 text-muted-foreground" />
            </div>
            <div class="min-w-0 flex-1">
              <div class="font-medium text-sm truncate">{{ project.name }}</div>
              <div class="text-xs text-muted-foreground truncate">
                {{ project.github_owner }}/{{ project.github_repo }}
              </div>
            </div>
            <button
              v-if="authStore.canManage('kanban')"
              class="p-1 rounded hover:bg-muted transition-colors text-muted-foreground opacity-0 group-hover:opacity-100 flex-shrink-0"
              :title="t('kanban.editProject')"
              @click.stop="openProjectEdit(project)"
            >
              <Settings class="w-3.5 h-3.5" />
            </button>
          </div>

          <!-- Empty state -->
          <div v-if="kanbanStore.projects.length === 0" class="p-4 text-center">
            <p class="text-xs text-muted-foreground">{{ t('kanban.emptyState') }}</p>
          </div>
        </div>
      </template>
    </div>

    <!-- Sidebar resize handle (desktop only) -->
    <div
      v-if="!sidebarCollapsed"
      class="hidden md:block w-1.5 cursor-col-resize hover:bg-primary/30 active:bg-primary/50 transition-colors flex-shrink-0"
      @mousedown="startSidebarResize"
      @touchstart="startSidebarTouchResize"
    />

    <!-- Mobile sidebar backdrop -->
    <div
      v-if="showSidebar"
      class="md:hidden fixed inset-0 bg-black/50 z-30"
      @click="showSidebar = false"
    />

    <!-- Mobile sidebar toggle -->
    <button
      class="md:hidden fixed left-4 bottom-24 z-50 p-3 bg-primary text-primary-foreground rounded-full shadow-lg"
      @click="showSidebar = !showSidebar"
    >
      <ChevronLeft :class="['w-5 h-5 transition-transform', showSidebar ? '' : 'rotate-180']" />
    </button>

    <!-- Main content area -->
    <div class="flex-1 flex flex-col overflow-hidden min-w-0">
      <!-- Compact header -->
      <div class="flex items-center justify-between px-4 py-3 border-b border-border bg-card">
        <div class="flex items-center gap-3 min-w-0">
          <div class="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center flex-shrink-0">
            <ClipboardList class="w-4 h-4 text-primary" />
          </div>
          <span class="font-semibold truncate">
            {{ kanbanStore.currentProject?.name || t('kanban.localTasks') }}
          </span>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <!-- Sync button (GitHub projects only) -->
          <button
            v-if="kanbanStore.currentProject && authStore.canEdit('kanban')"
            class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
            :disabled="kanbanStore.syncing"
            @click="handleSync"
          >
            <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': kanbanStore.syncing }" />
            <span class="hidden sm:inline">{{ t('kanban.syncGithub') }}</span>
          </button>

          <!-- Knowledge Base button (GitHub projects only) -->
          <template v-if="kanbanStore.currentProject && authStore.canEdit('kanban')">
            <button
              class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
              :disabled="datasetSyncing"
              :title="t('kanban.dataset.syncTooltip')"
              @click="handleDatasetSync"
            >
              <Database class="w-4 h-4" :class="{ 'animate-pulse': datasetSyncing }" />
              <span class="hidden sm:inline">{{ datasetSyncing ? t('kanban.dataset.syncing') : t('kanban.dataset.sync') }}</span>
            </button>
            <span
              v-if="datasetStatus?.synced"
              class="text-xs text-muted-foreground hidden lg:inline"
            >
              RAG: {{ datasetStatus.documents }} {{ t('kanban.dataset.files') }}
            </span>
          </template>

          <!-- View toggle -->
          <div class="flex rounded-lg border border-border overflow-hidden">
            <button
              class="flex items-center gap-1.5 px-2.5 py-1.5 text-sm font-medium transition-colors"
              :class="
                kanbanStore.activeView === 'kanban'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-card text-muted-foreground hover:bg-muted'
              "
              @click="kanbanStore.activeView = 'kanban'"
            >
              <LayoutGrid class="w-4 h-4" />
              <span class="hidden sm:inline">{{ t('kanban.viewKanban') }}</span>
            </button>
            <button
              class="flex items-center gap-1.5 px-2.5 py-1.5 text-sm font-medium transition-colors"
              :class="
                kanbanStore.activeView === 'roadmap'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-card text-muted-foreground hover:bg-muted'
              "
              @click="kanbanStore.activeView = 'roadmap'"
            >
              <ChartGantt class="w-4 h-4" />
              <span class="hidden sm:inline">{{ t('kanban.viewRoadmap') }}</span>
            </button>
          </div>

          <button
            class="p-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
            :disabled="kanbanStore.loading"
            @click="kanbanStore.fetchTasks()"
          >
            <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': kanbanStore.loading }" />
          </button>
        </div>
      </div>

      <!-- Board/Roadmap content -->
      <div class="flex-1 overflow-hidden p-4">
        <KanbanBoard
          v-if="kanbanStore.activeView === 'kanban'"
          :tasks-by-status="kanbanStore.tasksByStatus"
          :loading="kanbanStore.loading"
          :disabled="!authStore.canEdit('kanban')"
          :is-github-project="!!kanbanStore.currentProject"
          @reorder="handleReorder"
          @click-task="openDetail"
          @create-task="openCreate"
        />

        <KanbanRoadmap
          v-else
          :tasks="kanbanStore.ganttTasks"
          :loading="kanbanStore.loading"
          :disabled="!authStore.canEdit('kanban')"
          @click-task="handleGanttClick"
          @date-change="handleDateChange"
        />
      </div>
    </div>
  </div>

  <!-- Modals -->
  <KanbanTaskForm
    :visible="showForm"
    :task="editingTask"
    :initial-status="createStatus"
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
</template>
