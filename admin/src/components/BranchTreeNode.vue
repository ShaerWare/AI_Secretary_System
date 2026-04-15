<script setup lang="ts">
import { ref } from 'vue'
import { ChevronRight, ChevronDown, User, Bot, Settings, Trash2 } from 'lucide-vue-next'
import type { BranchNode } from '@/api/chat'

const props = defineProps<{
  node: BranchNode
  depth: number
  deleteMode: boolean
  selectedForDelete: Set<string>
}>()

const emit = defineEmits<{
  'click-node': [messageId: string]
  'scroll-to': [messageId: string]
  'delete-node': [messageId: string]
  'toggle-select': [messageId: string]
}>()

const collapsed = ref(true)

const maxVisualDepth = 8
const visualDepth = Math.min(props.depth, maxVisualDepth)

const isAssistant = props.node.role === 'assistant'
const isSystem = props.node.role === 'system'
const hasChildren = props.node.children.length > 0
const hasBranches = props.node.children.length > 1

function onClick() {
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
  collapsed.value = !collapsed.value
}

function onDeleteNode(e: Event) {
  e.stopPropagation()
  emit('delete-node', props.node.id)
}

function onChildClick(messageId: string) {
  emit('click-node', messageId)
}

function onChildScrollTo(messageId: string) {
  emit('scroll-to', messageId)
}

function onChildDeleteNode(messageId: string) {
  emit('delete-node', messageId)
}

function onChildToggleSelect(messageId: string) {
  emit('toggle-select', messageId)
}
</script>

<template>
  <div>
    <div
      :class="[
        'flex items-center gap-1.5 rounded cursor-pointer transition-colors group/node',
        isAssistant ? 'py-0.5 px-1' : 'py-1 px-1',
        deleteMode && selectedForDelete.has(node.id)
          ? 'bg-destructive/15 hover:bg-destructive/25'
          : node.is_active
            ? 'hover:bg-secondary/80'
            : 'opacity-50 hover:opacity-75 hover:bg-secondary/50',
      ]"
      :style="{ paddingLeft: `${visualDepth * 14 + (isAssistant ? 18 : 4)}px` }"
      data-branch-node
      :title="node.content_preview"
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
        :class="[
          'flex-shrink-0',
          node.is_active ? 'text-amber-500' : 'text-muted-foreground/50',
        ]"
      >
        <Settings class="w-3 h-3" />
      </span>
      <span
        v-else-if="isAssistant"
        :class="[
          'flex-shrink-0',
          node.is_active ? 'text-emerald-500' : 'text-muted-foreground/50',
        ]"
      >
        <Bot class="w-3 h-3" />
      </span>
      <span
        v-else
        :class="[
          'flex-shrink-0',
          node.is_active ? 'text-primary' : 'text-muted-foreground/50',
        ]"
      >
        <User class="w-3 h-3" />
      </span>

      <!-- Content preview -->
      <span
        :class="[
          'truncate',
          isAssistant ? 'text-[11px]' : 'text-xs',
          node.is_active
            ? isAssistant ? 'text-muted-foreground' : 'text-foreground font-medium'
            : 'text-muted-foreground',
        ]"
      >
        {{ node.content_preview }}
      </span>

      <!-- Branch count badge -->
      <span
        v-if="hasBranches && !deleteMode"
        class="ml-auto text-[10px] bg-primary/15 text-primary px-1 rounded-full flex-shrink-0"
      >
        {{ node.children.length }}
      </span>

      <!-- Delete button (hover-visible, outside delete mode) -->
      <button
        v-if="!deleteMode"
        class="ml-auto p-0.5 rounded opacity-0 group-hover/node:opacity-100 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all flex-shrink-0"
        :class="{ 'ml-1': hasBranches }"
        @click="onDeleteNode"
      >
        <Trash2 class="w-3 h-3" />
      </button>
    </div>

    <!-- Children (collapsible) -->
    <div v-if="hasChildren && !collapsed">
      <!-- Branch indicator line for multiple children -->
      <div :class="hasBranches ? 'border-l border-primary/20' : ''" :style="{ marginLeft: `${visualDepth * 14 + 10}px` }">
        <BranchTreeNode
          v-for="child in node.children"
          :key="child.id"
          :node="child"
          :depth="hasBranches ? depth + 1 : depth"
          :delete-mode="deleteMode"
          :selected-for-delete="selectedForDelete"
          @click-node="onChildClick"
          @scroll-to="onChildScrollTo"
          @delete-node="onChildDeleteNode"
          @toggle-select="onChildToggleSelect"
        />
      </div>
    </div>
  </div>
</template>
