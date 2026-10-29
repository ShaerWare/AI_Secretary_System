<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import {
  RefreshCw,
  Send,
  X,
  Pencil,
  Trash2,
  Save,
  ShieldCheck,
  MessageCircle,
  AlertTriangle,
  Check,
} from "lucide-vue-next";
import { outboundApi } from "@/api/outbound";
import type {
  OutboundMessage,
  OutboundMode,
  OutboundStatus,
  WhatsAppChannelSummary,
} from "@/api/outbound";
import { useToastStore } from "@/stores/toast";
import { useConfirmStore } from "@/stores/confirm";
import { useAuthStore } from "@/stores";

const emit = defineEmits<{ "open-kp": [] }>();

const { t } = useI18n();
const toast = useToastStore();
const confirmStore = useConfirmStore();
const authStore = useAuthStore();
const queryClient = useQueryClient();

const canEdit = computed(() => authStore.canEdit("sales"));
const canManage = computed(() => authStore.canManage("sales"));

type Filter = OutboundStatus | "all";
const filter = ref<Filter>("pending");
const filters: Filter[] = ["pending", "failed", "sent", "rejected", "all"];

const { data, isFetching, refetch } = useQuery({
  queryKey: ["outbound-messages", filter],
  queryFn: () => outboundApi.list(filter.value === "all" ? undefined : filter.value, 100),
  refetchInterval: 10000,
});

const messages = computed(() => data.value?.messages ?? []);
const counts = computed(
  () => data.value?.counts ?? { pending: 0, sent: 0, rejected: 0, failed: 0 }
);

// ─── Edit state: one draft per message, kept until saved or sent ───
const editing = ref<Record<number, string>>({});
const busy = ref<Record<number, boolean>>({});

function startEdit(m: OutboundMessage) {
  editing.value[m.id] = m.text;
}

function cancelEdit(id: number) {
  delete editing.value[id];
}

function isEditable(m: OutboundMessage) {
  return m.status === "pending" || m.status === "failed";
}

async function invalidate() {
  await queryClient.invalidateQueries({ queryKey: ["outbound-messages"] });
  await queryClient.invalidateQueries({ queryKey: ["outbound-monitor"] });
}

async function withBusy(id: number, fn: () => Promise<void>) {
  busy.value[id] = true;
  try {
    await fn();
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("outbound.actionFailed"));
  } finally {
    busy.value[id] = false;
  }
}

async function saveEdit(m: OutboundMessage) {
  const text = editing.value[m.id]?.trim();
  if (!text) return;
  await withBusy(m.id, async () => {
    await outboundApi.update(m.id, text);
    delete editing.value[m.id];
    toast.success(t("outbound.saved"));
    await invalidate();
  });
}

async function approve(m: OutboundMessage) {
  const edited = editing.value[m.id];
  await withBusy(m.id, async () => {
    const resp = await outboundApi.approve(m.id, edited !== undefined ? edited.trim() : undefined);
    delete editing.value[m.id];
    if (resp.message.status === "sent") {
      toast.success(t("outbound.approved"));
    } else {
      toast.error(t("outbound.sendFailed", { error: resp.message.error || "" }));
    }
    await invalidate();
  });
}

async function reject(m: OutboundMessage) {
  const ok = await confirmStore.confirm({
    title: t("outbound.confirmRejectTitle"),
    message: t("outbound.confirmRejectMessage"),
    confirmText: t("outbound.reject"),
    cancelText: t("outbound.cancel"),
    type: "warning",
  });
  if (!ok) return;
  await withBusy(m.id, async () => {
    await outboundApi.reject(m.id);
    delete editing.value[m.id];
    toast.success(t("outbound.rejectedToast"));
    await invalidate();
  });
}

async function remove(m: OutboundMessage) {
  const ok = await confirmStore.confirm({
    title: t("outbound.confirmDeleteTitle"),
    message: t("outbound.confirmDeleteMessage"),
    confirmText: t("outbound.delete"),
    cancelText: t("outbound.cancel"),
    type: "danger",
  });
  if (!ok) return;
  await withBusy(m.id, async () => {
    await outboundApi.remove(m.id);
    toast.success(t("outbound.deleted"));
    await invalidate();
  });
}

// ─── Channel modes (who needs approval) ───
const { data: monitorData } = useQuery({
  queryKey: ["outbound-monitor"],
  queryFn: () => outboundApi.monitor(),
  refetchInterval: 30000,
});

const instances = computed<WhatsAppChannelSummary[]>(() => monitorData.value?.whatsapp ?? []);
const modeForm = ref<Record<string, { mode: OutboundMode; ack_text: string }>>({});
const savingModes = ref(false);

watch(
  instances,
  (list) => {
    for (const inst of list) {
      if (!modeForm.value[inst.key]) {
        modeForm.value[inst.key] = { mode: inst.mode, ack_text: inst.ack_text };
      }
    }
  },
  { immediate: true }
);

