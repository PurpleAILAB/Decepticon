/**
 * Pure utility functions for stream event processing.
 *
 * Zero dependencies — used by both Web and CLI.
 */

/**
 * Extract text from LangChain message content.
 * Handles both string content and content-block arrays (Anthropic format).
 */
export function extractText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((block) =>
        typeof block === "string"
          ? block
          : (block as { text?: string }).text ?? ""
      )
      .join("")
      .trim();
  }
  return "";
}

/**
 * Strip `<result>` XML tags from AI message content.
 * These tags are used internally by the agent framework and should not be shown to users.
 */
export function stripResultTags(text: string): string {
  return text.replace(/<\/?result>/g, "").trim();
}
