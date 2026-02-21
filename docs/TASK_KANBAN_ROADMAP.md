# TASK: Kanban + Roadmap — вкладка «Tasks» в Admin Panel

## Статус: Stage 1 (Backend) ✅ PR #299 | Stage 2 (Kanban Board) ✅ PR #300 | Stage 3 (Roadmap) — PENDING
## Приоритет: HIGH
## Оценка: 6/10 сложности | ~4–6 дней

---

## 1. Контекст и цели

Добавить вкладку «Tasks» в существующую Vue 3 Admin Panel
AI Secretary System. Вкладка содержит **два представления**:
- **Kanban** — основное, drag-and-drop по статусам
- **Roadmap** — frappe-gantt с зависимостями между задачами

Скоуп MVP:
- Desktop only (мобильная версия — отложена)
- Внутренний инструмент (не SaaS)
- Три роли: admin (всё), operator (создание/редактирование своих),
  viewer (только чтение)

---

## 2. Схема данных (SQLAlchemy ORM)

### 2.1 Новые таблицы в `db/models.py`

```python
# db/models.py — ДОБАВИТЬ в конец файла

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship
import enum

class KanbanTaskStatus(str, enum.Enum):
    draft      = "draft"
    todo       = "todo"
    in_progress = "in_progress"
    review     = "review"
    done       = "done"

class KanbanTask(Base):
    __tablename__ = "kanban_tasks"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    title       = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status      = Column(SAEnum(KanbanTaskStatus), default=KanbanTaskStatus.draft, nullable=False)
    is_private  = Column(Boolean, default=True, nullable=False)  # Draft всегда приватный
    assignee    = Column(String(100), nullable=True)  # username из JWT (текстовое поле)
    created_by  = Column(String(100), nullable=False)  # username из JWT
    start_date  = Column(DateTime, nullable=True)      # frappe-gantt обязателен; fallback = created_at
    due_date    = Column(DateTime, nullable=True)
    position    = Column(Integer, default=0)           # порядок внутри колонки канбана
    tags        = Column(JSON, default=list)           # ["tag1", "tag2"]
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    checklist   = relationship("KanbanChecklistItem", back_populates="task",
                               cascade="all, delete-orphan", order_by="KanbanChecklistItem.position")
    dependencies_as_blocker = relationship(
        "KanbanTaskDependency",
        foreign_keys="KanbanTaskDependency.blocker_id",
        cascade="all, delete-orphan"
    )
    dependencies_as_dependent = relationship(
        "KanbanTaskDependency",
        foreign_keys="KanbanTaskDependency.dependent_id",
        cascade="all, delete-orphan"
    )


class KanbanTaskDependency(Base):
    """Task B зависит от Task A (A блокирует B)."""
    __tablename__ = "kanban_task_dependencies"

    blocker_id   = Column(Integer, ForeignKey("kanban_tasks.id", ondelete="CASCADE"),
                          primary_key=True)
    dependent_id = Column(Integer, ForeignKey("kanban_tasks.id", ondelete="CASCADE"),
                          primary_key=True)


class KanbanChecklistItem(Base):
    __tablename__ = "kanban_checklist_items"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    task_id   = Column(Integer, ForeignKey("kanban_tasks.id", ondelete="CASCADE"), nullable=False)
    text      = Column(String(500), nullable=False)
    is_done   = Column(Boolean, default=False)
    position  = Column(Integer, default=0)

    task = relationship("KanbanTask", back_populates="checklist")
```

### 2.2 Alembic-миграция

```bash
cd /opt/ai-secretary
source venv/bin/activate
alembic revision --autogenerate -m "add_kanban_tables"
alembic upgrade head
```

---

## 3. Repository (`db/repositories/kanban.py`)

Создать `db/repositories/kanban.py`, наследник `BaseRepository`:

