<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { wikiRagApi, type KnowledgeDocument } from '@/api/wikiRag'
import {
  googleApi,
  type CreateDriveSource,
  type DriveSourcePurpose,
  type DriveSyncReport,
  type GoogleDriveFile,
  type GoogleDriveProject,
} from '@/api/google'
import { BookOpen, Search, ArrowLeft, FileText, Loader2, RefreshCw, Trash2, Plus, FolderOpen, X, HardDrive, AlertTriangle, ChevronDown, Link } from 'lucide-vue-next'
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

// ─── Google Drive sources tab ────────────────────────────────
type DriveRoot = 'root' | 'shared'
const ROOT_LABELS: Record<DriveRoot, string> = { root: 'Мой диск', shared: 'Доступные мне' }
const PURPOSE_LABELS: Record<DriveSourcePurpose, string> = {
  rag: 'База знаний',
  prices: 'Прайсы поставщиков',
  both: 'Прайсы + база знаний',
}

const googleConnected = ref(false)
const showCreateForm = ref(false)
const showDrivePicker = ref(false)
const newProjectName = ref('')
const newPurpose = ref<DriveSourcePurpose>('rag')
const newAutoSync = ref(true)
const selectedFolder = ref<{ id: string; name: string }>({ id: 'root', name: ROOT_LABELS.root })
const selectedFiles = ref<GoogleDriveFile[]>([])
const pasteLink = ref('')
const resolvingLink = ref(false)
const expandedReport = ref<number | null>(null)

// Drive browser state
const gdriveFiles = ref<GoogleDriveFile[]>([])
const gdriveLoading = ref(false)
const gdriveRoot = ref<DriveRoot>('root')
const gdrivePath = ref<{ id: string; name: string }[]>([])
const gdriveSearchQuery = ref('')

const { data: driveProjects } = useQuery({
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
  mutationFn: (data: CreateDriveSource) => googleApi.createDriveRagProject(data),
  onSuccess: () => {
    toast.success('Источник подключён, синхронизация запущена')
    showCreateForm.value = false
    newProjectName.value = ''
    queryClient.invalidateQueries({ queryKey: ['gdrive-rag-projects'] })
  },
  onError: (e: Error) => toast.error(e.message || 'Ошибка создания источника'),
})

const syncMutation = useMutation({
  mutationFn: (id: number) => googleApi.syncDriveRagProject(id),
  onSuccess: () => {
    toast.success('Синхронизация запущена')
    queryClient.invalidateQueries({ queryKey: ['gdrive-rag-projects'] })
  },
  onError: () => toast.error('Ошибка синхронизации'),
})

const autoSyncMutation = useMutation({
  mutationFn: (p: GoogleDriveProject) =>
    googleApi.updateDriveRagProject(p.id, { auto_sync: !p.auto_sync }),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['gdrive-rag-projects'] }),
  onError: () => toast.error('Не удалось сохранить'),
})

const deleteMutation = useMutation({
  mutationFn: (id: number) => googleApi.deleteDriveRagProject(id),
  onSuccess: () => {
    toast.success('Источник удалён')
    queryClient.invalidateQueries({ queryKey: ['gdrive-rag-projects'] })
  },
  onError: () => toast.error('Ошибка удаления'),
})

async function deleteProject(project: GoogleDriveProject) {
  const ok = await confirm.confirm({
    title: 'Удалить источник',
    message: project.collection_id
      ? `Удалить "${project.name}" и все индексированные документы?`
      : `Удалить "${project.name}"? Уже загруженные прайсы останутся, но обновляться перестанут.`,
    confirmText: 'Удалить',
    type: 'danger',
  })
  if (ok) deleteMutation.mutate(project.id)
}

function openCreateForm() {
  showCreateForm.value = true
  newProjectName.value = ''
  newPurpose.value = 'rag'
  newAutoSync.value = true
  selectedFolder.value = { id: 'root', name: ROOT_LABELS.root }
  selectedFiles.value = []
  pasteLink.value = ''
}

// The server refuses to treat the whole "My Drive" as a price folder
const pricesNeedFolder = computed(
  () => newPurpose.value !== 'rag' && selectedFolder.value.id === 'root' && !selectedFiles.value.length,
)

