/**
 * useAgent — LangGraph SDK streaming hook for Ink.
 *
 * Uses stream_mode="values" (full state snapshots) and diffs the messages
 * array to detect new entries — the same approach as Python StreamingEngine.
 *
 * Also subscribes to stream_mode="custom" for sub-agent events emitted by
 * StreamingRunnable via get_stream_writer(). This enables real-time visibility
 * into sub-agent tool calls, bash execution, and AI reasoning.
 */

import { useState, useCallback, useRef } from "react";
import { Client } from "@langchain/langgraph-sdk";
import type { AgentEvent } from "../types.js";
import {
  type SubagentCustomEvent,
  STREAM_OPTIONS,
  extractText,
  stripResultTags,
} from "@decepticon/streaming";

interface LangChainMessage {
  type: string; // "human", "ai", "tool"
  name?: string; // tool name (on ToolMessage)
  content: string | Array<{ type: string; text?: string }>;
  tool_calls?: Array<{
    id: string;
    name: string;
    args: Record<string, unknown>;
  }>;
  tool_call_id?: string;
  status?: string; // "success" | "error" on tool messages
  response_metadata?: {
    token_usage?: {
      completion_tokens?: number;
      prompt_tokens?: number;
      total_tokens?: number;
    };
  };
}

interface UseAgentOptions {
  apiUrl?: string;
}

interface PendingTool {
  name: string;
  args: Record<string, unknown>;
}

export interface StreamStats {
  startTime: number;
  totalTokens: number;
  promptTokens: number;
  completionTokens: number;
}

interface UseAgentReturn {
  submit: (message: string) => void;
  /** Cancel the current streaming run. */
  cancel: () => void;
  events: AgentEvent[];
  isStreaming: boolean;
  pendingTool: PendingTool | null;
  streamStats: StreamStats | null;
  /** Currently active agent name (e.g. "decepticon", "recon"). */
  activeAgent: string | null;
  error: string | null;
  clearEvents: () => void;
  addSystemEvent: (content: string) => void;
}

const ASSISTANT_ID = "decepticon";

