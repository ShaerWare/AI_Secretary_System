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
  Plus,
  FileText,
  ExternalLink,
  Copy,
  AlertTriangle,
  Bell,
  Check,
  Clock,
  RotateCcw,
  ThumbsUp,
  ThumbsDown,
  Timer,
  Settings2,
  MessageSquareText,
} from "lucide-vue-next";
import { kpApi } from "@/api/kp";
import type {
  KpAction,
  KpCreatePayload,
  KpDelivery,
  KpQuote,
  KpRule,
  KpSettings,
  KpTrigger,
} from "@/api/kp";
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
const canManage = computed(() => authStore.canManage("sales"));

// ─── PIM connection ───
const { data: pimStatus } = useQuery({
  queryKey: ["kp-status"],
  queryFn: () => kpApi.status(),
  refetchInterval: 60000,
});

// ─── Quotes ───
type Filter = "pending" | "failed" | "open" | "expired" | "accepted" | "lost" | "all";
const filters: Filter[] = ["pending", "open", "expired", "failed", "accepted", "lost", "all"];
const FILTER_STATUSES: Record<Filter, string | undefined> = {
  pending: "pending",
  failed: "failed",
  open: "sent,viewed,clarification",
  expired: "expired",
  accepted: "accepted",
  lost: "lost,rejected,superseded",
  all: undefined,
};
const filter = ref<Filter>("pending");

const { data, isFetching, refetch } = useQuery({
  queryKey: ["kp-quotes", filter],
  queryFn: () => kpApi.list(FILTER_STATUSES[filter.value], 100),
  refetchInterval: 15000,
});
const quotes = computed(() => data.value?.quotes ?? []);

function filterCount(f: Filter): number {
  const counts = data.value?.counts ?? {};
  const statuses = FILTER_STATUSES[f];
  if (!statuses) return 0;
  return statuses.split(",").reduce((sum, s) => sum + (counts[s] ?? 0), 0);
}

const { data: settingsData } = useQuery({
  queryKey: ["kp-settings"],
  queryFn: () => kpApi.getSettings(),
});
const presets = computed(() => settingsData.value?.validity_presets ?? [1, 2, 3]);

const { data: monitorData } = useQuery({
  queryKey: ["outbound-monitor"],
  queryFn: () => outboundApi.monitor(),
  refetchInterval: 60000,
});
const waInstances = computed(() => monitorData.value?.whatsapp ?? []);

async function invalidate() {
  await queryClient.invalidateQueries({ queryKey: ["kp-quotes"] });
  await queryClient.invalidateQueries({ queryKey: ["kp-events"] });
  await queryClient.invalidateQueries({ queryKey: ["outbound-messages"] });
  await queryClient.invalidateQueries({ queryKey: ["outbound-monitor"] });
}

const busy = ref<Record<number, boolean>>({});
async function withBusy(id: number, fn: () => Promise<void>) {
  busy.value[id] = true;
  try {
    await fn();
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("kp.actionFailed"));
  } finally {
    busy.value[id] = false;
  }
}

const syncing = ref(false);
async function sync() {
  syncing.value = true;
  try {
    await kpApi.sync();
    toast.success(t("kp.synced"));
    await invalidate();
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("kp.actionFailed"));
  } finally {
    syncing.value = false;
  }
}

// ─── Editing a draft ───
interface DraftEdit {
  message: string;
  delivery: KpDelivery;
  channel_instance_id: string;
  target: string;
  email: string;
}
const editing = ref<Record<number, DraftEdit>>({});

function startEdit(q: KpQuote) {
  editing.value[q.id] = {
    message: q.message ?? "",
    delivery: q.delivery,
    channel_instance_id: q.channel_instance_id ?? waInstances.value[0]?.instance_id ?? "",
    target: q.target ?? q.customer.phone ?? "",
    email: q.email ?? q.customer.email ?? "",
  };
}

function cancelEdit(id: number) {
  delete editing.value[id];
}

async function saveEdit(q: KpQuote) {
  const e = editing.value[q.id];
  if (!e) return;
  await withBusy(q.id, async () => {
    await kpApi.update(q.id, { ...e });
    delete editing.value[q.id];
    toast.success(t("kp.saved"));
    await invalidate();
  });
}

function isDraft(q: KpQuote) {
  return q.status === "pending" || q.status === "failed";
}
function isOpen(q: KpQuote) {
  return ["sent", "viewed", "clarification"].includes(q.status);
}

async function approve(q: KpQuote) {
  const e = editing.value[q.id];
  await withBusy(q.id, async () => {
    if (e) {
      await kpApi.update(q.id, { ...e });
      delete editing.value[q.id];
    }
    const resp = await kpApi.approve(q.id);
    if (resp.quote.status === "sent") {
      toast.success(t("kp.approvedToast", { number: resp.quote.number }));
      if (resp.quote.delivery === "link" && resp.quote.link) {
        await copy(resp.quote.link);
      }
    } else {
      toast.error(t("kp.sendFailed", { error: resp.quote.error || "" }));
    }
    await invalidate();
  });
}