const modesDirty = computed(() =>
  instances.value.some((inst) => {
    const f = modeForm.value[inst.key];
    return f && (f.mode !== inst.mode || f.ack_text !== inst.ack_text);
  })
);

async function saveModes() {
  savingModes.value = true;
  try {
    const current = await outboundApi.getSettings();
    const merged = { ...current.instances };
    for (const [key, cfg] of Object.entries(modeForm.value)) {
      merged[key] = { mode: cfg.mode, ack_text: cfg.ack_text.trim() };
    }
    await outboundApi.saveSettings({ instances: merged });
    toast.success(t("outbound.modesSaved"));
    await queryClient.invalidateQueries({ queryKey: ["outbound-monitor"] });
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("outbound.actionFailed"));
  } finally {
    savingModes.value = false;
  }
}

function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "—";
}

function statusClass(status: string): string {
  switch (status) {
    case "pending":
      return "bg-yellow-500/20 text-yellow-400";
    case "sent":
      return "bg-green-500/20 text-green-400";
    case "rejected":
      return "bg-secondary text-muted-foreground";
    default:
      return "bg-red-500/20 text-red-400";
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Channel modes -->
    <div class="card p-5">
      <div class="flex items-center gap-2 mb-1">
        <ShieldCheck class="w-5 h-5 text-primary" />
        <h2 class="text-lg font-semibold">{{ t("outbound.modesTitle") }}</h2>
      </div>
      <p class="text-sm text-muted-foreground mb-4">{{ t("outbound.modesHint") }}</p>

      <div v-if="!instances.length" class="text-sm text-muted-foreground">
        {{ t("outbound.noInstances") }}
      </div>

      <div
        v-for="inst in instances"
        :key="inst.key"
        class="p-4 rounded-lg bg-secondary/50 border border-border mb-3"
      >
        <div v-if="modeForm[inst.key]" class="flex flex-col md:flex-row md:items-start gap-4">
          <div class="md:w-56 shrink-0">
            <div class="flex items-center gap-2 font-medium">
              <MessageCircle class="w-4 h-4 text-green-500" />
              {{ inst.name }}
            </div>
            <div class="text-xs text-muted-foreground mt-0.5">{{ inst.instance_id }}</div>
            <select
              v-model="modeForm[inst.key].mode"
              class="input w-full mt-2"
              :disabled="!canManage"
            >
              <option value="approval">{{ t("outbound.modeApproval") }}</option>
              <option value="auto">{{ t("outbound.modeAuto") }}</option>
            </select>
          </div>
          <div class="flex-1">
            <label class="block text-sm font-medium mb-1.5">{{ t("outbound.ackText") }}</label>
            <textarea
              v-model="modeForm[inst.key].ack_text"
              rows="2"
              class="input w-full resize-none"
              :placeholder="t('outbound.ackPlaceholder')"
              :disabled="!canManage || modeForm[inst.key].mode !== 'approval'"
            />
            <p class="text-xs text-muted-foreground mt-1">{{ t("outbound.ackHint") }}</p>
          </div>
        </div>
      </div>

      <div v-if="canManage && instances.length" class="flex justify-end">
        <button class="btn btn-primary" :disabled="!modesDirty || savingModes" @click="saveModes">
          <Save class="w-4 h-4" />
          {{ t("outbound.saveModes") }}
        </button>
      </div>
    </div>

    <!-- Queue -->
    <div class="card p-5">
      <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div class="flex flex-wrap gap-1">
          <button
            v-for="f in filters"
            :key="f"
            :class="[
              'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5',
              filter === f
                ? 'bg-primary text-primary-foreground'
                : 'bg-secondary text-muted-foreground hover:text-foreground',
            ]"
            @click="filter = f"
          >
            {{ t(`outbound.filter.${f}`) }}
            <span
              v-if="f !== 'all' && counts[f]"
              :class="[
                'text-xs px-1.5 rounded-full',
                f === 'pending' || f === 'failed' ? 'bg-red-500 text-white' : 'bg-background/40',
              ]"
            >
              {{ counts[f] }}
            </span>
          </button>
        </div>
        <button class="btn btn-ghost" :disabled="isFetching" @click="refetch()">
          <RefreshCw :class="['w-4 h-4', isFetching && 'animate-spin']" />
        </button>
      </div>

      <div v-if="!messages.length" class="py-10 text-center text-muted-foreground text-sm">
        {{ filter === "pending" ? t("outbound.emptyPending") : t("outbound.empty") }}
      </div>

      <div class="space-y-4">
        <div
          v-for="m in messages"
          :key="m.id"
          class="rounded-lg border border-border overflow-hidden"
        >
          <!-- Header -->
          <div class="flex flex-wrap items-center gap-2 px-4 py-2 bg-secondary/50 text-sm">
            <MessageCircle class="w-4 h-4 text-green-500" />
            <span class="font-medium">{{ m.target }}</span>
            <span class="text-muted-foreground">· {{ m.instance_id }}</span>
            <span :class="['px-2 py-0.5 rounded-full text-xs font-medium', statusClass(m.status)]">
              {{ t(`outbound.status.${m.status}`) }}
            </span>
            <span
              v-if="m.edited"
              class="px-2 py-0.5 rounded-full text-xs bg-blue-500/20 text-blue-400"
            >
              {{ t("outbound.editedBadge") }}
            </span>
            <button
              v-if="m.kp"
              class="px-2 py-0.5 rounded-full text-xs font-medium bg-primary/20 text-primary hover:bg-primary/30"
              :title="t('outbound.openKp')"
              @click="emit('open-kp')"
            >
              {{
                m.kp.kind === "kp"
                  ? t("outbound.kpBadge", { number: m.kp.number || "" })
                  : t("outbound.kpFollowupBadge", { number: m.kp.number || "" })
              }}
            </button>
            <span v-if="m.ack_sent" class="text-xs text-muted-foreground flex items-center gap-1">
              <Check class="w-3 h-3" /> {{ t("outbound.ackSent") }}
            </span>
            <span class="ml-auto text-xs text-muted-foreground">{{ formatDate(m.created) }}</span>
          </div>

          <div class="p-4 space-y-3">
            <!-- Client message -->
            <div v-if="m.client_text">
              <div class="text-xs text-muted-foreground mb-1">{{ t("outbound.clientWrote") }}</div>
              <div class="text-sm p-3 rounded-lg bg-secondary/30 whitespace-pre-wrap">
                {{ m.client_text }}
              </div>
            </div>

            <!-- Reply -->
            <div>
              <div class="text-xs text-muted-foreground mb-1">
                {{ m.status === "sent" ? t("outbound.sentText") : t("outbound.replyText") }}
              </div>
              <textarea
                v-if="editing[m.id] !== undefined"
                v-model="editing[m.id]"
                rows="8"
                class="input w-full"
              />
              <div
                v-else
                class="text-sm p-3 rounded-lg border border-primary/30 bg-primary/5 whitespace-pre-wrap"
              >
                {{ m.text }}
              </div>
              <p
                v-if="m.kp && m.status !== 'sent' && m.text.includes('{link}')"
                class="mt-1 text-xs text-muted-foreground"
              >
                {{ t("outbound.kpLinkHint") }}
              </p>
              <details v-if="m.edited" class="mt-2 text-xs text-muted-foreground">
                <summary class="cursor-pointer">{{ t("outbound.showDraft") }}</summary>
                <div class="mt-1 p-2 rounded bg-secondary/30 whitespace-pre-wrap">
                  {{ m.draft_text }}
                </div>
              </details>
            </div>

            <div v-if="m.error" class="flex items-start gap-2 text-sm text-red-400">
              <AlertTriangle class="w-4 h-4 shrink-0 mt-0.5" />
              {{ m.error }}
            </div>

            <div v-if="m.decided_by" class="text-xs text-muted-foreground">
              {{ t("outbound.decidedBy", { user: m.decided_by, date: formatDate(m.decided_at) }) }}
            </div>

            <!-- Actions -->
            <div class="flex flex-wrap gap-2 pt-1">
              <template v-if="isEditable(m) && canEdit">
                <button class="btn btn-primary btn-sm" :disabled="busy[m.id]" @click="approve(m)">
                  <Send class="w-4 h-4" />
                  {{
                    m.status === "failed"
                      ? t("outbound.retry")
                      : editing[m.id] !== undefined
                        ? t("outbound.approveEdited")
                        : t("outbound.approve")
                  }}
                </button>
                <template v-if="editing[m.id] !== undefined">
                  <button class="btn btn-ghost btn-sm" :disabled="busy[m.id]" @click="saveEdit(m)">
                    <Save class="w-4 h-4" /> {{ t("outbound.saveDraft") }}
                  </button>
                  <button class="btn btn-ghost btn-sm" @click="cancelEdit(m.id)">
                    {{ t("outbound.cancel") }}
                  </button>
                </template>
                <button v-else class="btn btn-ghost btn-sm" @click="startEdit(m)">
                  <Pencil class="w-4 h-4" /> {{ t("outbound.edit") }}
                </button>
                <button
                  class="btn btn-ghost btn-sm text-red-400"
                  :disabled="busy[m.id]"
                  @click="reject(m)"
                >
                  <X class="w-4 h-4" /> {{ t("outbound.reject") }}
                </button>
              </template>
              <button
                v-if="canManage && m.status !== 'sending'"
                class="btn btn-ghost btn-sm ml-auto text-muted-foreground"
                :disabled="busy[m.id]"
                @click="remove(m)"
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