```python
from db.repositories.base import BaseRepository
from db.models import KanbanTask, KanbanTaskDependency, KanbanChecklistItem, KanbanTaskStatus
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from collections import defaultdict

class KanbanRepository(BaseRepository[KanbanTask]):

    async def get_visible_tasks(
        self, session: AsyncSession, current_user: str, is_admin: bool
    ) -> list[KanbanTask]:
        """Admin видит всё; остальные — своё + не-draft чужие."""
        q = select(KanbanTask)
        if not is_admin:
            q = q.where(
                (KanbanTask.created_by == current_user) |
                (KanbanTask.status != KanbanTaskStatus.draft)
            )
        return (await session.execute(q.order_by(KanbanTask.position))).scalars().all()

    async def reorder(
        self, session: AsyncSession, task_id: int,
        new_status: str, new_position: int
    ) -> None:
        """Обновить статус и позицию при drag-and-drop."""
        await session.execute(
            update(KanbanTask)
            .where(KanbanTask.id == task_id)
            .values(status=new_status, position=new_position)
        )

    async def add_dependency(
        self, session: AsyncSession, blocker_id: int, dependent_id: int
    ) -> dict:
        """Добавить зависимость с проверкой циклов (DFS)."""
        if await self._creates_cycle(session, blocker_id, dependent_id):
            raise ValueError("Circular dependency detected")
        dep = KanbanTaskDependency(blocker_id=blocker_id, dependent_id=dependent_id)
        session.add(dep)
        return {"blocker_id": blocker_id, "dependent_id": dependent_id}

    async def _creates_cycle(
        self, session: AsyncSession, blocker_id: int, dependent_id: int
    ) -> bool:
        """DFS: проверяем, можно ли дойти от dependent_id до blocker_id."""
        visited: set[int] = set()
        stack = [dependent_id]
        while stack:
            node = stack.pop()
            if node == blocker_id:
                return True
            if node in visited:
                continue
            visited.add(node)
            rows = (await session.execute(
                select(KanbanTaskDependency.dependent_id)
                .where(KanbanTaskDependency.blocker_id == node)
            )).scalars().all()
            stack.extend(rows)
        return False

    async def remove_dependency(
        self, session: AsyncSession, blocker_id: int, dependent_id: int
    ) -> None:
        await session.execute(
            delete(KanbanTaskDependency)
            .where(
                KanbanTaskDependency.blocker_id == blocker_id,
                KanbanTaskDependency.dependent_id == dependent_id
            )
        )
```

---

## 4. Pydantic Schemas

Создать `schemas/kanban.py` (или добавить в существующий файл схем):

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class TaskStatus(str, Enum):
    draft       = "draft"
    todo        = "todo"
    in_progress = "in_progress"
    review      = "review"
    done        = "done"

class ChecklistItemOut(BaseModel):
    id: int
    text: str
    is_done: bool
    position: int
    model_config = {"from_attributes": True}

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    assignee: Optional[str] = None
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    tags: list[str] = []

class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    assignee: Optional[str] = None
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    tags: Optional[list[str]] = None

class TaskReorder(BaseModel):
    task_id: int
    new_status: TaskStatus
    new_position: int

class DependencyCreate(BaseModel):
    blocker_id: int
    dependent_id: int

class ChecklistItemCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)

class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: TaskStatus
    is_private: bool
    assignee: Optional[str]
    created_by: str
    start_date: Optional[datetime]
    due_date: Optional[datetime]
    position: int
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    checklist: list[ChecklistItemOut] = []
    blocker_ids: list[int] = []    # задачи, которые БЛОКИРУЮТ эту
    dependent_ids: list[int] = []  # задачи, которые ЭТА блокирует
    model_config = {"from_attributes": True}
```

---

## 5. FastAPI Endpoints

Создать `app/routers/kanban.py` (отдельный роутер, как остальные):

```python
# app/routers/kanban.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin/kanban", tags=["kanban"])

# ─── KANBAN TASKS ────────────────────────────────────────────────

