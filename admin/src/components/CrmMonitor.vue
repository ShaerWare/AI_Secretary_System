<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import {
  RefreshCw,
  Activity,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  MessageCircle,
  Globe,
  Send,
  Building2,
  Inbox,
  Save,
  Smartphone,
  Bot,
} from "lucide-vue-next";
import { outboundApi } from "@/api/outbound";
import type { ChannelSummary } from "@/api/outbound";
import { useToastStore } from "@/stores/toast";
import { useAuthStore } from "@/stores";

const emit = defineEmits<{ (e: "open-queue"): void }>();

const { t } = useI18n();
const toast = useToastStore();
const authStore = useAuthStore();
const queryClient = useQueryClient();
const canManage = computed(() => authStore.canManage("sales"));

const { data, isFetching, refetch, error } = useQuery({
  queryKey: ["outbound-monitor"],
  queryFn: () => outboundApi.monitor(),
  refetchInterval: 30000,
});

const monitor = computed(() => data.value);

// ─── Thresholds ───
const thresholds = ref({ unanswered_minutes: 10, pending_alert_minutes: 30 });
const savingThresholds = ref(false);
watch(
  () => monitor.value?.settings,
  (s) => {
    if (s) thresholds.value = { ...s };
  },
  { immediate: true }
);

async function saveThresholds() {
  savingThresholds.value = true;
  try {
    await outboundApi.saveSettings({
      unanswered_minutes: Number(thresholds.value.unanswered_minutes),
      pending_alert_minutes: Number(thresholds.value.pending_alert_minutes),
    });
    toast.success(t("monitor.thresholdsSaved"));
    await queryClient.invalidateQueries({ queryKey: ["outbound-monitor"] });
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t("outbound.actionFailed"));
  } finally {
    savingThresholds.value = false;
  }
}

// ─── Formatting ───
function duration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 60) return t("monitor.dur.sec", { n: seconds });
  const min = Math.floor(seconds / 60);
  if (min < 60) return t("monitor.dur.min", { n: min });
  const h = Math.floor(min / 60);
  if (h < 48) return t("monitor.dur.hour", { n: h, m: min % 60 });
  return t("monitor.dur.day", { n: Math.floor(h / 24) });
}

function ago(iso: string | null): string {
  if (!iso) return t("monitor.never");
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  return t("monitor.ago", { d: duration(seconds) });
}

const statusMeta = computed(() => {
  switch (monitor.value?.status) {
    case "ok":
      return { cls: "bg-green-500/10 border-green-500/30 text-green-400", icon: CheckCircle2 };
    case "warning":
      return { cls: "bg-yellow-500/10 border-yellow-500/30 text-yellow-400", icon: AlertTriangle };
    default:
      return { cls: "bg-red-500/10 border-red-500/30 text-red-400", icon: XCircle };
  }
});

function channelIcon(key: string) {
  if (key === "widget") return Globe;
  if (key === "telegram") return Send;
  return MessageCircle;
}

function bridgeLabel(status: string | null): string {
  if (!status) return "—";
  const known = [
    "idle",
    "starting",
    "qr",
    "pairing",
    "connected",
    "disconnected",
    "logged_out",
    "unreachable",
  ];
  return known.includes(status) ? t(`monitor.bridge.${status}`) : status;
}

function otherChannelName(c: ChannelSummary): string {
  return t(`monitor.channel.${c.key}`);
}
</script>

