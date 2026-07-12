/**
 * Per-process model override store.
 *
 * The /model slash command writes here; useAgent reads here when
 * building the LangGraph stream config so each submit() carries the
 * current override in config.configurable.model_override. The agent's
 * ModelOverrideMiddleware consumes that field and rebinds the LLM for
 * the call without restarting anything.
 *
 * Empty string == no override.
 */

let _override = (process.env.DECEPTICON_MODEL_OVERRIDE ?? "").trim();
let _roleOverrides: Record<string, string> = {};

try {
  const raw = (process.env.DECEPTICON_MODEL_OVERRIDES ?? "").trim();
  const parsed = raw ? JSON.parse(raw) : {};
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    _roleOverrides = Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>)
        .filter(([, model]) => typeof model === "string" && model.trim())
        .map(([role, model]) => [role, (model as string).trim()]),
    );
  }
} catch {
  _roleOverrides = {};
}

export function setModelOverride(id: string): void {
  _override = id.trim();
}

export function getModelOverride(): string {
  return _override;
}

export function getModelOverrides(): Record<string, string> {
  return { ..._roleOverrides };
}