async function reject(q: KpQuote) {
  const ok = await confirmStore.confirm({
    title: t("kp.confirmRejectTitle"),
    message: t("kp.confirmRejectMessage", { number: q.number }),
    confirmText: t("kp.reject"),
    cancelText: t("kp.cancel"),
    type: "warning",
  });
  if (!ok) return;
  await withBusy(q.id, async () => {
    await kpApi.reject(q.id);
    toast.success(t("kp.rejectedToast"));
    await invalidate();
  });
}

const reissueDays = ref<Record<number, number>>({});
const reissueRefresh = ref<Record<number, boolean>>({});

async function reissue(q: KpQuote) {
  const days = reissueDays.value[q.id] ?? settingsData.value?.default_valid_days ?? 3;
  await withBusy(q.id, async () => {
    const resp = await kpApi.reissue(
      q.id,
      days,
      reissueRefresh.value[q.id] ?? q.status === "expired"
    );
    toast.success(t("kp.reissuedToast", { number: resp.quote.number }));
    await invalidate();
  });
}

async function changeValidity(q: KpQuote, days: number) {
  await withBusy(q.id, async () => {
    const resp = await kpApi.update(q.id, { valid_days: days });
    toast.success(t("kp.reissuedToast", { number: resp.quote.number }));
    await invalidate();
  });
}

async function outcome(q: KpQuote, status: "accepted" | "lost") {
  await withBusy(q.id, async () => {
    await kpApi.outcome(q.id, status);
    toast.success(t(status === "accepted" ? "kp.acceptedToast" : "kp.lostToast"));
    await invalidate();
  });
}

async function remove(q: KpQuote) {
  const ok = await confirmStore.confirm({
    title: t("kp.confirmDeleteTitle"),
    message: t("kp.confirmDeleteMessage"),
    confirmText: t("kp.delete"),
    cancelText: t("kp.cancel"),
    type: "danger",
  });
  if (!ok) return;
  await withBusy(q.id, async () => {
    await kpApi.remove(q.id);
    toast.success(t("kp.deleted"));
    await invalidate();
  });
}

async function openPdf(q: KpQuote) {
  await withBusy(q.id, () => kpApi.openPdf(q.id));
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(t("kp.copied"));
  } catch {
    toast.info(text);
  }
}

// ─── History per quote ───
const history = ref<Record<number, KpQuote["events"]>>({});
async function toggleHistory(q: KpQuote) {
  if (history.value[q.id]) {
    delete history.value[q.id];
    return;
  }
  await withBusy(q.id, async () => {
    history.value[q.id] = (await kpApi.get(q.id)).quote.events ?? [];
  });
}

// ─── Attention list ───
const { data: eventsData } = useQuery({
  queryKey: ["kp-events"],
  queryFn: () => kpApi.events(true),
  refetchInterval: 30000,
});
const unreadEvents = computed(() => eventsData.value?.events ?? []);

async function ack(id: number) {
  try {
    await kpApi.ackEvent(id);
    await queryClient.invalidateQueries({ queryKey: ["kp-events"] });
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("kp.actionFailed"));
  }
}

// ─── Create ───
const showCreate = ref(false);
const creating = ref(false);
const dialogueSession = ref("");

function emptyForm() {
  return {
    customer: { name: "", contact: "", phone: "", email: "", bin: "" },
    items: [{ sku: "", name: "", price: 0, count: 1, delivery: "" }],
    valid_days: settingsData.value?.default_valid_days ?? 3,
    delivery: "link" as KpDelivery,
    channel_instance_id: "",
    target: "",
    email: "",
    message: "",
    request_number: "",
  };
}
const form = ref(emptyForm());

watch(showCreate, (open) => {
  if (open) form.value = emptyForm();
});

const formTotal = computed(() =>
  form.value.items.reduce((s, it) => s + (Number(it.price) || 0) * (Number(it.count) || 0), 0)
);

async function create() {
  creating.value = true;
  try {
    const f = form.value;
    const payload: KpCreatePayload = {
      customer: Object.fromEntries(Object.entries(f.customer).filter(([, v]) => v)),
      items: f.items
        .filter((it) => it.name.trim())
        .map((it) => ({ ...it, price: Number(it.price), count: Number(it.count) || 1 })),
      valid_days: f.valid_days,
      delivery: f.delivery,
      channel_instance_id: f.channel_instance_id || undefined,
      target: f.target || f.customer.phone || undefined,
      email: f.email || f.customer.email || undefined,
      message: f.message || undefined,
      request_number: f.request_number || undefined,
    };
    const resp = await kpApi.create(payload);
    toast.success(t("kp.createdToast", { number: resp.quote.number }));
    showCreate.value = false;
    filter.value = "pending";
    await invalidate();
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("kp.actionFailed"));
  } finally {
    creating.value = false;
  }
}

async function createFromDialogue() {
  if (!dialogueSession.value.trim()) return;
  creating.value = true;
  try {
    const resp = await kpApi.fromDialogue(dialogueSession.value.trim());
    toast.success(t("kp.createdToast", { number: resp.quote.number }));
    dialogueSession.value = "";
    showCreate.value = false;
    filter.value = "pending";
    await invalidate();
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("kp.actionFailed"));
  } finally {
    creating.value = false;
  }
}

