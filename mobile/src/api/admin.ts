import { api } from "./client";

export interface CloudProvider {
  id: number;
  name: string;
  provider_type: string;
  model_name: string;
  enabled: boolean;
  is_default: boolean;
}

export interface KnowledgeCollection {
  id: number;
  name: string;
  slug: string;
  description?: string;
  enabled: boolean;
  document_count: number;
}

export interface LlmOption {
  value: string;
  label: string;
  type: "vllm" | "cloud";
}

export const adminApi = {
  getProviders: () =>
    api.get<{ providers: CloudProvider[] }>(
      "/admin/llm/providers?enabled_only=true",
    ),

  getCollections: () =>
    api.get<{ collections: KnowledgeCollection[] }>(
      "/admin/wiki-rag/collections",
    ),
};
