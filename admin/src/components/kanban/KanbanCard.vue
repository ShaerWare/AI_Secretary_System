<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Link, User, Calendar, CheckSquare } from 'lucide-vue-next'
import type { KanbanTask } from '@/api'

const props = defineProps<{
  task: KanbanTask
  disabled?: boolean
}>()

const emit = defineEmits<{
  click: [task: KanbanTask]
}>()

const { t } = useI18n()

const visibleTags = computed(() => props.task.tags.slice(0, 2))
const overflowTagCount = computed(() => Math.max(0, props.task.tags.length - 2))

const checklistDone = computed(() => props.task.checklist.filter((c) => c.is_done).length)
const checklistTotal = computed(() => props.task.checklist.length)
const checklistPercent = computed(() =>
  checklistTotal.value > 0 ? Math.round((checklistDone.value / checklistTotal.value) * 100) : 0
)

const isOverdue = computed(() => {
  if (!props.task.due_date) return false
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return new Date(props.task.due_date) < today && props.task.status !== 'done'
})

</script>

<template>
  <div
    class="kanban-card bg-card border rounded-lg p-3 hover:shadow-md transition-shadow"
    :class="[
      disabled ? 'cursor-default' : 'cursor-grab active:cursor-grabbing',
      task.is_private ? 'border-dashed border-muted-foreground/40' : 'border-border',
    ]"
    @click="emit('click', task)"
  >
    <!-- Title row -->
    <div class="flex items-start gap-2">
      <span class="font-medium text-sm truncate flex-1">{{ task.title }}</span>
      <Link
        v-if="task.blockers.length > 0"
        class="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground mt-0.5"
        :title="t('kanban.dependencies')"
      />
    </div>

    <!-- Tags -->
    <div v-if="task.tags.length > 0" class="flex flex-wrap gap-1 mt-2">
      <span
        v-for="tag in visibleTags"
        :key="tag"
        class="px-1.5 py-0.5 text-[10px] rounded-full bg-muted text-muted-foreground"
      >
        {{ tag }}
      </span>
      <span
        v-if="overflowTagCount > 0"
        class="px-1.5 py-0.5 text-[10px] rounded-full bg-muted text-muted-foreground"
      >
        +{{ overflowTagCount }}
      </span>
    </div>

    <!-- Assignee + Due date row -->
    <div
      v-if="task.assignee || task.due_date"
      class="flex items-center gap-3 mt-2 text-xs text-muted-foreground"
    >
      <div v-if="task.assignee" class="flex items-center gap-1 min-w-0">
        <User class="w-3 h-3 flex-shrink-0" />
        <span class="truncate">{{ task.assignee }}</span>
      </div>
      <div class="flex-1" />
      <div
        v-if="task.due_date"
        class="flex items-center gap-1 flex-shrink-0"
        :class="isOverdue ? 'text-destructive' : ''"
        :title="isOverdue ? t('kanban.overdue') : ''"
      >
        <Calendar class="w-3 h-3" />
        <span>{{ task.due_date }}</span>
      </div>
    </div>

    <!-- Checklist progress -->
    <div v-if="checklistTotal > 0" class="flex items-center gap-2 mt-2">
      <CheckSquare class="w-3 h-3 text-muted-foreground flex-shrink-0" />
      <span class="text-xs text-muted-foreground">{{ checklistDone }}/{{ checklistTotal }}</span>
      <div class="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          class="h-full rounded-full transition-all"
          :class="checklistPercent === 100 ? 'bg-emerald-500' : 'bg-primary'"
          :style="{ width: checklistPercent + '%' }"
        />
      </div>
    </div>
  </div>
</template>
