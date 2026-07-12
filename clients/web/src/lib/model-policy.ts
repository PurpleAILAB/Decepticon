import * as fs from "fs/promises";
import * as path from "path";

export const DEFAULT_BLOCKED_MODEL_PATTERNS = ["wormgpt", "uncensored", "abliterate"] as const;

export type ModelPolicy = {
  blockedPatterns: string[];
};

const MAX_PATTERN_LENGTH = 200;

function policyPath(): string {
  return (
    process.env.MODEL_POLICY_PATH ??
    path.join(process.env.WORKSPACE_PATH ?? "/workspace", ".decepticon", "model-policy.json")
  );
}

function normalizePattern(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > MAX_PATTERN_LENGTH) return null;
  if (/[\x00-\x1f\x7f]/.test(trimmed)) return null;
  return trimmed;
}

function uniquePatterns(values: unknown[]): string[] {
  const seen = new Set<string>();
  const patterns: string[] = [];
  for (const value of values) {
    const pattern = normalizePattern(value);
    if (!pattern) continue;
    const key = pattern.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    patterns.push(pattern);
  }
  return patterns;
}

export function modelIdMatchesPattern(modelId: string, pattern: string): boolean {
  return modelId.toLowerCase().includes(pattern.toLowerCase());
}

export function isBlockedModelId(modelId: string, patterns: string[]): boolean {
  return patterns.some((pattern) => modelIdMatchesPattern(modelId, pattern));
}

export async function readModelPolicy(): Promise<ModelPolicy> {
  try {
    const raw = await fs.readFile(policyPath(), "utf8");
    const parsed = JSON.parse(raw) as { blockedPatterns?: unknown };
    const values = Array.isArray(parsed.blockedPatterns) ? parsed.blockedPatterns : [];
    return {
      blockedPatterns: uniquePatterns(values),
    };
  } catch {
    return {
      blockedPatterns: [...DEFAULT_BLOCKED_MODEL_PATTERNS],
    };
  }
}

export async function writeModelPolicy(blockedPatterns: unknown[]): Promise<ModelPolicy> {
  const clean = uniquePatterns(blockedPatterns);
  const target = policyPath();
  await fs.mkdir(path.dirname(target), { recursive: true });
  await fs.writeFile(
    target,
    `${JSON.stringify({ blockedPatterns: clean }, null, 2)}\n`,
    "utf8",
  );
  return {
    blockedPatterns: clean,
  };
}

export async function assertModelAllowed(modelId: string): Promise<void> {
  const trimmed = modelId.trim();
  if (!trimmed) return;
  const policy = await readModelPolicy();
  if (isBlockedModelId(trimmed, policy.blockedPatterns)) {
    throw new Error("Blocked model id is not allowed for this application");
  }
}
