import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useChatFullscreenStore = defineStore('chatFullscreen', () => {
  const isFullscreen = ref(false)

  function enter() {
    isFullscreen.value = true
  }
  function exit() {
    isFullscreen.value = false
  }
  function toggle() {
    isFullscreen.value = !isFullscreen.value
  }

  return { isFullscreen, enter, exit, toggle }
})
