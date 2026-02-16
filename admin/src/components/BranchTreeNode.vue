<script setup lang="ts">
import type { BranchNode } from '@/api/chat'

const props = defineProps<{
  node: BranchNode
  depth: number
}>()

const emit = defineEmits<{
  'click-node': [messageId: string]
  'scroll-to': [messageId: string]
}>()

function roleColor(role: string, isActive: boolean): string {
  if (!isActive) return 'bg-muted-foreground/30'
  switch (role) {
    case 'user': return 'bg-primary'
    case 'assistant': return 'bg-emerald-500'
    case 'system': return 'bg-amber-500'
    default: return 'bg-muted-foreground'
  }
}

function onClick() {
  if (props.node.is_active) {
    emit('scroll-to', props.node.id)
  } else {
    emit('click-node', props.node.id)
  }
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
        'flex items-center gap-1.5 py-1 px-1 rounded cursor-pointer text-xs transition-colors',
        node.is_active
          ? 'hover:bg-secondary/80'
          : 'opacity-50 hover:opacity-75 hover:bg-secondary/50',
      ]"
      :style="{ paddingLeft: `${depth * 12 + 4}px` }"
      :title="node.content_preview"
      @click="onClick"
    >
      <span
        :class="[
          'w-2.5 h-2.5 rounded-full flex-shrink-0 ring-1',
          roleColor(node.role, node.is_active),
          node.is_active ? 'ring-foreground/20' : 'ring-transparent',
        ]"
      />
      <span :class="['truncate', node.is_active ? 'text-foreground font-medium' : 'text-muted-foreground']">
        {{ node.content_preview }}
      </span>
    </div>

    <!-- Recursive children -->
    <div v-if="node.children.length > 0" :class="node.children.length > 1 ? 'border-l border-muted-foreground/20 ml-2' : ''">
      <BranchTreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :depth="node.children.length > 1 ? depth + 1 : depth"
        @click-node="onChildClick"
        @scroll-to="onChildScrollTo"
      />
    </div>
  </div>
</template>
