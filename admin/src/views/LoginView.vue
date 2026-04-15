<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'

const router = useRouter()
const route = useRoute()
const queryClient = useQueryClient()
const authStore = useAuthStore()
const toastStore = useToastStore()

const isDemo = import.meta.env.VITE_DEMO_MODE === 'true'
const username = ref(isDemo ? 'admin' : '')
const password = ref(isDemo ? 'admin' : '')
const isLoading = ref(false)
const showPassword = ref(false)

// About panel
const showAbout = ref(false)
const activeTab = ref<'ai' | 'privacy' | 'features' | 'channels' | 'cases'>('cases')

// Matrix rain animation
const matrixCanvas = ref<HTMLCanvasElement | null>(null)
let matrixRaf = 0

onMounted(() => {
  const canvas = matrixCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const chars = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEF<>/{}[]'
  const fontSize = 14
  let columns = 0
  let drops: number[] = []

  function resize() {
    canvas!.width = window.innerWidth
    canvas!.height = window.innerHeight
    columns = Math.floor(canvas!.width / fontSize)
    drops = Array.from({ length: columns }, () => Math.random() * -100)
  }
  resize()
  window.addEventListener('resize', resize)

  function draw() {
    ctx!.fillStyle = 'rgba(9, 9, 11, 0.03)'
    ctx!.fillRect(0, 0, canvas!.width, canvas!.height)
    ctx!.font = `${fontSize}px monospace`

    for (let i = 0; i < drops.length; i++) {
      const char = chars[Math.floor(Math.random() * chars.length)]
      const x = i * fontSize
      const y = drops[i] * fontSize

      // Orange-cinnamon palette
      const brightness = Math.random()
      if (brightness > 0.95) {
        ctx!.fillStyle = '#fed7aa' // orange-200 — flash
      } else if (brightness > 0.8) {
        ctx!.fillStyle = '#fb923c' // orange-400
      } else {
        ctx!.fillStyle = '#c2410c' // orange-700
      }
      ctx!.globalAlpha = 0.6 + Math.random() * 0.4
      ctx!.fillText(char, x, y)
      ctx!.globalAlpha = 1

      if (y > canvas!.height && Math.random() > 0.975) {
        drops[i] = 0
      }
      drops[i] += 0.2 + Math.random() * 0.3
    }
    matrixRaf = requestAnimationFrame(draw)
  }
  draw()
})

onUnmounted(() => {
  cancelAnimationFrame(matrixRaf)
})

