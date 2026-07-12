"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { BUILTIN_MODEL_GROUPS, BUILTIN_MODELS, DEFAULT_MODEL_OPTION } from "@/lib/model-options";
import { cn } from "@/lib/utils";
import { Ban, Check, RefreshCw, Save, Shield, SlidersHorizontal, X } from "lucide-react";

type LocalModel = {
  id: string;
  label: string;
  provider: "ollama" | "llamacpp" | "lmstudio" | "custom";
};

export type ModelOverrides = Record<string, string>;

type ModelPolicy = {
  blockedPatterns: string[];
};

const AGENT_ROLES = [
  { value: "soundwave", label: "Soundwave", hint: "planning" },
  { value: "decepticon", label: "Decepticon", hint: "orchestration" },
  { value: "recon", label: "Recon", hint: "discovery" },
  { value: "exploit", label: "Exploit", hint: "validation" },
  { value: "postexploit", label: "Post-Exploit", hint: "follow-up" },
  { value: "analyst", label: "Analyst", hint: "reasoning" },
  { value: "blue_cell", label: "Blue Cell", hint: "defense" },
  { value: "cloud_hunter", label: "Cloud Hunter", hint: "cloud" },
  { value: "ad_operator", label: "AD Operator", hint: "identity" },
  { value: "reverser", label: "Reverser", hint: "binaries" },
  { value: "forensicator", label: "Forensicator", hint: "evidence" },
  { value: "osint_operator", label: "OSINT Operator", hint: "passive" },
  { value: "mobile_operator", label: "Mobile Operator", hint: "mobile" },
  { value: "wireless_operator", label: "Wireless Operator", hint: "wireless" },
  { value: "iot_operator", label: "IoT Operator", hint: "devices" },
  { value: "ics_operator", label: "ICS Operator", hint: "safety" },
  { value: "contract_auditor", label: "Contract Auditor", hint: "contracts" },
  { value: "phisher", label: "Phisher", hint: "only if RoE allows" },
  { value: "supply_chain_operator", label: "Supply Chain", hint: "deps" },
] as const;

const LOCAL_PROVIDER_LABELS: Record<LocalModel["provider"], string> = {
  ollama: "Ollama",
  llamacpp: "llama.cpp",
  lmstudio: "LM Studio",
  custom: "Custom OpenAI",
};

function choiceFromOverride(value: string | null | undefined): string {
  const trimmed = (value ?? "").trim();
  if (!trimmed) return "default";
  if (BUILTIN_MODELS.some((model) => model.value === trimmed)) return trimmed;
  return "custom";
}

function normalizeOverrides(value: ModelOverrides | null | undefined): ModelOverrides {
  if (!value) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([role, model]) => [role, model.trim()])
      .filter(([, model]) => Boolean(model)),
  );
}

function isBlockedModel(id: string, patterns: string[]): boolean {
  const lower = id.toLowerCase();
  return patterns.some((pattern) => lower.includes(pattern.toLowerCase()));
}

function uniquePatterns(patterns: string[]): string[] {
  const seen = new Set<string>();
  const clean: string[] = [];
  for (const pattern of patterns) {
    const trimmed = pattern.trim();
    if (!trimmed) continue;
    const key = trimmed.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    clean.push(trimmed);
  }
  return clean;
}

function isKnownModelChoice(
  value: string,
  localModelsByProvider: Partial<Record<LocalModel["provider"], LocalModel[]>>,
): boolean {
  if (BUILTIN_MODELS.some((model) => model.value === value)) return true;
  return Object.values(localModelsByProvider).some((models) =>
    (models ?? []).some((model) => model.id === value),
  );
}