function createProject() {
  if (!newProjectName.value.trim() || pricesNeedFolder.value) return
  createMutation.mutate({
    name: newProjectName.value.trim(),
    folder_id: selectedFolder.value.id,
    folder_name: selectedFiles.value.length
      ? `${selectedFiles.value.length} файл(ов) из «${selectedFolder.value.name}»`
      : selectedFolder.value.name,
    purpose: newPurpose.value,
    file_ids: selectedFiles.value.map(f => f.id),
    auto_sync: newAutoSync.value,
  })
}

async function resolveLink() {
  if (!pasteLink.value.trim()) return
  resolvingLink.value = true
  try {
    const item = await googleApi.driveResolve(pasteLink.value.trim())
    if (item.isFolder) {
      selectedFolder.value = { id: item.id, name: item.name }
      selectedFiles.value = []
      if (!newProjectName.value.trim()) newProjectName.value = item.name
    } else if (!selectedFiles.value.some(f => f.id === item.id)) {
      selectedFiles.value.push(item)
    }
    pasteLink.value = ''
  } catch (e) {
    toast.error((e as Error).message || 'Не удалось открыть ссылку')
  } finally {
    resolvingLink.value = false
  }
}

// Drive picker
async function loadDriveFolder(folderId: string) {
  gdriveLoading.value = true
  try {
    const result = await googleApi.driveList(folderId)
    gdriveFiles.value = result.files
  } catch { gdriveFiles.value = [] }
  finally { gdriveLoading.value = false }
}

async function searchDrive() {
  if (!gdriveSearchQuery.value.trim()) { openRoot(gdriveRoot.value); return }
  gdriveLoading.value = true
  try {
    const result = await googleApi.driveSearch(gdriveSearchQuery.value)
    gdriveFiles.value = result.files
    gdrivePath.value = []
  } catch { gdriveFiles.value = [] }
  finally { gdriveLoading.value = false }
}

function openRoot(root: DriveRoot) {
  gdriveRoot.value = root
  gdrivePath.value = []
  gdriveSearchQuery.value = ''
  loadDriveFolder(root)
}

function navigateDrive(folderId: string, idx: number) {
  gdrivePath.value = gdrivePath.value.slice(0, idx + 1)
  gdriveSearchQuery.value = ''
  loadDriveFolder(folderId)
}

function enterDriveFolder(folder: GoogleDriveFile) {
  gdrivePath.value.push({ id: folder.id, name: folder.name })
  gdriveSearchQuery.value = ''
  loadDriveFolder(folder.id)
}

const currentFolder = computed(() => {
  const last = gdrivePath.value[gdrivePath.value.length - 1]
  return last || { id: gdriveRoot.value, name: ROOT_LABELS[gdriveRoot.value] }
})

function selectCurrentFolder() {
  if (currentFolder.value.id === 'shared') {
    toast.warning('Откройте нужную папку из «Доступные мне»')
    return
  }
  selectedFolder.value = { ...currentFolder.value }
  selectedFiles.value = []
  if (!newProjectName.value.trim()) newProjectName.value = currentFolder.value.name
  showDrivePicker.value = false
}

function isFileSelected(file: GoogleDriveFile) {
  return selectedFiles.value.some(f => f.id === file.id)
}

function toggleFile(file: GoogleDriveFile) {
  if (isFileSelected(file)) {
    selectedFiles.value = selectedFiles.value.filter(f => f.id !== file.id)
    return
  }
  if (currentFolder.value.id !== 'shared') selectedFolder.value = { ...currentFolder.value }
  selectedFiles.value.push(file)
}

function openDrivePicker() {
  showDrivePicker.value = true
  openRoot('root')
}

function gdriveIcon(file: GoogleDriveFile): string {
  if (file.isFolder) return '📁'
  const mt = file.mimeType
  if (mt.includes('document')) return '📔'
  if (mt.includes('spreadsheet') || mt.includes('excel')) return '📊'
  if (mt.includes('presentation')) return '📽️'
  if (mt.includes('pdf')) return '📄'
  return '📃'
}

