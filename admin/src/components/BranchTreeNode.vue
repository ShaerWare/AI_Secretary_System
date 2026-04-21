<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { ChevronRight, ChevronDown, User, Bot, Settings, Trash2, Pencil, Check, X, Pin, PinOff } from 'lucide-vue-next'
import type { BranchNode } from '@/api/chat'

const props = defineProps<{
  node: BranchNode
  depth: number
  deleteMode: boolean
  selectedForDelete: Set<string>
  collapsedNodes: Set<string>
  searchMatchIds?: Set<string>
}>()

const emit = defineEmits<{
  'click-node': [messageId: string]
  'scroll-to': [messageId: string]
  'delete-node': [messageId: string]
  'toggle-select': [messageId: string]
  'toggle-collapse': [messageId: string]
  'rename-node': [messageId: string, name: string]
  'pin-node': [messageId: string, pinned: boolean]
}>()

const collapsed = computed(() => props.collapsedNodes.has(props.node.id))
const isMatch = computed(() => props.searchMatchIds?.has(props.node.id) ?? false)

const maxVisualDepth = 8
const visualDepth = Math.min(props.depth, maxVisualDepth)

const isAssistant = props.node.role === 'assistant'
const isSystem = props.node.role === 'system'
const hasChildren = props.node.children.length > 0
const hasBranches = props.node.children.length > 1

// Inline rename
const editing = ref(false)
const editName = ref('')
const editInput = ref<HTMLInputElement | null>(null)

function startRename(e: Event) {
  e.stopPropagation()
  editName.value = props.node.branch_name || ''
  editing.value = true
  nextTick(() => editInput.value?.focus())
}

function confirmRename() {
  editing.value = false
  emit('rename-node', props.node.id, editName.value.trim())
}

function cancelRename(e?: Event) {
  e?.stopPropagation()
  editing.value = false
}

function onRenameKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') confirmRename()
  else if (e.key === 'Escape') cancelRename()
}

function onClick() {
  if (editing.value) return
  if (props.deleteMode) {
    emit('toggle-select', props.node.id)
    return
  }
  if (props.node.is_active) {
    emit('scroll-to', props.node.id)
  } else {
    emit('click-node', props.node.id)
  }
}

function toggleCollapse(e: Event) {
  e.stopPropagation()
  emit('toggle-collapse', props.node.id)
}

function onDeleteNode(e: Event) {
  e.stopPropagation()
  emit('delete-node', props.node.id)
}

function onChildClick(messageId: string) { emit('click-node', messageId) }
function onChildScrollTo(messageId: string) { emit('scroll-to', messageId) }
function onChildDeleteNode(messageId: string) { emit('delete-node', messageId) }
function onChildToggleSelect(messageId: string) { emit('toggle-select', messageId) }
function onChildToggleCollapse(messageId: string) { emit('toggle-collapse', messageId) }
function onChildRename(messageId: string, name: string) { emit('rename-node', messageId, name) }
function onChildPin(messageId: string, pinned: boolean) { emit('pin-node', messageId, pinned) }

function onPinNode(e: Event) {
  e.stopPropagation()
  emit('pin-node', props.node.id, !props.node.is_pinned)
}
</script>