// ─── Timers ───
const triggers: KpTrigger[] = [
  "not_approved",
  "not_viewed",
  "viewed_no_reply",
  "before_expiry",
  "expired",
];
const actions: KpAction[] = ["notify", "client_message", "mark_lost"];

const { data: rulesData } = useQuery({ queryKey: ["kp-rules"], queryFn: () => kpApi.rules() });
const ruleForms = ref<Record<number, KpRule>>({});
watch(
  () => rulesData.value?.rules,
  (rules) => {
    ruleForms.value = Object.fromEntries((rules ?? []).map((r) => [r.id, { ...r }]));
  },
  { immediate: true }
);
const rules = computed(() => rulesData.value?.rules ?? []);

function ruleDirty(r: KpRule) {
  const f = ruleForms.value[r.id];
  return (
    f &&
    (f.name !== r.name ||
      f.trigger !== r.trigger ||
      Number(f.offset_hours) !== r.offset_hours ||
      f.action !== r.action ||
      (f.message ?? "") !== (r.message ?? "") ||
      f.enabled !== r.enabled)
  );
}

async function saveRule(r: KpRule) {
  const f = ruleForms.value[r.id];
  try {
    await kpApi.updateRule(r.id, { ...f, offset_hours: Number(f.offset_hours) });
    toast.success(t("kp.ruleSaved"));
    await queryClient.invalidateQueries({ queryKey: ["kp-rules"] });
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("kp.actionFailed"));
  }
}

async function toggleRule(r: KpRule) {
  try {
    await kpApi.updateRule(r.id, { enabled: !r.enabled });
    await queryClient.invalidateQueries({ queryKey: ["kp-rules"] });
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("kp.actionFailed"));
  }
}

async function deleteRule(r: KpRule) {
  const ok = await confirmStore.confirm({
    title: t("kp.confirmDeleteRuleTitle"),
    message: r.name,
    confirmText: t("kp.delete"),
    cancelText: t("kp.cancel"),
    type: "danger",
  });
  if (!ok) return;
  try {
    await kpApi.deleteRule(r.id);
    await queryClient.invalidateQueries({ queryKey: ["kp-rules"] });
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("kp.actionFailed"));
  }
}

async function addRule() {
  try {
    await kpApi.createRule({
      name: t("kp.newRuleName"),
      trigger: "viewed_no_reply",
      offset_hours: 24,
      action: "notify",
      message: "",
      enabled: false,
      sort: (rules.value.at(-1)?.sort ?? 0) + 10,
    });
    await queryClient.invalidateQueries({ queryKey: ["kp-rules"] });
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("kp.actionFailed"));
  }
}

// ─── Settings ───
const settingsForm = ref<KpSettings | null>(null);
const presetsText = ref("");
watch(
  settingsData,
  (s) => {
    if (s) {
      settingsForm.value = { ...s };
      presetsText.value = s.validity_presets.join(", ");
    }
  },
  { immediate: true }
);
const savingSettings = ref(false);

async function saveSettings() {
  if (!settingsForm.value) return;
  savingSettings.value = true;
  try {
    const validity_presets = presetsText.value
      .split(/[,\s]+/)
      .map((v) => parseInt(v, 10))
      .filter((v) => v > 0);
    await kpApi.saveSettings({ ...settingsForm.value, validity_presets });
    toast.success(t("kp.settingsSaved"));
    await queryClient.invalidateQueries({ queryKey: ["kp-settings"] });
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("kp.actionFailed"));
  } finally {
    savingSettings.value = false;
  }
}

// ─── Formatting ───
function money(v: number | null, currency?: string | null) {
  if (v === null || v === undefined) return "—";
  return `${v.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ${currency || "₸"}`;
}

function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "—";
}

function formatDay(day: string | null): string {
  if (!day) return "—";
  const [y, m, d] = day.split("-");
  return `${d}.${m}.${y}`;
}

/** Days left until the end of validity, by calendar date. */
function daysLeft(q: KpQuote): number | null {
  if (!q.valid_until) return null;
  const end = new Date(`${q.valid_until}T23:59:59`);
  return Math.ceil((end.getTime() - Date.now()) / 86_400_000) - 1;
}

function validityClass(q: KpQuote): string {
  const left = daysLeft(q);
  if (left === null || !(isDraft(q) || isOpen(q))) return "text-muted-foreground";
  if (left < 0) return "text-red-400";
  if (left === 0) return "text-yellow-400";
  return "text-muted-foreground";
}

function statusClass(status: string): string {
  switch (status) {
    case "pending":
      return "bg-yellow-500/20 text-yellow-400";
    case "sent":
    case "viewed":
    case "clarification":
      return "bg-blue-500/20 text-blue-400";
    case "accepted":
      return "bg-green-500/20 text-green-400";
    case "expired":
    case "failed":
    case "sending":
      return "bg-red-500/20 text-red-400";
    default:
      return "bg-secondary text-muted-foreground";
  }
}

function approveLabel(q: KpQuote): string {
  if (q.status === "failed") return t("kp.retry");
  return t(`kp.approveVia.${q.delivery}`);
}
</script>

