<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  X,
  Trash2,
  Plus,
  CheckSquare,
  Square,
  Link,
  Unlink,
  Calendar,
  User,
  ExternalLink,
  Terminal,
} from 'lucide-vue-next'
import type { KanbanTask, KanbanProject } from '@/api'
import { kanbanApi } from '@/api/kanban'
import type { CcSessionSummary } from '@/api/claudeCode'
import { useAuthStore } from '@/stores/auth'
import KanbanStatusBadge from './KanbanStatusBadge.vue'

const props = defineProps<{
  visible: boolean
  task: KanbanTask | null
  allTasks: KanbanTask[]
  currentProject?: KanbanProject | null
}>()

const emit = defineEmits<{
  close: []
  update: [id: number, data: Record<string, unknown>]
  delete: [id: number]
  addChecklist: [taskId: number, text: string]
  toggleChecklist: [itemId: number]
  deleteChecklist: [itemId: number]
  addDependency: [blockerId: number, dependentId: number]
  removeDependency: [blockerId: number, dependentId: number]
}>()

const { t } = useI18n()
const authStore = useAuthStore()

const statuses = ['draft', 'todo', 'in_progress', 'review', 'done']

const newChecklistText = ref('')
const showAddDependency = ref(false)
const selectedDependencyId = ref<number | null>(null)

const isAdmin = computed(() => authStore.canManage('kanban'))

const githubIssueUrl = computed(() => {
  if (!props.task?.github_issue_number || !props.currentProject) return null
  return `https://github.com/${props.currentProject.github_owner}/${props.currentProject.github_repo}/issues/${props.task.github_issue_number}`
})

const availableBlockers = computed(() => {
  if (!props.task) return []
  return props.allTasks.filter(
    (t) =>
      t.id !== props.task!.id &&
      !props.task!.blockers.includes(t.id) &&
      !t.is_private
  )
})

function handleStatusChange(e: Event) {
  const status = (e.target as HTMLSelectElement).value
  if (props.task) {
    emit('update', props.task.id, { status })
  }
}

function handleAddChecklist() {
  if (!newChecklistText.value.trim() || !props.task) return
  emit('addChecklist', props.task.id, newChecklistText.value.trim())
  newChecklistText.value = ''
}

function handleAddDependency() {
  if (!selectedDependencyId.value || !props.task) return
  emit('addDependency', selectedDependencyId.value, props.task.id)
  selectedDependencyId.value = null
  showAddDependency.value = false
}

function getTaskTitle(id: number): string {
  const task = props.allTasks.find((t) => t.id === id)
  return task ? task.title : `#${id}`
}

// CC sessions linked to this task
const ccSessions = ref<CcSessionSummary[]>([])

watch(
  () => props.task?.id,
  async (taskId) => {
    ccSessions.value = []
    if (!taskId) return
    try {
      const result = await kanbanApi.getTaskCcSessions(taskId)
      ccSessions.value = result.sessions
    } catch { /* ignore */ }
  },
  { immediate: true }
)

