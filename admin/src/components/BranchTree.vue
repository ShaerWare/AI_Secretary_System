<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { GitBranch, Plus, X, Trash2 } from 'lucide-vue-next'
import type { BranchNode } from '@/api/chat'
import BranchTreeNode from '@/components/BranchTreeNode.vue'

const props = defineProps<{
  branches: BranchNode[]
  sessionId: string
}>()

const emit = defineEmits<{
  switch: [messageId: string]
  'scroll-to': [messageId: string]
  'new-branch': []
  close: []
  'delete-branches': [messageIds: string[]]
  'delete-node': [messageId: string]
}>()

const { t } = useI18n()

const deleteMode = ref(false)
const selectedForDelete = ref(new Set<string>())

// ── nodeMap: quick lookup by id → { node, parentId } ──
interface NodeEntry {
  node: BranchNode
  parentId: string | null
}
const nodeMap = ref<Record<string, NodeEntry>>({})

watch(
  () => props.branches,
  (roots) => {
    const map: Record<string, NodeEntry> = {}
    function walk(nodes: BranchNode[], parentId: string | null) {
      for (const n of nodes) {
        map[n.id] = { node: n, parentId }
        if (n.children?.length) walk(n.children, n.id)
      }
    }
    walk(roots, null)
    nodeMap.value = map
  },
  { immediate: true, deep: true },
)

function toggleDeleteMode() {
  deleteMode.value = !deleteMode.value
  if (!deleteMode.value) {
    selectedForDelete.value = new Set()
  }
}

function cancelDeleteMode() {
  deleteMode.value = false
  selectedForDelete.value = new Set()
}

function toggleSelect(messageId: string) {
  const s = new Set(selectedForDelete.value)
  const entry = nodeMap.value[messageId]
  if (!entry) return

  const selecting = !s.has(messageId)

  if (entry.node.role === 'user') {
    // User message: toggle self + all direct assistant children
    const targets = [messageId]
    for (const child of entry.node.children ?? []) {
      if (child.role === 'assistant') targets.push(child.id)
    }
    for (const id of targets) {
      if (selecting) s.add(id)
      else s.delete(id)
    }
  } else if (entry.node.role === 'assistant' && entry.parentId) {
    // Assistant message: toggle parent user + all sibling assistants
    const parent = nodeMap.value[entry.parentId]
    if (parent && parent.node.role === 'user') {
      const targets = [entry.parentId]
      for (const child of parent.node.children ?? []) {
        if (child.role === 'assistant') targets.push(child.id)
      }
      for (const id of targets) {
        if (selecting) s.add(id)
        else s.delete(id)
      }
    } else {
      // Parent is not user — toggle only self
      if (selecting) s.add(messageId)
      else s.delete(messageId)
    }
  } else {
    // System or orphan — toggle only self
    if (selecting) s.add(messageId)
    else s.delete(messageId)
  }

  selectedForDelete.value = s
}

// Count unique pairs for display (user messages count as the pair unit)
const selectedPairCount = computed(() => {
  let count = 0
  for (const id of selectedForDelete.value) {
    const entry = nodeMap.value[id]
    if (!entry) { count++; continue }
    // Count user messages, and assistant/system only if their parent is not selected
    if (entry.node.role === 'user') {
      count++
    } else if (!entry.parentId || !selectedForDelete.value.has(entry.parentId)) {
      count++
    }
  }
  return count
})

function confirmDeleteSelected() {
  if (selectedForDelete.value.size === 0) return
  // Filter to root IDs only — backend cascades descendants
  const ids = Array.from(selectedForDelete.value).filter((id) => {
    const entry = nodeMap.value[id]
    return !entry?.parentId || !selectedForDelete.value.has(entry.parentId)
  })
  if (ids.length === 0) return
  emit('delete-branches', ids)
  cancelDeleteMode()
}

function handleClick(messageId: string) {
  emit('switch', messageId)
}

function handleScrollTo(messageId: string) {
  emit('scroll-to', messageId)
}

function handleDeleteNode(messageId: string) {
  emit('delete-node', messageId)
}

// ── Drag-to-scroll ──
const scrollContainer = ref<HTMLElement | null>(null)
let isDragging = false
let startX = 0
let startY = 0
let scrollLeft = 0
let scrollTop = 0
let hasMoved = false