export function useAgent({
  apiUrl = process.env.DECEPTICON_API_URL || "http://localhost:2024",
}: UseAgentOptions = {}): UseAgentReturn {
  const clientRef = useRef(new Client({ apiUrl }));
  const threadIdRef = useRef<string | null>(null);
  const eventsRef = useRef<AgentEvent[]>([]);
  const lastCountRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingTool, setPendingTool] = useState<PendingTool | null>(null);
  const [streamStats, setStreamStats] = useState<StreamStats | null>(null);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const addEvent = useCallback(
    (partial: Omit<AgentEvent, "id" | "timestamp">) => {
      const newEvent: AgentEvent = {
        ...partial,
        id: `${Date.now()}-${Math.random()}`,
        timestamp: Date.now(),
      };
      eventsRef.current = [...eventsRef.current, newEvent];
      setEvents(eventsRef.current);
    },
    [],
  );

  const addSystemEvent = useCallback(
    (content: string) => {
      addEvent({ type: "system", content });
    },
    [addEvent],
  );

  const resetStreamState = useCallback(() => {
    setIsStreaming(false);
    setPendingTool(null);
    setStreamStats(null);
    setActiveAgent(null);
  }, []);

  const cancel = useCallback(() => {
    // Cancel running runs on the server FIRST (before aborting local stream)
    const threadId = threadIdRef.current;
    if (threadId) {
      clientRef.current.runs
        .cancelMany({ threadId, status: "running" })
        .catch(() => {});
    }

    // Then abort the local stream
    abortRef.current?.abort();
    abortRef.current = null;

    resetStreamState();
    addEvent({ type: "system", content: "Cancelled." });
  }, [addEvent, resetStreamState]);

  const clearEvents = useCallback(() => {
    eventsRef.current = [];
    setEvents([]);
    threadIdRef.current = null;
    lastCountRef.current = 0;
  }, []);

  const submit = useCallback(
    (message: string): void => {
      // Block submit while a stream is active to prevent race conditions
      // where a second run cancels the first, leaving dangling tool calls
      if (abortRef.current) return;

      addEvent({ type: "user", content: message });

      const runStream = async () => {
        const client = clientRef.current;
        setError(null);

        // Create thread if needed (retry for server startup race condition)
        if (!threadIdRef.current) {
          const maxRetries = 5;
          for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
              const thread = await client.threads.create();
              threadIdRef.current = thread.thread_id;
              break;
            } catch (err) {
              if (attempt === maxRetries) {
                const msg =
                  err instanceof Error ? err.message : "Failed to create thread";
                setError(`Connection failed: ${msg}`);
                return;
              }
              // Server may still be loading graphs — wait and retry
              await new Promise((r) => setTimeout(r, 2000));
            }
          }
        }

        const abortController = new AbortController();
        abortRef.current = abortController;

        setIsStreaming(true);
        setPendingTool(null);
        setActiveAgent("decepticon");
        setStreamStats({ startTime: Date.now(), totalTokens: 0, promptTokens: 0, completionTokens: 0 });

        // Track tool_call args and names by ID for matching with results
        const toolCallArgs = new Map<string, Record<string, unknown>>();
        const toolCallNames = new Map<string, string>();
        // Cumulative token counts
        let cumTotal = 0;
        let cumPrompt = 0;
        let cumCompletion = 0;

        // Handler for custom sub-agent events from StreamingRunnable
        const handleCustomEvent = (data: SubagentCustomEvent) => {
          switch (data.type) {
            case "subagent_start":
              setActiveAgent(data.agent);
              addEvent({
                type: "subagent_start",
                content: data.prompt ?? `Starting ${data.agent}`,
                subagent: data.agent,
              });
              break;

            case "subagent_tool_call":
              setPendingTool({
                name: data.tool ?? "",
                args: data.args ?? {},
              });
              break;

            case "subagent_tool_result": {
              setPendingTool(null);
              const status: "success" | "error" =
                data.status === "error" ? "error" : "success";

              if (data.tool === "bash") {
                addEvent({
                  type: "bash_result",
                  content: data.content ?? "",
                  toolName: "bash",
                  toolArgs: data.args ?? {},
                  status,
                  subagent: data.agent,
                });
              } else {
                addEvent({
                  type: "tool_result",
                  content: data.content ?? "",
                  toolName: data.tool ?? "",
                  toolArgs: data.args ?? {},
                  status,
                  subagent: data.agent,
                });
              }
              break;
            }

            case "subagent_message":
              addEvent({
                type: "ai_message",
                content: data.text ?? "",
                subagent: data.agent,
              });
              break;

            case "subagent_end":
              addEvent({
                type: "subagent_end",
                content: data.elapsed
                  ? `Completed (${Math.floor(data.elapsed / 1000)}s)`
                  : "Completed",
                subagent: data.agent,
                status: data.error ? "error" : "success",
              });
              setActiveAgent("decepticon");
              setPendingTool(null);
              break;
          }
        };

        try {
          const stream = client.runs.stream(
            threadIdRef.current!,
            ASSISTANT_ID,
            {
              input: {
                messages: [{ role: "user", content: message }],
              },
              ...STREAM_OPTIONS,
              onDisconnect: "cancel",
              signal: abortController.signal,
            },
          );

          for await (const event of stream) {
            if (abortController.signal.aborted) break;

            // Handle server-side errors (LLM connection failures, etc.)
            if (event.event === "error") {
              const errData = event.data as
                | { message?: string; error?: string }
                | string;
              const errMsg =
                typeof errData === "string"
                  ? errData
                  : errData?.message ?? errData?.error ?? "Server error";
              setError(errMsg);
              continue;
            }

            // Handle custom events (sub-agent streaming from StreamingRunnable)
            if (event.event === "custom") {
              const data = event.data as SubagentCustomEvent;
              if (data && typeof data === "object" && "type" in data) {
                handleCustomEvent(data);
              }
              continue;
            }

            if (event.event !== "values") continue;

            const data = event.data as {
              messages?: LangChainMessage[];
            };
            const messages = data.messages ?? [];
            const newMessages = messages.slice(lastCountRef.current);
            lastCountRef.current = messages.length;

            for (const msg of newMessages) {
              if (msg.type === "human") continue;

              if (msg.type === "ai") {
                // Extract token usage
                const usage = msg.response_metadata?.token_usage;
                if (usage) {
                  cumTotal += usage.total_tokens ?? 0;
                  cumPrompt += usage.prompt_tokens ?? 0;
                  cumCompletion += usage.completion_tokens ?? 0;
                  setStreamStats((prev) =>
                    prev
                      ? { ...prev, totalTokens: cumTotal, promptTokens: cumPrompt, completionTokens: cumCompletion }
                      : prev,
                  );
                }

                // Emit AI text content (even when tool_calls are present)
                const text = stripResultTags(extractText(msg.content));
                if (text) {
                  addEvent({ type: "ai_message", content: text });
                }

                if (msg.tool_calls?.length) {
                  for (const tc of msg.tool_calls) {
                    toolCallArgs.set(tc.id, tc.args);
                    toolCallNames.set(tc.id, tc.name);
                    if (tc.name === "task") {
                      // Emit delegate event for sub-agent dispatch
                      addEvent({
                        type: "delegate",
                        content: (tc.args.description as string) ?? "",
                        subagent: (tc.args.subagent_type as string) ?? "",
                      });
                    } else {
                      setPendingTool({ name: tc.name, args: tc.args });
                    }
                  }
                } else {
                  setPendingTool(null);
                }
              } else if (msg.type === "tool") {
                const content =
                  typeof msg.content === "string"
                    ? msg.content
                    : extractText(msg.content);
                const tcId = msg.tool_call_id ?? "";
                const args = toolCallArgs.get(tcId) ?? {};
                const toolName = msg.name ?? toolCallNames.get(tcId) ?? "";
                const status: "success" | "error" =
                  msg.status === "error" ? "error" : "success";

                setPendingTool(null);

                // Suppress task() tool results — already shown via sub-agent custom events
                if (toolName === "task") continue;

                if (toolName === "bash") {
                  addEvent({
                    type: "bash_result",
                    content,
                    toolName: "bash",
                    toolArgs: args,
                    status,
                  });
                } else {
                  addEvent({
                    type: "tool_result",
                    content,
                    toolName,
                    toolArgs: args,
                    status,
                  });
                }
              }
            }
          }
        } catch (err) {
          // Ignore abort errors — triggered by cancel()
          if (abortController.signal.aborted) return;
          const msg =
            err instanceof Error ? err.message : "Unknown streaming error";
          setError(msg);
        }

        abortRef.current = null;
        resetStreamState();
      };

      runStream().catch((err) => {
        if (abortRef.current?.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Unknown error");
        abortRef.current = null;
        resetStreamState();
      });
    },
    [addEvent],
  );

  return {
    submit,
    cancel,
    events,
    isStreaming,
    pendingTool,
    streamStats,
    activeAgent,
    error,
    clearEvents,
    addSystemEvent,
  };
}
