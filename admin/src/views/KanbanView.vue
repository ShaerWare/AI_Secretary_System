<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ClipboardList,
  Plus,
  RefreshCw,
  Loader2,
  Calendar,
  User,
  Pencil,
} from 'lucide-vue-next'
import { useKanbanStore } from '@/stores/kanban'
import { useConfirmStore } from '@/stores/confirm'
import { useToastStore } from '@/stores/toast'
import type { KanbanTask, TaskCreateData, TaskUpdateData } from '@/api'
import KanbanStatusBadge from '@/components/kanban/KanbanStatusBadge.vue'
import KanbanTaskForm from '@/components/kanban/KanbanTaskForm.vue'
import KanbanCardDetail from '@/components/kanban/KanbanCardDetail.vue'

const { t } = useI18n()
const kanbanStore = useKanbanStore()
const confirmStore = useConfirmStore()
const toast = useToastStore()

const statuses = ['all', 'draft', 'todo', 'in_progress', 'review', 'done']

const showForm = ref(false)
const editingTask = ref<KanbanTask | null>(null)
const showDetail = ref(false)
const detailTask = ref<KanbanTask | null>(null)

const statusCounts = computed(() => {
  const counts: Record<string, number> = { all: kanbanStore.tasks.length }
  for (const t of kanbanStore.tasks) {
    counts[t.status] = (counts[t.status] || 0) + 1
  }
  return counts
})

onMounted(() => {
  kanbanStore.fetchTasks()
})

function openCreate() {
  editingTask.value = null
  showForm.value = true
}

function openEdit(task: KanbanTask) {
  editingTask.value = task
  showForm.value = true
}

function openDetail(task: KanbanTask) {
  detailTask.value = task
  showDetail.value = true
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
    // Refresh detail task reference
    detailTask.value = kanbanStore.tasks.find((t) => t.id === id) || null
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function handleDelete(id: number) {
  const confirmed = await confirmStore.confirmDelete(
    kanbanStore.tasks.find((t) => t.id === id)?.title || '',
    t('kanban.task')
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
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
          <ClipboardList class="w-5 h-5 text-primary" />
        </div>
        <div>
          <h1 class="text-2xl font-bold">{{ t('kanban.title') }}</h1>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="p-2 rounded-lg border border-border hover:bg-muted transition-colors"
          :disabled="kanbanStore.loading"
          @click="kanbanStore.fetchTasks()"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': kanbanStore.loading }" />
        </button>
        <button
          class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          @click="openCreate"
        >
          <Plus class="w-4 h-4" />
          {{ t('kanban.create') }}
        </button>
      </div>
    </div>

    <!-- Filter chips -->
    <div class="flex flex-wrap gap-2">
      <button
        v-for="s in statuses"
        :key="s"
        class="px-3 py-1.5 text-sm rounded-full border transition-colors"
        :class="
          kanbanStore.statusFilter === s
            ? 'bg-primary text-primary-foreground border-primary'
            : 'border-border hover:bg-muted'
        "
        @click="kanbanStore.statusFilter = s"
      >
        {{ s === 'all' ? t('kanban.all') : t(`kanban.status.${s}`) }}
        <span class="ml-1 opacity-70">({{ statusCounts[s] || 0 }})</span>
      </button>
    </div>

    <!-- Loading -->
    <div v-if="kanbanStore.loading && !kanbanStore.tasks.length" class="flex justify-center py-12">
      <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!kanbanStore.filteredTasks.length"
      class="text-center py-12 text-muted-foreground"
    >
      <ClipboardList class="w-12 h-12 mx-auto mb-3 opacity-50" />
      <p>{{ t('kanban.emptyState') }}</p>
    </div>

    <!-- Table -->
    <div v-else class="bg-card border border-border rounded-xl overflow-hidden">
      <table class="w-full">
        <thead>
          <tr class="border-b border-border bg-muted/50">
            <th class="text-left px-4 py-3 text-sm font-medium">{{ t('kanban.taskTitle') }}</th>
            <th class="text-left px-4 py-3 text-sm font-medium w-32">
              {{ t('kanban.statusLabel') }}
            </th>
            <th class="text-left px-4 py-3 text-sm font-medium w-36">
              {{ t('kanban.assignee') }}
            </th>
            <th class="text-left px-4 py-3 text-sm font-medium w-32">
              {{ t('kanban.dueDate') }}
            </th>
            <th class="text-left px-4 py-3 text-sm font-medium w-36">
              {{ t('kanban.createdBy') }}
            </th>
            <th class="w-16"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="task in kanbanStore.filteredTasks"
            :key="task.id"
            class="border-b border-border last:border-0 hover:bg-muted/30 transition-colors cursor-pointer"
            @click="openDetail(task)"
          >
            <td class="px-4 py-3">
              <div class="font-medium">{{ task.title }}</div>
              <div v-if="task.tags && task.tags.length" class="flex flex-wrap gap-1 mt-1">
                <span
                  v-for="tag in task.tags"
                  :key="tag"
                  class="px-1.5 py-0.5 text-[10px] rounded-full bg-muted text-muted-foreground"
                >
                  {{ tag }}
                </span>
              </div>
            </td>
            <td class="px-4 py-3">
              <KanbanStatusBadge :status="task.status" />
            </td>
            <td class="px-4 py-3 text-sm text-muted-foreground">
              <div v-if="task.assignee" class="flex items-center gap-1">
                <User class="w-3.5 h-3.5" />
                {{ task.assignee }}
              </div>
              <span v-else class="opacity-40">-</span>
            </td>
            <td class="px-4 py-3 text-sm text-muted-foreground">
              <div v-if="task.due_date" class="flex items-center gap-1">
                <Calendar class="w-3.5 h-3.5" />
                {{ task.due_date }}
              </div>
              <span v-else class="opacity-40">-</span>
            </td>
            <td class="px-4 py-3 text-sm text-muted-foreground">
              {{ task.created_by }}
            </td>
            <td class="px-4 py-3">
              <button
                class="p-1.5 rounded-lg hover:bg-muted transition-colors"
                @click.stop="openEdit(task)"
              >
                <Pencil class="w-4 h-4 text-muted-foreground" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
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
      @close="showDetail = false"
      @update="handleDetailUpdate"
      @delete="handleDelete"
      @add-checklist="handleAddChecklist"
      @toggle-checklist="handleToggleChecklist"
      @delete-checklist="handleDeleteChecklist"
      @add-dependency="handleAddDependency"
      @remove-dependency="handleRemoveDependency"
    />
  </div>
</template>