function onPointerDown(e: PointerEvent) {
  const el = scrollContainer.value
  if (!el) return
  // Don't hijack clicks on buttons/interactive elements
  if ((e.target as HTMLElement).closest('[data-branch-node], button, input')) return
  isDragging = true
  hasMoved = false
  startX = e.clientX
  startY = e.clientY
  scrollLeft = el.scrollLeft
  scrollTop = el.scrollTop
  el.setPointerCapture(e.pointerId)
  el.style.cursor = 'grabbing'
  el.style.userSelect = 'none'
}

function onPointerMove(e: PointerEvent) {
  if (!isDragging) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  if (Math.abs(dx) > 6 || Math.abs(dy) > 6) hasMoved = true
  const el = scrollContainer.value!
  el.scrollLeft = scrollLeft - dx
  el.scrollTop = scrollTop - dy
}

function onPointerUp(e: PointerEvent) {
  if (!isDragging) return
  isDragging = false
  const el = scrollContainer.value!
  el.releasePointerCapture(e.pointerId)
  el.style.cursor = ''
  el.style.userSelect = ''
  // If we dragged, prevent the click from triggering node switch
  if (hasMoved) {
    el.addEventListener('click', suppressClick, { capture: true, once: true })
  }
}

function suppressClick(e: Event) {
  e.stopPropagation()
  e.preventDefault()
}

onUnmounted(() => {
  scrollContainer.value?.removeEventListener('click', suppressClick, { capture: true })
})
</script>

<template>
  <div class="border-l border-border bg-card/50 flex flex-col flex-shrink-0">
    <div class="p-3 border-b border-border flex items-center justify-between flex-shrink-0">
      <h3 class="text-xs font-semibold text-muted-foreground uppercase flex items-center gap-1.5">
        <GitBranch class="w-3.5 h-3.5" />
        {{ t('chatView.branchTree') }}
      </h3>
      <div class="flex items-center gap-1">
        <button
          :class="[
            'p-1 rounded transition-colors',
            deleteMode
              ? 'bg-destructive/15 text-destructive hover:bg-destructive/25'
              : 'hover:bg-secondary text-muted-foreground',
          ]"
          :title="t('chatView.deleteBranches')"
          @click="toggleDeleteMode"
        >
          <Trash2 class="w-3.5 h-3.5" />
        </button>
        <button
          v-if="!deleteMode"
          class="p-1 rounded hover:bg-secondary text-muted-foreground transition-colors"
          :title="t('chatView.newBranch')"
          @click="emit('new-branch')"
        >
          <Plus class="w-3.5 h-3.5" />
        </button>
        <button
          class="p-1 rounded hover:bg-secondary text-muted-foreground transition-colors"
          @click="emit('close')"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <div
      v-if="branches.length > 0"
      ref="scrollContainer"
      class="p-2 flex-1 overflow-auto cursor-grab"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
    >
      <div class="w-max min-w-full">
        <BranchTreeNode
          v-for="root in branches"
          :key="root.id"
          :node="root"
          :depth="0"
          :delete-mode="deleteMode"
          :selected-for-delete="selectedForDelete"
          @click-node="handleClick"
          @scroll-to="handleScrollTo"
          @delete-node="handleDeleteNode"
          @toggle-select="toggleSelect"
        />
      </div>
    </div>
    <div v-else class="p-4 text-center text-xs text-muted-foreground">
      {{ t('chatView.noBranches') }}
    </div>

    <!-- Delete mode action bar -->
    <div
      v-if="deleteMode"
      class="p-2 border-t border-border flex items-center gap-2 flex-shrink-0"
    >
      <button
        class="flex-1 px-2 py-1.5 text-xs rounded bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        :disabled="selectedForDelete.size === 0"
        @click="confirmDeleteSelected"
      >
        {{ t('chatView.deleteSelectedN', { n: selectedPairCount }) }}
      </button>
      <button
        class="px-2 py-1.5 text-xs rounded border border-border hover:bg-secondary transition-colors"
        @click="cancelDeleteMode"
      >
        {{ t('common.cancel') }}
      </button>
    </div>
  </div>
</template>
