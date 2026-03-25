<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { wikiRagApi, type KnowledgeDocument } from '@/api/wikiRag'
import { googleApi, type GoogleDriveFile, type GoogleDriveProject } from '@/api/google'
import { BookOpen, Search, ArrowLeft, FileText, Loader2, RefreshCw, Trash2, Plus, FolderOpen, X, HardDrive } from 'lucide-vue-next'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToastStore } from '@/stores/toast'
import { useConfirmStore } from '@/stores/confirm'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const { t } = useI18n()
const toast = useToastStore()
const confirm = useConfirmStore()
const queryClient = useQueryClient()

const activeTab = ref<'docs' | 'gdrive'>('docs')

// ─── Documents tab ───────────────────────────────────────────
const searchQuery = ref('')
const selectedDocId = ref<number | null>(null)
const isMobileDetail = ref(false)

const { data: docsData, isLoading: isLoadingList } = useQuery({
  queryKey: ['wiki-documents'],
  queryFn: () => wikiRagApi.getDocuments(),
})

const { data: docDetail, isLoading: isLoadingDoc } = useQuery({
  queryKey: computed(() => ['wiki-document', selectedDocId.value]),
  queryFn: () => wikiRagApi.getDocument(selectedDocId.value!),
  enabled: computed(() => selectedDocId.value != null),
})

const documents = computed(() => {
  if (!docsData.value?.documents) return []
  let docs = docsData.value.documents
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    docs = docs.filter(d => d.title.toLowerCase().includes(q) || d.filename.toLowerCase().includes(q))
  }
  return docs.sort((a, b) => a.title.localeCompare(b.title))
})

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
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

watch(selectedDocId, () => {})

// ─── Google Drive RAG tab ────────────────────────────────────
const googleConnected = ref(false)
const showCreateForm = ref(false)
const showDrivePicker = ref(false)
const newProjectName = ref('')
const selectedFolder = ref<{ id: string; name: string }>({ id: 'root', name: 'My Drive' })

// Drive browser state
const gdriveFiles = ref<GoogleDriveFile[]>([])
const gdriveLoading = ref(false)
const gdrivePath = ref<{ id: string; name: string }[]>([])
const gdriveSearchQuery = ref('')

const { data: driveProjects, refetch: refetchProjects } = useQuery({
  queryKey: ['gdrive-rag-projects'],
  queryFn: () => googleApi.driveRagProjects(),
  enabled: computed(() => activeTab.value === 'gdrive'),
  refetchInterval: 10000,
})

async function checkGoogle() {
  try {
    const s = await googleApi.getStatus()
    googleConnected.value = s.connected
  } catch { googleConnected.value = false }
}

const createMutation = useMutation({
  mutationFn: (data: { name: string; folder_id: string; folder_name?: string }) =>
    googleApi.createDriveRagProject(data),
  onSuccess: () => {
    toast.success('Проект создан, синхронизация запущена')
    showCreateForm.value = false
    newProjectName.value = ''
    queryClient.invalidateQueries({ queryKey: ['gdrive-rag-projects'] })
  },
  onError: () => toast.error('Ошибка создания проекта'),
})

const syncMutation = useMutation({
  mutationFn: (id: number) => googleApi.syncDriveRagProject(id),
  onSuccess: () => {
    toast.success('Синхронизация запущена')
    queryClient.invalidateQueries({ queryKey: ['gdrive-rag-projects'] })
  },
  onError: () => toast.error('Ошибка синхронизации'),
})

const deleteMutation = useMutation({
  mutationFn: (id: number) => googleApi.deleteDriveRagProject(id),
  onSuccess: () => {
    toast.success('Проект удалён')
    queryClient.invalidateQueries({ queryKey: ['gdrive-rag-projects'] })
  },
  onError: () => toast.error('Ошибка удаления'),
})

async function deleteProject(project: GoogleDriveProject) {
  const ok = await confirm.confirm({
    title: 'Удалить проект',
    message: `Удалить "${project.name}" и все индексированные документы?`,
    confirmText: 'Удалить',
    type: 'danger',
  })
  if (ok) deleteMutation.mutate(project.id)
}

