<script setup lang="ts">
import { ref, computed } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { workspaceApi, type RoleInfo } from "@/api/workspace";
import { useI18n } from "vue-i18n";
import { useToastStore } from "@/stores/toast";
import { X, Copy, Check, Link } from "lucide-vue-next";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ (e: "close"): void }>();

const { t } = useI18n();
const toast = useToastStore();
const queryClient = useQueryClient();

const roleName = ref("operator");
const email = ref("");
const maxUses = ref<number | undefined>(undefined);
const expiresHours = ref<number | undefined>(72);
const createdInviteCode = ref<string | null>(null);
const copied = ref(false);

const { data: roles } = useQuery({
  queryKey: ["roles-list"],
  queryFn: () => workspaceApi.listRoles(),
});

const availableRoles = computed<RoleInfo[]>(() =>
  (roles.value ?? []).filter((r) => r.name !== "owner")
);

const createMutation = useMutation({
  mutationFn: () =>
    workspaceApi.createInvite({
      role_name: roleName.value,
      email: email.value || undefined,
      max_uses: maxUses.value,
      expires_hours: expiresHours.value,
    }),
  onSuccess: (data) => {
    createdInviteCode.value = data.invite_code;
    queryClient.invalidateQueries({ queryKey: ["workspace-invites"] });
    toast.success(t("invites.created"));
  },
  onError: (err: Error) => {
    toast.error(err.message || t("invites.createFailed"));
  },
});

const inviteUrl = computed(() => {
  if (!createdInviteCode.value) return "";
  const base = window.location.origin + window.location.pathname;
  return `${base}#/invite/${createdInviteCode.value}`;
});

function onSubmit() {
  createMutation.mutate();
}

async function copyUrl() {
  try {
    await navigator.clipboard.writeText(inviteUrl.value);
    copied.value = true;
    setTimeout(() => (copied.value = false), 2000);
  } catch {
    toast.error("Failed to copy");
  }
}

function onClose() {
  createdInviteCode.value = null;
  copied.value = false;
  roleName.value = "operator";
  email.value = "";
  maxUses.value = undefined;
  expiresHours.value = 72;
  emit("close");
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="props.open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      @click.self="onClose"
    >
      <div class="bg-card border border-border rounded-xl shadow-2xl w-full max-w-md mx-4">
        <!-- Header -->
        <div class="flex items-center justify-between p-4 border-b border-border">
          <h3 class="text-lg font-semibold flex items-center gap-2">
            <Link class="w-5 h-5 text-primary" />
            {{ t("invites.createTitle") }}
          </h3>
          <button class="p-1 rounded-lg hover:bg-secondary transition-colors" @click="onClose">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Body -->
        <div class="p-4 space-y-4">
          <!-- Created invite URL -->
          <template v-if="createdInviteCode">
            <div class="space-y-2">
              <label class="block text-sm font-medium">{{ t("invites.inviteLink") }}</label>
              <div class="flex gap-2">
                <input
                  :value="inviteUrl"
                  readonly
                  class="flex-1 bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono select-all"
                />
                <button
                  class="flex items-center gap-1 px-3 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors text-sm"
                  @click="copyUrl"
                >
                  <component :is="copied ? Check : Copy" class="w-4 h-4" />
                  {{ copied ? t("invites.copied") : t("invites.copy") }}
                </button>
              </div>
            </div>
          </template>

          <!-- Create form -->
          <template v-else>
            <!-- Role -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t("users.role") }}</label>
              <select
                v-model="roleName"
                class="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option v-for="role in availableRoles" :key="role.name" :value="role.name">
                  {{ role.display_name || role.name }}
                </option>
              </select>
            </div>

            <!-- Email (optional) -->
            <div>
              <label class="block text-sm font-medium mb-1">
                {{ t("invites.email") }}
                <span class="text-muted-foreground font-normal">({{ t("invites.optional") }})</span>
              </label>
              <input
                v-model="email"
                type="email"
                class="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                :placeholder="t('invites.emailPlaceholder')"
              />
            </div>

            <!-- Max uses -->
            <div>
              <label class="block text-sm font-medium mb-1">
                {{ t("invites.maxUses") }}
                <span class="text-muted-foreground font-normal">({{ t("invites.optional") }})</span>
              </label>
              <input
                v-model.number="maxUses"
                type="number"
                min="1"
                class="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                :placeholder="t('invites.unlimited')"
              />
            </div>

            <!-- Expires -->
            <div>
              <label class="block text-sm font-medium mb-1">{{ t("invites.expiresIn") }}</label>
              <select
                v-model.number="expiresHours"
                class="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option :value="24">24 {{ t("invites.hours") }}</option>
                <option :value="72">3 {{ t("invites.days") }}</option>
                <option :value="168">7 {{ t("invites.days") }}</option>
                <option :value="720">30 {{ t("invites.days") }}</option>
                <option :value="undefined">{{ t("invites.never") }}</option>
              </select>
            </div>
          </template>
        </div>

        <!-- Footer -->
        <div class="flex justify-end gap-2 p-4 border-t border-border">
          <button
            class="px-4 py-2 rounded-lg bg-secondary text-foreground hover:bg-secondary/80 transition-colors text-sm"
            @click="onClose"
          >
            {{ createdInviteCode ? t("common.close") : t("common.cancel") }}
          </button>
          <button
            v-if="!createdInviteCode"
            class="px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors text-sm"
            :disabled="createMutation.isPending.value"
            @click="onSubmit"
          >
            {{ t("invites.create") }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