<template>
  <div class="space-y-6">
    <!-- PIM connection + toolbar -->
    <div class="card p-5">
      <div class="flex flex-wrap items-center gap-3">
        <FileText class="w-5 h-5 text-primary" />
        <h2 class="text-lg font-semibold">{{ t("kp.title") }}</h2>
        <span
          v-if="pimStatus"
          :class="[
            'px-2 py-0.5 rounded-full text-xs font-medium',
            pimStatus.ok ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400',
          ]"
        >
          {{
            pimStatus.ok
              ? t("kp.pimOk", { name: pimStatus.key_name || "" })
              : t("kp.pimError", { error: pimStatus.error || "" })
          }}
        </span>
        <span
          v-if="pimStatus?.ok && !pimStatus.can_send"
          class="px-2 py-0.5 rounded-full text-xs bg-yellow-500/20 text-yellow-400"
        >
          {{ t("kp.pimNoSend") }}
        </span>
        <div class="ml-auto flex gap-2">
          <button v-if="canEdit" class="btn btn-ghost" :disabled="syncing" @click="sync">
            <RefreshCw :class="['w-4 h-4', syncing && 'animate-spin']" />
            {{ t("kp.sync") }}
          </button>
          <button v-if="canEdit" class="btn btn-primary" @click="showCreate = !showCreate">
            <Plus class="w-4 h-4" />
            {{ t("kp.create") }}
          </button>
        </div>
      </div>
      <p class="text-sm text-muted-foreground mt-2">{{ t("kp.hint") }}</p>
    </div>

    <!-- Attention -->
    <div v-if="unreadEvents.length" class="card p-5 border-yellow-500/40">
      <div class="flex items-center gap-2 mb-3">
        <Bell class="w-5 h-5 text-yellow-400" />
        <h3 class="font-semibold">{{ t("kp.attention", { n: unreadEvents.length }) }}</h3>
      </div>
      <div class="space-y-2">
        <div
          v-for="ev in unreadEvents"
          :key="ev.id"
          class="flex items-start gap-3 p-3 rounded-lg bg-secondary/50 text-sm"
        >
          <Clock class="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground" />
          <div class="flex-1 whitespace-pre-wrap">
            <span class="font-medium">{{ ev.number }}</span>
            <span v-if="ev.customer" class="text-muted-foreground"> · {{ ev.customer }}</span>
            <div>{{ ev.text }}</div>
            <div class="text-xs text-muted-foreground mt-1">{{ formatDate(ev.created) }}</div>
          </div>
          <button v-if="canEdit" class="btn btn-ghost btn-sm" @click="ack(ev.id)">
            <Check class="w-4 h-4" /> {{ t("kp.ack") }}
          </button>
        </div>
      </div>
    </div>

    <!-- Create -->
    <div v-if="showCreate && canEdit" class="card p-5 space-y-4">
      <h3 class="font-semibold">{{ t("kp.createTitle") }}</h3>

      <div class="p-3 rounded-lg bg-secondary/40 flex flex-col md:flex-row gap-2 md:items-end">
        <div class="flex-1">
          <label class="block text-sm font-medium mb-1">{{ t("kp.fromDialogue") }}</label>
          <input
            v-model="dialogueSession"
            class="input w-full"
            :placeholder="t('kp.fromDialoguePlaceholder')"
          />
          <p class="text-xs text-muted-foreground mt-1">{{ t("kp.fromDialogueHint") }}</p>
        </div>
        <button
          class="btn btn-secondary"
          :disabled="creating || !dialogueSession.trim()"
          @click="createFromDialogue"
        >
          <MessageSquareText class="w-4 h-4" /> {{ t("kp.buildFromDialogue") }}
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div class="md:col-span-2">
          <label class="block text-sm font-medium mb-1">{{ t("kp.customerName") }} *</label>
          <input v-model="form.customer.name" class="input w-full" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t("kp.bin") }}</label>
          <input v-model="form.customer.bin" class="input w-full" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t("kp.contact") }}</label>
          <input v-model="form.customer.contact" class="input w-full" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t("kp.phone") }}</label>
          <input
            v-model="form.customer.phone"
            class="input w-full"
            placeholder="+7 7xx xxx xx xx"
          />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t("kp.email") }}</label>
          <input v-model="form.customer.email" class="input w-full" />
        </div>
      </div>

      <div>
        <label class="block text-sm font-medium mb-1">{{ t("kp.items") }}</label>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-muted-foreground">
                <th class="py-1 pr-2">{{ t("kp.sku") }}</th>
                <th class="py-1 pr-2">{{ t("kp.itemName") }}</th>
                <th class="py-1 pr-2 w-24">{{ t("kp.qty") }}</th>
                <th class="py-1 pr-2 w-32">{{ t("kp.price") }}</th>
                <th class="py-1 pr-2 w-36">{{ t("kp.deliveryTerm") }}</th>
                <th class="w-8"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(it, i) in form.items" :key="i">
                <td class="pr-2 py-1"><input v-model="it.sku" class="input w-full" /></td>
                <td class="pr-2 py-1"><input v-model="it.name" class="input w-full" /></td>
                <td class="pr-2 py-1">
                  <input v-model.number="it.count" type="number" min="1" class="input w-full" />
                </td>
                <td class="pr-2 py-1">
                  <input
                    v-model.number="it.price"
                    type="number"
                    min="0"
                    step="0.01"
                    class="input w-full"
                  />
                </td>
                <td class="pr-2 py-1">
                  <input
                    v-model="it.delivery"
                    class="input w-full"
                    :placeholder="t('kp.inStock')"
                  />
                </td>
                <td>
                  <button
                    class="btn btn-ghost btn-sm text-red-400"
                    :disabled="form.items.length === 1"
                    @click="form.items.splice(i, 1)"
                  >
                    <X class="w-4 h-4" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="flex items-center justify-between mt-2">
          <button
            class="btn btn-ghost btn-sm"
            @click="form.items.push({ sku: '', name: '', price: 0, count: 1, delivery: '' })"
          >
            <Plus class="w-4 h-4" /> {{ t("kp.addItem") }}
          </button>
          <span class="text-sm font-medium">{{ t("kp.total") }}: {{ money(formTotal) }}</span>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label class="block text-sm font-medium mb-1">{{ t("kp.validity") }}</label>
          <select v-model.number="form.valid_days" class="input w-full">
            <option v-for="d in presets" :key="d" :value="d">{{ t("kp.days", { n: d }) }}</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t("kp.delivery") }}</label>
          <select v-model="form.delivery" class="input w-full">
            <option value="whatsapp">{{ t("kp.deliveryMode.whatsapp") }}</option>
            <option value="email">{{ t("kp.deliveryMode.email") }}</option>
            <option value="link">{{ t("kp.deliveryMode.link") }}</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t("kp.requestNumber") }}</label>
          <input v-model="form.request_number" class="input w-full" />
        </div>
        <template v-if="form.delivery === 'whatsapp'">
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("kp.waInstance") }}</label>
            <select v-model="form.channel_instance_id" class="input w-full">
              <option v-for="inst in waInstances" :key="inst.instance_id" :value="inst.instance_id">
                {{ inst.name }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("kp.waTarget") }}</label>
            <input v-model="form.target" class="input w-full" :placeholder="form.customer.phone" />
          </div>
        </template>
        <div v-if="form.delivery === 'email'">
          <label class="block text-sm font-medium mb-1">{{ t("kp.emailTo") }}</label>
          <input v-model="form.email" class="input w-full" :placeholder="form.customer.email" />
        </div>
      </div>

      <div>
        <label class="block text-sm font-medium mb-1">{{ t("kp.messageText") }}</label>
        <textarea
          v-model="form.message"
          rows="3"
          class="input w-full"
          :placeholder="t('kp.messagePlaceholder')"
        />
      </div>

      <div class="flex justify-end gap-2">
        <button class="btn btn-ghost" @click="showCreate = false">{{ t("kp.cancel") }}</button>
        <button class="btn btn-primary" :disabled="creating" @click="create">
          <Save class="w-4 h-4" /> {{ t("kp.createDraft") }}
        </button>
      </div>
    </div>

    <!-- Quotes -->
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
            {{ t(`kp.filter.${f}`) }}
            <span
              v-if="f !== 'all' && filterCount(f)"
              :class="[
                'text-xs px-1.5 rounded-full',
                ['pending', 'failed', 'expired'].includes(f)
                  ? 'bg-red-500 text-white'
                  : 'bg-background/40',
              ]"
            >
              {{ filterCount(f) }}
            </span>
          </button>
        </div>
        <button class="btn btn-ghost" :disabled="isFetching" @click="refetch()">
          <RefreshCw :class="['w-4 h-4', isFetching && 'animate-spin']" />
        </button>
      </div>

      <div v-if="!quotes.length" class="py-10 text-center text-muted-foreground text-sm">
        {{ t("kp.empty") }}
      </div>

      <div class="space-y-4">
        <div
          v-for="q in quotes"
          :key="q.id"
          class="rounded-lg border border-border overflow-hidden"
        >
          <!-- Header -->
          <div class="flex flex-wrap items-center gap-2 px-4 py-2 bg-secondary/50 text-sm">
            <FileText class="w-4 h-4 text-primary" />
            <span class="font-semibold">{{ q.number || "—" }}</span>
            <span class="text-muted-foreground">· {{ q.customer.name || "—" }}</span>
            <span class="font-medium">· {{ money(q.total, q.currency) }}</span>
            <span :class="['px-2 py-0.5 rounded-full text-xs font-medium', statusClass(q.status)]">
              {{ t(`kp.status.${q.status}`) }}
            </span>
            <span class="px-2 py-0.5 rounded-full text-xs bg-secondary text-muted-foreground">
              {{ t(`kp.origin.${q.origin}`) }}
            </span>
            <span :class="['ml-auto text-xs flex items-center gap-1', validityClass(q)]">
              <Timer class="w-3 h-3" />
              {{ t("kp.validUntil", { date: formatDay(q.valid_until) }) }}
              <template v-if="(isDraft(q) || isOpen(q)) && daysLeft(q) !== null">
                ({{
                  daysLeft(q)! < 0
                    ? t("kp.expiredShort")
                    : daysLeft(q) === 0
                      ? t("kp.lastDay")
                      : t("kp.daysLeft", { n: daysLeft(q) })
                }})
              </template>
            </span>
          </div>

          <div class="p-4 space-y-3">
            <!-- Items -->
            <details>
              <summary class="text-sm cursor-pointer text-muted-foreground">
                {{ t("kp.itemsCount", { n: q.items.length }) }}
              </summary>
              <div class="overflow-x-auto mt-2">
                <table class="w-full text-sm">
                  <thead>
                    <tr class="text-left text-muted-foreground">
                      <th class="py-1 pr-2">{{ t("kp.sku") }}</th>
                      <th class="py-1 pr-2">{{ t("kp.itemName") }}</th>
                      <th class="py-1 pr-2 text-right">{{ t("kp.qty") }}</th>
                      <th class="py-1 pr-2 text-right">{{ t("kp.price") }}</th>
                      <th class="py-1 pr-2">{{ t("kp.deliveryTerm") }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(it, i) in q.items" :key="i" class="border-t border-border/50">
                      <td class="py-1 pr-2 text-muted-foreground">{{ it.sku || "—" }}</td>
                      <td class="py-1 pr-2">{{ it.name }}</td>
                      <td class="py-1 pr-2 text-right">{{ it.count }}</td>
                      <td class="py-1 pr-2 text-right">{{ money(it.price, q.currency) }}</td>
                      <td class="py-1 pr-2">{{ it.delivery || "—" }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </details>

            <div
              v-if="q.flags.length"
              class="text-sm p-3 rounded-lg bg-yellow-500/10 text-yellow-300"
            >
              <div class="font-medium mb-1 flex items-center gap-1">
                <AlertTriangle class="w-4 h-4" /> {{ t("kp.flagsTitle") }}
              </div>
              <ul class="list-disc pl-5 space-y-0.5">
                <li v-for="(f, i) in q.flags" :key="i">{{ f }}</li>
              </ul>
            </div>

            <!-- Delivery + message -->
            <div class="text-sm text-muted-foreground">
              {{ t(`kp.deliveryMode.${q.delivery}`) }}
              <template v-if="q.delivery === 'whatsapp'"
                >· {{ q.target }} · {{ q.channel_instance_id }}</template
              >
              <template v-if="q.delivery === 'email'">· {{ q.email || q.customer.email }}</template>
              <template v-if="q.customer.contact">· {{ q.customer.contact }}</template>
              <template v-if="q.customer.phone">· {{ q.customer.phone }}</template>
            </div>

            <template v-if="editing[q.id]">
              <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                <select v-model="editing[q.id].delivery" class="input w-full">
                  <option value="whatsapp">{{ t("kp.deliveryMode.whatsapp") }}</option>
                  <option value="email">{{ t("kp.deliveryMode.email") }}</option>
                  <option value="link">{{ t("kp.deliveryMode.link") }}</option>
                </select>
                <template v-if="editing[q.id].delivery === 'whatsapp'">
                  <select v-model="editing[q.id].channel_instance_id" class="input w-full">
                    <option
                      v-for="inst in waInstances"
                      :key="inst.instance_id"
                      :value="inst.instance_id"
                    >
                      {{ inst.name }}
                    </option>
                  </select>
                  <input
                    v-model="editing[q.id].target"
                    class="input w-full"
                    :placeholder="t('kp.waTarget')"
                  />
                </template>
                <input
                  v-if="editing[q.id].delivery === 'email'"
                  v-model="editing[q.id].email"
                  class="input w-full md:col-span-2"
                  :placeholder="t('kp.emailTo')"
                />
              </div>
              <textarea v-model="editing[q.id].message" rows="4" class="input w-full" />
              <p class="text-xs text-muted-foreground">{{ t("kp.linkHint") }}</p>
            </template>
            <div
              v-else-if="q.message && q.delivery !== 'link'"
              class="text-sm p-3 rounded-lg border border-primary/30 bg-primary/5 whitespace-pre-wrap"
            >
              {{ q.message }}
            </div>

            <div v-if="q.link" class="flex items-center gap-2 text-sm">
              <a
                :href="q.link"
                target="_blank"
                rel="noopener"
                class="text-primary hover:underline truncate"
              >
                {{ q.link }}
              </a>
              <button class="btn btn-ghost btn-sm" @click="copy(q.link)">
                <Copy class="w-4 h-4" />
              </button>
              <span v-if="q.link_active === false" class="text-xs text-red-400">{{
                t("kp.linkOff")
              }}</span>
            </div>

            <div v-if="q.error" class="flex items-start gap-2 text-sm text-red-400">
              <AlertTriangle class="w-4 h-4 shrink-0 mt-0.5" /> {{ q.error }}
            </div>
            <div v-if="q.note" class="text-xs text-muted-foreground whitespace-pre-wrap">
              {{ q.note }}
            </div>
            <div class="text-xs text-muted-foreground">
              {{ t("kp.createdBy", { user: q.created_by || "—", date: formatDate(q.created) }) }}
              <template v-if="q.sent_at">
                · {{ t("kp.sentAt", { date: formatDate(q.sent_at) }) }}</template
              >
              <template v-if="q.decided_by">
                · {{ t("kp.decidedBy", { user: q.decided_by }) }}</template
              >
            </div>

            <!-- Actions -->
            <div class="flex flex-wrap items-center gap-2 pt-1">
              <template v-if="canEdit && isDraft(q)">
                <button class="btn btn-primary btn-sm" :disabled="busy[q.id]" @click="approve(q)">
                  <Send class="w-4 h-4" /> {{ approveLabel(q) }}
                </button>
                <template v-if="editing[q.id]">
                  <button class="btn btn-ghost btn-sm" :disabled="busy[q.id]" @click="saveEdit(q)">
                    <Save class="w-4 h-4" /> {{ t("kp.save") }}
                  </button>
                  <button class="btn btn-ghost btn-sm" @click="cancelEdit(q.id)">
                    {{ t("kp.cancel") }}
                  </button>
                </template>
                <button v-else class="btn btn-ghost btn-sm" @click="startEdit(q)">
                  <Pencil class="w-4 h-4" /> {{ t("kp.edit") }}
                </button>
                <select
                  class="input input-sm w-auto"
                  :value="q.valid_days ?? ''"
                  :disabled="busy[q.id]"
                  :title="t('kp.changeValidity')"
                  @change="changeValidity(q, Number(($event.target as HTMLSelectElement).value))"
                >
                  <option v-for="d in presets" :key="d" :value="d">
                    {{ t("kp.days", { n: d }) }}
                  </option>
                </select>
                <button
                  class="btn btn-ghost btn-sm text-red-400"
                  :disabled="busy[q.id]"
                  @click="reject(q)"
                >
                  <X class="w-4 h-4" /> {{ t("kp.reject") }}
                </button>
              </template>

              <template v-if="canEdit && (isOpen(q) || q.status === 'expired')">
                <button
                  class="btn btn-ghost btn-sm text-green-400"
                  :disabled="busy[q.id]"
                  @click="outcome(q, 'accepted')"
                >
                  <ThumbsUp class="w-4 h-4" /> {{ t("kp.markAccepted") }}
                </button>
                <button
                  class="btn btn-ghost btn-sm text-red-400"
                  :disabled="busy[q.id]"
                  @click="outcome(q, 'lost')"
                >
                  <ThumbsDown class="w-4 h-4" /> {{ t("kp.markLost") }}
                </button>
                <select v-model.number="reissueDays[q.id]" class="input input-sm w-auto">
                  <option :value="undefined" disabled>{{ t("kp.validity") }}</option>
                  <option v-for="d in presets" :key="d" :value="d">
                    {{ t("kp.days", { n: d }) }}
                  </option>
                </select>
                <label class="flex items-center gap-1 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    :checked="reissueRefresh[q.id] ?? q.status === 'expired'"
                    @change="reissueRefresh[q.id] = ($event.target as HTMLInputElement).checked"
                  />
                  {{ t("kp.refreshPrices") }}
                </label>
                <button class="btn btn-secondary btn-sm" :disabled="busy[q.id]" @click="reissue(q)">
                  <RotateCcw class="w-4 h-4" /> {{ t("kp.reissue") }}
                </button>
              </template>

              <div class="ml-auto flex gap-1">
                <button
                  v-if="q.pim_id"
                  class="btn btn-ghost btn-sm"
                  :disabled="busy[q.id]"
                  :title="t('kp.pdf')"
                  @click="openPdf(q)"
                >
                  <FileText class="w-4 h-4" />
                </button>
                <a
                  v-if="q.edit_url"
                  :href="q.edit_url"
                  target="_blank"
                  rel="noopener"
                  class="btn btn-ghost btn-sm"
                  :title="t('kp.openInPim')"
                >
                  <ExternalLink class="w-4 h-4" />
                </a>
                <button
                  class="btn btn-ghost btn-sm"
                  :title="t('kp.history')"
                  @click="toggleHistory(q)"
                >
                  <Clock class="w-4 h-4" />
                </button>
                <button
                  v-if="canManage && q.status !== 'sending'"
                  class="btn btn-ghost btn-sm text-muted-foreground"
                  :disabled="busy[q.id]"
                  @click="remove(q)"
                >
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
            </div>

            <div v-if="history[q.id]" class="text-xs space-y-1 border-t border-border pt-2">
              <div v-for="ev in history[q.id]" :key="ev.id" class="flex gap-2">
                <span class="text-muted-foreground shrink-0">{{ formatDate(ev.created) }}</span>
                <span class="whitespace-pre-wrap">{{ ev.text }}</span>
              </div>
              <div v-if="!history[q.id]!.length" class="text-muted-foreground">
                {{ t("kp.noHistory") }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Timers -->
    <div class="card p-5">
      <div class="flex items-center gap-2 mb-1">
        <Timer class="w-5 h-5 text-primary" />
        <h2 class="text-lg font-semibold">{{ t("kp.timersTitle") }}</h2>
        <button v-if="canEdit" class="btn btn-ghost btn-sm ml-auto" @click="addRule">
          <Plus class="w-4 h-4" /> {{ t("kp.addRule") }}
        </button>
      </div>
      <p class="text-sm text-muted-foreground mb-4">{{ t("kp.timersHint") }}</p>

      <div class="space-y-3">
        <div
          v-for="r in rules"
          :key="r.id"
          :class="[
            'p-4 rounded-lg border border-border',
            r.enabled ? 'bg-secondary/40' : 'opacity-60',
          ]"
        >
          <div v-if="ruleForms[r.id]" class="grid grid-cols-1 md:grid-cols-12 gap-3">
            <input
              v-model="ruleForms[r.id].name"
              class="input md:col-span-4"
              :disabled="!canEdit"
            />
            <select
              v-model="ruleForms[r.id].trigger"
              class="input md:col-span-3"
              :disabled="!canEdit"
            >
              <option v-for="tr in triggers" :key="tr" :value="tr">
                {{ t(`kp.trigger.${tr}`) }}
              </option>
            </select>
            <div class="md:col-span-2 flex items-center gap-1">
              <input
                v-model.number="ruleForms[r.id].offset_hours"
                type="number"
                min="0"
                step="0.5"
                class="input w-full"
                :disabled="!canEdit"
              />
              <span class="text-xs text-muted-foreground">{{ t("kp.hours") }}</span>
            </div>
            <select
              v-model="ruleForms[r.id].action"
              class="input md:col-span-3"
              :disabled="!canEdit"
            >
              <option v-for="a in actions" :key="a" :value="a">{{ t(`kp.action.${a}`) }}</option>
            </select>
            <textarea
              v-model="ruleForms[r.id].message"
              rows="2"
              class="input md:col-span-12"
              :placeholder="t('kp.ruleMessagePlaceholder')"
              :disabled="!canEdit"
            />
            <div v-if="canEdit" class="md:col-span-12 flex items-center gap-2">
              <label class="flex items-center gap-2 text-sm">
                <input type="checkbox" :checked="r.enabled" @change="toggleRule(r)" />
                {{ t("kp.ruleEnabled") }}
              </label>
              <span class="text-xs text-muted-foreground">{{
                t(`kp.triggerHint.${ruleForms[r.id].trigger}`)
              }}</span>
              <button
                class="btn btn-primary btn-sm ml-auto"
                :disabled="!ruleDirty(r)"
                @click="saveRule(r)"
              >
                <Save class="w-4 h-4" /> {{ t("kp.save") }}
              </button>
              <button class="btn btn-ghost btn-sm text-red-400" @click="deleteRule(r)">
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
      <p class="text-xs text-muted-foreground mt-3">{{ t("kp.placeholdersHint") }}</p>
    </div>

    <!-- Settings -->
    <div v-if="settingsForm" class="card p-5">
      <div class="flex items-center gap-2 mb-4">
        <Settings2 class="w-5 h-5 text-primary" />
        <h2 class="text-lg font-semibold">{{ t("kp.settingsTitle") }}</h2>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium mb-1">{{ t("kp.presets") }}</label>
          <input
            v-model="presetsText"
            class="input w-full"
            :disabled="!canEdit"
            placeholder="1, 2, 3"
          />
          <p class="text-xs text-muted-foreground mt-1">{{ t("kp.presetsHint") }}</p>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t("kp.defaultValidity") }}</label>
          <input
            v-model.number="settingsForm.default_valid_days"
            type="number"
            min="1"
            class="input w-full"
            :disabled="!canEdit"
          />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t("kp.followupInstance") }}</label>
          <select
            v-model="settingsForm.followup_instance_id"
            class="input w-full"
            :disabled="!canEdit"
          >
            <option value="">{{ t("kp.none") }}</option>
            <option v-for="inst in waInstances" :key="inst.instance_id" :value="inst.instance_id">
              {{ inst.name }}
            </option>
          </select>
          <p class="text-xs text-muted-foreground mt-1">{{ t("kp.followupInstanceHint") }}</p>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t("kp.notifyChatId") }}</label>
          <input v-model="settingsForm.notify_chat_id" class="input w-full" :disabled="!canEdit" />
          <p class="text-xs text-muted-foreground mt-1">{{ t("kp.notifyChatIdHint") }}</p>
        </div>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="settingsForm.auto_draft" type="checkbox" :disabled="!canEdit" />
          {{ t("kp.autoDraft") }}
        </label>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="settingsForm.import_pim_quotes" type="checkbox" :disabled="!canEdit" />
          {{ t("kp.importPim") }}
        </label>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="settingsForm.notify_telegram" type="checkbox" :disabled="!canEdit" />
          {{ t("kp.notifyTelegram") }}
        </label>
        <div class="md:col-span-2">
          <label class="block text-sm font-medium mb-1">{{ t("kp.sendTemplate") }}</label>
          <textarea
            v-model="settingsForm.send_template"
            rows="3"
            class="input w-full"
            :disabled="!canEdit"
          />
        </div>
      </div>
      <div v-if="canEdit" class="flex justify-end mt-4">
        <button class="btn btn-primary" :disabled="savingSettings" @click="saveSettings">
          <Save class="w-4 h-4" /> {{ t("kp.saveSettings") }}
        </button>
      </div>
    </div>
  </div>
</template>
