import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { kanbanApi, type KanbanTask, type TaskCreateData, type TaskUpdateData } from '@/api'

export const useKanbanStore = defineStore('kanban', () => {
  const tasks = ref<KanbanTask[]>([])
  const loading = ref(false)
  const selectedTaskId = ref<number | null>(null)
  const statusFilter = ref<string>('all')
  const activeView = ref<'kanban' | 'roadmap'>('kanban')

  const filteredTasks = computed(() => {
    if (statusFilter.value === 'all') return tasks.value
    return tasks.value.filter((t) => t.status === statusFilter.value)
  })

  const tasksByStatus = computed(() => {
    const map: Record<string, KanbanTask[]> = {}
    const statuses = ['draft', 'todo', 'in_progress', 'review', 'done']
    for (const s of statuses) map[s] = []
    for (const t of tasks.value) {
      if (!map[t.status]) map[t.status] = []
      map[t.status].push(t)
    }
    for (const s of Object.keys(map)) {
      map[s].sort((a, b) => a.position - b.position)
    }
    return map
  })

  const ganttTasks = computed(() => {
    return tasks.value
      .filter((t) => t.start_date || t.due_date || t.created)
      .map((t) => {
        const start =
          t.start_date || t.created?.split('T')[0] || new Date().toISOString().split('T')[0]
        let end = t.due_date
        if (!end) {
          const d = new Date(start)
          d.setDate(d.getDate() + 7)
          end = d.toISOString().split('T')[0]
        }
        if (end < start) end = start

        const total = t.checklist.length
        const done = t.checklist.filter((c) => c.is_done).length
        const progress =
          total > 0 ? Math.round((done / total) * 100) : t.status === 'done' ? 100 : 0

        const STATUS_CLASS: Record<string, string> = {
          draft: 'gantt-bar-draft',
          todo: 'gantt-bar-todo',
          in_progress: 'gantt-bar-in-progress',
          review: 'gantt-bar-review',
          done: 'gantt-bar-done',
        }

        return {
          id: String(t.id),
          name: t.title,
          start,
          end,
          progress,
          dependencies: t.blockers.map(String).join(', '),
          custom_class: STATUS_CLASS[t.status] || '',
        }
      })
  })

  const selectedTask = computed(() =>
    selectedTaskId.value ? tasks.value.find((t) => t.id === selectedTaskId.value) || null : null
  )

  async function fetchTasks() {
    loading.value = true
    try {
      const res = await kanbanApi.getTasks()
      tasks.value = res.tasks
    } finally {
      loading.value = false
    }
  }

  async function createTask(data: TaskCreateData) {
    const res = await kanbanApi.createTask(data)
    tasks.value.push(res.task)
    return res.task
  }

  async function updateTask(id: number, data: TaskUpdateData) {
    const res = await kanbanApi.updateTask(id, data)
    const idx = tasks.value.findIndex((t) => t.id === id)
    if (idx !== -1) tasks.value[idx] = res.task
    return res.task
  }

  async function deleteTask(id: number) {
    await kanbanApi.deleteTask(id)
    tasks.value = tasks.value.filter((t) => t.id !== id)
    if (selectedTaskId.value === id) selectedTaskId.value = null
  }

  async function reorderTask(taskId: number, newStatus: string, newPosition: number) {
    const res = await kanbanApi.reorder(taskId, newStatus, newPosition)
    const idx = tasks.value.findIndex((t) => t.id === taskId)
    if (idx !== -1) tasks.value[idx] = res.task
    return res.task
  }

  async function addDependency(blockerId: number, dependentId: number) {
    await kanbanApi.addDependency(blockerId, dependentId)
    await fetchTasks()
  }

  async function removeDependency(blockerId: number, dependentId: number) {
    await kanbanApi.removeDependency(blockerId, dependentId)
    await fetchTasks()
  }

  async function addChecklistItem(taskId: number, text: string) {
    const res = await kanbanApi.addChecklistItem(taskId, text)
    const task = tasks.value.find((t) => t.id === taskId)
    if (task) task.checklist.push(res.item)
    return res.item
  }

  async function toggleChecklistItem(itemId: number) {
    const res = await kanbanApi.toggleChecklistItem(itemId)
    for (const task of tasks.value) {
      const item = task.checklist.find((c) => c.id === itemId)
      if (item) {
        item.is_done = res.item.is_done
        break
      }
    }
    return res.item
  }

  async function deleteChecklistItem(itemId: number) {
    await kanbanApi.deleteChecklistItem(itemId)
    for (const task of tasks.value) {
      const idx = task.checklist.findIndex((c) => c.id === itemId)
      if (idx !== -1) {
        task.checklist.splice(idx, 1)
        break
      }
    }
  }

  return {
    tasks,
    loading,
    selectedTaskId,
    statusFilter,
    activeView,
    filteredTasks,
    tasksByStatus,
    ganttTasks,
    selectedTask,
    fetchTasks,
    createTask,
    updateTask,
    deleteTask,
    reorderTask,
    addDependency,
    removeDependency,
    addChecklistItem,
    toggleChecklistItem,
    deleteChecklistItem,
  }
})
