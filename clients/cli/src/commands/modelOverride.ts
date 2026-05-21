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

let _override = "";

export function setModelOverride(id: string): void {
  _override = id.trim();
}

export function getModelOverride(): string {
  return _override;
}