function supplierRows(report: DriveSyncReport) {
  return (report.prices?.suppliers ?? []).map(s => ({
    name: s.name,
    price: s.price_file?.files ?? [],
    stock: s.stock_file?.files,
    parsed: report.parsed?.find(p => p.supplier === s.name),
  }))
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

    <!-- Google Drive sources tab -->
    <div v-if="activeTab === 'gdrive'" class="flex-1 min-h-0 overflow-y-auto space-y-4">
      <!-- Not connected -->
      <div v-if="!googleConnected" class="p-8 text-center bg-card border border-border rounded-lg">
        <HardDrive class="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-30" />
        <p class="text-muted-foreground mb-3">Подключите Google аккаунт в настройках для работы с Drive</p>
        <router-link to="/settings" class="text-primary hover:underline text-sm">Перейти в настройки</router-link>
      </div>

      <!-- Connected -->
      <template v-else>
        <!-- Source list -->
        <div class="space-y-3">
          <div v-for="project in driveProjects" :key="project.id" class="bg-card border border-border rounded-lg p-4">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 flex-wrap">
                  <h3 class="font-medium truncate">{{ project.name }}</h3>
                  <span class="px-2 py-0.5 text-xs rounded-full bg-secondary text-muted-foreground">
                    {{ PURPOSE_LABELS[project.purpose] }}
                  </span>
                </div>
                <div class="flex items-center gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
                  <span class="flex items-center gap-1">
                    <FolderOpen class="w-3 h-3" />
                    {{ project.folder_name || project.folder_id }}
                  </span>
                  <span>{{ project.file_count }} файлов</span>
                  <span>{{ formatSize(project.total_size_bytes) }}</span>
                </div>
                <div v-if="project.last_synced" class="text-xs text-muted-foreground mt-1">
                  Данные обновлены: {{ new Date(project.last_synced).toLocaleString() }}
                  <template v-if="project.last_checked && project.last_checked !== project.last_synced">
                    · проверено: {{ new Date(project.last_checked).toLocaleString() }}
                  </template>
                </div>
                <label class="inline-flex items-center gap-2 mt-2 text-xs text-muted-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    :checked="project.auto_sync"
                    :disabled="autoSyncMutation.isPending.value"
                    @change="autoSyncMutation.mutate(project)"
                  />
                  Проверять изменения на Диске раз в сутки
                </label>
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
                  title="Синхронизировать сейчас"
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

            <!-- Last sync report -->
            <template v-if="project.sync_report">
              <div
                v-if="project.sync_report.prices?.unmatched.length"
                class="mt-3 p-2 text-xs rounded-lg bg-amber-500/10 text-amber-400 flex gap-2"
              >
                <AlertTriangle class="w-4 h-4 shrink-0" />
                <span>
                  Не подошли ни одному поставщику — парсер их не читает:
                  {{ project.sync_report.prices.unmatched.join(', ') }}
                </span>
              </div>
              <div
                v-if="project.sync_report.prices?.ambiguous?.length"
                class="mt-2 p-2 text-xs rounded-lg bg-red-500/10 text-red-400 flex gap-2"
              >
                <AlertTriangle class="w-4 h-4 shrink-0" />
                <span>
                  Подходят сразу нескольким поставщикам — проверьте отчёт:
                  {{ project.sync_report.prices.ambiguous.join(', ') }}
                </span>
              </div>
              <button
                class="mt-2 text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
                @click="expandedReport = expandedReport === project.id ? null : project.id"
              >
                <ChevronDown :class="['w-3 h-3 transition-transform', expandedReport === project.id ? 'rotate-180' : '']" />
                Отчёт последней синхронизации
              </button>
              <div v-if="expandedReport === project.id" class="mt-2 space-y-2 text-xs">
                <table v-if="project.sync_report.prices" class="w-full">
                  <thead>
                    <tr class="text-muted-foreground text-left">
                      <th class="py-1 pr-2 font-normal">Поставщик</th>
                      <th class="py-1 pr-2 font-normal">Файл</th>
                      <th class="py-1 font-normal text-right">Позиций</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in supplierRows(project.sync_report)" :key="row.name" class="border-t border-border">
                      <td class="py-1 pr-2">{{ row.name }}</td>
                      <td class="py-1 pr-2 break-all">
                        <span v-if="row.price.length">{{ row.price.join(', ') }}</span>
                        <span v-else class="text-red-400">нет файла — останутся старые цены</span>
                        <span v-if="row.price.length > 1" class="text-amber-400"> (взят самый новый)</span>
                        <div v-if="row.stock" class="text-muted-foreground">
                          остатки: {{ row.stock.length ? row.stock.join(', ') : 'нет файла' }}
                        </div>
                      </td>
                      <td class="py-1 text-right">
                        <span v-if="row.parsed?.error" class="text-red-400" :title="row.parsed.error">ошибка</span>
                        <span v-else-if="row.parsed">{{ row.parsed.offers }}</span>
                        <span v-else class="text-muted-foreground">—</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <p v-if="project.sync_report.prices?.archived.length" class="text-muted-foreground">
                  Прежние файлы убраны в архив ({{ project.sync_report.prices.archived.length }}):
                  {{ project.sync_report.prices.archived.join(', ') }}
                </p>
                <p v-if="project.sync_report.rag" class="text-muted-foreground">
                  В базу знаний: {{ project.sync_report.rag.documents }} документов
                </p>
                <p v-if="project.sync_report.missing.length" class="text-red-400">
                  Недоступно выбранных файлов: {{ project.sync_report.missing.length }}
                </p>
                <div v-if="project.sync_report.skipped.length || project.sync_report.rag?.skipped.length" class="text-muted-foreground">
                  Пропущено:
                  <span v-for="s in [...project.sync_report.skipped, ...(project.sync_report.rag?.skipped ?? [])]" :key="s.name" class="block">
                    {{ s.name }} — {{ s.reason }}
                  </span>
                </div>
              </div>
            </template>
          </div>

          <div v-if="driveProjects && driveProjects.length === 0" class="p-8 text-center text-muted-foreground bg-card border border-border rounded-lg">
            <HardDrive class="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p>Нет подключённых источников Google Drive</p>
            <p class="text-xs mt-1">Подключите папку или отдельные файлы: в базу знаний ассистента и/или как прайсы поставщиков</p>
          </div>
        </div>

        <!-- Create new source -->
        <div v-if="!showCreateForm" class="flex">
          <button
            class="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors text-sm"
            @click="openCreateForm"
          >
            <Plus class="w-4 h-4" />
            Подключить папку или файлы
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
              placeholder="Например: Прайсы поставщиков"
              class="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label class="text-sm text-muted-foreground mb-1 block">Куда идут файлы</label>
            <div class="flex flex-col gap-1.5 text-sm">
              <label class="flex items-start gap-2 cursor-pointer">
                <input v-model="newPurpose" type="radio" value="rag" class="mt-1" />
                <span>База знаний <span class="text-xs text-muted-foreground">— текст документов в коллекцию для ассистентов (PDF, Excel, Word, Google-документы)</span></span>
              </label>
              <label class="flex items-start gap-2 cursor-pointer">
                <input v-model="newPurpose" type="radio" value="prices" class="mt-1" />
                <span>Прайсы поставщиков <span class="text-xs text-muted-foreground">— файлы заменяют текущие прайсы, старые уходят в архив, цены пересчитываются</span></span>
              </label>
              <label class="flex items-start gap-2 cursor-pointer">
                <input v-model="newPurpose" type="radio" value="both" class="mt-1" />
                <span>И то, и другое</span>
              </label>
            </div>
          </div>

          <div>
            <label class="text-sm text-muted-foreground mb-1 block">Папка или файлы на Google Диске</label>
            <div class="flex items-center gap-2">
              <div class="flex-1 min-w-0 px-3 py-2 bg-secondary border border-border rounded-lg text-sm truncate">
                <FolderOpen class="w-4 h-4 inline mr-1.5 text-muted-foreground" />
                <template v-if="selectedFiles.length">{{ selectedFiles.length }} файл(ов) выбрано</template>
                <template v-else>Вся папка: {{ selectedFolder.name }}</template>
              </div>
              <button
                class="px-3 py-2 bg-secondary border border-border rounded-lg text-sm hover:bg-secondary/80 transition-colors shrink-0"
                @click="openDrivePicker"
              >
                Выбрать
              </button>
            </div>
            <div class="flex items-center gap-2 mt-2">
              <input
                v-model="pasteLink"
                type="text"
                placeholder="…или вставьте ссылку на папку/файл Google Диска"
                class="flex-1 min-w-0 px-3 py-1.5 bg-secondary border border-border rounded-lg text-sm focus:ring-1 focus:ring-primary"
                @keyup.enter="resolveLink"
              />
              <button
                :disabled="!pasteLink.trim() || resolvingLink"
                class="px-3 py-1.5 bg-secondary border border-border rounded-lg text-sm hover:bg-secondary/80 disabled:opacity-50 shrink-0"
                @click="resolveLink"
              >
                <Loader2 v-if="resolvingLink" class="w-3.5 h-3.5 inline animate-spin" />
                <Link v-else class="w-3.5 h-3.5 inline" />
              </button>
            </div>
            <div v-if="selectedFiles.length" class="mt-2 flex flex-wrap gap-1">
              <span
                v-for="f in selectedFiles"
                :key="f.id"
                class="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-secondary rounded-full max-w-full"
              >
                <span class="truncate">{{ f.name }}</span>
                <button class="hover:text-red-400" @click="toggleFile(f)"><X class="w-3 h-3" /></button>
              </span>
            </div>
            <p v-if="pricesNeedFolder" class="text-xs text-amber-400 mt-1">
              Для прайсов выберите конкретную папку или файлы, а не весь «Мой диск»
            </p>
          </div>

          <!-- Drive picker -->
          <div v-if="showDrivePicker" class="p-3 bg-secondary/50 rounded-lg border border-border">
            <div class="flex items-center justify-between mb-2">
              <div class="flex gap-1">
                <button
                  v-for="root in (['root', 'shared'] as const)"
                  :key="root"
                  :class="['px-2 py-1 text-xs rounded', gdriveRoot === root && !gdrivePath.length ? 'bg-primary/20 text-primary' : 'hover:bg-secondary']"
                  @click="openRoot(root)"
                >
                  {{ ROOT_LABELS[root] }}
                </button>
              </div>
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
              <button class="hover:text-foreground" @click="openRoot(gdriveRoot)">{{ ROOT_LABELS[gdriveRoot] }}</button>
              <template v-for="(crumb, i) in gdrivePath" :key="crumb.id">
                <span>/</span>
                <button class="hover:text-foreground truncate max-w-[120px]" @click="navigateDrive(crumb.id, i)">{{ crumb.name }}</button>
              </template>
            </div>
            <!-- Use current folder -->
            <button
              v-if="currentFolder.id !== 'shared'"
              class="w-full mb-2 px-3 py-1.5 text-xs bg-primary/10 text-primary rounded-lg hover:bg-primary/20 transition-colors text-left"
              @click="selectCurrentFolder"
            >
              Взять всю папку: {{ currentFolder.name }}
            </button>
            <p class="text-xs text-muted-foreground mb-1">Или отметьте отдельные файлы:</p>
            <!-- File list -->
            <div v-if="gdriveLoading" class="py-4 text-center text-sm text-muted-foreground">
              <Loader2 class="w-4 h-4 inline animate-spin mr-1" />
              Загрузка...
            </div>
            <div v-else class="max-h-60 overflow-y-auto space-y-0.5">
              <template v-for="file in gdriveFiles" :key="file.id">
                <button
                  v-if="file.isFolder"
                  class="w-full text-left px-2 py-1.5 text-sm rounded hover:bg-secondary flex items-center gap-2 transition-colors"
                  @click="enterDriveFolder(file)"
                >
                  <span class="text-base shrink-0">{{ gdriveIcon(file) }}</span>
                  <span class="truncate flex-1">{{ file.name }}</span>
                  <span class="text-xs text-muted-foreground">папка</span>
                </button>
                <label
                  v-else
                  class="w-full px-2 py-1.5 text-sm rounded hover:bg-secondary flex items-center gap-2 cursor-pointer"
                >
                  <input type="checkbox" :checked="isFileSelected(file)" @change="toggleFile(file)" />
                  <span class="text-base shrink-0">{{ gdriveIcon(file) }}</span>
                  <span class="truncate flex-1">{{ file.name }}</span>
                </label>
              </template>
              <p v-if="!gdriveFiles.length" class="py-3 text-center text-xs text-muted-foreground">Пусто</p>
            </div>
            <button
              v-if="selectedFiles.length"
              class="w-full mt-2 px-3 py-1.5 text-xs bg-primary text-primary-foreground rounded-lg hover:bg-primary/90"
              @click="showDrivePicker = false"
            >
              Готово — выбрано файлов: {{ selectedFiles.length }}
            </button>
          </div>

          <label class="flex items-center gap-2 text-sm cursor-pointer">
            <input v-model="newAutoSync" type="checkbox" />
            Проверять изменения на Диске раз в сутки и обновлять данные
          </label>

          <div class="flex gap-2 justify-end">
            <button
              class="px-3 py-1.5 text-sm bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
              @click="showCreateForm = false"
            >
              Отмена
            </button>
            <button
              :disabled="!newProjectName.trim() || pricesNeedFolder || createMutation.isPending.value"
              class="px-4 py-1.5 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
              @click="createProject"
            >
              <Loader2 v-if="createMutation.isPending.value" class="w-3.5 h-3.5 inline animate-spin mr-1" />
              Подключить и синхронизировать
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
