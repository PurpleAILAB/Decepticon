"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { BUILTIN_MODEL_GROUPS, DEFAULT_MODEL_OPTION } from "@/lib/model-options";
import { Bot, Globe, Server, Loader2, RefreshCw } from "lucide-react";
import { isValidEngagementSlug } from "@/lib/engagement-slug";

type LocalModel = {
  id: string;
  label: string;
  provider: "ollama" | "llamacpp" | "lmstudio" | "custom";
};

type ModelPolicy = {
  blockedPatterns: string[];
};

const LOCAL_PROVIDER_LABELS: Record<LocalModel["provider"], string> = {
  ollama: "Ollama",
  llamacpp: "llama.cpp",
  lmstudio: "LM Studio",
  custom: "Custom OpenAI",
};

function isBlockedModel(id: string, patterns: string[]): boolean {
  const lower = id.toLowerCase();
  return patterns.some((pattern) => lower.includes(pattern.toLowerCase()));
}

export default function NewEngagementPage() {
  const router = useRouter();
  const [targetType, setTargetType] = useState("web_url");
  const [name, setName] = useState("");
  const [targetValue, setTargetValue] = useState("");
  const [modelChoice, setModelChoice] = useState("default");
  const [localModels, setLocalModels] = useState<LocalModel[]>([]);
  const [modelPolicy, setModelPolicy] = useState<ModelPolicy>({
    blockedPatterns: ["wormgpt", "uncensored", "abliterate"],
  });
  const [localModelsLoading, setLocalModelsLoading] = useState(false);
  const [customModel, setCustomModel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLocalModels = useCallback(async () => {
    setLocalModelsLoading(true);
    try {
      const res = await fetch("/api/local-models", { cache: "no-store" });
      if (!res.ok) throw new Error("Failed to load local models");
      const data = (await res.json()) as { models?: LocalModel[] };
      setLocalModels(data.models ?? []);
    } catch {
      setLocalModels([]);
    } finally {
      setLocalModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadLocalModels();
  }, [loadLocalModels]);

  const loadModelPolicy = useCallback(async () => {
    try {
      const res = await fetch("/api/model-policy", { cache: "no-store" });
      if (!res.ok) throw new Error("Failed to load model policy");
      setModelPolicy((await res.json()) as ModelPolicy);
    } catch {
      setModelPolicy({ blockedPatterns: ["wormgpt", "uncensored", "abliterate"] });
    }
  }, []);

  useEffect(() => {
    void loadModelPolicy();
  }, [loadModelPolicy]);

  const localModelsByProvider = useMemo(
    () =>
      localModels.reduce(
        (groups, model) => {
          const group = groups[model.provider] ?? [];
          group.push(model);
          groups[model.provider] = group;
          return groups;
        },
        {} as Partial<Record<LocalModel["provider"], LocalModel[]>>,
      ),
    [localModels],
  );

  const nameValid = isValidEngagementSlug(name);
  const nameError =
    name.length > 0 && !nameValid
      ? "Name must be 3-64 chars, lowercase letters / digits with internal hyphens only"
      : null;

  const modelOverride =
    modelChoice === "default"
      ? ""
      : modelChoice === "custom"
        ? customModel.trim()
        : modelChoice;

  async function handleSubmit() {
    if (!nameValid || !targetValue.trim()) {
      setError("Please fill in all required fields");
      return;
    }
    if (modelChoice === "custom" && !modelOverride) {
      setError("Please provide a model id");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const res = await fetch("/api/engagements", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, targetType, targetValue, modelOverride: modelOverride || null }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to create engagement");
      }

      const engagement = await res.json();
      const params = new URLSearchParams({ new: "true" });
      router.push(`/engagements/${engagement.id}/live?${params.toString()}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4 sm:space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">New Engagement</h1>
        <p className="text-sm text-muted-foreground">
          Configure a new red team testing operation (DAST)
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Engagement Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Engagement Name</Label>
            <Input
              id="name"
              placeholder="e.g., q2-security-assessment"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={nameError ? true : undefined}
            />
            {nameError ? (
              <p className="text-xs text-destructive">{nameError}</p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Used as the workspace folder name — 3-64 chars, lowercase
                letters / digits with internal hyphens
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Bot className="h-4 w-4" />
            Model
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="model">Primary Model</Label>
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => void loadLocalModels()}
                disabled={localModelsLoading}
                title="Refresh local models"
              >
                <RefreshCw className={`h-4 w-4 ${localModelsLoading ? "animate-spin" : ""}`} />
              </Button>
            </div>
            <Select value={modelChoice} onValueChange={(v) => setModelChoice(v ?? "default")}>
              <SelectTrigger id="model" className="w-full">
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent align="start" className="max-h-96">
                <SelectGroup>
                  <SelectLabel>Default</SelectLabel>
                  <SelectItem value={DEFAULT_MODEL_OPTION.value}>{DEFAULT_MODEL_OPTION.label}</SelectItem>
                </SelectGroup>
                {BUILTIN_MODEL_GROUPS.map((group) => (
                  <SelectGroup key={group.label}>
                    <SelectLabel>{group.label}</SelectLabel>
                    {group.models.map((model) => {
                      const blocked = isBlockedModel(model.value, modelPolicy.blockedPatterns);
                      return (
                        <SelectItem key={model.value} value={model.value} disabled={blocked}>
                          {blocked ? `${model.label} (gesperrt)` : model.label}
                        </SelectItem>
                      );
                    })}
                  </SelectGroup>
                ))}
                {(Object.keys(LOCAL_PROVIDER_LABELS) as LocalModel["provider"][]).map((provider) => {
                  const models = localModelsByProvider[provider] ?? [];
                  if (models.length === 0) return null;
                  return (
                    <SelectGroup key={provider}>
                      <SelectLabel>{LOCAL_PROVIDER_LABELS[provider]}</SelectLabel>
                      {models.map((model) => {
                        const blocked = isBlockedModel(model.id, modelPolicy.blockedPatterns);
                        return (
                          <SelectItem key={model.id} value={model.id} disabled={blocked}>
                            {blocked ? `${model.label} (gesperrt)` : model.label}
                          </SelectItem>
                        );
                      })}
                    </SelectGroup>
                  );
                })}
                <SelectGroup>
                  <SelectLabel>Manual</SelectLabel>
                  <SelectItem value="custom">Custom model ID</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>

          {modelChoice === "custom" && (
            <div className="space-y-2">
              <Label htmlFor="custom-model">Model ID</Label>
              <Input
                id="custom-model"
                placeholder="provider/model"
                value={customModel}
                onChange={(e) => setCustomModel(e.target.value)}
              />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Target Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs
            value={targetType}
            onValueChange={(v) => {
              setTargetType(v);
              setTargetValue("");
            }}
          >
            <TabsList className="w-full">
              <TabsTrigger value="web_url" className="flex-1 gap-2">
                <Globe className="h-4 w-4" />
                Web URL
              </TabsTrigger>
              <TabsTrigger value="ip_range" className="flex-1 gap-2">
                <Server className="h-4 w-4" />
                IP Range
              </TabsTrigger>
            </TabsList>

            <TabsContent value="web_url" className="mt-4 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="url">Target URL</Label>
                <Input
                  id="url"
                  type="url"
                  placeholder="https://example.com"
                  value={targetValue}
                  onChange={(e) => setTargetValue(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  The web application URL to test
                </p>
              </div>
            </TabsContent>

            <TabsContent value="ip_range" className="mt-4 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="ip">IP Range</Label>
                <Input
                  id="ip"
                  placeholder="192.168.1.0/24 or 10.0.0.1-10.0.0.255"
                  value={targetValue}
                  onChange={(e) => setTargetValue(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  CIDR notation or IP range to scan
                </p>
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-3">
        <Button variant="outline" className="w-full sm:w-auto" onClick={() => router.back()}>
          Cancel
        </Button>
        <Button className="w-full sm:w-auto" onClick={handleSubmit} disabled={submitting || !nameValid}>
          {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Create Engagement
        </Button>
      </div>
    </div>
  );
}