async function handleSubmit() {
  if (!username.value || !password.value) {
    toastStore.warning('Введите логин и пароль')
    return
  }

  isLoading.value = true

  try {
    const success = await authStore.login(username.value, password.value)

    if (success) {
      // Clear stale query cache so ChatView fetches fresh data with new token
      queryClient.clear()
      toastStore.success('Добро пожаловать!', `Вы вошли как ${username.value}`)
      const redirect = (route.query.redirect as string) || '/'
      router.push(redirect)
    } else {
      toastStore.error('Ошибка входа', authStore.error || 'Неверные учётные данные')
    }
  } catch (e) {
    toastStore.error('Ошибка входа', 'Ошибка соединения')
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-zinc-950 flex flex-col items-center py-8 sm:py-12 sm:px-6 lg:px-8 relative overflow-hidden">
    <!-- Matrix rain background -->
    <canvas ref="matrixCanvas" class="absolute inset-0 w-full h-full pointer-events-none" style="z-index: 0;" />
    <!-- Vignette overlay -->
    <div class="absolute inset-0 bg-gradient-to-b from-zinc-950/60 via-transparent to-zinc-950/80 pointer-events-none" style="z-index: 1;" />

    <!-- Login section -->
    <div class="w-full flex flex-col items-center" :class="showAbout ? 'mb-6' : 'flex-1 justify-center'">
      <div class="sm:mx-auto sm:w-full sm:max-w-md relative" style="z-index: 2;">
        <!-- Logo (gear from favicon, transparent background) -->
        <div class="flex justify-center">
          <svg
            class="w-20 h-20 drop-shadow-[0_6px_14px_rgba(194,112,16,0.35)]"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 512 512"
          >
            <defs>
              <linearGradient id="loginLogoGradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#F0A830" />
                <stop offset="100%" stop-color="#C27010" />
              </linearGradient>
            </defs>
            <path
              fill="url(#loginLogoGradient)"
              fill-rule="evenodd"
              d="M 431.8 217.4 L 484.1 226.3 L 484.1 285.7 L 431.8 294.6 L 407.6 353.0 L 438.3 396.3 L 396.3 438.3 L 353.0 407.6 L 294.6 431.8 L 285.7 484.1 L 226.3 484.1 L 217.4 431.8 L 159.0 407.6 L 115.7 438.3 L 73.7 396.3 L 104.4 353.0 L 80.2 294.6 L 27.9 285.7 L 27.9 226.3 L 80.2 217.4 L 104.4 159.0 L 73.7 115.7 L 115.7 73.7 L 159.0 104.4 L 217.4 80.2 L 226.3 27.9 L 285.7 27.9 L 294.6 80.2 L 353.0 104.4 L 396.3 73.7 L 438.3 115.7 L 407.6 159.0 Z M 341.0 256.0 A 85 85 0 1 0 171.0 256.0 A 85 85 0 1 0 341.0 256.0 Z"
            />
          </svg>
        </div>

        <h1 class="mt-6 text-center text-3xl font-bold tracking-tight text-white">
          AI-Секретарь
        </h1>
        <p class="mt-2 text-center text-sm text-gray-400">
          Виртуальный секретарь с локальным и облачным ИИ
        </p>
      </div>

      <div class="mt-8 sm:mx-auto sm:w-full sm:max-w-md relative" style="z-index: 2;">
        <div class="bg-zinc-900/90 backdrop-blur-sm py-8 px-4 shadow-xl ring-1 ring-zinc-800 sm:rounded-xl sm:px-10">
          <form class="space-y-6" @submit.prevent="handleSubmit">
            <!-- Username -->
            <div>
              <label for="username" class="block text-sm font-medium text-gray-300">
                Логин
              </label>
              <div class="mt-2">
                <input
                  id="username"
                  v-model="username"
                  name="username"
                  type="text"
                  autocomplete="username"
                  required
                  class="block w-full rounded-lg border-0 bg-zinc-800 px-3 py-2 text-white shadow-sm ring-1 ring-inset ring-zinc-700 placeholder:text-gray-500 focus:ring-2 focus:ring-inset focus:ring-orange-500 sm:text-sm sm:leading-6"
                  placeholder="admin"
                />
              </div>
            </div>

            <!-- Password -->
            <div>
              <label for="password" class="block text-sm font-medium text-gray-300">
                Пароль
              </label>
              <div class="mt-2 relative">
                <input
                  id="password"
                  v-model="password"
                  name="password"
                  :type="showPassword ? 'text' : 'password'"
                  autocomplete="current-password"
                  required
                  class="block w-full rounded-lg border-0 bg-zinc-800 px-3 py-2 pr-10 text-white shadow-sm ring-1 ring-inset ring-zinc-700 placeholder:text-gray-500 focus:ring-2 focus:ring-inset focus:ring-orange-500 sm:text-sm sm:leading-6"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  class="absolute inset-y-0 right-0 flex items-center pr-3"
                  @click="showPassword = !showPassword"
                >
                  <svg
                    v-if="showPassword"
                    class="h-5 w-5 text-gray-400 hover:text-gray-300"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke-width="1.5"
                    stroke="currentColor"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88"
                    />
                  </svg>
                  <svg
                    v-else
                    class="h-5 w-5 text-gray-400 hover:text-gray-300"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke-width="1.5"
                    stroke="currentColor"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"
                    />
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                    />
                  </svg>
                </button>
              </div>
            </div>

            <!-- Error message -->
            <div v-if="authStore.error" class="rounded-lg bg-red-900/50 p-3">
              <p class="text-sm text-red-400">{{ authStore.error }}</p>
            </div>

            <!-- Submit -->
            <div>
              <button
                type="submit"
                :disabled="isLoading"
                class="flex w-full justify-center rounded-lg bg-orange-700 px-3 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-orange-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <svg
                  v-if="isLoading"
                  class="animate-spin -ml-1 mr-2 h-5 w-5 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    class="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    stroke-width="4"
                  />
                  <path
                    class="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                {{ isLoading ? 'Вход...' : 'Войти' }}
              </button>
            </div>
          </form>

          <!-- Hint -->
          <div class="mt-6 text-center space-y-1">
            <p class="text-xs text-gray-500">
              Демо-доступ: admin / admin
            </p>
            <p class="text-xs text-orange-500/70">
              Демо-режим: работает без бэкенда
            </p>
          </div>

          <!-- Links -->
          <div class="mt-6 flex justify-center items-center gap-4">
            <!-- GitHub -->
            <a
              href="https://github.com/ShaerWare/AI_Secretary_System"
              target="_blank"
              rel="noopener noreferrer"
              title="Исходный код на GitHub"
              class="w-10 h-10 rounded-full bg-zinc-800 ring-1 ring-zinc-700 flex items-center justify-center text-gray-400 hover:text-white hover:bg-zinc-700 hover:ring-orange-600/50 transition-all"
            >
              <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
              </svg>
            </a>

            <!-- Website -->
            <a
              href="https://shaerware.digital/ru"
              target="_blank"
              rel="noopener noreferrer"
              title="ShaerWare Digital — разработчик"
              class="w-10 h-10 rounded-full bg-zinc-800 ring-1 ring-zinc-700 flex items-center justify-center text-gray-400 hover:text-white hover:bg-zinc-700 hover:ring-orange-600/50 transition-all"
            >
              <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 003 12c0-1.605.42-3.113 1.157-4.418" />
              </svg>
            </a>

            <!-- Telegram Support -->
            <a
              href="https://t.me/ai_sekretar24bot"
              target="_blank"
              rel="noopener noreferrer"
              title="Техподдержка 24/7 в Telegram"
              class="w-10 h-10 rounded-full bg-zinc-800 ring-1 ring-zinc-700 flex items-center justify-center text-gray-400 hover:text-white hover:bg-zinc-700 hover:ring-orange-600/50 transition-all"
            >
              <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M11.944 0A12 12 0 000 12a12 12 0 0012 12 12 12 0 0012-12A12 12 0 0012 0a12 12 0 00-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 01.171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
              </svg>
            </a>
          </div>

          <!-- Android APK download -->
          <div class="mt-4 flex justify-center">
            <a
              href="https://github.com/ShaerWare/AI_Secretary_System/releases/download/mobile-v1.3/ai-secretary-1.3.apk"
              target="_blank"
              rel="noopener noreferrer"
              title="Скачать Android-приложение AI-Секретарь"
              class="group inline-flex items-center gap-2.5 rounded-full px-5 py-2.5 bg-gradient-to-r from-orange-600 via-amber-500 to-orange-600 bg-[length:200%_100%] bg-left hover:bg-right text-white text-sm font-semibold shadow-lg shadow-orange-900/30 ring-1 ring-orange-400/30 hover:ring-orange-300/60 hover:shadow-orange-700/50 hover:-translate-y-0.5 active:translate-y-0 transition-all duration-500"
            >
              <svg class="w-4 h-4 transition-transform group-hover:-translate-y-0.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M17.523 15.341c-.5866 0-1.0615-.4751-1.0615-1.0613 0-.5862.4749-1.0614 1.0615-1.0614.5864 0 1.0613.4752 1.0613 1.0614 0 .5862-.4749 1.0613-1.0613 1.0613m-11.0456 0c-.5868 0-1.0616-.4751-1.0616-1.0613 0-.5862.4748-1.0614 1.0616-1.0614.5863 0 1.0612.4752 1.0612 1.0614 0 .5862-.4749 1.0613-1.0612 1.0613m11.4264-6.0201 2.1195-3.6713a.4413.4413 0 0 0-.1616-.6025.4415.4415 0 0 0-.6024.1616l-2.1465 3.7185C15.4732 8.1637 13.7923 7.7999 12 7.7999c-1.7922 0-3.4732.3638-4.9924 1.0232L4.8611 5.1046a.441.441 0 0 0-.6023-.1616.4413.4413 0 0 0-.1616.6025l2.1195 3.6713C2.574 10.9842.3949 14.3505 0 18.413h24c-.3949-4.0625-2.5734-7.4288-6.2548-9.4991" />
              </svg>
              <span>Скачать Android-приложение</span>
              <span class="text-[10px] font-bold uppercase tracking-wide bg-white/20 rounded-full px-1.5 py-0.5">v1.3</span>
            </a>
          </div>
        </div>

        <!-- About toggle -->
        <div class="mt-4 text-center relative" style="z-index: 2;">
          <button
            class="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-orange-400 transition-colors"
            @click="showAbout = !showAbout"
          >
            <svg
              class="w-4 h-4 transition-transform duration-300"
              :class="showAbout ? 'rotate-180' : ''"
              fill="none"
              viewBox="0 0 24 24"
              stroke-width="2"
              stroke="currentColor"
            >
              <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
            </svg>
            {{ showAbout ? 'Скрыть описание' : 'О проекте' }}
          </button>
        </div>
      </div>
    </div>

    <!-- About section -->
    <Transition
      enter-active-class="transition-all duration-500 ease-out"
      enter-from-class="opacity-0 -translate-y-4 max-h-0"
      enter-to-class="opacity-100 translate-y-0 max-h-[2000px]"
      leave-active-class="transition-all duration-300 ease-in"
      leave-from-class="opacity-100 translate-y-0 max-h-[2000px]"
      leave-to-class="opacity-0 -translate-y-4 max-h-0"
    >
      <div
        v-if="showAbout"
        class="w-full max-w-4xl mx-auto px-4 relative overflow-hidden"
        style="z-index: 2;"
      >
        <!-- Tagline -->
        <div class="text-center mb-6">
          <h2 class="text-xl sm:text-2xl font-bold text-white">
            Локальный и облачный ИИ &mdash; вместе и порознь
          </h2>
          <p class="mt-2 text-sm text-gray-400 max-w-2xl mx-auto">
            Гибридная система, которая работает с любыми LLM-провайдерами одновременно,
            позволяет настраивать произвольные роли и обеспечивает максимальную приватность
            при использовании локальных моделей.
          </p>
        </div>

        <!-- Tabs -->
        <div class="flex justify-center mb-6 overflow-x-auto">
          <div class="inline-flex rounded-lg bg-zinc-900/80 backdrop-blur-sm p-1 ring-1 ring-zinc-800">
            <button
              v-for="tab in [
                { id: 'cases', label: 'Успешные кейсы' },
                { id: 'ai', label: 'ИИ-движки' },
                { id: 'privacy', label: 'Приватность' },
                { id: 'features', label: 'Возможности' },
                { id: 'channels', label: 'Каналы' },
              ]"
              :key="tab.id"
              class="px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium rounded-md transition-all whitespace-nowrap"
              :class="activeTab === tab.id
                ? 'bg-orange-700 text-white shadow-sm'
                : 'text-gray-400 hover:text-white'"
              @click="activeTab = tab.id as typeof activeTab"
            >
              {{ tab.label }}
            </button>
          </div>
        </div>

        <!-- Tab content -->
        <div class="bg-zinc-900/80 backdrop-blur-sm rounded-xl ring-1 ring-zinc-800 p-5 sm:p-8">

          <!-- Successful Cases -->
          <div v-if="activeTab === 'cases'" class="space-y-6">
            <div class="rounded-lg bg-gradient-to-br from-orange-900/20 via-zinc-800/60 to-zinc-800/60 p-5 ring-1 ring-orange-700/30">
              <h3 class="text-base font-semibold text-white mb-2">Один движок &mdash; любая роль</h3>
              <p class="text-sm text-gray-400 leading-relaxed">
                Ключевое преимущество платформы &mdash; из одной и той же системы можно собрать
                AI-сотрудника под любую профессию. Мы уже создали и готовы создать для вас
                автономных ассистентов с индивидуальными промптами, базой знаний, голосом
                и интеграциями. Ниже &mdash; проверенные сценарии внедрения.
              </p>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-3 mb-2">
                  <div class="w-9 h-9 rounded-lg bg-sky-900/50 flex items-center justify-center text-xl">📞</div>
                  <h4 class="text-base font-semibold text-white">Колл-центр</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  Обработка входящих и исходящих звонков через GSM или SIP, распознавание речи,
                  голосовые ответы, квалификация лидов, передача сложных диалогов оператору.
                </p>
              </div>

              <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-3 mb-2">
                  <div class="w-9 h-9 rounded-lg bg-emerald-900/50 flex items-center justify-center text-xl">🛠️</div>
                  <h4 class="text-base font-semibold text-white">Техподдержка</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  L1-линия поддержки 24/7 в Telegram, WhatsApp и чате сайта. RAG по базе знаний,
                  тикеты, эскалация инженерам, история обращений и аналитика качества.
                </p>
              </div>

              <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-3 mb-2">
                  <div class="w-9 h-9 rounded-lg bg-violet-900/50 flex items-center justify-center text-xl">📇</div>
                  <h4 class="text-base font-semibold text-white">Секретарь</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  Приём звонков, запись на встречи в Google Calendar, фильтр спама, напоминания,
                  краткие сводки переписки, работа с почтой и документами.
                </p>
              </div>

              <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-3 mb-2">
                  <div class="w-9 h-9 rounded-lg bg-amber-900/50 flex items-center justify-center text-xl">⚖️</div>
                  <h4 class="text-base font-semibold text-white">Юрист</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  Консультации по законодательству с опорой на актуальную базу (RAG по НК, ГК,
                  судебной практике), анализ договоров, подготовка шаблонов документов.
                </p>
              </div>

              <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-3 mb-2">
                  <div class="w-9 h-9 rounded-lg bg-lime-900/50 flex items-center justify-center text-xl">📊</div>
                  <h4 class="text-base font-semibold text-white">Бухгалтер</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  Ответы по налогам и отчётности, расчёт УСН/НДС, напоминания о сроках,
                  первичная обработка документов, интеграция с 1С и банковскими выписками.
                </p>
              </div>

              <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-3 mb-2">
                  <div class="w-9 h-9 rounded-lg bg-rose-900/50 flex items-center justify-center text-xl">💼</div>
                  <h4 class="text-base font-semibold text-white">Менеджер по продажам</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  Воронка продаж в Telegram/WhatsApp/виджете сайта, квалификация, допродажи,
                  приём платежей (YooKassa, Stars), интеграция с amoCRM и WooCommerce.
                </p>
              </div>

              <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-3 mb-2">
                  <div class="w-9 h-9 rounded-lg bg-cyan-900/50 flex items-center justify-center text-xl">🎨</div>
                  <h4 class="text-base font-semibold text-white">Веб-студия</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  AI-бриф, генерация ТЗ, подбор стека, прототипирование landing-страниц,
                  автоматическая сдача и поддержка сайтов клиентов под ключ.
                </p>
              </div>

              <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-3 mb-2">
                  <div class="w-9 h-9 rounded-lg bg-indigo-900/50 flex items-center justify-center text-xl">👨‍💻</div>
                  <h4 class="text-base font-semibold text-white">Команда программистов</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  Мост с Claude Code CLI: написание и ревью кода, работа с git, запуск тестов
                  и деплой прямо из чата. Автономный агент для ваших репозиториев.
                </p>
              </div>
            </div>

            <div class="rounded-lg bg-zinc-800/40 p-4 ring-1 ring-zinc-700/40 text-center">
              <p class="text-sm text-gray-400">
                Нужна роль, которой нет в списке? Напишите нам &mdash;
                <a href="https://t.me/ai_sekretar24bot" target="_blank" rel="noopener noreferrer" class="text-orange-400 hover:text-orange-300 underline">соберём под вашу задачу</a>.
              </p>
            </div>
          </div>

          <!-- AI Engines -->
          <div v-if="activeTab === 'ai'" class="space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
              <!-- Local AI -->
              <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-3 mb-3">
                  <div class="w-9 h-9 rounded-lg bg-emerald-900/50 flex items-center justify-center">
                    <svg class="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25z" />
                    </svg>
                  </div>
                  <h3 class="text-base font-semibold text-white">Локальные модели</h3>
                </div>
                <p class="text-sm text-gray-400 leading-relaxed mb-3">
                  Запускайте LLM прямо на вашем сервере через vLLM. Поддерживаются Qwen, Llama, DeepSeek, Mistral, Phi и другие модели в форматах AWQ, GPTQ, GGUF.
                </p>
                <ul class="space-y-1.5 text-sm text-gray-400">
                  <li class="flex items-start gap-2">
                    <span class="text-emerald-400 mt-0.5">&#10003;</span>
                    Полная автономность без интернета
                  </li>
                  <li class="flex items-start gap-2">
                    <span class="text-emerald-400 mt-0.5">&#10003;</span>
                    LoRA/QLoRA-дообучение на собственных данных
                  </li>
                  <li class="flex items-start gap-2">
                    <span class="text-emerald-400 mt-0.5">&#10003;</span>
                    GPU-ускорение (RTX 3060+ / 12 GB VRAM)
                  </li>
                  <li class="flex items-start gap-2">
                    <span class="text-emerald-400 mt-0.5">&#10003;</span>
                    Автообнаружение моделей из HuggingFace
                  </li>
                </ul>
              </div>

              <!-- Cloud AI -->
              <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-3 mb-3">
                  <div class="w-9 h-9 rounded-lg bg-sky-900/50 flex items-center justify-center">
                    <svg class="w-5 h-5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z" />
                    </svg>
                  </div>
                  <h3 class="text-base font-semibold text-white">Облачные провайдеры</h3>
                </div>
                <p class="text-sm text-gray-400 leading-relaxed mb-3">
                  Подключайте любые облачные LLM одновременно. Переключайтесь между ними на лету, комбинируйте с локальными моделями, настраивайте автоматический фоллбек.
                </p>
                <ul class="space-y-1.5 text-sm text-gray-400">
                  <li class="flex items-start gap-2">
                    <span class="text-sky-400 mt-0.5">&#10003;</span>
                    Google Gemini, OpenAI, Anthropic Claude
                  </li>
                  <li class="flex items-start gap-2">
                    <span class="text-sky-400 mt-0.5">&#10003;</span>
                    DeepSeek, Kimi (Moonshot), OpenRouter
                  </li>
                  <li class="flex items-start gap-2">
                    <span class="text-sky-400 mt-0.5">&#10003;</span>
                    Claude Bridge &mdash; Claude Code CLI как LLM-бэкенд
                  </li>
                  <li class="flex items-start gap-2">
                    <span class="text-sky-400 mt-0.5">&#10003;</span>
                    VLESS-прокси для обхода региональных блокировок
                  </li>
                </ul>
              </div>
            </div>

            <!-- Hybrid mode -->
            <div class="rounded-lg bg-gradient-to-r from-emerald-900/20 via-zinc-800/60 to-sky-900/20 p-5 ring-1 ring-zinc-700/50">
              <div class="flex items-center gap-3 mb-3">
                <div class="w-9 h-9 rounded-lg bg-orange-900/50 flex items-center justify-center">
                  <svg class="w-5 h-5 text-orange-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
                  </svg>
                </div>
                <h3 class="text-base font-semibold text-white">Гибридный режим</h3>
              </div>
              <p class="text-sm text-gray-400 leading-relaxed">
                Используйте локальные и облачные модели одновременно. Назначайте разные LLM-бэкенды для разных задач:
                локальную модель для конфиденциальных разговоров, облачную &mdash; для сложных аналитических запросов.
                Каждый Telegram-бот, каждая чат-сессия может работать на собственном LLM-провайдере.
                При недоступности основного провайдера система автоматически переключается на резервный.
              </p>
            </div>

            <!-- Roles -->
            <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
              <div class="flex items-center gap-3 mb-3">
                <div class="w-9 h-9 rounded-lg bg-violet-900/50 flex items-center justify-center">
                  <svg class="w-5 h-5 text-violet-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
                  </svg>
                </div>
                <h3 class="text-base font-semibold text-white">Любые роли и персоны</h3>
              </div>
              <p class="text-sm text-gray-400 leading-relaxed">
                Настраивайте произвольные роли секретаря: от строгого делового ассистента до дружелюбного консультанта.
                Каждая персона имеет собственный системный промпт, голос (клонированный или синтетический),
                стиль общения и набор знаний. Создавайте специализированных ботов-продавцов
                с воронками продаж, квизами и сегментацией клиентов. Несколько персон могут работать параллельно,
                обслуживая разные каналы коммуникации.
              </p>
            </div>
          </div>

          <!-- Privacy -->
          <div v-if="activeTab === 'privacy'" class="space-y-5">
            <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
              <div class="flex items-center gap-3 mb-3">
                <div class="w-9 h-9 rounded-lg bg-emerald-900/50 flex items-center justify-center">
                  <svg class="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
                  </svg>
                </div>
                <h3 class="text-base font-semibold text-white">Полная автономность</h3>
              </div>
              <p class="text-sm text-gray-400 leading-relaxed">
                При использовании локальных моделей система работает полностью без выхода в интернет.
                Все данные &mdash; разговоры, голосовые записи, FAQ, история взаимодействий &mdash; хранятся
                на вашем сервере в SQLite-базе. Ни один байт не покидает ваш контур безопасности.
              </p>
            </div>

            <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
              <div class="flex items-center gap-3 mb-3">
                <div class="w-9 h-9 rounded-lg bg-amber-900/50 flex items-center justify-center">
                  <svg class="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4.26 10.147a60.436 60.436 0 00-.491 6.347A48.627 48.627 0 0112 20.904a48.627 48.627 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.57 50.57 0 00-2.658-.813A59.905 59.905 0 0112 3.493a59.902 59.902 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.697 50.697 0 0112 13.489a50.702 50.702 0 017.74-3.342M6.75 15a.75.75 0 100-1.5.75.75 0 000 1.5zm0 0v-3.675A55.378 55.378 0 0112 8.443m-7.007 11.55A5.981 5.981 0 006.75 15.75v-1.5" />
                  </svg>
                </div>
                <h3 class="text-base font-semibold text-white">Обучение на своих данных</h3>
              </div>
              <p class="text-sm text-gray-400 leading-relaxed">
                Дообучайте языковую модель на собственных данных методом LoRA/QLoRA прямо из панели администратора.
                Используйте экспорт из Telegram-диалогов, базу FAQ, техническую документацию и сценарии продаж
                как обучающий датасет. После обучения модель работает автономно, глубоко понимая специфику вашего бизнеса &mdash;
                без отправки данных в облако.
              </p>
            </div>

            <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
              <div class="flex items-center gap-3 mb-3">
                <div class="w-9 h-9 rounded-lg bg-rose-900/50 flex items-center justify-center">
                  <svg class="w-5 h-5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
                  </svg>
                </div>
                <h3 class="text-base font-semibold text-white">Контроль доступа и аудит</h3>
              </div>
              <p class="text-sm text-gray-400 leading-relaxed">
                JWT-аутентификация, настраиваемые rate-лимиты для каждого типа эндпоинтов,
                Security-заголовки (CSP, X-Frame-Options), детальный журнал аудита всех действий
                в панели управления. Вы всегда знаете, кто, когда и что изменил в настройках системы.
              </p>
            </div>

            <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
              <div class="flex items-center gap-3 mb-3">
                <div class="w-9 h-9 rounded-lg bg-sky-900/50 flex items-center justify-center">
                  <svg class="w-5 h-5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 003 12c0-1.605.42-3.113 1.157-4.418" />
                  </svg>
                </div>
                <h3 class="text-base font-semibold text-white">Гибкость развёртывания</h3>
              </div>
              <p class="text-sm text-gray-400 leading-relaxed">
                Разворачивайте на собственном сервере, в закрытом контуре организации или в облаке &mdash; на ваш выбор.
                Docker-контейнеры для GPU и CPU режимов, поддержка VLESS-прокси для доступа к облачным провайдерам
                из ограниченных сетей. Open-source лицензия &mdash; полный контроль над исходным кодом.
              </p>
            </div>
          </div>

          <!-- Features -->
          <div v-if="activeTab === 'features'" class="space-y-5">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <!-- Voice cloning -->
              <div class="rounded-lg bg-zinc-800/60 p-4 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-2.5 mb-2">
                  <svg class="w-5 h-5 text-orange-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
                  </svg>
                  <h4 class="text-sm font-semibold text-white">Клонирование голоса</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  XTTS v2 клонирует голос по аудио-образцу. Piper TTS для CPU-режима.
                  Стриминг-синтез с задержкой менее 500 мс для телефонии.
                </p>
              </div>

              <!-- STT -->
              <div class="rounded-lg bg-zinc-800/60 p-4 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-2.5 mb-2">
                  <svg class="w-5 h-5 text-orange-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z" />
                  </svg>
                  <h4 class="text-sm font-semibold text-white">Распознавание речи</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  Vosk для потокового распознавания в реальном времени,
                  Whisper для пакетной транскрибации. Оба работают локально.
                </p>
              </div>

              <!-- FAQ -->
              <div class="rounded-lg bg-zinc-800/60 p-4 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-2.5 mb-2">
                  <svg class="w-5 h-5 text-orange-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" />
                  </svg>
                  <h4 class="text-sm font-semibold text-white">FAQ и мгновенные ответы</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  Быстрые ответы на типовые вопросы без обращения к LLM.
                  Управляйте базой знаний через админ-панель. Приоритет FAQ перед генерацией.
                </p>
              </div>

              <!-- Fine-tuning -->
              <div class="rounded-lg bg-zinc-800/60 p-4 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-2.5 mb-2">
                  <svg class="w-5 h-5 text-orange-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
                  </svg>
                  <h4 class="text-sm font-semibold text-white">Дообучение моделей</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  LoRA/QLoRA файнтюнинг из панели управления. Генерация датасета из FAQ,
                  Telegram-диалогов и документации. Управление адаптерами.
                </p>
              </div>

              <!-- Sales bot -->
              <div class="rounded-lg bg-zinc-800/60 p-4 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-2.5 mb-2">
                  <svg class="w-5 h-5 text-orange-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" />
                  </svg>
                  <h4 class="text-sm font-semibold text-white">Бот-продавец</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  Воронки продаж, квизы для квалификации лидов, сегментация клиентов,
                  автоматические follow-up цепочки. Приём платежей через YooKassa, YooMoney, Telegram Stars.
                </p>
              </div>

              <!-- Monitoring -->
              <div class="rounded-lg bg-zinc-800/60 p-4 ring-1 ring-zinc-700/50">
                <div class="flex items-center gap-2.5 mb-2">
                  <svg class="w-5 h-5 text-orange-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
                  </svg>
                  <h4 class="text-sm font-semibold text-white">Мониторинг и аналитика</h4>
                </div>
                <p class="text-xs text-gray-400 leading-relaxed">
                  GPU/CPU/RAM в реальном времени через SSE. Статистика использования,
                  лимиты, журнал аудита. Управление сервисами из единого дашборда.
                </p>
              </div>
            </div>
          </div>

          <!-- Channels -->
          <div v-if="activeTab === 'channels'" class="space-y-5">
            <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
              <div class="flex items-center gap-3 mb-3">
                <div class="w-9 h-9 rounded-lg bg-sky-900/50 flex items-center justify-center">
                  <svg class="w-5 h-5 text-sky-400" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M11.944 0A12 12 0 000 12a12 12 0 0012 12 12 12 0 0012-12A12 12 0 0012 0a12 12 0 00-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 01.171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
                  </svg>
                </div>
                <h3 class="text-base font-semibold text-white">Telegram-боты</h3>
              </div>
              <p class="text-sm text-gray-400 leading-relaxed">
                Неограниченное количество Telegram-ботов, каждый со своей ролью, LLM-бэкендом и голосом.
                Бот-поддержка, бот-продавец, бот-консультант &mdash; управляйте всеми из единой панели.
                Автозапуск ботов при перезагрузке, мультиплатформенные платежи (YooKassa, YooMoney, Telegram Stars),
                сессии с сохранением контекста.
              </p>
            </div>

            <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
              <div class="flex items-center gap-3 mb-3">
                <div class="w-9 h-9 rounded-lg bg-violet-900/50 flex items-center justify-center">
                  <svg class="w-5 h-5 text-violet-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
                  </svg>
                </div>
                <h3 class="text-base font-semibold text-white">Чат-виджет для сайта</h3>
              </div>
              <p class="text-sm text-gray-400 leading-relaxed">
                Встраиваемый чат-виджет для любого сайта. Мультиинстансность &mdash;
                разные виджеты для разных сайтов с индивидуальными настройками.
                Настраиваемый внешний вид, интеграция с FAQ и LLM-бэкендом.
              </p>
            </div>

            <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
              <div class="flex items-center gap-3 mb-3">
                <div class="w-9 h-9 rounded-lg bg-emerald-900/50 flex items-center justify-center">
                  <svg class="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
                  </svg>
                </div>
                <h3 class="text-base font-semibold text-white">GSM-телефония</h3>
              </div>
              <p class="text-sm text-gray-400 leading-relaxed">
                Подключите GSM-модуль SIM7600E-H и принимайте реальные телефонные звонки.
                Распознавание речи в реальном времени, генерация ответов через LLM, синтез речи
                с потоковой отдачей аудио. Полноценный голосовой AI-секретарь на обычном телефонном номере.
              </p>
            </div>

            <div class="rounded-lg bg-zinc-800/60 p-5 ring-1 ring-zinc-700/50">
              <div class="flex items-center gap-3 mb-3">
                <div class="w-9 h-9 rounded-lg bg-orange-900/50 flex items-center justify-center">
                  <svg class="w-5 h-5 text-orange-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
                  </svg>
                </div>
                <h3 class="text-base font-semibold text-white">OpenAI-совместимый API</h3>
              </div>
              <p class="text-sm text-gray-400 leading-relaxed">
                Система предоставляет стандартный <code class="text-orange-400/80">/v1/chat/completions</code> API,
                совместимый с OpenWebUI и другими клиентами. Подключайте AI-Секретаря как бэкенд
                к любым инструментам, поддерживающим OpenAI API.
              </p>
            </div>
          </div>

        </div>

        <!-- Free & Open Source + Contact -->
        <div class="mt-6 rounded-xl bg-gradient-to-br from-orange-900/20 via-zinc-900/80 to-zinc-900/80 ring-1 ring-orange-700/30 p-5 sm:p-6">
          <div class="flex items-start gap-4">
            <div class="w-10 h-10 rounded-lg bg-orange-700/30 flex items-center justify-center shrink-0 mt-0.5">
              <svg class="w-6 h-6 text-orange-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z" />
              </svg>
            </div>
            <div>
              <h3 class="text-base font-semibold text-white mb-2">
                Полностью бесплатно и открыто
              </h3>
              <p class="text-sm text-gray-400 leading-relaxed mb-3">
                AI-Секретарь &mdash; это open-source проект. Скачайте исходный код с GitHub, разверните
                на своём сервере и пользуйтесь без ограничений, лицензионных сборов и скрытых платежей.
                Система целиком в ваших руках.
              </p>
              <a
                href="https://github.com/ShaerWare/AI_Secretary_System"
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex items-center gap-2 rounded-lg bg-zinc-800 px-4 py-2 text-sm font-medium text-white ring-1 ring-zinc-700 hover:bg-zinc-700 hover:ring-orange-600/50 transition-all"
              >
                <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
                </svg>
                Скачать с GitHub
              </a>
            </div>
          </div>
        </div>

        <!-- Feedback -->
        <div class="mt-4 rounded-xl bg-zinc-900/80 ring-1 ring-zinc-800 p-5 sm:p-6">
          <h3 class="text-base font-semibold text-white mb-3">
            Обратная связь
          </h3>
          <p class="text-sm text-gray-400 leading-relaxed mb-4">
            Буду благодарен за любую обратную связь! Если проект оказался полезен &mdash;
            поставьте звезду на GitHub, откройте issue с предложениями или сделайте форк
            и предложите свои улучшения через pull request.
          </p>
          <div class="flex flex-wrap gap-3">
            <a
              href="https://github.com/ShaerWare/AI_Secretary_System/stargazers"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex items-center gap-1.5 rounded-lg bg-zinc-800 px-3 py-1.5 text-xs font-medium text-gray-300 ring-1 ring-zinc-700 hover:bg-zinc-700 hover:text-white hover:ring-orange-600/50 transition-all"
            >
              <svg class="w-4 h-4 text-amber-400" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 .587l3.668 7.568 8.332 1.151-6.064 5.828 1.48 8.279L12 19.771l-7.416 3.642 1.48-8.279L0 9.306l8.332-1.151z" />
              </svg>
              Star
            </a>
            <a
              href="https://github.com/ShaerWare/AI_Secretary_System/issues"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex items-center gap-1.5 rounded-lg bg-zinc-800 px-3 py-1.5 text-xs font-medium text-gray-300 ring-1 ring-zinc-700 hover:bg-zinc-700 hover:text-white hover:ring-orange-600/50 transition-all"
            >
              <svg class="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Issues
            </a>
            <a
              href="https://github.com/ShaerWare/AI_Secretary_System/fork"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex items-center gap-1.5 rounded-lg bg-zinc-800 px-3 py-1.5 text-xs font-medium text-gray-300 ring-1 ring-zinc-700 hover:bg-zinc-700 hover:text-white hover:ring-orange-600/50 transition-all"
            >
              <svg class="w-4 h-4 text-violet-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" />
              </svg>
              Fork
            </a>
          </div>
        </div>

        <!-- Contact -->
        <div class="mt-4 rounded-xl bg-zinc-900/80 ring-1 ring-zinc-800 p-5 sm:p-6">
          <h3 class="text-base font-semibold text-white mb-3">
            Вопросы и поддержка
          </h3>
          <p class="text-sm text-gray-400 leading-relaxed mb-4">
            По любым вопросам &mdash; установка, настройка, интеграция, доработка &mdash;
            обращайтесь в Telegram-бот поддержки или на сайт разработчика.
          </p>
          <div class="flex flex-wrap gap-3">
            <a
              href="https://t.me/ai_sekretar24bot"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex items-center gap-2 rounded-lg bg-zinc-800 px-4 py-2 text-sm font-medium text-white ring-1 ring-zinc-700 hover:bg-zinc-700 hover:ring-orange-600/50 transition-all"
            >
              <svg class="w-5 h-5 text-sky-400" fill="currentColor" viewBox="0 0 24 24">
                <path d="M11.944 0A12 12 0 000 12a12 12 0 0012 12 12 12 0 0012-12A12 12 0 0012 0a12 12 0 00-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 01.171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
              </svg>
              Telegram-поддержка 24/7
            </a>
            <a
              href="https://shaerware.digital/ru"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex items-center gap-2 rounded-lg bg-zinc-800 px-4 py-2 text-sm font-medium text-white ring-1 ring-zinc-700 hover:bg-zinc-700 hover:ring-orange-600/50 transition-all"
            >
              <svg class="w-5 h-5 text-orange-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 003 12c0-1.605.42-3.113 1.157-4.418" />
              </svg>
              ShaerWare Digital
            </a>
          </div>
        </div>

      </div>
    </Transition>

    <!-- SEO footer -->
    <div class="mt-8 text-center relative" style="z-index: 2;">
      <p class="text-xs text-gray-600">
        &copy; 2025 <a href="https://shaerware.digital/ru" target="_blank" rel="noopener noreferrer" class="hover:text-gray-400 transition-colors">ShaerWare Digital</a>
      </p>
    </div>
  </div>
</template>
