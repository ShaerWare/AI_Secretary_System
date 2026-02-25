import { api, getAuthHeaders } from "./client";

export interface SttStatus {
  vosk_available: boolean;
  whisper_available: boolean;
  vosk_model: string | null;
  whisper_model: string | null;
  unified_available: boolean;
}

export interface SttModel {
  name: string;
  path: string;
  size_mb: number;
  language: string;
}

export interface TranscribeResult {
  text: string;
  confidence?: number;
  duration?: number;
  engine: string;
}

// STT API
export const sttApi = {
  getStatus: () => api.get<SttStatus>("/admin/stt/status"),

  getModels: () => api.get<{ models: SttModel[] }>("/admin/stt/models"),

  transcribe: async (
    audioBlob: Blob,
    language: string = "ru",
    engine: string = "auto"
  ): Promise<TranscribeResult> => {
    const formData = new FormData();
    formData.append("file", audioBlob, "recording.webm");
    formData.append("language", language);
    formData.append("engine", engine);

    const response = await fetch("/admin/stt/transcribe", {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`STT failed: ${response.statusText}`);
    }

    return response.json();
  },

  test: (textToSpeak: string = "Привет, это тест распознавания речи") =>
    api.post<{
      original_text: string;
      recognized_text: string;
      match: boolean;
      duration_seconds: number;
    }>("/admin/stt/test", { text_to_speak: textToSpeak }),
};