function createProject() {
  if (!newProjectName.value.trim()) return
  createMutation.mutate({
    name: newProjectName.value.trim(),
    folder_id: selectedFolder.value.id,
    folder_name: selectedFolder.value.name,
  })
}

// Drive picker
async function loadDriveFolder(folderId = 'root') {
  gdriveLoading.value = true
  try {
    const result = await googleApi.driveList(folderId)
    gdriveFiles.value = result.files
  } catch { gdriveFiles.value = [] }
  finally { gdriveLoading.value = false }
}

async function searchDrive() {
  if (!gdriveSearchQuery.value.trim()) { loadDriveFolder('root'); return }
  gdriveLoading.value = true
  try {
    const result = await googleApi.driveSearch(gdriveSearchQuery.value)
    gdriveFiles.value = result.files
    gdrivePath.value = []
  } catch { gdriveFiles.value = [] }
  finally { gdriveLoading.value = false }
}

function navigateDrive(folderId: string, idx?: number) {
  if (folderId === 'root') gdrivePath.value = []
  else if (idx !== undefined) gdrivePath.value = gdrivePath.value.slice(0, idx + 1)
  gdriveSearchQuery.value = ''
  loadDriveFolder(folderId)
}

function enterDriveFolder(folder: GoogleDriveFile) {
  gdrivePath.value.push({ id: folder.id, name: folder.name })
  gdriveSearchQuery.value = ''
  loadDriveFolder(folder.id)
}

function selectDriveFolder(folder?: GoogleDriveFile) {
  if (folder) {
    selectedFolder.value = { id: folder.id, name: folder.name }
  } else {
    // Use current browsed folder
    const last = gdrivePath.value[gdrivePath.value.length - 1]
    selectedFolder.value = last || { id: 'root', name: 'My Drive' }
  }
  showDrivePicker.value = false
}

function openDrivePicker() {
  showDrivePicker.value = true
  gdrivePath.value = []
  gdriveSearchQuery.value = ''
  loadDriveFolder('root')
}

function gdriveIcon(file: GoogleDriveFile): string {
  if (file.isFolder) return '\ud83d\udcc1'
  const mt = file.mimeType
  if (mt.includes('document')) return '\ud83d\udcd4'
  if (mt.includes('spreadsheet')) return '\ud83d\udcca'
  if (mt.includes('presentation')) return '\ud83d\udcfd\ufe0f'
  if (mt.includes('pdf')) return '\ud83d\udcc4'
  return '\ud83d\udcc3'
}

