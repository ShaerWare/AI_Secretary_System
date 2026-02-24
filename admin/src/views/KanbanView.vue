<script setup lang="ts">
import { ref, onMounted, defineAsyncComponent, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ClipboardList,
  Plus,
  RefreshCw,
  LayoutGrid,
  ChartGantt,
  Github,
  ChevronDown,
  ChevronLeft,
  FolderOpen,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-vue-next'
import { useKanbanStore } from '@/stores/kanban'
import { useAuthStore } from '@/stores/auth'
import { useConfirmStore } from '@/stores/confirm'
import { useToastStore } from '@/stores/toast'
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
const showDetail = ref(false)
const detailTask = ref<KanbanTask | null>(null)

// Project selector
const showProjectSelect = ref(false)
const showProjectForm = ref(false)
const editingProject = ref<(typeof kanbanStore.projects)[0] | null>(null)

// Sidebar
const { collapsed: sidebarCollapsed, toggle: toggleSidebarCollapse } = useSidebarCollapse('kanban-sidebar-collapsed')
const { width: sidebarWidth, startResize: startSidebarResize, startTouchResize: startSidebarTouchResize } = useResizablePanel('kanban-sidebar-width', 288, 220, 440, 'right')
const showSidebar = ref(true)

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-400',
  todo: 'bg-blue-400',
  in_progress: 'bg-yellow-400',
  review: 'bg-purple-400',
  done: 'bg-green-400',
}

const sortedTasks = computed(() => {
  return [...kanbanStore.tasks].sort((a, b) => {
    const statusOrder = ['in_progress', 'review', 'todo', 'draft', 'done']
    const ai = statusOrder.indexOf(a.status)
    const bi = statusOrder.indexOf(b.status)
    if (ai !== bi) return ai - bi
    return a.position - b.position
  })
})

function isOverdue(task: KanbanTask) {
  if (!task.due_date || task.status === 'done') return false
  return new Date(task.due_date) < new Date()
}

function formatDate(date: string) {
  return new Date(date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

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
  <div class="flex h-full">
    <!-- Sidebar: Task List -->
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
            v-if="authStore.canEdit('kanban')"
            class="p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            :title="t('kanban.create')"
            @click="openCreate"
          >
            <Plus class="w-4 h-4" />
          </button>
        </div>

        <!-- Collapsed items list -->
        <div class="hidden md:block flex-1 overflow-y-auto">
          <button
            v-for="task in sortedTasks"
            :key="task.id"
            :title="task.title"
            :class="[
              'w-full flex items-center justify-center py-2 transition-colors relative',
              detailTask?.id === task.id && showDetail
                ? 'bg-primary/10 border-l-2 border-l-primary'
                : 'hover:bg-secondary/50'
            ]"
            @click="openDetail(task)"
          >
            <div class="w-8 h-8 rounded-full border border-border flex items-center justify-center">
              <span class="w-2.5 h-2.5 rounded-full" :class="STATUS_COLORS[task.status] || 'bg-gray-400'" />
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
              v-if="authStore.canEdit('kanban')"
              class="p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
              :title="t('kanban.create')"
              @click="openCreate"
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

        <!-- Project selector -->
        <div class="p-3 border-b border-border">
          <div class="relative">
            <button
              class="flex items-center gap-2 w-full px-3 py-2 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
              @click="showProjectSelect = !showProjectSelect"
            >
              <Github v-if="kanbanStore.currentProject" class="w-4 h-4 flex-shrink-0" />
              <FolderOpen v-else class="w-4 h-4 flex-shrink-0" />
              <span class="truncate flex-1 text-left">
                {{ kanbanStore.currentProject?.name || t('kanban.localTasks') }}
              </span>
              <ChevronDown class="w-3 h-3 flex-shrink-0" />
            </button>
            <!-- Edit project button -->
            <button
              v-if="kanbanStore.currentProject && authStore.canManage('kanban')"
              class="absolute right-10 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-muted transition-colors text-muted-foreground"
              :title="t('kanban.editProject')"
              @click.stop="openProjectEdit"
            >
              <Settings class="w-3.5 h-3.5" />
            </button>
            <div
              v-if="showProjectSelect"
              class="absolute top-full left-0 right-0 mt-1 bg-card border border-border rounded-lg shadow-lg z-10"
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
              </button>
              <div v-if="authStore.canManage('kanban')" class="border-t border-border">
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
        </div>

        <!-- Task list -->
        <div class="flex-1 overflow-y-auto">
          <div v-if="kanbanStore.loading" class="p-4 text-center text-muted-foreground text-sm">
            {{ t('kanban.roadmap.noTasks') }}...
          </div>
          <div v-else-if="sortedTasks.length === 0" class="p-6 text-center">
            <ClipboardList class="w-10 h-10 mx-auto text-muted-foreground/30 mb-3" />
            <p class="text-sm text-muted-foreground mb-3">{{ t('kanban.emptyState') }}</p>
            <button
              v-if="authStore.canEdit('kanban')"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
              @click="openCreate"
            >
              <Plus class="w-4 h-4" />
              {{ t('kanban.create') }}
            </button>
          </div>
          <template v-else>
            <div
              v-for="task in sortedTasks"
              :key="task.id"
              class="px-3 py-2.5 cursor-pointer border-b border-border group hover:bg-secondary/50 transition-colors"
              :class="{ 'bg-primary/10 border-l-2 border-l-primary': detailTask?.id === task.id && showDetail }"
              @click="openDetail(task)"
            >
              <div class="flex items-center gap-2">
                <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" :class="STATUS_COLORS[task.status] || 'bg-gray-400'" />
                <span class="font-medium text-sm truncate flex-1">{{ task.title }}</span>
              </div>
              <div class="flex items-center gap-2 mt-1 text-xs text-muted-foreground pl-[18px]">
                <span v-if="task.assignee" class="truncate">{{ task.assignee }}</span>
                <span
                  v-if="task.due_date"
                  class="ml-auto flex-shrink-0"
                  :class="{ 'text-red-500 font-medium': isOverdue(task) }"
                >{{ formatDate(task.due_date) }}</span>
              </div>
            </div>
          </template>
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
          <span class="font-semibold truncate">{{ t('kanban.title') }}</span>
          <span v-if="kanbanStore.currentProject" class="text-sm text-muted-foreground truncate hidden sm:inline">
            / {{ kanbanStore.currentProject.name }}
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

  <!-- Click-away for project selector -->
  <Teleport to="body">
    <div
      v-if="showProjectSelect"
      class="fixed inset-0 z-[5]"
      @click="showProjectSelect = false"
    />
  </Teleport>
</template>
