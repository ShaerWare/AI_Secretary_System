<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from "@tanstack/vue-query";
import {
  workspaceApi,
  type WorkspaceMember,
  type WorkspaceInfo,
  type WorkspaceInvite,
  type RoleInfo,
} from "@/api/workspace";
import { usageApi, type UsageByUserResponse } from "@/api/usage";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import { useConfirmStore } from "@/stores/confirm";
import { computed, ref } from "vue";
import {
  UserCog,
  Users,
  Shield,
  Crown,
  Trash2,
  RefreshCw,
  Link,
  Plus,
  Copy,
  Check,
} from "lucide-vue-next";
import InviteDialog from "@/components/InviteDialog.vue";

const { t } = useI18n();
const authStore = useAuthStore();
const toast = useToastStore();
const confirm = useConfirmStore();
const queryClient = useQueryClient();

const showInviteDialog = ref(false);

// Queries
const { data: workspaceInfo, isLoading: infoLoading } = useQuery({
  queryKey: ["workspace-info"],
  queryFn: () => workspaceApi.getInfo(),
});

const {
  data: members,
  isLoading: membersLoading,
  refetch: refetchMembers,
} = useQuery({
  queryKey: ["workspace-members"],
  queryFn: () => workspaceApi.listMembers(),
});

const { data: roles } = useQuery({
  queryKey: ["roles-list"],
  queryFn: () => workspaceApi.listRoles(),
  enabled: computed(() => authStore.canManage("users")),
});

const { data: invites, isLoading: invitesLoading } = useQuery({
  queryKey: ["workspace-invites"],
  queryFn: () => workspaceApi.listInvites(),
  enabled: computed(() => authStore.canManage("users")),
});

// Per-user Claude token totals for the current billing period (admin only)
const { data: usageByUser } = useQuery({
  queryKey: ["usage-by-user"],
  queryFn: () => usageApi.getByUser(),
  enabled: computed(() => authStore.canManage("users")),
});

const tokensByUserId = computed<Record<number, number>>(() => {
  const result: Record<number, number> = {};
  const data = usageByUser.value as UsageByUserResponse | undefined;
  if (!data?.users) return result;
  for (const u of data.users) {
    result[u.user_id] = u.tokens;
  }
  return result;
});

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

// Mutations
const updateRoleMutation = useMutation({
  mutationFn: ({ userId, roleName }: { userId: number; roleName: string }) =>
    workspaceApi.updateMemberRole(userId, roleName),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["workspace-members"] });
    toast.success(t("users.roleUpdated"));
  },
  onError: (err: Error) => {
    toast.error(err.message || t("users.roleUpdateFailed"));
    refetchMembers();
  },
});

const removeMutation = useMutation({
  mutationFn: (userId: number) => workspaceApi.removeMember(userId),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["workspace-members"] });
    queryClient.invalidateQueries({ queryKey: ["workspace-info"] });
    toast.success(t("users.memberRemoved"));
  },
  onError: (err: Error) => {
    toast.error(err.message || t("users.removeFailed"));
  },
});

const deleteInviteMutation = useMutation({
  mutationFn: (inviteId: number) => workspaceApi.deleteInvite(inviteId),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["workspace-invites"] });
    toast.success(t("invites.deleted"));
  },
  onError: (err: Error) => {
    toast.error(err.message || t("invites.deleteFailed"));
  },
});

// Computed
const info = computed<WorkspaceInfo | null>(() => workspaceInfo.value ?? null);
const memberList = computed<WorkspaceMember[]>(() => members.value ?? []);
const roleOptions = computed<RoleInfo[]>(() => roles.value ?? []);
const inviteList = computed<WorkspaceInvite[]>(() => invites.value ?? []);
const canManage = computed(() => authStore.canManage("users"));

const currentUserId = computed(() => {
  const token = localStorage.getItem("admin_token");
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.user_id ?? null;
  } catch {
    return null;
  }
});

// Methods
function isOwner(member: WorkspaceMember): boolean {
  return info.value?.owner_id === member.user_id;
}