watch(activeTab, (tab) => {
  if (tab === 'gdrive') checkGoogle()
})
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-4">
      <BookOpen class="w-6 h-6 text-primary" />
      <h1 class="text-xl font-bold">{{ t('wiki.title') }}</h1>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 mb-4 border-b border-border">
      <button
        :class="['px-4 py-2 text-sm font-medium border-b-2 transition-colors', activeTab === 'docs' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground']"
        @click="activeTab = 'docs'"
      >
        <FileText class="w-4 h-4 inline mr-1.5" />
        {{ t('wiki.documents') || 'Документы' }}
        <span v-if="docsData?.documents" class="text-xs ml-1 opacity-60">({{ documents.length }})</span>
      </button>
      <button
        :class="['px-4 py-2 text-sm font-medium border-b-2 transition-colors', activeTab === 'gdrive' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground']"
        @click="activeTab = 'gdrive'"
      >
        <HardDrive class="w-4 h-4 inline mr-1.5" />
        Google Drive
        <span v-if="driveProjects?.length" class="text-xs ml-1 opacity-60">({{ driveProjects.length }})</span>
      </button>
    </div>

    <!-- Documents tab (original) -->
    <div v-if="activeTab === 'docs'" class="flex-1 min-h-0 flex gap-4">
      <!-- List panel -->
      <div
        :class="[
          'flex flex-col border border-border rounded-lg bg-card overflow-hidden',
          selectedDocId ? 'hidden md:flex md:w-72 lg:w-80 shrink-0' : 'flex-1'
        ]"
      >
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
              :class="['w-full text-left p-3 transition-colors hover:bg-secondary/50', selectedDocId === doc.id ? 'bg-primary/10 border-l-2 border-l-primary' : '']"
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
        :class="['flex-1 flex flex-col border border-border rounded-lg bg-card overflow-hidden', isMobileDetail ? 'flex' : 'hidden md:flex']"
      >
        <div class="flex items-center gap-3 p-4 border-b border-border">
          <button class="md:hidden p-1.5 rounded-lg hover:bg-secondary transition-colors" @click="goBack">
            <ArrowLeft class="w-5 h-5" />
          </button>
          <FileText class="w-5 h-5 text-primary shrink-0" />
          <h2 class="font-semibold truncate">{{ selectedDoc?.title }}</h2>
        </div>
        <div class="flex-1 overflow-y-auto p-6">
          <div v-if="isLoadingDoc" class="flex items-center justify-center py-12 text-muted-foreground">
            <Loader2 class="w-5 h-5 animate-spin mr-2" />
            {{ t('wiki.loading') }}
          </div>
          <div v-else class="chat-markdown max-w-none" v-html="renderedContent"></div>
        </div>
      </div>

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

    <!-- Google Drive RAG tab -->
    <div v-if="activeTab === 'gdrive'" class="flex-1 min-h-0 overflow-y-auto space-y-4">
      <!-- Not connected -->
      <div v-if="!googleConnected" class="p-8 text-center bg-card border border-border rounded-lg">
        <HardDrive class="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-30" />
        <p class="text-muted-foreground mb-3">Подключите Google аккаунт в настройках для работы с Drive</p>
        <router-link to="/settings" class="text-primary hover:underline text-sm">Перейти в настройки</router-link>
      </div>

      <!-- Connected -->
      <template v-else>
        <!-- Project list -->
        <div class="space-y-3">
          <div v-for="project in driveProjects" :key="project.id" class="bg-card border border-border rounded-lg p-4">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <h3 class="font-medium truncate">{{ project.name }}</h3>
                <div class="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                  <span class="flex items-center gap-1">
                    <FolderOpen class="w-3 h-3" />
                    {{ project.folder_name || project.folder_id }}
                  </span>
                  <span>{{ project.file_count }} файлов</span>
                  <span>{{ formatSize(project.total_size_bytes) }}</span>
                </div>
                <div v-if="project.last_synced" class="text-xs text-muted-foreground mt-1">
                  Последняя синхронизация: {{ new Date(project.last_synced).toLocaleString() }}
                </div>
                <div v-if="project.sync_error" class="text-xs text-red-400 mt-1">
                  {{ project.sync_error }}
                </div>
              </div>
              <div class="flex items-center gap-1.5 shrink-0">
                <!-- Status badge -->
                <span
                  :class="[
                    'px-2 py-0.5 text-xs rounded-full',
                    project.sync_status === 'syncing' ? 'bg-blue-500/20 text-blue-400' :
                    project.sync_status === 'error' ? 'bg-red-500/20 text-red-400' :
                    'bg-green-500/20 text-green-400'
                  ]"
                >
                  {{ project.sync_status === 'syncing' ? 'Синхронизация...' : project.sync_status === 'error' ? 'Ошибка' : 'Готов' }}
                </span>
                <button
                  :disabled="project.sync_status === 'syncing'"
                  class="p-1.5 rounded-lg hover:bg-secondary transition-colors disabled:opacity-50"
                  title="Синхронизировать"
                  @click="syncMutation.mutate(project.id)"
                >
                  <RefreshCw :class="['w-4 h-4', project.sync_status === 'syncing' ? 'animate-spin' : '']" />
                </button>
                <button
                  class="p-1.5 rounded-lg hover:bg-red-500/10 text-muted-foreground hover:text-red-500 transition-colors"
                  title="Удалить"
                  @click="deleteProject(project)"
                >
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          <div v-if="driveProjects && driveProjects.length === 0" class="p-8 text-center text-muted-foreground bg-card border border-border rounded-lg">
            <HardDrive class="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p>Нет подключённых папок Google Drive</p>
            <p class="text-xs mt-1">Нажмите "Подключить папку" чтобы создать RAG коллекцию из файлов на Google Диске</p>
          </div>
        </div>

        <!-- Create new project -->
        <div v-if="!showCreateForm" class="flex">
          <button
            class="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors text-sm"
            @click="showCreateForm = true; selectedFolder = { id: 'root', name: 'My Drive' }"
          >
            <Plus class="w-4 h-4" />
            Подключить папку
          </button>
        </div>

        <!-- Create form -->
        <div v-if="showCreateForm" class="bg-card border border-border rounded-lg p-4 space-y-3">
          <h3 class="font-medium">Новый источник из Google Drive</h3>

          <div>
            <label class="text-sm text-muted-foreground mb-1 block">Название</label>
            <input
              v-model="newProjectName"
              type="text"
              placeholder="Например: Рабочие документы"
              class="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label class="text-sm text-muted-foreground mb-1 block">Папка на Google Диске</label>
            <div class="flex items-center gap-2">
              <div class="flex-1 px-3 py-2 bg-secondary border border-border rounded-lg text-sm truncate">
                <FolderOpen class="w-4 h-4 inline mr-1.5 text-muted-foreground" />
                {{ selectedFolder.name }}
              </div>
              <button
                class="px-3 py-2 bg-secondary border border-border rounded-lg text-sm hover:bg-secondary/80 transition-colors shrink-0"
                @click="openDrivePicker"
              >
                Выбрать
              </button>
            </div>
          </div>

          <!-- Drive picker modal -->
          <div v-if="showDrivePicker" class="p-3 bg-secondary/50 rounded-lg border border-border">
            <div class="flex items-center justify-between mb-2">
              <h4 class="text-sm font-medium">Выберите папку</h4>
              <button class="p-1 hover:bg-secondary rounded" @click="showDrivePicker = false">
                <X class="w-4 h-4" />
              </button>
            </div>
            <div class="mb-2">
              <input
                v-model="gdriveSearchQuery"
                type="text"
                placeholder="Поиск..."
                class="w-full px-3 py-1.5 text-sm bg-background border border-border rounded-lg focus:ring-1 focus:ring-primary"
                @keyup.enter="searchDrive"
              />
            </div>
            <!-- Breadcrumbs -->
            <div class="flex items-center gap-1 text-xs text-muted-foreground mb-2 flex-wrap">
              <button class="hover:text-foreground" @click="navigateDrive('root')">Drive</button>
              <template v-for="(crumb, i) in gdrivePath" :key="crumb.id">
                <span>/</span>
                <button class="hover:text-foreground truncate max-w-[120px]" @click="navigateDrive(crumb.id, i)">{{ crumb.name }}</button>
              </template>
            </div>
            <!-- Use current folder -->
            <button
              class="w-full mb-2 px-3 py-1.5 text-xs bg-primary/10 text-primary rounded-lg hover:bg-primary/20 transition-colors text-left"
              @click="selectDriveFolder()"
            >
              Выбрать текущую папку: {{ gdrivePath.length ? gdrivePath[gdrivePath.length - 1].name : 'My Drive' }}
            </button>
            <!-- File list -->
            <div v-if="gdriveLoading" class="py-4 text-center text-sm text-muted-foreground">
              <Loader2 class="w-4 h-4 inline animate-spin mr-1" />
              Загрузка...
            </div>
            <div v-else class="max-h-48 overflow-y-auto space-y-0.5">
              <button
                v-for="file in gdriveFiles"
                :key="file.id"
                class="w-full text-left px-2 py-1.5 text-sm rounded hover:bg-secondary flex items-center gap-2 transition-colors"
                @click="file.isFolder ? enterDriveFolder(file) : selectDriveFolder(file)"
              >
                <span class="text-base shrink-0">{{ gdriveIcon(file) }}</span>
                <span class="truncate flex-1">{{ file.name }}</span>
                <span v-if="file.isFolder" class="text-xs text-muted-foreground">папка</span>
              </button>
            </div>
          </div>

          <div class="flex gap-2 justify-end">
            <button
              class="px-3 py-1.5 text-sm bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
              @click="showCreateForm = false"
            >
              Отмена
            </button>
            <button
              :disabled="!newProjectName.trim() || createMutation.isPending.value"
              class="px-4 py-1.5 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
              @click="createProject"
            >
              <Loader2 v-if="createMutation.isPending.value" class="w-3.5 h-3.5 inline animate-spin mr-1" />
              Создать и синхронизировать
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