function ccStatusColor(status: string): string {
  switch (status) {
    case 'active': return 'bg-green-500/20 text-green-400'
    case 'completed': return 'bg-blue-500/20 text-blue-400'
    case 'error': return 'bg-red-500/20 text-red-400'
    case 'aborted': return 'bg-yellow-500/20 text-yellow-400'
    default: return 'bg-muted text-muted-foreground'
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible && task" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="fixed inset-0 bg-black/50" @click="emit('close')" />
      <div
        class="relative bg-card border border-border rounded-xl shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto"
      >
        <!-- Header -->
        <div class="flex items-center justify-between p-4 border-b border-border">
          <div class="flex items-center gap-3 min-w-0">
            <h3 class="text-lg font-semibold truncate">{{ task.title }}</h3>
            <KanbanStatusBadge :status="task.status" />
          </div>
          <div class="flex items-center gap-1 flex-shrink-0">
            <a
              v-if="githubIssueUrl"
              :href="githubIssueUrl"
              target="_blank"
              rel="noopener"
              class="p-1 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
              :title="t('kanban.viewOnGithub')"
            >
              <ExternalLink class="w-5 h-5" />
            </a>
            <button
              class="p-1 rounded-lg hover:bg-muted transition-colors"
              @click="emit('close')"
            >
              <X class="w-5 h-5" />
            </button>
          </div>
        </div>

        <div class="p-4 space-y-6">
          <!-- Status -->
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('kanban.statusLabel') }}</label>
            <select
              :value="task.status"
              class="px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              @change="handleStatusChange"
            >
              <option v-for="s in statuses" :key="s" :value="s">
                {{ t(`kanban.status.${s}`) }}
              </option>
            </select>
          </div>

          <!-- Description -->
          <div v-if="task.description">
            <label class="block text-sm font-medium mb-1">{{ t('kanban.description') }}</label>
            <p class="text-sm text-muted-foreground whitespace-pre-wrap">{{ task.description }}</p>
          </div>

          <!-- Meta -->
          <div class="grid grid-cols-2 gap-4 text-sm">
            <div v-if="task.assignee" class="flex items-center gap-2 text-muted-foreground">
              <User class="w-4 h-4" />
              <span>{{ task.assignee }}</span>
            </div>
            <div class="flex items-center gap-2 text-muted-foreground">
              <User class="w-4 h-4" />
              <span>{{ t('kanban.createdBy') }}: {{ task.created_by }}</span>
            </div>
            <div v-if="task.start_date" class="flex items-center gap-2 text-muted-foreground">
              <Calendar class="w-4 h-4" />
              <span>{{ t('kanban.startDate') }}: {{ task.start_date }}</span>
            </div>
            <div v-if="task.due_date" class="flex items-center gap-2 text-muted-foreground">
              <Calendar class="w-4 h-4" />
              <span>{{ t('kanban.dueDate') }}: {{ task.due_date }}</span>
            </div>
          </div>

          <!-- Tags -->
          <div v-if="task.tags && task.tags.length" class="flex flex-wrap gap-1.5">
            <span
              v-for="tag in task.tags"
              :key="tag"
              class="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground"
            >
              {{ tag }}
            </span>
          </div>

          <!-- Checklist -->
          <div>
            <h4 class="text-sm font-medium mb-2">{{ t('kanban.checklist') }}</h4>
            <div class="space-y-1">
              <div
                v-for="item in task.checklist"
                :key="item.id"
                class="flex items-center gap-2 group"
              >
                <button
                  class="flex-shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                  @click="emit('toggleChecklist', item.id)"
                >
                  <CheckSquare v-if="item.is_done" class="w-4 h-4 text-emerald-500" />
                  <Square v-else class="w-4 h-4" />
                </button>
                <span
                  class="text-sm flex-1"
                  :class="{ 'line-through text-muted-foreground': item.is_done }"
                >
                  {{ item.text }}
                </span>
                <button
                  class="opacity-0 group-hover:opacity-100 p-0.5 text-muted-foreground hover:text-destructive transition-all"
                  @click="emit('deleteChecklist', item.id)"
                >
                  <Trash2 class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            <div class="flex gap-2 mt-2">
              <input
                v-model="newChecklistText"
                type="text"
                class="flex-1 px-3 py-1.5 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                :placeholder="t('kanban.checklistPlaceholder')"
                @keydown.enter.prevent="handleAddChecklist"
              />
              <button
                class="px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                :disabled="!newChecklistText.trim()"
                @click="handleAddChecklist"
              >
                <Plus class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Dependencies -->
          <div>
            <h4 class="text-sm font-medium mb-2">{{ t('kanban.dependencies') }}</h4>
            <div v-if="task.blockers.length" class="space-y-1 mb-2">
              <div
                v-for="blockerId in task.blockers"
                :key="blockerId"
                class="flex items-center gap-2 text-sm group"
              >
                <Link class="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <span class="flex-1 truncate">{{ getTaskTitle(blockerId) }}</span>
                <button
                  class="opacity-0 group-hover:opacity-100 p-0.5 text-muted-foreground hover:text-destructive transition-all"
                  @click="emit('removeDependency', blockerId, task.id)"
                >
                  <Unlink class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            <p v-else class="text-sm text-muted-foreground mb-2">
              {{ t('kanban.noDependencies') }}
            </p>

            <div v-if="showAddDependency" class="flex gap-2">
              <select
                v-model="selectedDependencyId"
                class="flex-1 px-3 py-1.5 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option :value="null" disabled>{{ t('kanban.selectBlocker') }}</option>
                <option v-for="opt in availableBlockers" :key="opt.id" :value="opt.id">
                  {{ opt.title }}
                </option>
              </select>
              <button
                class="px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                :disabled="!selectedDependencyId"
                @click="handleAddDependency"
              >
                <Plus class="w-4 h-4" />
              </button>
              <button
                class="px-3 py-1.5 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
                @click="showAddDependency = false"
              >
                <X class="w-4 h-4" />
              </button>
            </div>
            <button
              v-else
              class="text-sm text-primary hover:underline"
              @click="showAddDependency = true"
            >
              {{ t('kanban.addDependency') }}
            </button>
          </div>

          <!-- Claude Code Sessions -->
          <div v-if="ccSessions.length" class="pt-2 border-t border-border">
            <h4 class="text-sm font-medium mb-2 flex items-center gap-1.5">
              <Terminal class="w-4 h-4 text-green-500" />
              Claude Code Sessions
            </h4>
            <div class="space-y-1">
              <div
                v-for="ccS in ccSessions"
                :key="ccS.id"
                class="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-secondary/50 text-sm"
              >
                <Terminal class="w-3.5 h-3.5 text-green-500 shrink-0" />
                <span class="truncate flex-1">{{ ccS.title }}</span>
                <span class="text-[10px] text-muted-foreground">{{ ccS.total_turns }}t</span>
                <span :class="['text-[10px] px-1.5 py-0.5 rounded-full', ccStatusColor(ccS.status)]">{{ ccS.status }}</span>
              </div>
            </div>
          </div>

          <!-- Delete button (admin only) -->
          <div v-if="isAdmin" class="pt-2 border-t border-border">
            <button
              class="flex items-center gap-2 px-4 py-2 text-sm text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
              @click="emit('delete', task.id)"
            >
              <Trash2 class="w-4 h-4" />
              {{ t('kanban.delete') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
