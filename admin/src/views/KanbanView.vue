<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ClipboardList, Plus, RefreshCw } from 'lucide-vue-next'
import { useKanbanStore } from '@/stores/kanban'
import { useAuthStore } from '@/stores/auth'
import { useConfirmStore } from '@/stores/confirm'
import { useToastStore } from '@/stores/toast'
import type { KanbanTask, TaskCreateData, TaskUpdateData } from '@/api'
import KanbanBoard from '@/components/kanban/KanbanBoard.vue'
import KanbanTaskForm from '@/components/kanban/KanbanTaskForm.vue'
import KanbanCardDetail from '@/components/kanban/KanbanCardDetail.vue'

const { t } = useI18n()
const kanbanStore = useKanbanStore()
const authStore = useAuthStore()
const confirmStore = useConfirmStore()
const toast = useToastStore()

const showForm = ref(false)
const editingTask = ref<KanbanTask | null>(null)
const showDetail = ref(false)
const detailTask = ref<KanbanTask | null>(null)

onMounted(() => {
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
      :tasks-by-status="kanbanStore.tasksByStatus"
      :loading="kanbanStore.loading"
      :disabled="authStore.isGuest"
      @reorder="handleReorder"
      @click-task="openDetail"
      @create-task="openCreate"
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
