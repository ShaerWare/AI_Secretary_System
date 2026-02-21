import type { DemoRoute } from './types'

interface MockChecklistItem {
  id: number
  task_id: number
  text: string
  is_done: boolean
  position: number
}

interface MockTask {
  id: number
  title: string
  description: string | null
  status: string
  is_private: boolean
  assignee: string | null
  created_by: string
  start_date: string | null
  due_date: string | null
  position: number
  tags: string[]
  checklist: MockChecklistItem[]
  blockers: number[]
  dependents: number[]
  created: string
  updated: string
}

let nextId = 10
const tasks: MockTask[] = [
  {
    id: 1,
    title: 'Настроить интеграцию с Telegram',
    description: 'Подключить бота к Telegram API и настроить вебхуки',
    status: 'done',
    is_private: false,
    assignee: 'admin',
    created_by: 'admin',
    start_date: '2026-01-10',
    due_date: '2026-01-20',
    position: 0,
    tags: ['интеграция', 'telegram'],
    checklist: [
      { id: 1, task_id: 1, text: 'Получить токен бота', is_done: true, position: 0 },
      { id: 2, task_id: 1, text: 'Настроить вебхук', is_done: true, position: 1 },
    ],
    blockers: [],
    dependents: [2],
    created: '2026-01-10T10:00:00',
    updated: '2026-01-20T15:30:00',
  },
  {
    id: 2,
    title: 'Тестирование Telegram-бота',
    description: 'Провести полное тестирование бота в Telegram',
    status: 'in_progress',
    is_private: false,
    assignee: 'admin',
    created_by: 'admin',
    start_date: '2026-01-21',
    due_date: '2026-02-01',
    position: 0,
    tags: ['тестирование'],
    checklist: [
      { id: 3, task_id: 2, text: 'Тест отправки сообщений', is_done: true, position: 0 },
      { id: 4, task_id: 2, text: 'Тест голосовых сообщений', is_done: false, position: 1 },
    ],
    blockers: [1],
    dependents: [],
    created: '2026-01-21T09:00:00',
    updated: '2026-01-25T12:00:00',
  },
  {
    id: 3,
    title: 'Добавить FAQ раздел',
    description: 'Создать базу часто задаваемых вопросов для бота',
    status: 'todo',
    is_private: false,
    assignee: null,
    created_by: 'admin',
    start_date: null,
    due_date: '2026-02-15',
    position: 0,
    tags: ['контент', 'faq'],
    checklist: [],
    blockers: [],
    dependents: [],
    created: '2026-01-15T14:00:00',
    updated: '2026-01-15T14:00:00',
  },
  {
    id: 4,
    title: 'Настроить виджет на сайте',
    description: 'Установить чат-виджет на основной сайт компании',
    status: 'review',
    is_private: false,
    assignee: 'admin',
    created_by: 'admin',
    start_date: '2026-02-01',
    due_date: '2026-02-10',
    position: 0,
    tags: ['виджет', 'сайт'],
    checklist: [
      { id: 5, task_id: 4, text: 'Сгенерировать код виджета', is_done: true, position: 0 },
      { id: 6, task_id: 4, text: 'Встроить на сайт', is_done: true, position: 1 },
      { id: 7, task_id: 4, text: 'Проверить на мобильных', is_done: false, position: 2 },
    ],
    blockers: [],
    dependents: [],
    created: '2026-02-01T08:00:00',
    updated: '2026-02-08T16:00:00',
  },
  {
    id: 5,
    title: 'Обновить модель LLM',
    description: null,
    status: 'draft',
    is_private: true,
    assignee: null,
    created_by: 'admin',
    start_date: null,
    due_date: null,
    position: 0,
    tags: [],
    checklist: [],
    blockers: [],
    dependents: [],
    created: '2026-02-10T11:00:00',
    updated: '2026-02-10T11:00:00',
  },
  {
    id: 6,
    title: 'Подготовить документацию',
    description: 'Написать пользовательскую документацию для админ-панели',
    status: 'todo',
    is_private: false,
    assignee: 'admin',
    created_by: 'admin',
    start_date: '2026-02-15',
    due_date: '2026-03-01',
    position: 1,
    tags: ['документация'],
    checklist: [],
    blockers: [],
    dependents: [],
    created: '2026-02-12T10:00:00',
    updated: '2026-02-12T10:00:00',
  },
  {
    id: 7,
    title: 'Настроить WhatsApp канал',
    description: 'Подключить WhatsApp Business API',
    status: 'in_progress',
    is_private: false,
    assignee: 'admin',
    created_by: 'admin',
    start_date: '2026-02-10',
    due_date: '2026-02-20',
    position: 1,
    tags: ['интеграция', 'whatsapp'],
    checklist: [
      { id: 8, task_id: 7, text: 'Зарегистрировать бизнес-аккаунт', is_done: true, position: 0 },
      { id: 9, task_id: 7, text: 'Настроить API-ключи', is_done: true, position: 1 },
      { id: 10, task_id: 7, text: 'Тестовая отправка', is_done: false, position: 2 },
      { id: 11, task_id: 7, text: 'Обработка входящих', is_done: false, position: 3 },
    ],
    blockers: [],
    dependents: [],
    created: '2026-02-10T09:00:00',
    updated: '2026-02-18T14:00:00',
  },
  {
    id: 8,
    title: 'Добавить аналитику разговоров',
    description: 'Дашборд со статистикой по чатам',
    status: 'draft',
    is_private: true,
    assignee: null,
    created_by: 'admin',
    start_date: null,
    due_date: null,
    position: 1,
    tags: ['аналитика'],
    checklist: [],
    blockers: [],
    dependents: [],
    created: '2026-02-15T10:00:00',
    updated: '2026-02-15T10:00:00',
  },
  {
    id: 9,
    title: 'Проверить SSL-сертификаты',
    description: 'Убедиться что все сертификаты актуальны',
    status: 'done',
    is_private: false,
    assignee: 'admin',
    created_by: 'admin',
    start_date: '2026-01-05',
    due_date: '2026-01-07',
    position: 1,
    tags: ['безопасность'],
    checklist: [],
    blockers: [],
    dependents: [],
    created: '2026-01-05T08:00:00',
    updated: '2026-01-07T11:00:00',
  },
]