<template>
  <div class="space-y-6">
    <div v-if="error && !monitor" class="card p-6 text-red-400 text-sm">
      {{ t("monitor.loadFailed") }}
    </div>

    <template v-if="monitor">
      <!-- Overall status -->
      <div :class="['rounded-xl border p-4 flex items-start gap-3', statusMeta.cls]">
        <component :is="statusMeta.icon" class="w-6 h-6 shrink-0" />
        <div class="flex-1">
          <div class="font-semibold">{{ t(`monitor.overall.${monitor.status}`) }}</div>
          <ul v-if="monitor.alerts.length" class="mt-1 space-y-0.5 text-sm text-foreground">
            <li v-for="(a, i) in monitor.alerts" :key="i" class="flex items-start gap-1.5">
              <span
                :class="[
                  'mt-1.5 w-1.5 h-1.5 rounded-full shrink-0',
                  a.level === 'error' ? 'bg-red-400' : 'bg-yellow-400',
                ]"
              />
              {{ a.text }}
            </li>
          </ul>
          <div class="text-xs text-muted-foreground mt-1">
            {{ t("monitor.checkedAt", { d: new Date(monitor.checked_at).toLocaleTimeString() }) }}
          </div>
        </div>
        <button class="btn btn-ghost btn-sm" :disabled="isFetching" @click="refetch()">
          <RefreshCw :class="['w-4 h-4', isFetching && 'animate-spin']" />
        </button>
      </div>

      <!-- Queue stats -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <button
          class="card p-4 text-left hover:border-primary/50 transition-colors"
          @click="emit('open-queue')"
        >
          <div class="flex items-center gap-2 text-sm text-muted-foreground">
            <Inbox class="w-4 h-4" /> {{ t("monitor.pending") }}
          </div>
          <div :class="['text-2xl font-bold mt-1', monitor.queue.pending ? 'text-yellow-400' : '']">
            {{ monitor.queue.pending }}
          </div>
        </button>
        <div class="card p-4">
          <div class="text-sm text-muted-foreground">{{ t("monitor.oldestPending") }}</div>
          <div class="text-2xl font-bold mt-1">
            {{ duration(monitor.queue.oldest_pending_seconds) }}
          </div>
        </div>
        <button
          class="card p-4 text-left hover:border-primary/50 transition-colors"
          @click="emit('open-queue')"
        >
          <div class="text-sm text-muted-foreground">{{ t("monitor.failed") }}</div>
          <div :class="['text-2xl font-bold mt-1', monitor.queue.failed ? 'text-red-400' : '']">
            {{ monitor.queue.failed }}
          </div>
        </button>
        <div class="card p-4">
          <div class="text-sm text-muted-foreground">{{ t("monitor.sentToday") }}</div>
          <div class="text-2xl font-bold mt-1">{{ monitor.queue.sent_today }}</div>
        </div>
      </div>

      <!-- WhatsApp instances -->
      <div v-for="wa in monitor.whatsapp" :key="wa.key" class="card p-5">
        <div class="flex flex-wrap items-center gap-2 mb-4">
          <MessageCircle class="w-5 h-5 text-green-500" />
          <h3 class="font-semibold">WhatsApp · {{ wa.name }}</h3>
          <span class="text-xs text-muted-foreground">{{ wa.instance_id }}</span>
          <span
            :class="[
              'ml-auto px-2 py-0.5 rounded-full text-xs font-medium',
              wa.mode === 'approval'
                ? 'bg-blue-500/20 text-blue-400'
                : 'bg-secondary text-muted-foreground',
            ]"
          >
            {{ wa.mode === "approval" ? t("outbound.modeApproval") : t("outbound.modeAuto") }}
          </span>
          <span
            v-if="!wa.enabled"
            class="px-2 py-0.5 rounded-full text-xs bg-secondary text-muted-foreground"
          >
            {{ t("monitor.disabled") }}
          </span>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
          <div class="p-3 rounded-lg bg-secondary/50">
            <div class="flex items-center gap-1.5 text-muted-foreground">
              <Bot class="w-4 h-4" /> {{ t("monitor.bot") }}
            </div>
            <div :class="['font-medium mt-1', wa.bot_running ? 'text-green-400' : 'text-red-400']">
              {{
                wa.bot_running
                  ? t("monitor.running", { d: duration(wa.bot_uptime_seconds) })
                  : t("monitor.stopped")
              }}
            </div>
          </div>
          <div class="p-3 rounded-lg bg-secondary/50">
            <div class="flex items-center gap-1.5 text-muted-foreground">
              <Smartphone class="w-4 h-4" /> {{ t("monitor.phone") }}
            </div>
            <div
              v-if="wa.provider === 'bridge'"
              :class="[
                'font-medium mt-1',
                wa.bridge_status === 'connected' ? 'text-green-400' : 'text-red-400',
              ]"
              :title="wa.bridge_error || ''"
            >
              {{ bridgeLabel(wa.bridge_status) }}
            </div>
            <div v-else class="font-medium mt-1 text-muted-foreground">Cloud API</div>
            <div v-if="wa.bridge_error" class="text-xs text-red-400 mt-0.5 truncate">
              {{ wa.bridge_error }}
            </div>
          </div>
          <div class="p-3 rounded-lg bg-secondary/50">
            <div class="text-muted-foreground">{{ t("monitor.lastInbound") }}</div>
            <div class="font-medium mt-1">{{ ago(wa.last_inbound_at) }}</div>
          </div>
          <div class="p-3 rounded-lg bg-secondary/50">
            <div class="text-muted-foreground">{{ t("monitor.lastOutbound") }}</div>
            <div class="font-medium mt-1">{{ ago(wa.last_outbound_at) }}</div>
          </div>
        </div>

        <div class="mt-3 text-xs text-muted-foreground">
          {{ t("monitor.conversations72h", { n: wa.conversations_72h }) }}
        </div>

        <div v-if="wa.unanswered.length" class="mt-4">
          <div class="text-sm font-medium text-red-400 mb-2 flex items-center gap-1.5">
            <AlertTriangle class="w-4 h-4" />
            {{ t("monitor.unanswered", { n: wa.unanswered_count }) }}
          </div>
          <div class="space-y-1.5">
            <div
              v-for="u in wa.unanswered"
              :key="u.session_id"
              class="flex items-start gap-3 text-sm p-2 rounded bg-red-500/5 border border-red-500/20"
            >
              <span class="font-medium shrink-0">{{ u.target }}</span>
              <span class="text-muted-foreground flex-1 truncate">{{ u.preview }}</span>
              <span class="text-red-400 shrink-0">{{ duration(u.waiting_seconds) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Other channels + CRM -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div v-for="c in monitor.channels" :key="c.key" class="card p-4">
          <div class="flex items-center gap-2 font-medium mb-3">
            <component :is="channelIcon(c.key)" class="w-4 h-4 text-primary" />
            {{ otherChannelName(c) }}
          </div>
          <div class="text-sm space-y-1">
            <div class="flex justify-between gap-2">
              <span class="text-muted-foreground">{{ t("monitor.lastInbound") }}</span
              ><span>{{ ago(c.last_inbound_at) }}</span>
            </div>
            <div class="flex justify-between gap-2">
              <span class="text-muted-foreground">{{ t("monitor.lastOutbound") }}</span
              ><span>{{ ago(c.last_outbound_at) }}</span>
            </div>
            <div class="flex justify-between gap-2">
              <span class="text-muted-foreground">{{ t("monitor.dialogs") }}</span
              ><span>{{ c.conversations_72h }}</span>
            </div>
            <div v-if="c.unanswered_count" class="text-red-400 pt-1">
              {{ t("monitor.unanswered", { n: c.unanswered_count }) }}
            </div>
          </div>
        </div>

        <div class="card p-4">
          <div class="flex items-center gap-2 font-medium mb-3">
            <Building2 class="w-4 h-4 text-blue-500" /> amoCRM
          </div>
          <div class="text-sm space-y-1">
            <div class="flex justify-between gap-2">
              <span class="text-muted-foreground">{{ t("monitor.crmStatus") }}</span>
              <span :class="monitor.crm.connected ? 'text-green-400' : 'text-red-400'">
                {{ monitor.crm.connected ? t("crm.connected") : t("crm.notConnected") }}
              </span>
            </div>
            <div class="flex justify-between gap-2">
              <span class="text-muted-foreground">{{ t("monitor.autoLead") }}</span>
              <span>{{ monitor.crm.auto_create_lead ? t("monitor.yes") : t("monitor.no") }}</span>
            </div>
            <div class="flex justify-between gap-2">
              <span class="text-muted-foreground">{{ t("crm.lastSync") }}</span>
              <span>{{
                monitor.crm.last_sync_at
                  ? new Date(monitor.crm.last_sync_at).toLocaleDateString()
                  : t("crm.never")
              }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Thresholds -->
      <div class="card p-5">
        <div class="flex items-center gap-2 mb-4">
          <Activity class="w-5 h-5 text-primary" />
          <h3 class="font-semibold">{{ t("monitor.thresholds") }}</h3>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">{{
              t("monitor.unansweredMinutes")
            }}</label>
            <input
              v-model.number="thresholds.unanswered_minutes"
              type="number"
              min="1"
              class="input w-full"
              :disabled="!canManage"
            />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">{{
              t("monitor.pendingAlertMinutes")
            }}</label>
            <input
              v-model.number="thresholds.pending_alert_minutes"
              type="number"
              min="1"
              class="input w-full"
              :disabled="!canManage"
            />
          </div>
        </div>
        <div v-if="canManage" class="flex justify-end mt-4">
          <button class="btn btn-primary" :disabled="savingThresholds" @click="saveThresholds">
            <Save class="w-4 h-4" /> {{ t("monitor.save") }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
