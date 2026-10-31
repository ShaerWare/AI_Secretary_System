<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { RefreshCw, Pencil, Trash2, Save, Brain, MessageCircle, Search } from "lucide-vue-next";
import { clientsApi } from "@/api/clients";
import type { ClientProfile } from "@/api/clients";
import { outboundApi } from "@/api/outbound";
import { useToastStore } from "@/stores/toast";
import { useConfirmStore } from "@/stores/confirm";
import { useAuthStore } from "@/stores";

const { t } = useI18n();
const toast = useToastStore();
const confirmStore = useConfirmStore();
const authStore = useAuthStore();
const queryClient = useQueryClient();

const canEdit = computed(() => authStore.canEdit("sales"));

// ─── Which channels remember clients ───
const { data: settings } = useQuery({
  queryKey: ["client-memory-settings"],
  queryFn: () => clientsApi.getSettings(),
});
// The WhatsApp instance list (names, ids) already comes with the monitor.
const { data: monitor } = useQuery({
  queryKey: ["outbound-monitor"],
  queryFn: () => outboundApi.monitor(),
});
const instances = computed(() => monitor.value?.whatsapp ?? []);

const form = ref<Record<string, boolean>>({});
const idleMinutes = ref(30);
const savingSettings = ref(false);

watch(
  [settings, instances],
  () => {
    for (const inst of instances.value) {
      if (form.value[inst.key] === undefined) {
        form.value[inst.key] = settings.value?.instances[inst.key] ?? false;
      }
    }
    if (settings.value) idleMinutes.value = settings.value.idle_minutes;
  },
  { immediate: true }
);

const settingsDirty = computed(
  () =>
    !!settings.value &&
    (idleMinutes.value !== settings.value.idle_minutes ||
      instances.value.some(
        (inst) => (form.value[inst.key] ?? false) !== (settings.value?.instances[inst.key] ?? false)
      ))
);

async function saveSettings() {
  savingSettings.value = true;
  try {
    await clientsApi.saveSettings({
      instances: { ...(settings.value?.instances ?? {}), ...form.value },
      idle_minutes: idleMinutes.value,
    });
    toast.success(t("clients.settingsSaved"));
    await queryClient.invalidateQueries({ queryKey: ["client-memory-settings"] });
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("clients.actionFailed"));
  } finally {
    savingSettings.value = false;
  }
}

// ─── Cards ───
const search = ref("");
const { data, isFetching, refetch } = useQuery({
  queryKey: ["client-profiles", search],
  queryFn: () => clientsApi.list(search.value.trim(), 200),
  refetchInterval: 60000,
});
const profiles = computed(() => data.value?.profiles ?? []);

const editing = ref<
  Record<number, { card_md: string; manager_notes: string; display_name: string }>
>({});
const busy = ref<Record<number, boolean>>({});

function startEdit(p: ClientProfile) {
  editing.value[p.id] = {
    card_md: p.card_md,
    manager_notes: p.manager_notes,
    display_name: p.display_name,
  };
}

async function withBusy(id: number, fn: () => Promise<void>) {
  busy.value[id] = true;
  try {
    await fn();
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("clients.actionFailed"));
  } finally {
    busy.value[id] = false;
  }
}

async function save(p: ClientProfile) {
  const draft = editing.value[p.id];
  if (!draft) return;
  await withBusy(p.id, async () => {
    await clientsApi.update(p.id, draft);
    delete editing.value[p.id];
    toast.success(t("clients.saved"));
    await queryClient.invalidateQueries({ queryKey: ["client-profiles"] });
  });
}

async function refresh(p: ClientProfile) {
  if (!p.last_session_id) return;
  await withBusy(p.id, async () => {
    await clientsApi.refresh(p.last_session_id as string);
    toast.success(t("clients.refreshed"));
    await queryClient.invalidateQueries({ queryKey: ["client-profiles"] });
  });
}

async function remove(p: ClientProfile) {
  const ok = await confirmStore.confirm({
    title: t("clients.confirmDeleteTitle"),
    message: t("clients.confirmDeleteMessage"),
    confirmText: t("clients.delete"),
    cancelText: t("clients.cancel"),
    type: "danger",
  });
  if (!ok) return;
  await withBusy(p.id, async () => {
    await clientsApi.remove(p.id);
    toast.success(t("clients.deleted"));
    await queryClient.invalidateQueries({ queryKey: ["client-profiles"] });
  });
}

function instanceOf(p: ClientProfile): string {
  return p.external_id.split(":")[0] ?? "";
}

function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "—";
}
</script>

