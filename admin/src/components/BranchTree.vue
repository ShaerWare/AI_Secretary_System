<script setup lang="ts">
import { ref, watch, computed, onUnmounted, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { GitBranch, Plus, X, Trash2, Search } from 'lucide-vue-next'
import type { BranchNode, BranchSearchMatch } from '@/api/chat'
import { chatApi } from '@/api'
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
  'rename-node': [messageId: string, name: string]
  'refetch-branches': []
}>()

const { t } = useI18n()

const deleteMode = ref(false)
const selectedForDelete = ref(new Set<string>())
const collapsedNodes = ref(new Set<string>())

// Search state
const showSearch = ref(false)
const searchQuery = ref('')
const searchResults = ref<BranchSearchMatch[]>([])
const searchMatchIds = ref(new Set<string>())
const searchLoading = ref(false)
let searchDebounce: ReturnType<typeof setTimeout> | null = null

function collectDescendantIds(node: BranchNode, out: string[]) {
  out.push(node.id)
  if (node.children?.length) {
    for (const c of node.children) collectDescendantIds(c, out)
  }
}

function collectAllIds(nodes: BranchNode[], out: Set<string>) {
  for (const n of nodes) {
    out.add(n.id)
    if (n.children?.length) collectAllIds(n.children, out)
  }
}

// Whenever branches change, collapse any new nodes by default
watch(
  () => props.branches,
  (roots) => {
    const next = new Set(collapsedNodes.value)
    collectAllIds(roots, next)
    collapsedNodes.value = next
  },
  { immediate: true, deep: true },
)

function toggleCollapse(messageId: string) {
  const entry = nodeMap.value[messageId]
  if (!entry) return
  const next = new Set(collapsedNodes.value)
  const ids: string[] = []
  collectDescendantIds(entry.node, ids)
  if (next.has(messageId)) {
    for (const d of ids) next.delete(d)
  } else {
    for (const d of ids) next.add(d)
  }
  collapsedNodes.value = next
}

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
    const targets = [messageId]
    for (const child of entry.node.children ?? []) {
      if (child.role === 'assistant') targets.push(child.id)
    }
    for (const id of targets) {
      if (selecting) s.add(id)
      else s.delete(id)
    }
  } else if (entry.node.role === 'assistant' && entry.parentId) {
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
      if (selecting) s.add(messageId)
      else s.delete(messageId)
    }
  } else {
    if (selecting) s.add(messageId)
    else s.delete(messageId)
  }

  selectedForDelete.value = s
}

const selectedPairCount = computed(() => {
  let count = 0
  for (const id of selectedForDelete.value) {
    const entry = nodeMap.value[id]
    if (!entry) { count++; continue }
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

// ── Rename ──
async function handleRenameNode(messageId: string, name: string) {
  if (!props.sessionId) return
  try {
    await chatApi.renameBranch(props.sessionId, messageId, name)
    emit('refetch-branches')
  } catch { /* toast handled by api client */ }
}

// ── Pin/Unpin ──
async function handlePinNode(messageId: string, pinned: boolean) {
  if (!props.sessionId) return
  try {
    await chatApi.pinBranch(props.sessionId, messageId, pinned)
    emit('refetch-branches')
  } catch { /* toast handled by api client */ }
}

// ── Search ──
function toggleSearch() {
  showSearch.value = !showSearch.value
  if (!showSearch.value) {
    searchQuery.value = ''
    searchResults.value = []
    searchMatchIds.value = new Set()
  }
}

watch(searchQuery, (q) => {
  if (searchDebounce) clearTimeout(searchDebounce)
  if (!q.trim()) {
    searchResults.value = []
    searchMatchIds.value = new Set()
    return
  }
  searchDebounce = setTimeout(() => doSearch(q.trim()), 300)
})

async function doSearch(q: string) {
  if (!props.sessionId || !q) return
  searchLoading.value = true
  try {
    const data = await chatApi.searchBranches(props.sessionId, q)
    searchResults.value = data.matches
    const ids = new Set<string>()
    for (const m of data.matches) ids.add(m.id)
    searchMatchIds.value = ids

    // Auto-expand branches containing matches
    if (ids.size > 0) {
      const next = new Set(collapsedNodes.value)
      for (const matchId of ids) {
        // Walk ancestors and uncollapse them
        let current: string | null = matchId
        while (current) {
          next.delete(current)
          const e: NodeEntry | undefined = nodeMap.value[current]
          current = e?.parentId ?? null
        }
      }
      collapsedNodes.value = next
    }
  } catch {
    searchResults.value = []
    searchMatchIds.value = new Set()
  } finally {
    searchLoading.value = false
  }
}

// Ctrl+F shortcut
function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
    e.preventDefault()
    showSearch.value = true
    setTimeout(() => {
      const el = document.querySelector('[data-branch-search]') as HTMLInputElement
      el?.focus()
    }, 50)
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

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
  <div class="border-l border-border bg-card/50 flex flex-col flex-shrink-0 h-full">
    <div class="p-3 border-b border-border flex items-center justify-between flex-shrink-0">
      <h3 class="text-xs font-semibold text-muted-foreground uppercase flex items-center gap-1.5">
        <GitBranch class="w-3.5 h-3.5" />
        {{ t('chatView.branchTree') }}
      </h3>
      <div class="flex items-center gap-1">
        <button
          :class="[
            'p-1 rounded transition-colors',
            showSearch
              ? 'bg-primary/15 text-primary hover:bg-primary/25'
              : 'hover:bg-secondary text-muted-foreground',
          ]"
          :title="t('chatView.searchBranches')"
          @click="toggleSearch"
        >
          <Search class="w-3.5 h-3.5" />
        </button>
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

    <!-- Search bar -->
    <div v-if="showSearch" class="px-3 py-2 border-b border-border flex items-center gap-2 flex-shrink-0">
      <input
        v-model="searchQuery"
        data-branch-search
        class="flex-1 min-w-0 text-xs bg-background border border-border rounded px-2 py-1 outline-none focus:ring-1 focus:ring-primary"
        :placeholder="t('chatView.searchPlaceholder')"
      />
      <span v-if="searchQuery && !searchLoading" class="text-[10px] text-muted-foreground whitespace-nowrap">
        {{ searchResults.length > 0 ? t('chatView.searchResults', { n: searchResults.length }) : t('chatView.noSearchResults') }}
      </span>
      <span v-if="searchLoading" class="text-[10px] text-muted-foreground animate-pulse">...</span>
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
          :collapsed-nodes="collapsedNodes"
          :search-match-ids="searchMatchIds"
          @click-node="handleClick"
          @scroll-to="handleScrollTo"
          @delete-node="handleDeleteNode"
          @toggle-select="toggleSelect"
          @toggle-collapse="toggleCollapse"
          @rename-node="handleRenameNode"
          @pin-node="handlePinNode"
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