function RoleModelSelect({
  value,
  blockedPatterns,
  localModelsByProvider,
  compact = false,
  onChange,
}: {
  value: string;
  blockedPatterns: string[];
  localModelsByProvider: Partial<Record<LocalModel["provider"], LocalModel[]>>;
  compact?: boolean;
  onChange: (value: string) => void;
}) {
  const [forceCustom, setForceCustom] = useState(false);
  const trimmedValue = value.trim();
  const knownChoice = isKnownModelChoice(trimmedValue, localModelsByProvider);
  const choice = forceCustom || (trimmedValue && !knownChoice) ? "custom" : trimmedValue || "default";
  const customValue = choice === "custom" && trimmedValue !== "default" ? trimmedValue : "";

  useEffect(() => {
    if (trimmedValue && knownChoice) setForceCustom(false);
  }, [knownChoice, trimmedValue]);

  return (
    <div className={compact ? "flex min-w-0 flex-1 flex-col gap-2" : "flex min-w-0 flex-1 flex-col gap-2 sm:flex-row"}>
      <Select
        value={choice}
        onValueChange={(next) => {
          if (next === "custom") {
            setForceCustom(true);
            return;
          }
          setForceCustom(false);
          onChange(next === "default" ? "" : next ?? "");
        }}
      >
        <SelectTrigger className={compact ? "h-8 w-full min-w-0" : "h-8 min-w-0 sm:w-72"}>
          <SelectValue placeholder="Default chain" />
        </SelectTrigger>
        <SelectContent align="start">
          <SelectGroup>
            <SelectLabel>Default</SelectLabel>
            <SelectItem value={DEFAULT_MODEL_OPTION.value}>{DEFAULT_MODEL_OPTION.label}</SelectItem>
          </SelectGroup>
          {BUILTIN_MODEL_GROUPS.map((group) => (
            <SelectGroup key={group.label}>
              <SelectLabel>{group.label}</SelectLabel>
              {group.models.map((model) => {
                const blocked = isBlockedModel(model.value, blockedPatterns);
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
                  const blocked = isBlockedModel(model.id, blockedPatterns);
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
      {choice === "custom" && (
        <Input
          className={compact ? "h-8 w-full min-w-0" : "h-8 min-w-0 sm:w-72"}
          placeholder="provider/model"
          value={customValue}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </div>
  );
}

export function EngagementModelPicker({
  engagementId,
  value,
  overrides,
  variant = "bar",
  onChange,
}: {
  engagementId: string;
  value: string;
  overrides?: ModelOverrides | null;
  variant?: "bar" | "sidebar";
  onChange: (value: string, overrides: ModelOverrides) => void;
}) {
  const [choice, setChoice] = useState(choiceFromOverride(value));
  const [customModel, setCustomModel] = useState(choiceFromOverride(value) === "custom" ? value.trim() : "");
  const [roleOverrides, setRoleOverrides] = useState<ModelOverrides>(() => normalizeOverrides(overrides));
  const [showRoles, setShowRoles] = useState(false);
  const [showPolicy, setShowPolicy] = useState(false);
  const [localModels, setLocalModels] = useState<LocalModel[]>([]);
  const [modelPolicy, setModelPolicy] = useState<ModelPolicy>({
    blockedPatterns: ["wormgpt", "uncensored", "abliterate"],
  });
  const [policyDraft, setPolicyDraft] = useState("");
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");

  useEffect(() => {
    const trimmed = (value ?? "").trim();
    const localMatch = localModels.some((model) => model.id === trimmed);
    const next = localMatch ? trimmed : choiceFromOverride(trimmed);
    setChoice(next);
    if (next === "custom") setCustomModel(trimmed);
  }, [localModels, value]);

  useEffect(() => {
    setRoleOverrides(normalizeOverrides(overrides));
  }, [overrides]);

  const loadLocalModels = useCallback(async () => {
    setLoadingModels(true);
    try {
      const res = await fetch("/api/local-models", { cache: "no-store" });
      if (!res.ok) throw new Error("failed");
      const data = (await res.json()) as { models?: LocalModel[] };
      setLocalModels(data.models ?? []);
    } catch {
      setLocalModels([]);
    } finally {
      setLoadingModels(false);
    }
  }, []);

  useEffect(() => {
    void loadLocalModels();
  }, [loadLocalModels]);

  const loadModelPolicy = useCallback(async () => {
    try {
      const res = await fetch("/api/model-policy", { cache: "no-store" });
      if (!res.ok) throw new Error("failed");
      setModelPolicy((await res.json()) as ModelPolicy);
    } catch {
      setModelPolicy({
        blockedPatterns: ["wormgpt", "uncensored", "abliterate"],
      });
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

  const selectedModel = choice === "custom" ? customModel.trim() : choice === "default" ? "" : choice;
  const cleanOverrides = normalizeOverrides(roleOverrides);
  const blockedPatterns = modelPolicy.blockedPatterns;
  const dirty =
    selectedModel !== (value ?? "").trim() ||
    JSON.stringify(cleanOverrides) !== JSON.stringify(normalizeOverrides(overrides));

  const selectableModels = useMemo(
    () => [
      ...BUILTIN_MODELS.filter((model) => model.value !== "default").map((model) => ({
        id: model.value,
        label: model.label,
        provider: "cloud",
      })),
      ...localModels.map((model) => ({
        id: model.id,
        label: model.label,
        provider: LOCAL_PROVIDER_LABELS[model.provider],
      })),
    ],
    [localModels],
  );

  async function savePolicy(nextPatterns: string[]) {
    setSavingPolicy(true);
    setStatus("idle");
    try {
      const res = await fetch("/api/model-policy", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ blockedPatterns: uniquePatterns(nextPatterns) }),
      });
      if (!res.ok) throw new Error("save failed");
      setModelPolicy((await res.json()) as ModelPolicy);
    } catch {
      setStatus("error");
    } finally {
      setSavingPolicy(false);
    }
  }

  function blockModel(id: string) {
    void savePolicy([...blockedPatterns, id]);
  }

  function freeModel(id: string) {
    const lower = id.toLowerCase();
    void savePolicy(blockedPatterns.filter((pattern) => !lower.includes(pattern.toLowerCase())));
  }

  function addPattern() {
    if (!policyDraft.trim()) return;
    void savePolicy([...blockedPatterns, policyDraft]);
    setPolicyDraft("");
  }

  function updateRole(role: string, model: string) {
    setStatus("idle");
    setRoleOverrides((current) => {
      const next = { ...current };
      const trimmed = model.trim();
      if (trimmed) next[role] = trimmed;
      else delete next[role];
      return next;
    });
  }

  async function save() {
    if (choice === "custom" && !customModel.trim()) return;
    if ([selectedModel, ...Object.values(cleanOverrides)].some((model) => isBlockedModel(model, blockedPatterns))) {
      setStatus("error");
      return;
    }
    setSaving(true);
    setStatus("idle");
    try {
      const res = await fetch(`/api/engagements/${engagementId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          modelOverride: selectedModel || null,
          modelOverrides: Object.keys(cleanOverrides).length ? cleanOverrides : null,
        }),
      });
      if (!res.ok) throw new Error("save failed");
      const engagement = (await res.json()) as {
        modelOverride?: string | null;
        modelOverrides?: ModelOverrides | null;
      };
      const nextModel = engagement.modelOverride ?? "";
      const nextOverrides = normalizeOverrides(engagement.modelOverrides);
      onChange(nextModel, nextOverrides);
      window.dispatchEvent(
        new CustomEvent("decepticon:engagement-models-updated", {
          detail: {
            engagementId,
            modelOverride: nextModel,
            modelOverrides: nextOverrides,
          },
        }),
      );
      setStatus("saved");
    } catch {
      setStatus("error");
    } finally {
      setSaving(false);
    }
  }

  const compact = variant === "sidebar";

  return (
    <div
      className={cn(
        compact
          ? "rounded-lg border border-border/60 bg-sidebar-accent/20 p-2"
          : "border-b border-border/60 px-3 py-2 sm:px-4",
      )}
    >
      <div className={cn("flex gap-2", compact ? "flex-col" : "flex-wrap items-center")}>
        <span className="text-xs font-medium uppercase text-muted-foreground sm:shrink-0">Model</span>
        <RoleModelSelect
          value={selectedModel}
          blockedPatterns={blockedPatterns}
          localModelsByProvider={localModelsByProvider}
          compact={compact}
          onChange={(next) => {
            const nextChoice =
              next && isKnownModelChoice(next, localModelsByProvider)
                ? next
                : choiceFromOverride(next);
            setChoice(nextChoice);
            setCustomModel(nextChoice === "custom" ? next : "");
            setStatus("idle");
          }}
        />
        <div className={cn("flex flex-wrap items-center gap-2", compact && "grid grid-cols-2")}>
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            className={compact ? "w-full" : "w-10"}
            onClick={() => void loadLocalModels()}
            disabled={loadingModels}
            title="Refresh models"
          >
            <RefreshCw className={loadingModels ? "animate-spin" : ""} />
          </Button>
          <Button
            type="button"
            variant={showRoles ? "secondary" : "outline"}
            size="sm"
            className={cn("w-auto", compact && "w-full px-2")}
            onClick={() => setShowRoles((open) => !open)}
          >
            <SlidersHorizontal />
            Agents
          </Button>
          <Button
            type="button"
            variant={showPolicy ? "secondary" : "outline"}
            size="sm"
            className={cn("w-auto", compact && "w-full px-2")}
            onClick={() => setShowPolicy((open) => !open)}
          >
            <Shield />
            Policy
          </Button>
          <Button
            type="button"
            size="sm"
            className={cn("w-auto", compact && "w-full px-2")}
            onClick={() => void save()}
            disabled={saving || !dirty || (choice === "custom" && !customModel.trim())}
          >
            {saving ? <RefreshCw className="animate-spin" /> : <Save />}
            Save
          </Button>
        </div>
        {status === "saved" && <span className="text-xs text-emerald-400">Saved</span>}
        {status === "error" && <span className="text-xs text-destructive">Error</span>}
      </div>

      {showPolicy && (
        <div className={cn("mt-3 space-y-3 overflow-auto rounded-md border border-border/60 bg-background/40 p-2", compact ? "max-h-72" : "max-h-96")}>
          <div className={cn("flex flex-col gap-2", !compact && "sm:flex-row sm:items-center")}>
            <Input
              className={compact ? "h-8 min-w-0" : "h-8 min-w-0 sm:w-80"}
              placeholder="Modell-ID oder Muster"
              value={policyDraft}
              onChange={(event) => setPolicyDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") addPattern();
              }}
            />
            <Button
              type="button"
              size="sm"
              className="w-auto"
              disabled={savingPolicy || !policyDraft.trim()}
              onClick={addPattern}
            >
              <Ban />
              Sperren
            </Button>
          </div>

          <div className="flex flex-wrap gap-2">
            {blockedPatterns.map((pattern) => (
              <button
                key={`blocked-${pattern}`}
                type="button"
                className="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-muted px-2 text-xs hover:bg-muted/80"
                disabled={savingPolicy}
                onClick={() => void savePolicy(blockedPatterns.filter((item) => item !== pattern))}
                title="Sperre entfernen"
              >
                {pattern}
                <X className="size-3" />
              </button>
            ))}
          </div>

          <div className="space-y-1">
            {selectableModels.map((model) => {
              const blocked = isBlockedModel(model.id, blockedPatterns);
              return (
                <div
                  key={model.id}
                  className={cn("flex flex-col gap-2 border-b border-border/40 py-2 last:border-b-0", !compact && "sm:flex-row sm:items-center")}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{model.label}</div>
                    <div className="truncate text-xs text-muted-foreground">{model.provider} · {model.id}</div>
                  </div>
                  <Button
                    type="button"
                    variant={blocked ? "destructive" : "outline"}
                    size="sm"
                    className="w-auto"
                    disabled={savingPolicy}
                    onClick={() => (blocked ? freeModel(model.id) : blockModel(model.id))}
                    title={blocked ? "Modell freigeben" : "Modell sperren"}
                  >
                    {blocked ? <Ban /> : <Check />}
                    {blocked ? "Gesperrt" : "Frei"}
                  </Button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {showRoles && (
        <div className={cn("mt-3 space-y-2 overflow-auto rounded-md border border-border/60 bg-background/40 p-2", compact ? "max-h-72" : "max-h-96")}>
          {AGENT_ROLES.map((role) => (
            <div
              key={role.value}
              className={cn("flex flex-col gap-2 border-b border-border/40 py-2 last:border-b-0", !compact && "sm:flex-row sm:items-center")}
            >
              <div className={compact ? "min-w-0" : "min-w-40"}>
                <div className="text-sm font-medium">{role.label}</div>
                <div className="text-xs text-muted-foreground">{role.hint}</div>
              </div>
              <RoleModelSelect
                value={roleOverrides[role.value] ?? ""}
                blockedPatterns={blockedPatterns}
                localModelsByProvider={localModelsByProvider}
                compact={compact}
                onChange={(next) => updateRole(role.value, next)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
