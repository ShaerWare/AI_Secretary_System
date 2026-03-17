import { defineStore } from 'pinia'
import { ref, readonly } from 'vue'

export const useChatFullscreenStore = defineStore('chatFullscreen', () => {
  const isFullscreen = ref(false)
  const locked = ref(false)

  function enter() {
    isFullscreen.value = true
  }
  function exit() {
    if (!locked.value) isFullscreen.value = false
  }
  function toggle() {
    if (!locked.value) isFullscreen.value = !isFullscreen.value
  }
  function lock() {
    isFullscreen.value = true
    locked.value = true
  }
  function unlock() {
    locked.value = false
  }

  return { isFullscreen, locked: readonly(locked), enter, exit, toggle, lock, unlock }
})
