<script setup lang="ts">
import { onMounted, watch } from "vue";
import { StatusBar } from "@capacitor/status-bar";
import { Capacitor } from "@capacitor/core";
import { useAuthStore } from "@/stores/auth";
import { initPush } from "@/composables/usePush";

const auth = useAuthStore();

onMounted(async () => {
  if (Capacitor.isNativePlatform()) {
    await StatusBar.setBackgroundColor({ color: "#1a1308" });
  }
  // Initialize push if already logged in (token restored from Preferences)
  if (auth.isAuthenticated) {
    void initPush();
  }
});

// Initialize push after login
watch(
  () => auth.isAuthenticated,
  (isAuth) => {
    if (isAuth) void initPush();
  },
);
</script>

<template>
  <div class="h-full safe-top">
    <router-view />
  </div>
</template>
