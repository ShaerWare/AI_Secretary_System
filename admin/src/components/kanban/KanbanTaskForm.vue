<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from 'lucide-vue-next'
import type { KanbanTask, TaskCreateData, TaskUpdateData } from '@/api'

const props = defineProps<{
  visible: boolean
  task?: KanbanTask | null
  initialStatus?: string
}>()

const emit = defineEmits<{
  close: []
  create: [data: TaskCreateData]
  update: [id: number, data: TaskUpdateData]
}>()

const { t } = useI18n()

const title = ref('')
const description = ref('')
const assignee = ref('')
const startDate = ref('')
const dueDate = ref('')
const tagsInput = ref('')

const isEdit = ref(false)

watch(
  () => props.visible,
  (val) => {
    if (val && props.task) {
      isEdit.value = true
      title.value = props.task.title
      description.value = props.task.description || ''
      assignee.value = props.task.assignee || ''
      startDate.value = props.task.start_date || ''
      dueDate.value = props.task.due_date || ''
      tagsInput.value = (props.task.tags || []).join(', ')
    } else if (val) {
      isEdit.value = false
      title.value = ''
      description.value = ''
      assignee.value = ''
      startDate.value = ''
      dueDate.value = ''
      tagsInput.value = ''
    }
  }
)

function handleSubmit() {
  const tags = tagsInput.value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)

  if (isEdit.value && props.task) {
    const data: TaskUpdateData = {}
    if (title.value !== props.task.title) data.title = title.value
    if (description.value !== (props.task.description || '')) data.description = description.value
    if (assignee.value !== (props.task.assignee || '')) data.assignee = assignee.value
    if (startDate.value !== (props.task.start_date || '')) data.start_date = startDate.value
    if (dueDate.value !== (props.task.due_date || '')) data.due_date = dueDate.value
    data.tags = tags
    emit('update', props.task.id, data)
  } else {
    const data: TaskCreateData = { title: title.value }
    if (props.initialStatus) data.status = props.initialStatus
    if (description.value) data.description = description.value
    if (assignee.value) data.assignee = assignee.value
    if (startDate.value) data.start_date = startDate.value
    if (dueDate.value) data.due_date = dueDate.value
    if (tags.length) data.tags = tags
    emit('create', data)
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="fixed inset-0 bg-black/50" @click="emit('close')" />
      <div class="relative bg-card border border-border rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between p-4 border-b border-border">
          <h3 class="text-lg font-semibold">
            {{ isEdit ? t('kanban.edit') : t('kanban.create') }}
          </h3>
          <button
            class="p-1 rounded-lg hover:bg-muted transition-colors"
            @click="emit('close')"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <form class="p-4 space-y-4" @submit.prevent="handleSubmit">
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('kanban.taskTitle') }}</label>
            <input
              v-model="title"
              type="text"
              required
              class="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              :placeholder="t('kanban.taskTitlePlaceholder')"
            />
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">{{ t('kanban.description') }}</label>
            <textarea
              v-model="description"
              rows="3"
              class="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
            />
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('kanban.assignee') }}</label>
              <input
                v-model="assignee"
                type="text"
                class="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('kanban.tags') }}</label>
              <input
                v-model="tagsInput"
                type="text"
                class="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                :placeholder="t('kanban.tagsPlaceholder')"
              />
            </div>
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('kanban.startDate') }}</label>
              <input
                v-model="startDate"
                type="date"
                class="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('kanban.dueDate') }}</label>
              <input
                v-model="dueDate"
                type="date"
                class="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>

          <div class="flex justify-end gap-3 pt-2">
            <button
              type="button"
              class="px-4 py-2 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
              @click="emit('close')"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              type="submit"
              :disabled="!title.trim()"
              class="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {{ isEdit ? t('common.save') : t('kanban.create') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>
