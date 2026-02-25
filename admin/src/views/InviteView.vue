<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { workspaceApi, type InviteInfo } from "@/api/workspace";
import { useI18n } from "vue-i18n";
import { UserPlus, AlertCircle, Eye, EyeOff } from "lucide-vue-next";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();

const inviteCode = route.params.code as string;
const inviteInfo = ref<InviteInfo | null>(null);
const loading = ref(true);
const error = ref("");

const username = ref("");
const password = ref("");
const confirmPassword = ref("");
const displayName = ref("");
const showPassword = ref(false);
const submitting = ref(false);
const submitError = ref("");

onMounted(async () => {
  try {
    inviteInfo.value = await workspaceApi.getInviteInfo(inviteCode);
  } catch {
    error.value = t("invite.notFound");
  } finally {
    loading.value = false;
  }
});

async function onSubmit() {
  submitError.value = "";

  if (password.value !== confirmPassword.value) {
    submitError.value = t("invite.passwordMismatch");
    return;
  }

  submitting.value = true;
  try {
    const result = await workspaceApi.acceptInvite({
      invite_code: inviteCode,
      username: username.value,
      password: password.value,
      display_name: displayName.value || undefined,
    });

    // Save token and reload — store auto-initializes from localStorage
    localStorage.setItem("admin_token", result.access_token);
    window.location.href = window.location.pathname + "#/chat";
    window.location.reload();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    submitError.value = msg;
  } finally {
    submitting.value = false;
  }
}

const roleDisplayNames: Record<string, string> = {
  admin: "Administrator",
  operator: "Operator",
  viewer: "Viewer",
};

function roleLabel(name: string): string {
  return roleDisplayNames[name] || name;
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-background p-4">
    <div class="w-full max-w-md">
      <!-- Loading -->
      <div v-if="loading" class="text-center text-muted-foreground">
        {{ t("common.loading") }}...
      </div>

      <!-- Error: invalid invite -->
      <div
        v-else-if="error"
        class="bg-card border border-border rounded-xl p-8 text-center space-y-4"
      >
        <AlertCircle class="w-12 h-12 text-red-400 mx-auto" />
        <h2 class="text-xl font-semibold">{{ error }}</h2>
        <p class="text-muted-foreground text-sm">{{ t("invite.notFoundDesc") }}</p>
        <button
          class="px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors text-sm"
          @click="router.push('/login')"
        >
          {{ t("invite.goToLogin") }}
        </button>
      </div>

      <!-- Invite form -->
      <div v-else-if="inviteInfo" class="bg-card border border-border rounded-xl overflow-hidden">
        <!-- Header -->
        <div class="p-6 border-b border-border text-center space-y-2">
          <UserPlus class="w-10 h-10 text-primary mx-auto" />
          <h2 class="text-xl font-semibold">{{ t("invite.title") }}</h2>
          <p class="text-muted-foreground text-sm">
            {{ t("invite.joinWorkspace", { name: inviteInfo.workspace_name }) }}
          </p>
          <span
            class="inline-block px-3 py-1 rounded-full text-xs font-medium bg-primary/20 text-primary"
          >
            {{ roleLabel(inviteInfo.role_name) }}
          </span>
        </div>

        <!-- Form -->
        <form class="p-6 space-y-4" @submit.prevent="onSubmit">
          <!-- Display name -->
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("invite.displayName") }}</label>
            <input
              v-model="displayName"
              type="text"
              class="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              :placeholder="t('invite.displayNamePlaceholder')"
            />
          </div>

          <!-- Username -->
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("invite.username") }} *</label>
            <input
              v-model="username"
              type="text"
              required
              minlength="2"
              maxlength="50"
              pattern="[a-zA-Z0-9_.\-]+"
              class="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              :placeholder="t('invite.usernamePlaceholder')"
            />
          </div>

          <!-- Password -->
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("invite.password") }} *</label>
            <div class="relative">
              <input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                required
                minlength="6"
                maxlength="128"
                class="w-full bg-secondary border border-border rounded-lg px-3 py-2 pr-10 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <button
                type="button"
                class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
                @click="showPassword = !showPassword"
              >
                <component :is="showPassword ? EyeOff : Eye" class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Confirm password -->
          <div>
            <label class="block text-sm font-medium mb-1"
              >{{ t("invite.confirmPassword") }} *</label
            >
            <input
              v-model="confirmPassword"
              type="password"
              required
              minlength="6"
              class="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <!-- Error -->
          <div
            v-if="submitError"
            class="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm"
          >
            <AlertCircle class="w-4 h-4 shrink-0" />
            {{ submitError }}
          </div>

          <!-- Submit -->
          <button
            type="submit"
            class="w-full py-2.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors font-medium"
            :disabled="submitting"
          >
            {{ submitting ? t("common.loading") + "..." : t("invite.join") }}
          </button>
        </form>

        <!-- Footer -->
        <div class="px-6 pb-4 text-center">
          <p class="text-xs text-muted-foreground">
            {{ t("invite.alreadyHaveAccount") }}
            <router-link to="/login" class="text-primary hover:underline">
              {{ t("invite.login") }}
            </router-link>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
