import { NextResponse } from "next/server";

type LocalModel = {
  id: string;
  label: string;
  provider: "ollama" | "llamacpp" | "lmstudio" | "custom";
};

type ProbeResult = {
  provider: LocalModel["provider"];
  status: "ok" | "error" | "skipped";
  detail?: string;
};

const ROUTE_PREFIX: Record<LocalModel["provider"], string> = {
  ollama: "ollama_chat",
  llamacpp: "llamacpp",
  lmstudio: "lm_studio",
  custom: "custom",
};

const LITELLM_URL = trimBaseUrl(process.env.LITELLM_URL) || "http://litellm:4000";
const LITELLM_KEY = process.env.LITELLM_API_KEY ?? process.env.LITELLM_MASTER_KEY ?? "";

function trimBaseUrl(value: string | undefined): string {
  return (value ?? "").trim().replace(/\/+$/, "");
}

function ollamaNativeBase(value: string | undefined): string {
  const base = trimBaseUrl(value);
  return base.replace(/\/v1$/i, "");
}

function uniqueModels(models: LocalModel[]): LocalModel[] {
  const seen = new Set<string>();
  return models.filter((model) => {
    if (seen.has(model.id)) return false;
    seen.add(model.id);
    return true;
  });
}

async function fetchJson(url: string, headers?: HeadersInit): Promise<unknown> {
  const res = await fetch(url, {
    headers,
    signal: AbortSignal.timeout(5000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function registeredLiteLLMModels(): Promise<Set<string>> {
  if (!LITELLM_KEY) return new Set();
  try {
    const data = (await fetchJson(`${LITELLM_URL}/v1/models`, {
      Authorization: `Bearer ${LITELLM_KEY}`,
    })) as { data?: Array<{ id?: string }> };
    return new Set(data.data?.map((model) => model.id).filter((id): id is string => Boolean(id)) ?? []);
  } catch {
    return new Set();
  }
}

function litellmParamsFor(model: LocalModel): Record<string, string> {
  if (model.provider === "ollama") {
    const base = ollamaNativeBase(process.env.OLLAMA_API_BASE) || "http://host.docker.internal:11434";
    return {
      model: model.id,
      api_base: base,
    };
  }
  if (model.provider === "llamacpp") {
    return {
      model: `openai/${model.id.split("/", 2)[1]}`,
      api_base: trimBaseUrl(process.env.LLAMACPP_API_BASE),
      api_key: process.env.LLAMACPP_API_KEY ? "os.environ/LLAMACPP_API_KEY" : "llama-cpp",
    };
  }
  if (model.provider === "lmstudio") {
    return {
      model: `openai/${model.id.split("/", 2)[1]}`,
      api_base: trimBaseUrl(process.env.LMSTUDIO_API_BASE),
      api_key: process.env.LMSTUDIO_API_KEY ? "os.environ/LMSTUDIO_API_KEY" : "lm-studio",
    };
  }
  return {
    model: `openai/${model.id.split("/", 2)[1]}`,
    api_base: trimBaseUrl(process.env.CUSTOM_OPENAI_API_BASE),
    api_key: "os.environ/CUSTOM_OPENAI_API_KEY",
  };
}

async function ensureLiteLLMModels(models: LocalModel[]): Promise<ProbeResult> {
  if (!LITELLM_KEY) return { provider: "ollama", status: "skipped", detail: "LiteLLM key not configured" };
  const registered = await registeredLiteLLMModels();
  const missing = models.filter((model) => !registered.has(model.id));
  if (missing.length === 0) return { provider: "ollama", status: "ok", detail: "all local models registered" };

  let added = 0;
  for (const model of missing) {
    try {
      const res = await fetch(`${LITELLM_URL}/model/new`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${LITELLM_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model_name: model.id,
          litellm_params: litellmParamsFor(model),
          model_info: { source: model.provider, display_name: model.label },
        }),
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) added += 1;
    } catch {
      // Keep discovery usable even if a route could not be registered.
    }
  }
  return {
    provider: "ollama",
    status: added === missing.length ? "ok" : "error",
    detail: `registered ${added}/${missing.length} missing local models`,
  };
}

async function listOllama(): Promise<{ models: LocalModel[]; result: ProbeResult }> {
  const base = ollamaNativeBase(process.env.OLLAMA_API_BASE) || "http://host.docker.internal:11434";
  try {
    const data = (await fetchJson(`${base}/api/tags`)) as {
      models?: Array<{ name?: string; model?: string }>;
    };
    const models =
      data.models
        ?.map((item) => (item.name ?? item.model ?? "").trim())
        .filter(Boolean)
        .map((name) => ({
          id: `ollama_chat/${name}`,
          label: name,
          provider: "ollama" as const,
        })) ?? [];
    return { models, result: { provider: "ollama", status: "ok", detail: `${models.length} models` } };
  } catch (err) {
    return {
      models: [],
      result: {
        provider: "ollama",
        status: "error",
        detail: err instanceof Error ? err.message : "unreachable",
      },
    };
  }
}

async function listOpenAICompatible(
  provider: "llamacpp" | "lmstudio" | "custom",
  baseUrl: string | undefined,
  apiKey: string | undefined,
): Promise<{ models: LocalModel[]; result: ProbeResult }> {
  const base = trimBaseUrl(baseUrl);
  if (!base) return { models: [], result: { provider, status: "skipped", detail: "base URL not configured" } };

  const headers: HeadersInit = apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
  try {
    const data = (await fetchJson(`${base}/models`, headers)) as {
      data?: Array<{ id?: string }>;
    };
    const models =
      data.data
        ?.map((item) => (item.id ?? "").trim())
        .filter(Boolean)
        .map((name) => ({
          id: `${ROUTE_PREFIX[provider]}/${name}`,
          label: name,
          provider,
        })) ?? [];
    return { models, result: { provider, status: "ok", detail: `${models.length} models` } };
  } catch (err) {
    return {
      models: [],
      result: {
        provider,
        status: "error",
        detail: err instanceof Error ? err.message : "unreachable",
      },
    };
  }
}

export async function GET() {
  const [ollama, llamacpp, lmstudio, custom] = await Promise.all([
    listOllama(),
    listOpenAICompatible("llamacpp", process.env.LLAMACPP_API_BASE, process.env.LLAMACPP_API_KEY),
    listOpenAICompatible("lmstudio", process.env.LMSTUDIO_API_BASE, process.env.LMSTUDIO_API_KEY),
    listOpenAICompatible("custom", process.env.CUSTOM_OPENAI_API_BASE, process.env.CUSTOM_OPENAI_API_KEY),
  ]);

  const models = uniqueModels([...ollama.models, ...llamacpp.models, ...lmstudio.models, ...custom.models]);
  const registration = await ensureLiteLLMModels(models);

  return NextResponse.json({
    models,
    sources: [ollama.result, llamacpp.result, lmstudio.result, custom.result, registration],
  });
}