let nextChecklistId = 12

export const kanbanRoutes: DemoRoute[] = [
  // GET /admin/kanban/tasks
  {
    method: 'GET',
    pattern: /^\/admin\/kanban\/tasks$/,
    handler: () => ({ tasks }),
  },
  // POST /admin/kanban/tasks
  {
    method: 'POST',
    pattern: /^\/admin\/kanban\/tasks$/,
    handler: ({ body }) => {
      const b = body as Record<string, unknown>
      const task = {
        id: nextId++,
        title: (b.title as string) || 'Новая задача',
        description: (b.description as string) || null,
        status: 'draft',
        is_private: true,
        assignee: (b.assignee as string) || null,
        created_by: 'admin',
        start_date: (b.start_date as string) || null,
        due_date: (b.due_date as string) || null,
        position: tasks.length,
        tags: (b.tags as string[]) || [],
        checklist: [],
        blockers: [],
        dependents: [],
        created: new Date().toISOString(),
        updated: new Date().toISOString(),
      }
      tasks.push(task)
      return { task }
    },
  },
  // PATCH /admin/kanban/tasks/:id
  {
    method: 'PATCH',
    pattern: /^\/admin\/kanban\/tasks\/(\d+)$/,
    handler: ({ matches, body }) => {
      const id = Number(matches[1])
      const task = tasks.find((t) => t.id === id)
      if (!task) throw new Error('Task not found')
      const b = body as Record<string, unknown>
      if (b.title !== undefined) task.title = b.title as string
      if (b.description !== undefined) task.description = b.description as string | null
      if (b.status !== undefined) {
        task.status = b.status as string
        if (task.status !== 'draft') task.is_private = false
      }
      if (b.assignee !== undefined) task.assignee = b.assignee as string | null
      if (b.start_date !== undefined) task.start_date = b.start_date as string | null
      if (b.due_date !== undefined) task.due_date = b.due_date as string | null
      if (b.tags !== undefined) task.tags = b.tags as string[]
      if (b.is_private !== undefined) task.is_private = b.is_private as boolean
      task.updated = new Date().toISOString()
      return { task }
    },
  },
  // DELETE /admin/kanban/tasks/:id
  {
    method: 'DELETE',
    pattern: /^\/admin\/kanban\/tasks\/(\d+)$/,
    handler: ({ matches }) => {
      const id = Number(matches[1])
      const idx = tasks.findIndex((t) => t.id === id)
      if (idx === -1) throw new Error('Task not found')
      tasks.splice(idx, 1)
      return { status: 'ok' }
    },
  },
  // POST /admin/kanban/reorder
  {
    method: 'POST',
    pattern: /^\/admin\/kanban\/reorder$/,
    handler: ({ body }) => {
      const b = body as Record<string, unknown>
      const task = tasks.find((t) => t.id === (b.task_id as number))
      if (!task) throw new Error('Task not found')
      task.status = b.new_status as string
      task.position = b.new_position as number
      if (task.status !== 'draft') task.is_private = false
      task.updated = new Date().toISOString()
      return { task }
    },
  },
  // POST /admin/kanban/dependencies
  {
    method: 'POST',
    pattern: /^\/admin\/kanban\/dependencies$/,
    handler: ({ body }) => {
      const b = body as Record<string, unknown>
      const blocker = tasks.find((t) => t.id === (b.blocker_id as number))
      const dependent = tasks.find((t) => t.id === (b.dependent_id as number))
      if (!blocker || !dependent) throw new Error('Task not found')
      if (!blocker.dependents.includes(dependent.id)) blocker.dependents.push(dependent.id)
      if (!dependent.blockers.includes(blocker.id)) dependent.blockers.push(blocker.id)
      return { status: 'ok' }
    },
  },
  // DELETE /admin/kanban/dependencies
  {
    method: 'DELETE',
    pattern: /^\/admin\/kanban\/dependencies$/,
    handler: ({ searchParams }) => {
      const blockerId = Number(searchParams.get('blocker_id'))
      const dependentId = Number(searchParams.get('dependent_id'))
      const blocker = tasks.find((t) => t.id === blockerId)
      const dependent = tasks.find((t) => t.id === dependentId)
      if (blocker) blocker.dependents = blocker.dependents.filter((d) => d !== dependentId)
      if (dependent) dependent.blockers = dependent.blockers.filter((b) => b !== blockerId)
      return { status: 'ok' }
    },
  },
  // POST /admin/kanban/tasks/:id/checklist
  {
    method: 'POST',
    pattern: /^\/admin\/kanban\/tasks\/(\d+)\/checklist$/,
    handler: ({ matches, body }) => {
      const taskId = Number(matches[1])
      const task = tasks.find((t) => t.id === taskId)
      if (!task) throw new Error('Task not found')
      const b = body as Record<string, unknown>
      const item = {
        id: nextChecklistId++,
        task_id: taskId,
        text: (b.text as string) || '',
        is_done: false,
        position: (b.position as number) || 0,
      }
      task.checklist.push(item)
      return { item }
    },
  },
  // PATCH /admin/kanban/checklist/:id/toggle
  {
    method: 'PATCH',
    pattern: /^\/admin\/kanban\/checklist\/(\d+)\/toggle$/,
    handler: ({ matches }) => {
      const itemId = Number(matches[1])
      for (const task of tasks) {
        const item = task.checklist.find((c) => c.id === itemId)
        if (item) {
          item.is_done = !item.is_done
          return { item }
        }
      }
      throw new Error('Checklist item not found')
    },
  },
  // DELETE /admin/kanban/checklist/:id
  {
    method: 'DELETE',
    pattern: /^\/admin\/kanban\/checklist\/(\d+)$/,
    handler: ({ matches }) => {
      const itemId = Number(matches[1])
      for (const task of tasks) {
        const idx = task.checklist.findIndex((c) => c.id === itemId)
        if (idx !== -1) {
          task.checklist.splice(idx, 1)
          return { status: 'ok' }
        }
      }
      throw new Error('Checklist item not found')
    },
  },
]
