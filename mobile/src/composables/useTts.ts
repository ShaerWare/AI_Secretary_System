import { ref } from "vue";
import { useSettingsStore } from "@/stores/settings";
import { useAuthStore } from "@/stores/auth";

export function useTts() {
  const isSpeaking = ref(false);
  const speakingMessageId = ref<string | null>(null);
  let currentAudio: HTMLAudioElement | null = null;

  async function speak(text: string, messageId?: string) {
    stop();

    const settings = useSettingsStore();
    const auth = useAuthStore();

    isSpeaking.value = true;
    speakingMessageId.value = messageId || null;

    try {
      const response = await fetch(
        `${settings.serverUrl}/admin/voice/test`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...auth.getAuthHeaders(),
          },
          body: JSON.stringify({ text }),
        },
      );

      if (!response.ok) throw new Error("TTS failed");

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);

      currentAudio = new Audio(url);
      currentAudio.onended = () => {
        cleanup();
      };
      currentAudio.onerror = () => {
        cleanup();
      };
      await currentAudio.play();
    } catch {
      cleanup();
    }
  }

  function stop() {
    if (currentAudio) {
      currentAudio.pause();
      if (currentAudio.src) {
        URL.revokeObjectURL(currentAudio.src);
      }
      currentAudio = null;
    }
    cleanup();
  }

  function cleanup() {
    isSpeaking.value = false;
    speakingMessageId.value = null;
  }

  return { isSpeaking, speakingMessageId, speak, stop };
}
