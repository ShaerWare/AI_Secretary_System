import { api, createSSE } from './client'

export interface DatasetStats {
  total_sessions: number
  total_messages: number
  total_tokens: number
  avg_tokens_per_message: number
  file_path: string | null
  file_size_mb: number
  modified: string | null
}

export interface DatasetFile {
  name: string
  path: string
  size_mb: number
  modified: string
  type?: string
}

export interface DatasetConfig {
  owner_name: string
  transcribe_voice: boolean
  min_dialog_messages: number
  max_message_length: number
  max_dialog_length: number
  include_groups: boolean
  output_name: string
}

export interface ProcessingStatus {
  is_running: boolean
  stage: string
  current: number
  total: number
  voice_transcribed: number
  voice_total: number
  error: string | null
}

export interface TrainingConfig {
  base_model: string
  lora_rank: number
  lora_alpha: number
  lora_dropout: number
  batch_size: number
  gradient_accumulation_steps: number
  learning_rate: number
  num_epochs: number
  warmup_ratio: number
  max_seq_length: number
  output_dir: string
}

export interface TrainingStatus {
  is_running: boolean
  current_step: number
  total_steps: number
  current_epoch: number
  total_epochs: number
  loss: number
  learning_rate: number
  elapsed_seconds: number
  eta_seconds: number
  error: string | null
}

export interface Adapter {
  name: string
  path: string
  size_mb: number
  modified: string
  active: boolean
  config: Record<string, unknown> | null
}

// Finetune API
export const finetuneApi = {
  // Dataset
  uploadDataset: (file: File) =>
    api.upload<{ status: string; message: string; path: string; size_mb: number }>(
      '/admin/finetune/dataset/upload',
      file
    ),

  processDataset: (config?: Partial<DatasetConfig>) =>
    api.post<{ status: string; message: string; output_file?: string; stats?: Record<string, number> }>(
      '/admin/finetune/dataset/process',
      config
    ),

  getDatasetConfig: () =>
    api.get<{ config: DatasetConfig }>('/admin/finetune/dataset/config'),

  setDatasetConfig: (config: Partial<DatasetConfig>) =>
    api.post<{ status: string; config: DatasetConfig }>('/admin/finetune/dataset/config', config),

  getProcessingStatus: () =>
    api.get<{ status: ProcessingStatus }>('/admin/finetune/dataset/processing-status'),

  getDatasetStats: () =>
    api.get<{ stats: DatasetStats }>('/admin/finetune/dataset/stats'),

  listDatasets: () =>
    api.get<{ datasets: DatasetFile[] }>('/admin/finetune/dataset/list'),

  augmentDataset: () =>
    api.post<{ status: string; message: string; stats?: DatasetStats }>(
      '/admin/finetune/dataset/augment'
    ),

  generateProjectDataset: (config?: {
    include_tz?: boolean
    include_faq?: boolean
    include_docs?: boolean
    include_escalation?: boolean
    include_code?: boolean
    output_name?: string
  }) =>
    api.post<{
      status: string
      message: string
      output_file?: string
      stats?: {
        total_dialogs: number
        total_messages: number
        sources: Record<string, number>
      }
    }>('/admin/finetune/dataset/generate-project', config),

  // Config
  getConfig: () =>
    api.get<{
      config: TrainingConfig
      presets: Record<string, Partial<TrainingConfig>>
    }>('/admin/finetune/config'),

  setConfig: (config: Partial<TrainingConfig>) =>
    api.post<{ status: string; config?: TrainingConfig }>('/admin/finetune/config', config),

  // Training
  startTraining: () =>
    api.post<{ status: string; message: string; config?: TrainingConfig; pid?: number }>(
      '/admin/finetune/train/start'
    ),

  stopTraining: () =>
    api.post<{ status: string; message: string }>('/admin/finetune/train/stop'),

  getTrainingStatus: () =>
    api.get<{ status: TrainingStatus }>('/admin/finetune/train/status'),

  streamTrainingLog: (onMessage: (data: { type: string; line?: string; status?: TrainingStatus }) => void) =>
    createSSE<{ type: string; line?: string; status?: TrainingStatus }>('/admin/finetune/train/log', onMessage),

  // Adapters
  listAdapters: () =>
    api.get<{ adapters: Adapter[]; active: string | null }>('/admin/finetune/adapters'),

  activateAdapter: (adapter: string) =>
    api.post<{ status: string; message: string; adapter?: string; path?: string; note?: string }>(
      '/admin/finetune/adapters/activate',
      { adapter }
    ),

  deleteAdapter: (name: string) =>
    api.delete<{ status: string; message: string }>(`/admin/finetune/adapters/${name}`),
}
