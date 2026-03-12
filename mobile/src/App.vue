<script setup lang="ts">
import { onMounted } from "vue";
import { StatusBar } from "@capacitor/status-bar";
import { Capacitor } from "@capacitor/core";

onMounted(async () => {
  if (Capacitor.isNativePlatform()) {
    await StatusBar.setBackgroundColor({ color: "#1a1308" });
  }
});
</script>

<template>
  <div class="h-full safe-top safe-bottom">
    <router-view />
  </div>
</template>