<template>
  <div>
    <div
      :class="[
        'flex items-center gap-1.5 rounded cursor-pointer transition-colors group/node',
        isAssistant ? 'py-0.5 px-1' : 'py-1 px-1',
        isMatch
          ? 'bg-yellow-500/20 ring-1 ring-yellow-500/40'
          : deleteMode && selectedForDelete.has(node.id)
            ? 'bg-destructive/15 hover:bg-destructive/25'
            : node.is_active
              ? 'hover:bg-secondary/80'
              : 'opacity-50 hover:opacity-75 hover:bg-secondary/50',
      ]"
      :style="{ paddingLeft: `${visualDepth * 14 + (isAssistant ? 18 : 4)}px` }"
      data-branch-node
      :title="node.branch_name || node.content_preview"
      @click="onClick"
    >
      <!-- Checkbox in delete mode -->
      <input
        v-if="deleteMode"
        type="checkbox"
        :checked="selectedForDelete.has(node.id)"
        class="w-3.5 h-3.5 flex-shrink-0 accent-destructive pointer-events-none"
        tabindex="-1"
      />

      <!-- Collapse toggle (only if has children, not in delete mode) -->
      <template v-else>
        <button
          v-if="hasChildren"
          class="w-3.5 h-3.5 flex items-center justify-center flex-shrink-0 text-muted-foreground hover:text-foreground"
          @click="toggleCollapse"
        >
          <ChevronRight v-if="collapsed" class="w-3 h-3" />
          <ChevronDown v-else class="w-3 h-3" />
        </button>
        <span v-else class="w-3.5 h-3.5 flex-shrink-0" />
      </template>

      <!-- Role icon -->
      <span
        v-if="isSystem"
        :class="['flex-shrink-0', node.is_active ? 'text-amber-500' : 'text-muted-foreground/50']"
      >
        <Settings class="w-3 h-3" />
      </span>
      <span
        v-else-if="isAssistant"
        :class="['flex-shrink-0', node.is_active ? 'text-emerald-500' : 'text-muted-foreground/50']"
      >
        <Bot class="w-3 h-3" />
      </span>
      <span
        v-else
        :class="['flex-shrink-0', node.is_active ? 'text-primary' : 'text-muted-foreground/50']"
      >
        <User class="w-3 h-3" />
      </span>

      <!-- Inline rename editor -->
      <template v-if="editing">
        <input
          ref="editInput"
          v-model="editName"
          class="flex-1 min-w-0 text-xs bg-background border border-border rounded px-1 py-0.5 outline-none focus:ring-1 focus:ring-primary"
          @keydown="onRenameKeydown"
          @click.stop
        />
        <button class="p-0.5 text-emerald-500 hover:text-emerald-400 flex-shrink-0" @click.stop="confirmRename">
          <Check class="w-3 h-3" />
        </button>
        <button class="p-0.5 text-muted-foreground hover:text-foreground flex-shrink-0" @click.stop="cancelRename">
          <X class="w-3 h-3" />
        </button>
      </template>

      <!-- Content preview / branch name -->
      <template v-else>
        <span
          :class="[
            'truncate',
            isAssistant ? 'text-[11px]' : 'text-xs',
            node.branch_name ? 'italic' : '',
            node.is_active
              ? isAssistant ? 'text-muted-foreground' : 'text-foreground font-medium'
              : 'text-muted-foreground',
          ]"
        >
          {{ node.branch_name || node.content_preview }}
        </span>

        <!-- Branch count badge -->
        <span
          v-if="hasBranches && !deleteMode"
          class="ml-auto text-[10px] bg-primary/15 text-primary px-1 rounded-full flex-shrink-0"
        >
          {{ node.children.length }}
        </span>

        <!-- Pinned indicator -->
        <Pin v-if="node.is_pinned" class="w-2.5 h-2.5 text-primary flex-shrink-0" />

        <!-- Action buttons (hover-visible, outside delete mode) -->
        <div v-if="!deleteMode" class="ml-auto flex items-center gap-0.5 opacity-0 group-hover/node:opacity-100 transition-all flex-shrink-0" :class="{ 'ml-1': hasBranches }">
          <button
            class="p-0.5 rounded hover:bg-primary/10 transition-colors"
            :class="node.is_pinned ? 'text-primary' : 'text-muted-foreground hover:text-primary'"
            :title="node.is_pinned ? 'Открепить' : 'Закрепить'"
            @click="onPinNode"
          >
            <PinOff v-if="node.is_pinned" class="w-3 h-3" />
            <Pin v-else class="w-3 h-3" />
          </button>
          <button
            class="p-0.5 rounded text-muted-foreground hover:text-primary hover:bg-primary/10"
            @click="startRename"
          >
            <Pencil class="w-3 h-3" />
          </button>
          <button
            class="p-0.5 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10"
            @click="onDeleteNode"
          >
            <Trash2 class="w-3 h-3" />
          </button>
        </div>
      </template>
    </div>

    <!-- Children (collapsible) -->
    <div v-if="hasChildren && !collapsed">
      <div :class="hasBranches ? 'border-l border-primary/20' : ''" :style="{ marginLeft: `${visualDepth * 14 + 10}px` }">
        <BranchTreeNode
          v-for="child in node.children"
          :key="child.id"
          :node="child"
          :depth="hasBranches ? depth + 1 : depth"
          :delete-mode="deleteMode"
          :selected-for-delete="selectedForDelete"
          :collapsed-nodes="collapsedNodes"
          :search-match-ids="searchMatchIds"
          @click-node="onChildClick"
          @scroll-to="onChildScrollTo"
          @delete-node="onChildDeleteNode"
          @toggle-select="onChildToggleSelect"
          @toggle-collapse="onChildToggleCollapse"
          @rename-node="onChildRename"
          @pin-node="onChildPin"
        />
      </div>
    </div>
  </div>
</template>
