<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { wikiRagApi, type KnowledgeDocument } from '@/api/wikiRag'
import { BookOpen, Search, ArrowLeft, FileText, Loader2 } from 'lucide-vue-next'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const { t } = useI18n()

// State
const searchQuery = ref('')
const selectedDocId = ref<number | null>(null)
const isMobileDetail = ref(false)

// Fetch document list
const { data: docsData, isLoading: isLoadingList } = useQuery({
  queryKey: ['wiki-documents'],
  queryFn: () => wikiRagApi.getDocuments(),
})

// Fetch selected document content
const { data: docDetail, isLoading: isLoadingDoc } = useQuery({
  queryKey: computed(() => ['wiki-document', selectedDocId.value]),
  queryFn: () => wikiRagApi.getDocument(selectedDocId.value!),
  enabled: computed(() => selectedDocId.value != null),
})

// Filtered list
const documents = computed(() => {
  if (!docsData.value?.documents) return []
  let docs = docsData.value.documents
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    docs = docs.filter(d => d.title.toLowerCase().includes(q) || d.filename.toLowerCase().includes(q))
  }
  return docs.sort((a, b) => a.title.localeCompare(b.title))
})

// Rendered markdown
const renderedContent = computed(() => {
  const raw = docDetail.value?.content_preview
  if (!raw) return ''
  return DOMPurify.sanitize(marked.parse(raw) as string)
})

const selectedDoc = computed(() => {
  if (!selectedDocId.value || !docsData.value?.documents) return null
  return docsData.value.documents.find(d => d.id === selectedDocId.value) ?? null
})

function selectDoc(doc: KnowledgeDocument) {
  selectedDocId.value = doc.id
  isMobileDetail.value = true
}

function goBack() {
  isMobileDetail.value = false
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

// Reset detail when doc changes
watch(selectedDocId, () => {
  // just triggers refetch via queryKey
})
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-4">
      <BookOpen class="w-6 h-6 text-primary" />
      <h1 class="text-xl font-bold">{{ t('wiki.title') }}</h1>
      <span v-if="docsData?.documents" class="text-sm text-muted-foreground">
        ({{ documents.length }})
      </span>
    </div>

    <!-- Main layout -->
    <div class="flex-1 min-h-0 flex gap-4">
      <!-- List panel -->
      <div
        :class="[
          'flex flex-col border border-border rounded-lg bg-card overflow-hidden',
          selectedDocId ? 'hidden md:flex md:w-72 lg:w-80 shrink-0' : 'flex-1'
        ]"
      >
        <!-- Search -->
        <div class="p-3 border-b border-border">
          <div class="relative">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              v-model="searchQuery"
              type="text"
              :placeholder="t('wiki.search')"
              class="w-full pl-10 pr-4 py-2 bg-secondary rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>

        <!-- Document list -->
        <div class="flex-1 overflow-y-auto">
          <div v-if="isLoadingList" class="p-8 text-center text-muted-foreground">
            <Loader2 class="w-5 h-5 animate-spin mx-auto mb-2" />
            {{ t('wiki.loading') }}
          </div>

          <div v-else-if="documents.length === 0" class="p-8 text-center text-muted-foreground">
            {{ t('wiki.noPages') }}
          </div>

          <div v-else class="divide-y divide-border">
            <button
              v-for="doc in documents"
              :key="doc.id"
              :class="[
                'w-full text-left p-3 transition-colors hover:bg-secondary/50',
                selectedDocId === doc.id ? 'bg-primary/10 border-l-2 border-l-primary' : ''
              ]"
              @click="selectDoc(doc)"
            >
              <div class="font-medium text-sm truncate">{{ doc.title }}</div>
              <div class="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                <span>{{ doc.section_count }} {{ t('wiki.sections') }}</span>
                <span>{{ formatSize(doc.file_size_bytes) }}</span>
              </div>
            </button>
          </div>
        </div>
      </div>

      <!-- Content panel -->
      <div
        v-if="selectedDocId"
        :class="[
          'flex-1 flex flex-col border border-border rounded-lg bg-card overflow-hidden',
          isMobileDetail ? 'flex' : 'hidden md:flex'
        ]"
      >
        <!-- Content header -->
        <div class="flex items-center gap-3 p-4 border-b border-border">
          <button
            class="md:hidden p-1.5 rounded-lg hover:bg-secondary transition-colors"
            @click="goBack"
          >
            <ArrowLeft class="w-5 h-5" />
          </button>
          <FileText class="w-5 h-5 text-primary shrink-0" />
          <h2 class="font-semibold truncate">{{ selectedDoc?.title }}</h2>
        </div>

        <!-- Rendered content -->
        <div class="flex-1 overflow-y-auto p-6">
          <div v-if="isLoadingDoc" class="flex items-center justify-center py-12 text-muted-foreground">
            <Loader2 class="w-5 h-5 animate-spin mr-2" />
            {{ t('wiki.loading') }}
          </div>
          <div v-else class="chat-markdown max-w-none" v-html="renderedContent"></div>
        </div>
      </div>

      <!-- Empty state (desktop, nothing selected) -->
      <div
        v-if="!selectedDocId && docsData?.documents?.length"
        class="hidden md:flex flex-1 items-center justify-center border border-border rounded-lg bg-card"
      >
        <div class="text-center text-muted-foreground">
          <BookOpen class="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>{{ t('wiki.selectPage') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
