<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { GitBranch, X } from 'lucide-vue-next'
import type { BranchNode } from '@/api/chat'
import BranchTreeNode from '@/components/BranchTreeNode.vue'

const props = defineProps<{
  branches: BranchNode[]
  sessionId: string
}>()

const emit = defineEmits<{
  switch: [messageId: string]
  'scroll-to': [messageId: string]
  close: []
}>()

const { t } = useI18n()

function handleClick(messageId: string) {
  emit('switch', messageId)
}

function handleScrollTo(messageId: string) {
  emit('scroll-to', messageId)
}
</script>

<template>
  <div class="border-l border-border bg-card/50 overflow-y-auto flex-shrink-0">
    <div class="p-3 border-b border-border flex items-center justify-between">
      <h3 class="text-xs font-semibold text-muted-foreground uppercase flex items-center gap-1.5">
        <GitBranch class="w-3.5 h-3.5" />
        {{ t('chatView.branchTree') }}
      </h3>
      <button
        class="p-1 rounded hover:bg-secondary text-muted-foreground transition-colors"
        @click="emit('close')"
      >
        <X class="w-3.5 h-3.5" />
      </button>
    </div>

    <div v-if="branches.length > 0" class="p-2">
      <BranchTreeNode
        v-for="root in branches"
        :key="root.id"
        :node="root"
        :depth="0"
        @click-node="handleClick"
        @scroll-to="handleScrollTo"
      />
    </div>
    <div v-else class="p-4 text-center text-xs text-muted-foreground">
      {{ t('chatView.noBranches') }}
    </div>
  </div>
</template>
