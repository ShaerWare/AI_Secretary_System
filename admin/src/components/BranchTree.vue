<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { GitBranch, Plus, X } from 'lucide-vue-next'
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
}>()

const { t } = useI18n()

function handleClick(messageId: string) {
  emit('switch', messageId)
}

function handleScrollTo(messageId: string) {
  emit('scroll-to', messageId)
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
  if ((e.target as HTMLElement).closest('[data-branch-node], button')) return
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
          @click-node="handleClick"
          @scroll-to="handleScrollTo"
        />
      </div>
    </div>
    <div v-else class="p-4 text-center text-xs text-muted-foreground">
      {{ t('chatView.noBranches') }}
    </div>
  </div>
</template>
