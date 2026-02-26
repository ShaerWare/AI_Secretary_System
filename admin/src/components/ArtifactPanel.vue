<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { X, Copy, Code2, Eye } from 'lucide-vue-next'
import { useToastStore } from '@/stores/toast'

export interface Artifact {
  id: string
  language: string
  code: string
  messageId: string
}

const props = defineProps<{
  artifact: Artifact
}>()

const emit = defineEmits<{
  close: []
}>()

const { t } = useI18n()
const toastStore = useToastStore()

const activeTab = ref<'code' | 'preview'>('code')

// Reset tab to code when artifact changes
watch(() => props.artifact.id, () => {
  activeTab.value = 'code'
})

const renderedPreview = computed(() => {
  if (!props.artifact.code) return ''
  // Wrap code in a fenced block for markdown rendering
  const lang = props.artifact.language || ''
  const md = '```' + lang + '\n' + props.artifact.code + '\n```'
  return DOMPurify.sanitize(marked.parse(md) as string)
})

function copyCode() {
  navigator.clipboard.writeText(props.artifact.code)
  toastStore.success(t('common.copied'))
}
</script>

<template>
  <div class="border-l border-border bg-card flex flex-col flex-shrink-0 overflow-hidden">
    <!-- Header -->
    <div class="p-3 border-b border-border flex items-center justify-between">
      <div class="flex items-center gap-2 min-w-0">
        <Code2 class="w-4 h-4 text-muted-foreground shrink-0" />
        <span class="text-xs font-semibold text-muted-foreground uppercase truncate">
          {{ t('chatView.artifactViewer') }}
        </span>
        <span v-if="artifact.language" class="text-xs text-muted-foreground font-mono">
          · {{ artifact.language }}
        </span>
      </div>
      <div class="flex items-center gap-1">
        <button
          class="p-1.5 rounded hover:bg-secondary text-muted-foreground transition-colors"
          :title="t('common.copy')"
          @click="copyCode"
        >
          <Copy class="w-3.5 h-3.5" />
        </button>
        <button
          class="p-1.5 rounded hover:bg-secondary text-muted-foreground transition-colors"
          @click="emit('close')"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex border-b border-border">
      <button
        :class="[
          'flex-1 px-3 py-2 text-xs font-medium flex items-center justify-center gap-1.5 transition-colors',
          activeTab === 'code'
            ? 'text-foreground border-b-2 border-primary'
            : 'text-muted-foreground hover:text-foreground'
        ]"
        @click="activeTab = 'code'"
      >
        <Code2 class="w-3.5 h-3.5" />
        {{ t('chatView.artifactCode') }}
      </button>
      <button
        :class="[
          'flex-1 px-3 py-2 text-xs font-medium flex items-center justify-center gap-1.5 transition-colors',
          activeTab === 'preview'
            ? 'text-foreground border-b-2 border-primary'
            : 'text-muted-foreground hover:text-foreground'
        ]"
        @click="activeTab = 'preview'"
      >
        <Eye class="w-3.5 h-3.5" />
        {{ t('chatView.artifactPreview') }}
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-auto">
      <!-- Code tab -->
      <div v-if="activeTab === 'code'" class="p-4">
        <pre class="text-sm font-mono leading-relaxed whitespace-pre-wrap break-words"><code>{{ artifact.code }}</code></pre>
      </div>

      <!-- Preview tab -->
      <div v-else class="p-4 chat-markdown" v-html="renderedPreview"></div>
    </div>
  </div>
</template>
