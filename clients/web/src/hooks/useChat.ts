"use client";

/**
 * useChat — LangGraph SDK `useStream` hook for the web dashboard.
 *
 * Uses `useStream` from `@langchain/langgraph-sdk/react` which provides:
 * - Automatic message deduplication and chunk concatenation
 * - Thread lifecycle management (create, switch, history)
 * - Optimistic updates via `submit({ optimisticValues })`
 * - `stop()` for cancellation, `joinStream()` for reconnection
 * - Built-in error handling and `isLoading` state
 * - Sub-agent tracking via custom events from StreamingRunnable
 *
 * Proxied through Next.js rewrite: /lgs → LANGGRAPH_API_URL
 */

import { useMemo, useCallback, useState } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import type { ChatMessage } from "@/lib/chat/types";
import type { Message } from "@langchain/langgraph-sdk";
import {
  type SubagentCustomEvent,
  STREAM_OPTIONS,
  extractText,
  stripResultTags,
} from "@decepticon/streaming";

interface UseChatOptions {
  engagementId: string;
  assistantId?: string;
}

interface UseChatReturn {
  /** All messages (user + assistant + tool + system) for rendering. */
  messages: ChatMessage[];
  /** True while the agent is streaming. */
  isStreaming: boolean;
  /** Error from the stream, if any. */
  error: string | null;
  /** Send a user message. */
  sendMessage: (content: string) => void;
  /** Stop the current stream. */
  stop: () => void;
  /** The raw SDK stream for advanced usage. */
  stream: ReturnType<typeof useStream>;
}

// ── Helpers ─────────────────────────────────────────────────────

/** Convert SDK Message[] to our ChatMessage[] for rendering. */
function sdkMessagesToChatMessages(messages: Message[]): ChatMessage[] {
  const result: ChatMessage[] = [];

  for (const msg of messages) {
    if (msg.type === "human") {
      result.push({
        id: msg.id ?? `user-${result.length}`,
        role: "user",
        content: extractText(msg.content),
        timestamp: Date.now(),
      });
    } else if (msg.type === "ai") {
      const text = stripResultTags(extractText(msg.content));
      if (text) {
        result.push({
          id: msg.id ?? `assistant-${result.length}`,
          role: "assistant",
          content: text,
          timestamp: Date.now(),
        });
      }
      // Tool calls from the AI message
      const toolCalls = (msg as { tool_calls?: Array<{ id: string; name: string; args: Record<string, unknown> }> }).tool_calls;
      if (toolCalls?.length) {
        for (const tc of toolCalls) {
          if (tc.name === "task") continue; // Shown via custom events
          result.push({
            id: tc.id ?? `tool-${result.length}`,
            role: "tool",
            content: "",
            toolName: tc.name,
            toolArgs: tc.args,
            timestamp: Date.now(),
          });
        }
      }
    } else if (msg.type === "tool") {
      const toolMsg = msg as { name?: string; tool_call_id?: string; content: unknown };
      const toolName = toolMsg.name ?? "";
      if (toolName === "task") continue; // Shown via custom events
      result.push({
        id: msg.id ?? `result-${result.length}`,
        role: "tool",
        content: extractText(msg.content),
        toolName,
        toolArgs: {},
        timestamp: Date.now(),
      });
    }
  }

  return result;
}

// ── Hook ────────────────────────────────────────────────────────

export function useChat({ engagementId: _engagementId, assistantId = "soundwave" }: UseChatOptions): UseChatReturn {
  // Track custom events (sub-agent activity) in state so changes trigger re-renders
  const [customEvents, setCustomEvents] = useState<ChatMessage[]>([]);

  // Connect directly to LangGraph server — NOT through Next.js rewrite proxy.
  // Next.js rewrite buffers SSE responses, breaking real-time streaming.
  // LANGGRAPH_API_URL is exposed via NEXT_PUBLIC_ for browser access.
  const apiUrl = typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_LANGGRAPH_API_URL ?? "http://localhost:2024")
    : (process.env.LANGGRAPH_API_URL ?? "http://localhost:2024");

  const stream = useStream({
    apiUrl,
    assistantId,
    threadId: undefined, // Let SDK auto-create UUID threads; engagementId reserved for future thread mapping
    // Callbacks
    onCustomEvent: (data: unknown) => {
      const event = data as SubagentCustomEvent;
      if (!event || typeof event !== "object" || !("type" in event)) return;
      const chatMsg = customEventToChatMessage(event);
      if (chatMsg) {
        setCustomEvents((prev) => [...prev, chatMsg]);
      }
    },
    onError: (err: unknown) => {
      console.error("[useChat] Stream error:", err);
    },
  });

  // Merge SDK messages with custom events into a unified ChatMessage[]
  const messages = useMemo(() => {
    const sdkMessages = sdkMessagesToChatMessages(stream.messages ?? []);
    if (customEvents.length === 0) return sdkMessages;

    // Interleave: SDK messages first, then custom events appended
    // Custom events have timestamps so they sort correctly
    return [...sdkMessages, ...customEvents].sort((a, b) => a.timestamp - b.timestamp);
  }, [stream.messages, customEvents]);

  const sendMessage = useCallback(
    (content: string) => {
      // Reset custom events for new turn
      setCustomEvents([]);
      stream.submit(
        { messages: [{ type: "human" as const, content, id: `user-${Date.now()}` }] },
        {
          // Stream options go in submit(), not useStream()
          ...STREAM_OPTIONS,
          optimisticValues: (prev) => {
            const existing = (Array.isArray(prev.messages) ? prev.messages : []) as Message[];
            return {
              ...prev,
              messages: [
                ...existing,
                { type: "human" as const, content, id: `user-${Date.now()}` },
              ],
            };
          },
        },
      );
    },
    [stream],
  );

  const stop = useCallback(() => {
    stream.stop();
  }, [stream]);

  const error = stream.error
    ? stream.error instanceof Error
      ? stream.error.message
      : String(stream.error)
    : null;

  return {
    messages,
    isStreaming: stream.isLoading,
    error,
    sendMessage,
    stop,
    stream,
  };
}

// ── Custom event → ChatMessage ──────────────────────────────────

function customEventToChatMessage(event: SubagentCustomEvent): ChatMessage | null {
  const ts = Date.now();
  const id = `${event.type}-${ts}-${Math.random()}`;

  switch (event.type) {
    case "subagent_start":
      return {
        id, role: "system", timestamp: ts,
        content: `Agent **${event.agent}** started`,
        agent: event.agent,
      };

    case "subagent_tool_call":
      return {
        id, role: "tool", timestamp: ts,
        content: "",
        toolName: event.tool ?? "",
        toolArgs: event.args ?? {},
        agent: event.agent,
      };

    case "subagent_tool_result":
      return {
        id, role: "tool", timestamp: ts,
        content: event.content ?? "",
        toolName: event.tool ?? "",
        toolArgs: event.args ?? {},
        agent: event.agent,
      };

    case "subagent_message":
      return {
        id, role: "assistant", timestamp: ts,
        content: event.text ?? "",
        agent: event.agent,
      };

    case "subagent_end":
      return {
        id, role: "system", timestamp: ts,
        content: `Agent **${event.agent}** completed${event.elapsed ? ` in ${(event.elapsed / 1000).toFixed(1)}s` : ""}`,
        agent: event.agent,
      };

    default:
      return null;
  }
}
