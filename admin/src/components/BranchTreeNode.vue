<script setup lang="ts">
import { ref } from 'vue'
import { ChevronRight, ChevronDown, User, Bot, Settings } from 'lucide-vue-next'
import type { BranchNode } from '@/api/chat'

const props = defineProps<{
  node: BranchNode
  depth: number
}>()

const emit = defineEmits<{
  'click-node': [messageId: string]
  'scroll-to': [messageId: string]
}>()

const collapsed = ref(false)

const isAssistant = props.node.role === 'assistant'
const isSystem = props.node.role === 'system'
const hasChildren = props.node.children.length > 0
const hasBranches = props.node.children.length > 1

function onClick() {
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

function onChildClick(messageId: string) {
  emit('click-node', messageId)
}

function onChildScrollTo(messageId: string) {
  emit('scroll-to', messageId)
}
</script>

<template>
  <div>
    <div
      :class="[
        'flex items-center gap-1.5 rounded cursor-pointer transition-colors group/node',
        isAssistant ? 'py-0.5 px-1' : 'py-1 px-1',
        node.is_active
          ? 'hover:bg-secondary/80'
          : 'opacity-50 hover:opacity-75 hover:bg-secondary/50',
      ]"
      :style="{ paddingLeft: `${depth * 14 + (isAssistant ? 18 : 4)}px` }"
      :title="node.content_preview"
      @click="onClick"
    >
      <!-- Collapse toggle (only if has children) -->
      <button
        v-if="hasChildren"
        class="w-3.5 h-3.5 flex items-center justify-center flex-shrink-0 text-muted-foreground hover:text-foreground"
        @click="toggleCollapse"
      >
        <ChevronRight v-if="collapsed" class="w-3 h-3" />
        <ChevronDown v-else class="w-3 h-3" />
      </button>
      <span v-else class="w-3.5 h-3.5 flex-shrink-0" />

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
        v-if="hasBranches"
        class="ml-auto text-[10px] bg-primary/15 text-primary px-1 rounded-full flex-shrink-0"
      >
        {{ node.children.length }}
      </span>
    </div>

    <!-- Children (collapsible) -->
    <div v-if="hasChildren && !collapsed">
      <!-- Branch indicator line for multiple children -->
      <div :class="hasBranches ? 'border-l border-primary/20' : ''" :style="{ marginLeft: `${depth * 14 + 10}px` }">
        <BranchTreeNode
          v-for="child in node.children"
          :key="child.id"
          :node="child"
          :depth="hasBranches ? depth + 1 : depth"
          @click-node="onChildClick"
          @scroll-to="onChildScrollTo"
        />
      </div>
    </div>
  </div>
</template>
