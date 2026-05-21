/**
 * Per-process orchestrator override store.
 *
 * The /agent slash command writes here; useAgent reads here on every
 * submit() / resume() so user-driven switches take effect on the next
 * message. When set, the override beats both the default
 * INITIAL_ASSISTANT_ID and the in-flight soundwave→decepticon handoff
 * — the user explicitly picked this orchestrator, so honour it.
 *
 * Empty string == no override (default useAgent behaviour resumes).
 */

let _override = "";

export function setAssistantOverride(id: string): void {
  _override = id.trim();
}

export function getAssistantOverride(): string {
  return _override;
}
