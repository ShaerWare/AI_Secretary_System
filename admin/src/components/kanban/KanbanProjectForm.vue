<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X, Trash2, RefreshCw } from 'lucide-vue-next'
import type { KanbanProject } from '@/api'

const props = defineProps<{
  visible: boolean
  project?: KanbanProject | null
}>()

const emit = defineEmits<{
  close: []
  create: [data: Record<string, unknown>]
  update: [id: number, data: Record<string, unknown>]
  delete: [id: number]
}>()

const { t } = useI18n()

const name = ref('')
const githubOwner = ref('')
const githubRepo = ref('')
const githubToken = ref('')
const webhookSecret = ref('')
const syncEnabled = ref(true)
const labelTodo = ref('status:todo')
const labelInProgress = ref('status:in_progress')
const labelReview = ref('status:review')

const isEdit = ref(false)

watch(
  () => props.visible,
  (val) => {
    if (val && props.project) {
      isEdit.value = true
      name.value = props.project.name
      githubOwner.value = props.project.github_owner
      githubRepo.value = props.project.github_repo
      githubToken.value = ''
      webhookSecret.value = ''
      syncEnabled.value = props.project.sync_enabled
      const mapping = props.project.label_mapping || {}
      labelTodo.value = mapping.todo || 'status:todo'
      labelInProgress.value = mapping.in_progress || 'status:in_progress'
      labelReview.value = mapping.review || 'status:review'
    } else if (val) {
      isEdit.value = false
      name.value = ''
      githubOwner.value = ''
      githubRepo.value = ''
      githubToken.value = ''
      webhookSecret.value = ''
      syncEnabled.value = true
      labelTodo.value = 'status:todo'
      labelInProgress.value = 'status:in_progress'
      labelReview.value = 'status:review'
    }
  },
)

function generateWebhookSecret() {
  const arr = new Uint8Array(32)
  crypto.getRandomValues(arr)
  webhookSecret.value = Array.from(arr, (b) => b.toString(16).padStart(2, '0')).join('')
}

function handleSubmit() {
  const labelMapping: Record<string, string> = {
    todo: labelTodo.value,
    in_progress: labelInProgress.value,
    review: labelReview.value,
  }

  if (isEdit.value && props.project) {
    const data: Record<string, unknown> = {}
    if (name.value !== props.project.name) data.name = name.value
    if (githubOwner.value !== props.project.github_owner) data.github_owner = githubOwner.value
    if (githubRepo.value !== props.project.github_repo) data.github_repo = githubRepo.value
    if (githubToken.value) data.github_token = githubToken.value
    if (webhookSecret.value) data.webhook_secret = webhookSecret.value
    if (syncEnabled.value !== props.project.sync_enabled) data.sync_enabled = syncEnabled.value
    data.label_mapping = labelMapping
    emit('update', props.project.id, data)
  } else {
    const data: Record<string, unknown> = {
      name: name.value,
      github_owner: githubOwner.value,
      github_repo: githubRepo.value,
      sync_enabled: syncEnabled.value,
      label_mapping: labelMapping,
    }
    if (githubToken.value) data.github_token = githubToken.value
    if (webhookSecret.value) data.webhook_secret = webhookSecret.value
    emit('create', data)
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="fixed inset-0 bg-black/50" @click="emit('close')" />
      <div
        class="relative bg-card border border-border rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto"
      >
        <div class="flex items-center justify-between p-4 border-b border-border">
          <h3 class="text-lg font-semibold">
            {{ isEdit ? t('kanban.editProject') : t('kanban.addProject') }}
          </h3>
          <button class="p-1 rounded-lg hover:bg-muted transition-colors" @click="emit('close')">
            <X class="w-5 h-5" />
          </button>
        </div>

        <form class="p-4 space-y-4" @submit.prevent="handleSubmit">
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('kanban.projectName') }}</label>
            <input
              v-model="name"
              type="text"
              required
              class="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('kanban.githubOwner') }}</label>
              <input
                v-model="githubOwner"
                type="text"
                required
                class="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="owner"
              />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('kanban.githubRepo') }}</label>
              <input
                v-model="githubRepo"
                type="text"
                required
                class="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="repo"
              />
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">
              {{ t('kanban.githubToken') }}
              <span
                v-if="isEdit && project?.has_token"
                class="text-xs text-muted-foreground ml-1"
              >
                ({{ t('kanban.tokenSet') }})
              </span>
            </label>
            <input
              v-model="githubToken"
              type="password"
              class="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              :placeholder="isEdit ? t('kanban.leaveEmptyKeep') : 'ghp_...'"
            />
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">
              {{ t('kanban.webhookSecret') }}
              <span
                v-if="isEdit && project?.webhook_secret_set"
                class="text-xs text-muted-foreground ml-1"
              >
                ({{ t('kanban.tokenSet') }})
              </span>
            </label>
            <div class="flex gap-2">
              <input
                v-model="webhookSecret"
                type="password"
                class="flex-1 px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                :placeholder="isEdit ? t('kanban.leaveEmptyKeep') : ''"
              />
              <button
                type="button"
                class="px-3 py-2 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
                :title="t('kanban.generate')"
                @click="generateWebhookSecret"
              >
                <RefreshCw class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Label mapping -->
          <div>
            <label class="block text-sm font-medium mb-2">{{ t('kanban.labelMapping') }}</label>
            <div class="space-y-2">
              <div class="flex items-center gap-2">
                <span class="text-sm text-muted-foreground w-24">To Do:</span>
                <input
                  v-model="labelTodo"
                  type="text"
                  class="flex-1 px-3 py-1.5 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div class="flex items-center gap-2">
                <span class="text-sm text-muted-foreground w-24">In Progress:</span>
                <input
                  v-model="labelInProgress"
                  type="text"
                  class="flex-1 px-3 py-1.5 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div class="flex items-center gap-2">
                <span class="text-sm text-muted-foreground w-24">Review:</span>
                <input
                  v-model="labelReview"
                  type="text"
                  class="flex-1 px-3 py-1.5 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>
          </div>

          <!-- Sync enabled -->
          <div class="flex items-center gap-2">
            <input
              id="syncEnabled"
              v-model="syncEnabled"
              type="checkbox"
              class="rounded border-border"
            />
            <label for="syncEnabled" class="text-sm">{{ t('kanban.syncEnabled') }}</label>
          </div>

          <div class="flex justify-between pt-2">
            <div>
              <button
                v-if="isEdit && project"
                type="button"
                class="flex items-center gap-2 px-4 py-2 text-sm text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
                @click="emit('delete', project.id)"
              >
                <Trash2 class="w-4 h-4" />
                {{ t('kanban.deleteProject') }}
              </button>
            </div>
            <div class="flex gap-3">
              <button
                type="button"
                class="px-4 py-2 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
                @click="emit('close')"
              >
                {{ t('common.cancel') }}
              </button>
              <button
                type="submit"
                :disabled="!name.trim() || !githubOwner.trim() || !githubRepo.trim()"
                class="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {{ isEdit ? t('common.save') : t('kanban.addProject') }}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>