<template>
  <div class="space-y-6">
    <!-- Where memory is on -->
    <div class="card p-5">
      <div class="flex items-center gap-2 mb-1">
        <Brain class="w-5 h-5 text-primary" />
        <h2 class="text-lg font-semibold">{{ t("clients.settingsTitle") }}</h2>
      </div>
      <p class="text-sm text-muted-foreground mb-4">{{ t("clients.settingsHint") }}</p>

      <div v-if="!instances.length" class="text-sm text-muted-foreground">
        {{ t("clients.noInstances") }}
      </div>
      <label
        v-for="inst in instances"
        :key="inst.key"
        class="flex items-center gap-3 p-3 rounded-lg bg-secondary/50 border border-border mb-2"
      >
        <input v-model="form[inst.key]" type="checkbox" class="w-4 h-4" :disabled="!canEdit" />
        <MessageCircle class="w-4 h-4 text-green-500" />
        <span class="font-medium">{{ inst.name }}</span>
        <span class="text-xs text-muted-foreground">{{ inst.instance_id }}</span>
      </label>

      <div v-if="instances.length" class="flex flex-wrap items-end justify-between gap-3 mt-3">
        <div>
          <label class="block text-sm font-medium mb-1.5">{{ t("clients.idleMinutes") }}</label>
          <input
            v-model.number="idleMinutes"
            type="number"
            min="5"
            class="input w-32"
            :disabled="!canEdit"
          />
        </div>
        <button
          v-if="canEdit"
          class="btn btn-primary"
          :disabled="!settingsDirty || savingSettings"
          @click="saveSettings"
        >
          <Save class="w-4 h-4" />
          {{ t("clients.saveSettings") }}
        </button>
      </div>
    </div>

    <!-- Cards -->
    <div class="card p-5">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <div class="relative flex-1 min-w-[200px]">
          <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            v-model="search"
            class="input w-full pl-9"
            :placeholder="t('clients.searchPlaceholder')"
          />
        </div>
        <button class="btn btn-ghost" :disabled="isFetching" @click="refetch()">
          <RefreshCw :class="['w-4 h-4', isFetching && 'animate-spin']" />
        </button>
      </div>

      <div v-if="!profiles.length" class="py-10 text-center text-muted-foreground text-sm">
        {{ t("clients.empty") }}
      </div>

      <div class="space-y-4">
        <div
          v-for="p in profiles"
          :key="p.id"
          class="rounded-lg border border-border overflow-hidden"
        >
          <div class="flex flex-wrap items-center gap-2 px-4 py-2 bg-secondary/50 text-sm">
            <MessageCircle class="w-4 h-4 text-green-500" />
            <input
              v-if="editing[p.id]"
              v-model="editing[p.id].display_name"
              class="input py-1 w-56"
            />
            <span v-else class="font-medium">{{ p.display_name || p.external_id }}</span>
            <span class="text-muted-foreground">· {{ instanceOf(p) }}</span>
            <span class="ml-auto text-xs text-muted-foreground">
              {{ t("clients.lastMessage", { date: formatDate(p.last_message_at) }) }}
            </span>
          </div>

          <div class="p-4 space-y-3">
            <div>
              <div class="text-xs text-muted-foreground mb-1">{{ t("clients.card") }}</div>
              <textarea
                v-if="editing[p.id]"
                v-model="editing[p.id].card_md"
                rows="8"
                class="input w-full"
              />
              <div
                v-else
                class="text-sm p-3 rounded-lg border border-primary/30 bg-primary/5 whitespace-pre-wrap"
              >
                {{ p.card_md || t("clients.cardEmpty") }}
              </div>
              <p v-if="editing[p.id]" class="mt-1 text-xs text-muted-foreground">
                {{ t("clients.cardHint") }}
              </p>
            </div>

            <div>
              <div class="text-xs text-muted-foreground mb-1">{{ t("clients.notes") }}</div>
              <textarea
                v-if="editing[p.id]"
                v-model="editing[p.id].manager_notes"
                rows="3"
                class="input w-full"
                :placeholder="t('clients.notesPlaceholder')"
              />
              <div
                v-else-if="p.manager_notes"
                class="text-sm p-3 rounded-lg bg-secondary/30 whitespace-pre-wrap"
              >
                {{ p.manager_notes }}
              </div>
              <div v-else class="text-sm text-muted-foreground">—</div>
            </div>

            <div v-if="canEdit" class="flex flex-wrap gap-2 pt-1">
              <template v-if="editing[p.id]">
                <button class="btn btn-primary btn-sm" :disabled="busy[p.id]" @click="save(p)">
                  <Save class="w-4 h-4" /> {{ t("clients.save") }}
                </button>
                <button class="btn btn-ghost btn-sm" @click="delete editing[p.id]">
                  {{ t("clients.cancel") }}
                </button>
              </template>
              <template v-else>
                <button class="btn btn-ghost btn-sm" @click="startEdit(p)">
                  <Pencil class="w-4 h-4" /> {{ t("clients.edit") }}
                </button>
                <button
                  v-if="p.last_session_id"
                  class="btn btn-ghost btn-sm"
                  :disabled="busy[p.id]"
                  :title="t('clients.refreshHint')"
                  @click="refresh(p)"
                >
                  <RefreshCw :class="['w-4 h-4', busy[p.id] && 'animate-spin']" />
                  {{ t("clients.refresh") }}
                </button>
              </template>
              <button
                class="btn btn-ghost btn-sm ml-auto text-red-400"
                :disabled="busy[p.id]"
                @click="remove(p)"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
