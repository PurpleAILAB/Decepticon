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
 * Supports three run lifecycle operations:
 * - interrupt(): Pause at checkpoint (state preserved)
 * - resume(): Continue from pause point with optional feedback
 * - Message queuing: type during streaming, auto-submit on completion
 *
 * Proxied through Next.js rewrite: /lgs → LANGGRAPH_API_URL
 */

import { useMemo, useCallback, useState, useRef, useEffect } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import type { ChatMessage } from "@/lib/chat/types";
import type { Message } from "@langchain/langgraph-sdk";
import {
  type SubagentCustomEvent,
  STREAM_OPTIONS,
  extractText,
  stripResultTags,
} from "@decepticon/streaming";

/** Run lifecycle state. */
export type WebRunState = "idle" | "streaming" | "paused";

interface UseChatOptions {
  engagementId: string;
  assistantId?: string;
}

interface UseChatReturn {
  /** All messages (user + assistant + tool + system) for rendering. */
  messages: ChatMessage[];
  /** True while the agent is streaming. */
  isStreaming: boolean;
  /** Current run lifecycle state. */
  runState: WebRunState;
  /** Error from the stream, if any. */
  error: string | null;
  /** Send a user message (queues if streaming). */
  sendMessage: (content: string) => void;
  /** Pause the current run (preserves checkpoint). */
  interrupt: () => void;
  /** Hard cancel the current run (destroys state). */
  stop: () => void;
  /** Resume a paused run with optional feedback. */
  resume: (value?: string) => void;
  /** Queued message to auto-submit on completion. */
  queuedMessage: string | null;
  /** Enqueue a message for auto-submit after stream completes. */
  enqueue: (message: string) => void;
  /** Clear the queued message. */
  clearQueuedMessage: () => void;
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

/** Load persisted thread ID for an engagement from localStorage. */
function loadEngagementThread(engagementId: string): string | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const stored = localStorage.getItem(`decepticon:thread:${engagementId}`);
    return stored ?? undefined;
  } catch {
    return undefined;
  }
}

/** Save thread ID for an engagement to localStorage. */
function saveEngagementThread(engagementId: string, threadId: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(`decepticon:thread:${engagementId}`, threadId);
  } catch {
    // Non-critical
  }
}

export function useChat({ engagementId, assistantId = "soundwave" }: UseChatOptions): UseChatReturn {
  // Track custom events (sub-agent activity) in state so changes trigger re-renders
  const [customEvents, setCustomEvents] = useState<ChatMessage[]>([]);
  // Only track "paused" explicitly — "streaming" and "idle" are derived from SDK isLoading
  const [isPaused, setIsPaused] = useState(false);
  const [queuedMessage, setQueuedMessage] = useState<string | null>(null);
  const queuedMessageRef = useRef<string | null>(null);
  const sendRef = useRef<((content: string) => void) | null>(null);

  // Load persisted thread ID for this engagement
  const persistedThreadId = loadEngagementThread(engagementId);

  // Connect directly to LangGraph server — NOT through Next.js rewrite proxy.
  // Next.js rewrite buffers SSE responses, breaking real-time streaming.
  // LANGGRAPH_API_URL is exposed via NEXT_PUBLIC_ for browser access.
  const apiUrl = typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_LANGGRAPH_API_URL ?? "http://localhost:2024")
    : (process.env.LANGGRAPH_API_URL ?? "http://localhost:2024");

  const stream = useStream({
    apiUrl,
    assistantId,
    threadId: persistedThreadId, // Reuse persisted thread for conversation continuity
    onThreadId: (threadId: string) => saveEngagementThread(engagementId, threadId),
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

  // Derive runState from SDK isLoading + isPaused (no setState in effects)
  const runState: WebRunState = stream.isLoading ? "streaming" : isPaused ? "paused" : "idle";

  // Auto-submit queued message when stream completes (not when paused).
  // Uses setTimeout to avoid calling setState synchronously in an effect.
  const prevLoading = useRef(stream.isLoading);
  useEffect(() => {
    if (prevLoading.current && !stream.isLoading && !isPaused) {
      const pending = queuedMessageRef.current;
      if (pending) {
        queuedMessageRef.current = null;
        setTimeout(() => {
          setQueuedMessage(null);
          sendRef.current?.(pending);
        }, 0);
      }
    }
    prevLoading.current = stream.isLoading;
  }, [stream.isLoading, isPaused]);

  // Merge SDK messages with custom events into a unified ChatMessage[]
  const messages = useMemo(() => {
    const sdkMessages = sdkMessagesToChatMessages(stream.messages ?? []);
    if (customEvents.length === 0) return sdkMessages;

    // Interleave: SDK messages first, then custom events appended
    // Custom events have timestamps so they sort correctly
    return [...sdkMessages, ...customEvents].sort((a, b) => a.timestamp - b.timestamp);
  }, [stream.messages, customEvents]);

  const sendMessageDirect = useCallback(
    (content: string) => {
      setCustomEvents([]);
      setIsPaused(false);
      stream.submit(
        { messages: [{ type: "human" as const, content, id: `user-${Date.now()}` }] },
        {
          ...STREAM_OPTIONS,
          multitaskStrategy: "interrupt",
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

  // Keep ref updated for deferred auto-submit
  useEffect(() => {
    sendRef.current = sendMessageDirect;
  }, [sendMessageDirect]);

  const sendMessage = useCallback(
    (content: string) => {
      // If streaming, queue instead of interrupting
      if (stream.isLoading) {
        queuedMessageRef.current = content;
        setQueuedMessage(content);
        return;
      }
      // If paused, starting a new message implicitly cancels the paused run
      if (isPaused) {
        setIsPaused(false);
      }
      sendMessageDirect(content);
    },
    [stream.isLoading, sendMessageDirect, isPaused],
  );

  const interrupt = useCallback(() => {
    stream.stop();
    setIsPaused(true);
  }, [stream]);

  const stopFn = () => {
    stream.stop();
    queuedMessageRef.current = null;
    setQueuedMessage(null);
    setIsPaused(false);
  };

  const resume = (value?: string) => {
    if (!isPaused) return;
    setCustomEvents([]);
    setIsPaused(false);
    stream.submit(
      { command: { resume: value ?? true } },
      {
        ...STREAM_OPTIONS,
        multitaskStrategy: "interrupt",
      },
    );
  };

  const enqueue = useCallback((message: string) => {
    queuedMessageRef.current = message;
    setQueuedMessage(message);
  }, []);

  const clearQueuedMessage = useCallback(() => {
    queuedMessageRef.current = null;
    setQueuedMessage(null);
  }, []);

  const error = stream.error
    ? stream.error instanceof Error
      ? stream.error.message
      : String(stream.error)
    : null;

  return {
    messages,
    isStreaming: stream.isLoading,
    runState,
    error,
    sendMessage,
    interrupt,
    stop: stopFn,
    resume,
    queuedMessage,
    enqueue,
    clearQueuedMessage,
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
