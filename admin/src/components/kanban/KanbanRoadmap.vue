<script setup lang="ts">
import { ref, watch, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import Gantt from 'frappe-gantt'
// CSS imported in main.css to avoid exports resolution issues
import type { GanttTask } from 'frappe-gantt'

const props = defineProps<{
  tasks: GanttTask[]
  loading: boolean
  disabled: boolean
}>()

const emit = defineEmits<{
  clickTask: [taskId: number]
  dateChange: [taskId: number, startDate: string, endDate: string]
}>()

const { t } = useI18n()
const containerRef = ref<HTMLElement | null>(null)
const viewMode = ref<'Day' | 'Week' | 'Month'>('Week')

let ganttInstance: Gantt | null = null

function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function initGantt() {
  if (!containerRef.value || props.tasks.length === 0) return

  containerRef.value.innerHTML = ''

  ganttInstance = new Gantt(containerRef.value, props.tasks, {
    view_mode: viewMode.value,
    date_format: 'YYYY-MM-DD',
    readonly: props.disabled,
    on_click: (task: GanttTask) => {
      emit('clickTask', Number(task.id))
    },
    on_date_change: (task: GanttTask, start: Date, end: Date) => {
      if (props.disabled) return
      emit('dateChange', Number(task.id), formatDate(start), formatDate(end))
    },
    custom_popup_html: (task: GanttTask) => {
      return `
        <div class="gantt-popup">
          <div class="gantt-popup-title">${task.name}</div>
          <div class="gantt-popup-dates">${task.start} &mdash; ${task.end}</div>
          <div class="gantt-popup-progress">${t('kanban.roadmap.progress')}: ${task.progress}%</div>
        </div>
      `
    },
  })
}

onMounted(() => {
  nextTick(() => {
    if (props.tasks.length > 0) initGantt()
  })
})

onBeforeUnmount(() => {
  ganttInstance = null
})

watch(
  () => props.tasks,
  (newTasks) => {
    if (newTasks.length === 0) {
      if (containerRef.value) containerRef.value.innerHTML = ''
      ganttInstance = null
      return
    }
    if (ganttInstance) {
      ganttInstance.refresh(newTasks)
    } else {
      nextTick(() => initGantt())
    }
  },
  { deep: true },
)

watch(viewMode, (mode) => {
  if (ganttInstance) {
    ganttInstance.change_view_mode(mode)
  }
})

watch(
  () => props.disabled,
  () => {
    nextTick(() => initGantt())
  },
)
</script>

<template>
  <div class="space-y-3">
    <!-- View mode toggle -->
    <div class="flex items-center justify-between">
      <div class="flex rounded-lg border border-border overflow-hidden">
        <button
          v-for="mode in (['Day', 'Week', 'Month'] as const)"
          :key="mode"
          class="px-3 py-1.5 text-sm font-medium transition-colors"
          :class="
            viewMode === mode
              ? 'bg-primary text-primary-foreground'
              : 'bg-card text-muted-foreground hover:bg-muted'
          "
          @click="viewMode = mode"
        >
          {{ t(`kanban.roadmap.${mode.toLowerCase()}`) }}
        </button>
      </div>
    </div>

    <!-- Gantt container -->
    <div
      v-if="tasks.length > 0"
      ref="containerRef"
      class="gantt-container rounded-lg border border-border overflow-auto"
    />

    <!-- Empty state -->
    <div
      v-else-if="!loading"
      class="flex flex-col items-center justify-center py-16 text-muted-foreground"
    >
      <p class="text-lg">{{ t('kanban.roadmap.noTasks') }}</p>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex items-center justify-center py-16">
      <div class="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full" />
    </div>
  </div>
</template>

<style scoped>
.gantt-container {
  height: calc(100vh - 14rem);
  min-height: 400px;
}
</style>
