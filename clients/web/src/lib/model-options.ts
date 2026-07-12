export type BuiltinModelGroup = "default" | "gpt" | "mittwald" | "cloud";

export type BuiltinModelOption = {
  value: string;
  label: string;
  group: BuiltinModelGroup;
};

export const DEFAULT_MODEL_OPTION: BuiltinModelOption = {
  value: "default",
  label: "Default chain",
  group: "default",
};

export const GPT_MODELS: BuiltinModelOption[] = [
  { value: "auth/gpt-5.5", label: "GPT OAuth 5.5", group: "gpt" },
  { value: "auth/gpt-5.4", label: "GPT OAuth 5.4", group: "gpt" },
  { value: "auth/gpt-5.4-mini", label: "GPT OAuth 5.4 Mini", group: "gpt" },
  { value: "auth/gpt-5.3-codex", label: "GPT OAuth 5.3 Codex", group: "gpt" },
  { value: "auth/gpt-5.3-codex-spark", label: "GPT OAuth 5.3 Codex Spark", group: "gpt" },
];

export const MITTWALD_MODELS: BuiltinModelOption[] = [
  { value: "mittwald/gpt-oss-120b", label: "gpt-oss-120b", group: "mittwald" },
  { value: "mittwald/Ministral-3-14B-Instruct-2512", label: "Ministral-3-14B-Instruct-2512", group: "mittwald" },
  { value: "mittwald/whisper-large-v3-turbo", label: "whisper-large-v3-turbo", group: "mittwald" },
  { value: "mittwald/Qwen3.5-122B-A10B-FP8", label: "Qwen3.5-122B-A10B-FP8", group: "mittwald" },
  { value: "mittwald/Qwen3.6-35B-A3B-FP8", label: "Qwen3.6-35B-A3B-FP8", group: "mittwald" },
  { value: "mittwald/Qwen3.5-0.8B", label: "Qwen3.5-0.8B", group: "mittwald" },
  { value: "mittwald/Qwen3-VL-Reranker-2B", label: "Qwen3-VL-Reranker-2B", group: "mittwald" },
  { value: "mittwald/GLM-OCR", label: "GLM-OCR", group: "mittwald" },
  { value: "mittwald/Mistral-Medium-3.5-128B", label: "Mistral-Medium-3.5-128B", group: "mittwald" },
  { value: "mittwald/Qwen3-Embedding-8B", label: "Qwen3-Embedding-8B", group: "mittwald" },
];

export const CLOUD_MODELS: BuiltinModelOption[] = [
  { value: "openrouter/moonshotai/kimi-k2", label: "Kimi K2 via OpenRouter", group: "cloud" },
  { value: "groq/llama-3.1-8b-instant", label: "Groq Free", group: "cloud" },
];

export const BUILTIN_MODEL_GROUPS = [
  { label: "GPT", models: GPT_MODELS },
  { label: "Mittwald", models: MITTWALD_MODELS },
  { label: "Cloud", models: CLOUD_MODELS },
] as const;

export const BUILTIN_MODELS: BuiltinModelOption[] = [
  DEFAULT_MODEL_OPTION,
  ...GPT_MODELS,
  ...MITTWALD_MODELS,
  ...CLOUD_MODELS,
];