@router.get("/tasks")
async def kanban_get_tasks(
    current_user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
) -> list[TaskOut]:
    is_admin = current_user.get("role") == "admin"
    tasks = await kanban_repo.get_visible_tasks(db, current_user["username"], is_admin)
    result = []
    for task in tasks:
        blockers  = [d.blocker_id   for d in task.dependencies_as_dependent]
        dependents = [d.dependent_id for d in task.dependencies_as_blocker]
        t = TaskOut.model_validate(task)
        t.blocker_ids   = blockers
        t.dependent_ids = dependents
        result.append(t)
    return result

@router.post("/tasks", status_code=201)
async def kanban_create_task(
    body: TaskCreate,
    current_user: dict = Depends(require_roles(["admin", "operator"])),
    db: AsyncSession = Depends(get_db)
) -> TaskOut:
    task = KanbanTask(
        **body.model_dump(),
        created_by=current_user["username"],
        status=KanbanTaskStatus.draft,
        is_private=True
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    await _sse_broadcast("kanban_task_created", {"id": task.id})
    return TaskOut.model_validate(task)

@router.patch("/tasks/{task_id}")
async def kanban_update_task(
    task_id: int, body: TaskUpdate,
    current_user: dict = Depends(require_roles(["admin", "operator"])),
    db: AsyncSession = Depends(get_db)
) -> TaskOut:
    task = await kanban_repo.get(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if current_user["role"] == "operator" and task.created_by != current_user["username"]:
        raise HTTPException(403, "Not your task")
    data = body.model_dump(exclude_none=True)
    if "status" in data and data["status"] != "draft":
        data["is_private"] = False
    for k, v in data.items():
        setattr(task, k, v)
    await db.commit()
    await db.refresh(task)
    await _sse_broadcast("kanban_task_updated", {"id": task.id, "status": task.status})
    return TaskOut.model_validate(task)

@router.delete("/tasks/{task_id}", status_code=204)
async def kanban_delete_task(
    task_id: int,
    current_user: dict = Depends(require_roles(["admin"])),
    db: AsyncSession = Depends(get_db)
) -> None:
    task = await kanban_repo.get(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    await db.delete(task)
    await db.commit()
    await _sse_broadcast("kanban_task_deleted", {"id": task_id})

@router.post("/reorder")
async def kanban_reorder(
    body: TaskReorder,
    current_user: dict = Depends(require_roles(["admin", "operator"])),
    db: AsyncSession = Depends(get_db)
) -> dict:
    await kanban_repo.reorder(db, body.task_id, body.new_status, body.new_position)
    await db.commit()
    await _sse_broadcast("kanban_reordered", body.model_dump())
    return {"ok": True}

# ─── DEPENDENCIES ─────────────────────────────────────────────────

@router.post("/dependencies", status_code=201)
async def kanban_add_dependency(
    body: DependencyCreate,
    current_user: dict = Depends(require_roles(["admin", "operator"])),
    db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        result = await kanban_repo.add_dependency(db, body.blocker_id, body.dependent_id)
        await db.commit()
        await _sse_broadcast("kanban_dependency_added", result)
        return result
    except ValueError as e:
        raise HTTPException(409, str(e))

@router.delete("/dependencies", status_code=204)
async def kanban_remove_dependency(
    blocker_id: int, dependent_id: int,
    current_user: dict = Depends(require_roles(["admin"])),
    db: AsyncSession = Depends(get_db)
) -> None:
    await kanban_repo.remove_dependency(db, blocker_id, dependent_id)
    await db.commit()

# ─── CHECKLIST ────────────────────────────────────────────────────

@router.post("/tasks/{task_id}/checklist", status_code=201)
async def kanban_add_checklist_item(
    task_id: int, body: ChecklistItemCreate,
    current_user: dict = Depends(require_roles(["admin", "operator"])),
    db: AsyncSession = Depends(get_db)
) -> ChecklistItemOut:
    item = KanbanChecklistItem(task_id=task_id, text=body.text)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return ChecklistItemOut.model_validate(item)

@router.patch("/checklist/{item_id}/toggle")
async def kanban_toggle_checklist(
    item_id: int,
    current_user: dict = Depends(require_roles(["admin", "operator"])),
    db: AsyncSession = Depends(get_db)
) -> ChecklistItemOut:
    item = await db.get(KanbanChecklistItem, item_id)
    if not item:
        raise HTTPException(404)
    item.is_done = not item.is_done
    await db.commit()
    await db.refresh(item)
    return ChecklistItemOut.model_validate(item)

@router.delete("/checklist/{item_id}", status_code=204)
async def kanban_delete_checklist_item(
    item_id: int,
    current_user: dict = Depends(require_roles(["admin"])),
    db: AsyncSession = Depends(get_db)
) -> None:
    item = await db.get(KanbanChecklistItem, item_id)
    if not item:
        raise HTTPException(404)
    await db.delete(item)
    await db.commit()
```

---

## 6. SSE Events

Новые события для real-time синхронизации:

| Event | Payload | Кто слушает |
|---|---|---|
| `kanban_task_created` | `{id}` | Все активные клиенты |
| `kanban_task_updated` | `{id, status}` | Все |
| `kanban_task_deleted` | `{id}` | Все |
| `kanban_reordered` | `{task_id, new_status, new_position}` | Все |
| `kanban_dependency_added` | `{blocker_id, dependent_id}` | Все |

Использовать `_sse_broadcast()` — существующий хелпер проекта.

---

## 7. Frontend: Vue 3 Admin Panel

### 7.1 Зависимости

```bash
cd /opt/ai-secretary/admin
npm install vue-draggable-plus frappe-gantt
npm install -D @types/frappe-gantt  # если есть
```

### 7.2 Структура файлов

```
admin/src/
  views/
    KanbanView.vue          <- корневой компонент
  components/kanban/
    KanbanBoard.vue         <- drag-and-drop доска (5 колонок)
    KanbanColumn.vue        <- одна колонка со статусом
    KanbanCard.vue          <- карточка задачи
    KanbanCardDetail.vue    <- модальное окно: детали + чеклист
    KanbanRoadmap.vue       <- frappe-gantt wrapper
    KanbanTaskForm.vue      <- форма создания/редактирования
  api/
    kanban.ts               <- API клиент
  stores/
    kanban.ts               <- Pinia store
```

### 7.3 Pinia Store (`stores/kanban.ts`)

```typescript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/api/kanban'

export type TaskStatus = 'draft' | 'todo' | 'in_progress' | 'review' | 'done'

export interface ChecklistItem {
  id: number
  text: string
  is_done: boolean
  position: number
}

export interface Task {
  id: number
  title: string
  description: string | null
  status: TaskStatus
  is_private: boolean
  assignee: string | null
  created_by: string
  start_date: string | null
  due_date: string | null
  position: number
  tags: string[]
  created_at: string
  updated_at: string
  checklist: ChecklistItem[]
  blocker_ids: number[]
  dependent_ids: number[]
}

export const COLUMNS: { key: TaskStatus; label: string; color: string }[] = [
  { key: 'draft',       label: 'Черновик',   color: 'gray' },
  { key: 'todo',        label: 'To-do',      color: 'blue' },
  { key: 'in_progress', label: 'В работе',   color: 'yellow' },
  { key: 'review',      label: 'Проверка',   color: 'purple' },
  { key: 'done',        label: 'Готово',     color: 'green' },
]

export const useKanbanStore = defineStore('kanban', () => {
  const tasks = ref<Task[]>([])
  const loading = ref(false)
  const activeView = ref<'kanban' | 'roadmap'>('kanban')
  const selectedTaskId = ref<number | null>(null)

  const tasksByStatus = computed(() => {
    const map: Record<TaskStatus, Task[]> = {
      draft: [], todo: [], in_progress: [], review: [], done: []
    }
    tasks.value
      .sort((a, b) => a.position - b.position)
      .forEach(t => map[t.status]?.push(t))
    return map
  })

  const selectedTask = computed(() =>
    tasks.value.find(t => t.id === selectedTaskId.value) ?? null
  )

  // frappe-gantt data format
  const ganttTasks = computed(() =>
    tasks.value
      .filter(t => t.status !== 'draft')
      .map(t => ({
        id: String(t.id),
        name: t.title,
        start: t.start_date ?? t.created_at.split('T')[0],
        end: t.due_date ?? t.start_date ?? t.created_at.split('T')[0],
        progress: t.status === 'done' ? 100
          : t.status === 'in_progress' ? 50
          : t.status === 'review' ? 75 : 0,
        dependencies: t.blocker_ids.join(','),
      }))
  )

  async function fetchTasks() {
    loading.value = true
    try {
      tasks.value = await api.getTasks()
    } finally {
      loading.value = false
    }
  }

  async function createTask(data: Partial<Task>) {
    const task = await api.createTask(data)
    tasks.value.push(task)
    return task
  }

  async function updateTask(id: number, data: Partial<Task>) {
    const updated = await api.updateTask(id, data)
    const idx = tasks.value.findIndex(t => t.id === id)
    if (idx !== -1) tasks.value[idx] = updated
    return updated
  }

  async function deleteTask(id: number) {
    await api.deleteTask(id)
    tasks.value = tasks.value.filter(t => t.id !== id)
  }

  async function reorderTask(taskId: number, newStatus: TaskStatus, newPosition: number) {
    // Optimistic update
    const task = tasks.value.find(t => t.id === taskId)
    if (task) {
      task.status = newStatus
      task.position = newPosition
      if (newStatus !== 'draft') task.is_private = false
    }
    await api.reorderTask(taskId, newStatus, newPosition)
  }

  async function addDependency(blockerId: number, dependentId: number) {
    await api.addDependency(blockerId, dependentId)
    const dep = tasks.value.find(t => t.id === dependentId)
    if (dep && !dep.blocker_ids.includes(blockerId)) dep.blocker_ids.push(blockerId)
  }

  // SSE real-time sync
  function applySSEEvent(event: string, payload: Record<string, unknown>) {
    if (event === 'kanban_task_deleted') {
      tasks.value = tasks.value.filter(t => t.id !== payload.id)
    } else if (['kanban_task_created', 'kanban_task_updated', 'kanban_reordered'].includes(event)) {
      fetchTasks() // простой рефетч
    }
  }

  return {
    tasks, loading, activeView, selectedTaskId,
    tasksByStatus, selectedTask, ganttTasks,
    fetchTasks, createTask, updateTask, deleteTask,
    reorderTask, addDependency, applySSEEvent
  }
})
```

### 7.4 API клиент (`api/kanban.ts`)

```typescript
import { apiClient } from './index'   // существующий axios/fetch инстанс с JWT

const BASE = '/admin/kanban'

export const getTasks      = ()            => apiClient.get(`${BASE}/tasks`).then(r => r.data)
export const createTask    = (data: unknown) => apiClient.post(`${BASE}/tasks`, data).then(r => r.data)
export const updateTask    = (id: number, data: unknown) =>
  apiClient.patch(`${BASE}/tasks/${id}`, data).then(r => r.data)
export const deleteTask    = (id: number)  => apiClient.delete(`${BASE}/tasks/${id}`)
export const reorderTask   = (id: number, status: string, pos: number) =>
  apiClient.post(`${BASE}/reorder`, { task_id: id, new_status: status, new_position: pos })
export const addDependency = (b: number, d: number) =>
  apiClient.post(`${BASE}/dependencies`, { blocker_id: b, dependent_id: d })
export const removeDependency = (b: number, d: number) =>
  apiClient.delete(`${BASE}/dependencies`, { params: { blocker_id: b, dependent_id: d } })
export const addChecklist  = (taskId: number, text: string) =>
  apiClient.post(`${BASE}/tasks/${taskId}/checklist`, { text }).then(r => r.data)
export const toggleChecklist = (itemId: number) =>
  apiClient.patch(`${BASE}/checklist/${itemId}/toggle`).then(r => r.data)
export const deleteChecklist = (itemId: number) =>
  apiClient.delete(`${BASE}/checklist/${itemId}`)
```

### 7.5 KanbanBoard.vue (ключевая логика)

```vue
<!-- admin/src/components/kanban/KanbanBoard.vue -->
<template>
  <div class="flex gap-4 overflow-x-auto h-full p-4">
    <div
      v-for="col in COLUMNS" :key="col.key"
      class="flex-shrink-0 w-72 flex flex-col bg-gray-100 dark:bg-gray-800 rounded-lg"
    >
      <!-- Заголовок колонки -->
      <div class="flex items-center justify-between px-3 py-2">
        <span class="font-semibold text-sm">{{ col.label }}</span>
        <span class="text-xs bg-gray-200 dark:bg-gray-700 rounded-full px-2 py-0.5">
          {{ store.tasksByStatus[col.key].length }}
        </span>
      </div>

      <!-- Drag-and-drop список -->
      <VueDraggable
        v-model="store.tasksByStatus[col.key]"
        :group="{ name: 'kanban' }"
        item-key="id"
        class="flex-1 min-h-16 p-2 space-y-2 overflow-y-auto"
        @end="onDragEnd($event, col.key)"
      >
        <template #item="{ element }">
          <KanbanCard
            :task="element"
            @click="store.selectedTaskId = element.id"
          />
        </template>
      </VueDraggable>

      <!-- Кнопка добавить (только для admin/operator) -->
      <button
        v-if="col.key === 'draft' && canEdit"
        @click="$emit('create')"
        class="m-2 py-1.5 text-sm text-center rounded-lg border-2 border-dashed
               border-gray-300 dark:border-gray-600 hover:border-blue-400 transition-colors"
      >
        + Новая задача
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { VueDraggable } from 'vue-draggable-plus'
import { useKanbanStore, COLUMNS, type TaskStatus } from '@/stores/kanban'
import { useAuthStore } from '@/stores/auth'
import KanbanCard from './KanbanCard.vue'

const store  = useKanbanStore()
const auth   = useAuthStore()
const canEdit = computed(() => ['admin', 'operator'].includes(auth.role))

function onDragEnd(event: { newIndex: number }, newStatus: TaskStatus) {
  const task = store.tasksByStatus[newStatus][event.newIndex]
  if (!task) return
  store.reorderTask(task.id, newStatus, event.newIndex)
}
</script>
```

### 7.6 KanbanRoadmap.vue (frappe-gantt wrapper)

```vue
<!-- admin/src/components/kanban/KanbanRoadmap.vue -->
<template>
  <div class="p-4 overflow-x-auto">
    <div v-if="store.ganttTasks.length === 0" class="text-center text-gray-500 py-16">
      Нет задач для отображения на роадмапе.<br>
      <span class="text-sm">Задачи в статусе «Черновик» не отображаются.</span>
    </div>
    <div v-else ref="ganttEl" class="frappe-gantt-container" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import Gantt from 'frappe-gantt'
import { useKanbanStore } from '@/stores/kanban'

const store   = useKanbanStore()
const ganttEl = ref<HTMLElement | null>(null)
let ganttInst: Gantt | null = null

function initGantt() {
  if (!ganttEl.value || store.ganttTasks.length === 0) return
  ganttEl.value.innerHTML = ''
  ganttInst = new Gantt(ganttEl.value, store.ganttTasks, {
    view_mode: 'Week',
    language: 'ru',
    on_click: (task) => {
      store.selectedTaskId = Number(task.id)
    },
    on_date_change: async (task, start, end) => {
      await store.updateTask(Number(task.id), {
        start_date: start.toISOString(),
        due_date: end.toISOString()
      })
    },
  })
}

onMounted(() => nextTick(initGantt))
watch(() => store.ganttTasks, () => nextTick(initGantt), { deep: true })
onBeforeUnmount(() => { ganttInst = null })
</script>

<style>
@import 'frappe-gantt/dist/frappe-gantt.css';
.frappe-gantt-container svg { width: 100%; }
</style>
```

### 7.7 KanbanView.vue (корневой)

```vue
<!-- admin/src/views/KanbanView.vue -->
<template>
  <div class="flex flex-col h-full">
    <!-- Header: переключатель Kanban / Roadmap -->
    <div class="flex items-center justify-between px-6 py-3 border-b
                border-gray-200 dark:border-gray-700">
      <h1 class="text-xl font-bold">{{ $t('kanban.title') }}</h1>
      <div class="flex rounded-lg overflow-hidden border border-gray-300 dark:border-gray-600">
        <button
          v-for="view in ['kanban', 'roadmap']" :key="view"
          :class="['px-4 py-1.5 text-sm transition-colors',
            store.activeView === view
              ? 'bg-blue-500 text-white'
              : 'hover:bg-gray-100 dark:hover:bg-gray-700']"
          @click="store.activeView = view as 'kanban' | 'roadmap'"
        >
          {{ view === 'kanban' ? 'Канбан' : 'Роадмап' }}
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-hidden">
      <KanbanBoard v-if="store.activeView === 'kanban'" @create="showForm = true" />
      <KanbanRoadmap v-else />
    </div>

    <!-- Task Detail Modal -->
    <KanbanCardDetail
      v-if="store.selectedTask"
      :task="store.selectedTask"
      @close="store.selectedTaskId = null"
    />

    <!-- Create Task Modal -->
    <KanbanTaskForm
      v-if="showForm"
      @close="showForm = false"
      @created="showForm = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useKanbanStore } from '@/stores/kanban'
import KanbanBoard from '@/components/kanban/KanbanBoard.vue'
import KanbanRoadmap from '@/components/kanban/KanbanRoadmap.vue'
import KanbanCardDetail from '@/components/kanban/KanbanCardDetail.vue'
import KanbanTaskForm from '@/components/kanban/KanbanTaskForm.vue'

const store    = useKanbanStore()
const showForm = ref(false)

onMounted(() => store.fetchTasks())
</script>
```

### 7.8 Регистрация вкладки

**`admin/src/router/index.ts`** — добавить маршрут:
```typescript
{ path: '/kanban', name: 'Kanban', component: () => import('@/views/KanbanView.vue') }
```

**Sidebar** — добавить пункт меню:
```typescript
{ path: '/kanban', icon: 'Trello', label: $t('kanban.title') }
```

**i18n** — добавить переводы для ru/en/kk.

---

## 8. Бизнес-логика (обязательные правила)

| Правило | Детали |
|---|---|
| **Draft = приватный** | `is_private=True` при создании; снимается автоматически при смене статуса |
| **Чеклист не обязателен в MVP** | Рекомендуется, но не блокирует переход |
| **Переделегирование** | Поле `assignee` можно менять; история не хранится (MVP) |
| **Зависимости -> Draft** | Запрещать зависимости на приватные задачи: 409 с `"Target task is private"` |
| **Цикличные зависимости** | DFS-проверка в `add_dependency`; 409 с `"Circular dependency detected"` |
| **Роли** | admin: все; operator: CRUD своих задач; viewer: только GET |
| **start_date fallback** | Если `start_date=null` -> frappe-gantt использует `created_at` |
| **Drag-and-drop Draft** | Перетащить из Draft -> сбрасывает `is_private=False` автоматически |

---

## 9. Порядок реализации (рекомендуемый)

```
Sprint 1 (Backend):
  1. db/models.py          — 3 новые модели
  2. alembic migration     — создание таблиц
  3. db/repositories/kanban.py
  4. app/routers/kanban.py — все endpoints
  5. ruff check + mypy     — линтинг

Sprint 2 (Frontend):
  6. npm install           — vue-draggable-plus + frappe-gantt
  7. api/kanban.ts         — API клиент
  8. stores/kanban.ts      — Pinia store
  9. components/kanban/*   — все 6 компонентов
  10. KanbanView.vue       — корневой
  11. Router + Sidebar     — регистрация вкладки
  12. i18n                 — переводы

Sprint 3 (SSE + polish):
  13. SSE events           — real-time sync
  14. Тесты               — pytest backend + ручное QA frontend
  15. npm run build        — production build
```

---

## 10. Тесты (pytest)

```python
# tests/test_kanban.py

async def test_draft_is_private(client, admin_token):
    """Новая задача всегда draft и приватная."""
    r = await client.post("/admin/kanban/tasks",
        json={"title": "Test task"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 201
    assert r.json()["status"] == "draft"
    assert r.json()["is_private"] is True

async def test_status_change_removes_private(client, admin_token, sample_task_id):
    """При смене статуса с draft задача становится публичной."""
    r = await client.patch(f"/admin/kanban/tasks/{sample_task_id}",
        json={"status": "todo"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.json()["is_private"] is False

async def test_circular_dependency_rejected(client, admin_token, task_a, task_b):
    """Циклические зависимости отклоняются."""
    await client.post("/admin/kanban/dependencies",
        json={"blocker_id": task_a, "dependent_id": task_b},
        headers={"Authorization": f"Bearer {admin_token}"})
    r = await client.post("/admin/kanban/dependencies",
        json={"blocker_id": task_b, "dependent_id": task_a},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 409

async def test_viewer_cannot_create(client, viewer_token):
    """Viewer не может создавать задачи."""
    r = await client.post("/admin/kanban/tasks",
        json={"title": "Hack"},
        headers={"Authorization": f"Bearer {viewer_token}"})
    assert r.status_code == 403
```

---

## 11. Неочевидные аспекты

1. **frappe-gantt и `start_date=null`** — библиотека упадет без даты начала. Fallback на `created_at` обязателен уже в store, не в компоненте.

2. **Drag между колонками на мобиле** — `vue-draggable-plus` использует `pointer events`, не `touch events`. На iPad могут быть проблемы — добавить `touch-action: none` на карточки.

3. **SSE и Kanban** — при параллельной работе двух пользователей простой `fetchTasks()` на любое SSE-событие создает race condition. Лучший паттерн: `kanban_task_updated` обновляет только одну задачу точечно, а не делает полный рефетч.

4. **DFS циклов при bulk-import** — если захотим загружать задачи CSV в будущем, проверка циклов должна быть транзакционной. Сейчас OK, но закладывать в Repository.

5. **`position` при drag** — при перетаскивании нужно переиндексировать ВСЕ карточки колонки, а не только перемещенную. Иначе `position` станет не уникальным и сортировка сломается.

6. **`ADMIN_JWT_SECRET` перегенерируется при рестарте** — сервис перезапускается при деплое. После `alembic upgrade head` нужно будет снова залогиниться в админке.

---

## 12. Риски

| Риск | Вероятность | Митигация |
|---|---|---|
| frappe-gantt CSS конфликтует с Tailwind | Средняя | Изолировать в `scoped` + проверить при первом запуске |
| N+1 при загрузке зависимостей | Высокая | `selectinload` в репозитории для `dependencies_*` |
| vue-draggable-plus несовместим с SSE-обновлениями | Низкая | Запрещать drag во время загрузки (`loading.value`) |

---

## 13. Открытые вопросы (уточнить перед реализацией)

1. **Имя sidebar-иконки** — в проекте используется `Lucide`; для Kanban подойдет `Trello` или `LayoutDashboard`?
2. **Существующий `apiClient`** — где точно находится базовый axios/fetch инстанс с JWT? (предположительно `admin/src/api/index.ts` или `client.ts`)
3. **`require_roles()`** — существует ли такой декоратор в `auth_manager.py` или нужно создать?
4. **`_sse_broadcast()`** — подтвердить сигнатуру существующей SSE-функции в `orchestrator.py`
5. **Позиция вкладки в Sidebar** — после какой из существующих вкладок вставить «Tasks»?
