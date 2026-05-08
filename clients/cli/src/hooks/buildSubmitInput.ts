interface BuildSubmitInputOpts {
  message: string;
  handoffSlug: string | null;
  envSlug: string | undefined;
  envWorkspacePath: string | undefined;
  modelOverride: string | null;
}

interface StreamConfig {
  configurable?: Record<string, unknown>;
}

export interface SubmitInput {
  input: Record<string, unknown>;
  streamConfig: StreamConfig;
}

/**
 * Build the run input and stream config for a LangGraph submit.
 *
 * Slug precedence: handoffSlug (from Soundwave's engagement_ready event)
 * takes priority over envSlug (DECEPTICON_ENGAGEMENT env var), so a
 * freshly-authored engagement name is not overwritten by a stale launcher value.
 */
export function buildSubmitInput({
  message,
  handoffSlug,
  envSlug,
  envWorkspacePath,
  modelOverride,
}: BuildSubmitInputOpts): SubmitInput {
  const input: Record<string, unknown> = {
    messages: [{ role: "user", content: message }],
  };

  const slug = handoffSlug ?? envSlug;
  if (slug) {
    input.engagement_name = slug;
    input.workspace_path = envWorkspacePath ?? "/workspace";
  }

  const streamConfig: StreamConfig = {};
  if (modelOverride) {
    input.model_override = modelOverride;
    streamConfig.configurable = { model_override: modelOverride };
  }

  return { input, streamConfig };
}