function isSelf(member: WorkspaceMember): boolean {
  return currentUserId.value === member.user_id;
}

function isProtected(member: WorkspaceMember): boolean {
  return isOwner(member) || isSelf(member);
}

function onRoleChange(member: WorkspaceMember, newRole: string) {
  if (isProtected(member)) return;
  updateRoleMutation.mutate({ userId: member.user_id, roleName: newRole });
}

async function onRemoveMember(member: WorkspaceMember) {
  if (isProtected(member)) return;
  const name = member.display_name || member.username || `ID ${member.user_id}`;
  const confirmed = await confirm.confirm({
    title: t("users.remove"),
    message: t("users.confirmRemove", { name }),
    confirmText: t("common.delete"),
    type: "danger",
  });
  if (!confirmed) return;
  removeMutation.mutate(member.user_id);
}

async function onDeleteInvite(invite: WorkspaceInvite) {
  const confirmed = await confirm.confirm({
    title: t("invites.deleteTitle"),
    message: t("invites.confirmDelete"),
    confirmText: t("common.delete"),
    type: "danger",
  });
  if (!confirmed) return;
  deleteInviteMutation.mutate(invite.id);
}

const copiedInviteId = ref<number | null>(null);

async function copyInviteUrl(invite: WorkspaceInvite) {
  const base = window.location.origin + window.location.pathname;
  const url = `${base}#/invite/${invite.invite_code}`;
  try {
    await navigator.clipboard.writeText(url);
    copiedInviteId.value = invite.id;
    setTimeout(() => (copiedInviteId.value = null), 2000);
  } catch {
    toast.error("Failed to copy");
  }
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString();
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

const roleBadgeColors: Record<string, string> = {
  owner: "bg-amber-500/20 text-amber-400",
  admin: "bg-red-500/20 text-red-400",
  operator: "bg-blue-500/20 text-blue-400",
  viewer: "bg-gray-500/20 text-gray-400",
};

function roleBadgeClass(roleName: string): string {
  return roleBadgeColors[roleName] || "bg-gray-500/20 text-gray-400";
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UserCog class="w-8 h-8 text-primary" />
        <div>
          <h1 class="text-2xl font-bold">{{ t("users.title") }}</h1>
          <p class="text-sm text-muted-foreground">{{ t("users.subtitle") }}</p>
        </div>
      </div>
      <button
        class="flex items-center gap-2 px-3 py-2 rounded-lg bg-secondary text-foreground hover:bg-secondary/80 transition-colors"
        @click="refetchMembers()"
      >
        <RefreshCw class="w-4 h-4" />
        <span class="hidden sm:inline">{{ t("common.refresh") }}</span>
      </button>
    </div>

    <!-- Workspace Info Card -->
    <div class="bg-card border border-border rounded-xl p-6">
      <div class="flex items-center gap-3 mb-4">
        <Shield class="w-5 h-5 text-primary" />
        <h2 class="text-lg font-semibold">{{ t("users.workspaceInfo") }}</h2>
      </div>
      <div v-if="infoLoading" class="text-muted-foreground text-sm">
        {{ t("common.loading") }}...
      </div>
      <div v-else-if="info" class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <p class="text-xs text-muted-foreground uppercase tracking-wide">
            {{ t("users.workspaceName") }}
          </p>
          <p class="font-medium">{{ info.name }}</p>
        </div>
        <div>
          <p class="text-xs text-muted-foreground uppercase tracking-wide">
            {{ t("users.memberCount") }}
          </p>
          <p class="font-medium flex items-center gap-1">
            <Users class="w-4 h-4" />
            {{ info.member_count }}
          </p>
        </div>
        <div>
          <p class="text-xs text-muted-foreground uppercase tracking-wide">
            {{ t("users.created") }}
          </p>
          <p class="font-medium">{{ formatDate(info.created_at) }}</p>
        </div>
      </div>
    </div>

    <!-- Members Table -->
    <div class="bg-card border border-border rounded-xl overflow-hidden">
      <div class="p-4 border-b border-border flex items-center gap-3">
        <Users class="w-5 h-5 text-primary" />
        <h2 class="text-lg font-semibold">{{ t("users.members") }}</h2>
      </div>

      <div v-if="membersLoading" class="p-8 text-center text-muted-foreground">
        {{ t("common.loading") }}...
      </div>
      <div v-else-if="memberList.length === 0" class="p-8 text-center text-muted-foreground">
        {{ t("users.noMembers") }}
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-border bg-muted/30">
              <th class="text-left px-4 py-3 font-medium text-muted-foreground">
                {{ t("users.displayName") }}
              </th>
              <th class="text-left px-4 py-3 font-medium text-muted-foreground">
                {{ t("users.username") }}
              </th>
              <th class="text-left px-4 py-3 font-medium text-muted-foreground">
                {{ t("users.role") }}
              </th>
              <th class="text-left px-4 py-3 font-medium text-muted-foreground">
                {{ t("users.joined") }}
              </th>
              <th class="text-left px-4 py-3 font-medium text-muted-foreground">
                {{ t("users.lastLogin") }}
              </th>
              <th class="text-right px-4 py-3 font-medium text-muted-foreground" :title="'Claude tokens this billing period'">
                Токены
              </th>
              <th class="text-left px-4 py-3 font-medium text-muted-foreground">
                {{ t("users.status") }}
              </th>
              <th v-if="canManage" class="text-right px-4 py-3 font-medium text-muted-foreground">
                {{ t("users.actions") }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="member in memberList"
              :key="member.user_id"
              class="border-b border-border/50 hover:bg-muted/20 transition-colors"
            >
              <td class="px-4 py-3">
                <div class="flex items-center gap-2">
                  <span class="font-medium">{{ member.display_name || "—" }}</span>
                  <Crown
                    v-if="isOwner(member)"
                    class="w-4 h-4 text-amber-400"
                    :title="t('users.owner')"
                  />
                </div>
              </td>
              <td class="px-4 py-3 text-muted-foreground">
                {{ member.username || "—" }}
              </td>
              <td class="px-4 py-3">
                <template v-if="canManage && !isProtected(member) && roleOptions.length > 0">
                  <select
                    :value="member.role_name"
                    class="bg-secondary border border-border rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                    @change="onRoleChange(member, ($event.target as HTMLSelectElement).value)"
                  >
                    <option v-for="role in roleOptions" :key="role.name" :value="role.name">
                      {{ role.display_name || role.name }}
                    </option>
                  </select>
                </template>
                <template v-else>
                  <span
                    :class="[
                      'px-2 py-0.5 rounded text-xs font-medium',
                      roleBadgeClass(member.role_name),
                    ]"
                  >
                    {{ member.role_name }}
                  </span>
                </template>
              </td>
              <td class="px-4 py-3 text-muted-foreground">
                {{ formatDate(member.joined_at) }}
              </td>
              <td class="px-4 py-3 text-muted-foreground">
                {{ formatDateTime(member.last_login) }}
              </td>
              <td class="px-4 py-3 text-right tabular-nums">
                <span
                  v-if="tokensByUserId[member.user_id]"
                  class="text-xs text-orange-400"
                  :title="`${tokensByUserId[member.user_id].toLocaleString()} токенов в текущем периоде Claude`"
                >{{ formatTokens(tokensByUserId[member.user_id]) }}</span>
                <span v-else class="text-xs text-muted-foreground/50">—</span>
              </td>
              <td class="px-4 py-3">
                <span
                  v-if="member.is_active !== undefined"
                  :class="[
                    'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium',
                    member.is_active
                      ? 'bg-green-500/20 text-green-400'
                      : 'bg-red-500/20 text-red-400',
                  ]"
                >
                  <span
                    class="w-1.5 h-1.5 rounded-full"
                    :class="member.is_active ? 'bg-green-400' : 'bg-red-400'"
                  />
                  {{ member.is_active ? t("users.active") : t("users.inactive") }}
                </span>
              </td>
              <td v-if="canManage" class="px-4 py-3 text-right">
                <button
                  v-if="!isProtected(member)"
                  class="p-1.5 rounded-lg text-red-400 hover:bg-red-500/20 transition-colors"
                  :title="t('users.remove')"
                  :disabled="removeMutation.isPending.value"
                  @click="onRemoveMember(member)"
                >
                  <Trash2 class="w-4 h-4" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Invites Section (manage only) -->
    <div v-if="canManage" class="bg-card border border-border rounded-xl overflow-hidden">
      <div class="p-4 border-b border-border flex items-center justify-between">
        <div class="flex items-center gap-3">
          <Link class="w-5 h-5 text-primary" />
          <h2 class="text-lg font-semibold">{{ t("invites.title") }}</h2>
        </div>
        <button
          class="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors text-sm"
          @click="showInviteDialog = true"
        >
          <Plus class="w-4 h-4" />
          {{ t("invites.create") }}
        </button>
      </div>

      <div v-if="invitesLoading" class="p-8 text-center text-muted-foreground">
        {{ t("common.loading") }}...
      </div>
      <div v-else-if="inviteList.length === 0" class="p-8 text-center text-muted-foreground">
        {{ t("invites.noInvites") }}
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-border bg-muted/30">
              <th class="text-left px-4 py-3 font-medium text-muted-foreground">
                {{ t("users.role") }}
              </th>
              <th class="text-left px-4 py-3 font-medium text-muted-foreground">
                {{ t("invites.email") }}
              </th>
              <th class="text-left px-4 py-3 font-medium text-muted-foreground">
                {{ t("invites.usage") }}
              </th>
              <th class="text-left px-4 py-3 font-medium text-muted-foreground">
                {{ t("invites.expires") }}
              </th>
              <th class="text-left px-4 py-3 font-medium text-muted-foreground">
                {{ t("users.status") }}
              </th>
              <th class="text-right px-4 py-3 font-medium text-muted-foreground">
                {{ t("users.actions") }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="invite in inviteList"
              :key="invite.id"
              class="border-b border-border/50 hover:bg-muted/20 transition-colors"
            >
              <td class="px-4 py-3">
                <span
                  :class="[
                    'px-2 py-0.5 rounded text-xs font-medium',
                    roleBadgeClass(invite.role_name),
                  ]"
                >
                  {{ invite.role_name }}
                </span>
              </td>
              <td class="px-4 py-3 text-muted-foreground">
                {{ invite.email || "—" }}
              </td>
              <td class="px-4 py-3 text-muted-foreground">
                {{ invite.used_count }}{{ invite.max_uses != null ? ` / ${invite.max_uses}` : "" }}
              </td>
              <td class="px-4 py-3 text-muted-foreground">
                {{ invite.expires_at ? formatDateTime(invite.expires_at) : t("invites.never") }}
              </td>
              <td class="px-4 py-3">
                <span
                  :class="[
                    'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium',
                    invite.is_valid
                      ? 'bg-green-500/20 text-green-400'
                      : 'bg-red-500/20 text-red-400',
                  ]"
                >
                  <span
                    class="w-1.5 h-1.5 rounded-full"
                    :class="invite.is_valid ? 'bg-green-400' : 'bg-red-400'"
                  />
                  {{ invite.is_valid ? t("users.active") : t("invites.expired") }}
                </span>
              </td>
              <td class="px-4 py-3 text-right flex items-center justify-end gap-1">
                <button
                  v-if="invite.is_valid"
                  class="p-1.5 rounded-lg text-muted-foreground hover:bg-secondary transition-colors"
                  :title="t('invites.copyLink')"
                  @click="copyInviteUrl(invite)"
                >
                  <component :is="copiedInviteId === invite.id ? Check : Copy" class="w-4 h-4" />
                </button>
                <button
                  class="p-1.5 rounded-lg text-red-400 hover:bg-red-500/20 transition-colors"
                  :title="t('common.delete')"
                  @click="onDeleteInvite(invite)"
                >
                  <Trash2 class="w-4 h-4" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Invite Dialog -->
    <InviteDialog :open="showInviteDialog" @close="showInviteDialog = false" />
  </div>
</template>
