/**
 * Stream configuration constants matching the LangGraph Chat UI reference.
 *
 * Used in both submit() options (Web useStream) and client.runs.stream() (CLI).
 *
 * The streamMode values are typed as a mutable tuple to satisfy the SDK's
 * StreamMode[] type without requiring the SDK as a dependency.
 */
export const STREAM_OPTIONS = {
  streamMode: ["values", "messages", "updates", "custom"] as ("values" | "messages" | "updates" | "custom")[],
  streamSubgraphs: true as const,
  streamResumable: true as const,
};
