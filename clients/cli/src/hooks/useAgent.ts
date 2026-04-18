/**
 * useAgent — LangGraph SDK streaming hook for Ink.
 *
 * Uses stream_mode="values" (full state snapshots) and diffs the messages
 * array to detect new entries — the same approach as Python StreamingEngine.
 *
 * Also subscribes to stream_mode="custom" for sub-agent events emitted by
 * StreamingRunnable via get_stream_writer(). This enables real-time visibility
 * into sub-agent tool calls, bash execution, and AI reasoning.
 *
 * Supports three run lifecycle operations:
 * - interrupt(): Pause at checkpoint (Ctrl+C single press) — state preserved
 * - cancel(): Hard abort (Ctrl+C double press, or from paused) — state lost
 * - resume(): Continue from pause point with optional feedback
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

/** Agent run lifecycle state. */
export type RunState = "idle" | "connecting" | "streaming" | "paused";

interface UseAgentReturn {
  submit: (message: string) => void;
  /** Pause the current run at checkpoint (Ctrl+C single). State preserved. */
  interrupt: () => void;
  /** Hard cancel the current run (Ctrl+C double, or from paused). State lost. */
  cancel: () => void;
  /** Resume a paused run with optional operator feedback. */
  resume: (value?: string) => void;
  /** Enqueue a message to auto-submit when current run completes. */
  enqueue: (message: string) => void;
  /** Clear the queued message. */
  clearQueuedMessage: () => void;
  events: AgentEvent[];
  /** Current run lifecycle state. */
  runState: RunState;
  /** Derived from runState for backward compatibility. */
  isStreaming: boolean;
  pendingTool: PendingTool | null;
  streamStats: StreamStats | null;
  /** Currently active agent name (e.g. "decepticon", "recon"). */
  activeAgent: string | null;
  /** Queued message to auto-submit on completion. */
  queuedMessage: string | null;
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
  const runIdRef = useRef<string | null>(null);
  const queuedMessageRef = useRef<string | null>(null);

  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [runState, setRunState] = useState<RunState>("idle");
  const [pendingTool, setPendingTool] = useState<PendingTool | null>(null);
  const [streamStats, setStreamStats] = useState<StreamStats | null>(null);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [queuedMessage, setQueuedMessage] = useState<string | null>(null);

  // Ref for runState to avoid stale closures in async callbacks
  const runStateRef = useRef<RunState>(runState);
  runStateRef.current = runState;

  // Derived for backward compatibility
  const isStreaming = runState === "streaming" || runState === "connecting";

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
    setRunState("idle");
    setPendingTool(null);
    setStreamStats(null);
    setActiveAgent(null);
  }, []);

  // ── Enqueue / clear queue ───────────────────────────────────────

  const enqueue = useCallback(
    (message: string) => {
      queuedMessageRef.current = message;
      setQueuedMessage(message);
      addEvent({ type: "system", content: `Queued: "${message}"` });
    },
    [addEvent],
  );

  const clearQueuedMessage = useCallback(() => {
    queuedMessageRef.current = null;
    setQueuedMessage(null);
  }, []);

  // ── Stream event processing (shared by submit and resume) ──────

  const processStream = useCallback(
    async (
      stream: AsyncIterable<{ event: string; data: unknown }>,
      abortController: AbortController,
    ) => {
      // Capture run_id from the first metadata event for interrupt/cancel
      // LangGraph SDK emits: { event: "metadata", data: { run_id, thread_id } }
      const toolCallArgs = new Map<string, Record<string, unknown>>();
      const toolCallNames = new Map<string, string>();
      let cumTotal = 0;
      let cumPrompt = 0;
      let cumCompletion = 0;

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

      for await (const event of stream) {
        if (abortController.signal.aborted) break;

        // Capture run_id from metadata event for precise interrupt/cancel
        if (event.event === "metadata") {
          const meta = event.data as { run_id?: string };
          if (meta.run_id) {
            runIdRef.current = meta.run_id;
          }
          continue;
        }

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
    },
    [addEvent],
  );

  // ── Handle stream completion (shared by submit and resume) ─────

  const handleStreamComplete = useCallback(
    (abortController: AbortController) => {
      if (!abortController.signal.aborted) {
        abortRef.current = null;
        runIdRef.current = null;
        resetStreamState();

        // Auto-submit queued message
        const pending = queuedMessageRef.current;
        if (pending) {
          queuedMessageRef.current = null;
          setQueuedMessage(null);
          // Defer to next tick so React state settles
          setTimeout(() => submitRef.current(pending), 0);
        }
      }
    },
    [resetStreamState],
  );

  // ── Interrupt (pause at checkpoint) ────────────────────────────

  const interrupt = useCallback(() => {
    // Abort local stream first (stops event processing immediately)
    abortRef.current?.abort();
    abortRef.current = null;

    // Pause on server — preserves checkpoint state (don't await to keep responsive)
    const threadId = threadIdRef.current;
    const runId = runIdRef.current;
    if (threadId && runId) {
      clientRef.current.runs
        .cancel(threadId, runId, true, "interrupt")
        .catch(() => {
          addEvent({ type: "system", content: "Warning: server pause failed." });
        });
    }

    setPendingTool(null);
    setStreamStats(null);
    setActiveAgent(null);
    setRunState("paused");
    runIdRef.current = null;
    addEvent({ type: "system", content: "Paused. Type /resume to continue, or send a new message." });
  }, [addEvent]);

  // ── Cancel (hard abort, no resume) ─────────────────────────────

  const cancel = useCallback(() => {
    // Abort local stream
    abortRef.current?.abort();
    abortRef.current = null;

    // Hard cancel on server — destroys run state
    const threadId = threadIdRef.current;
    const runId = runIdRef.current;
    if (threadId && runId) {
      clientRef.current.runs
        .cancel(threadId, runId, false, "rollback")
        .catch(() => {
          addEvent({ type: "system", content: "Warning: server cancel failed." });
        });
    }

    runIdRef.current = null;
    // Clear queued message on hard cancel
    queuedMessageRef.current = null;
    setQueuedMessage(null);
    resetStreamState();
    addEvent({ type: "system", content: "Cancelled." });
  }, [addEvent, resetStreamState]);

  // ── Clear ──────────────────────────────────────────────────────

  const clearEvents = useCallback(() => {
    eventsRef.current = [];
    setEvents([]);
    threadIdRef.current = null;
    lastCountRef.current = 0;
    runIdRef.current = null;
    queuedMessageRef.current = null;
    setQueuedMessage(null);
    setRunState("idle");
  }, []);

  // ── Submit (only when idle or paused) ──────────────────────────

  const submit = useCallback(
    (message: string): void => {
      // If streaming/connecting, callers should use enqueue() instead
      if (abortRef.current) return;

      // If paused, cancel the paused run before starting fresh
      if (runStateRef.current === "paused") {
        const threadId = threadIdRef.current;
        const runId = runIdRef.current;
        if (threadId && runId) {
          clientRef.current.runs
            .cancel(threadId, runId, false, "rollback")
            .catch(() => {});
        }
        runIdRef.current = null;
      }

      setRunState("connecting");
      addEvent({ type: "user", content: message });

      const abortController = new AbortController();
      abortRef.current = abortController;

      const runStream = async () => {
        const client = clientRef.current;
        setError(null);

        // Create thread if needed (retry for server startup race condition)
        if (!threadIdRef.current) {
          const maxRetries = 5;
          for (let attempt = 1; attempt <= maxRetries; attempt++) {
            if (abortController.signal.aborted) return;
            try {
              const thread = await client.threads.create();
              threadIdRef.current = thread.thread_id;
              break;
            } catch (err) {
              if (attempt === maxRetries) {
                const msg =
                  err instanceof Error ? err.message : "Failed to create thread";
                setError(`Connection failed: ${msg}`);
                // Clear queued message to prevent infinite retry loop
                queuedMessageRef.current = null;
                setQueuedMessage(null);
                return;
              }
              // Server may still be loading graphs — wait and retry
              await new Promise((r) => setTimeout(r, 2000));
            }
          }
        }

        if (abortController.signal.aborted) return;

        setRunState("streaming");
        setPendingTool(null);
        setActiveAgent("decepticon");
        setStreamStats({ startTime: Date.now(), totalTokens: 0, promptTokens: 0, completionTokens: 0 });

        try {
          const stream = client.runs.stream(
            threadIdRef.current!,
            ASSISTANT_ID,
            {
              input: {
                messages: [{ role: "user", content: message }],
              },
              ...STREAM_OPTIONS,
              onDisconnect: "continue",
              signal: abortController.signal,
            },
          );

          await processStream(stream, abortController);
        } catch (err) {
          // Ignore abort errors — triggered by interrupt() or cancel()
          if (abortController.signal.aborted) return;
          const msg =
            err instanceof Error ? err.message : "Unknown streaming error";
          setError(msg);
        }

        handleStreamComplete(abortController);
      };

      runStream().catch((err) => {
        if (abortController.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Unknown error");
        abortRef.current = null;
        runIdRef.current = null;
        resetStreamState();
      });
    },
    [addEvent, processStream, handleStreamComplete, resetStreamState],
  );

  // Ref to submit for use in deferred auto-submit (avoids stale closure)
  const submitRef = useRef(submit);
  submitRef.current = submit;

  // ── Resume (continue from pause point) ─────────────────────────

  const resume = useCallback(
    (value?: string): void => {
      if (runStateRef.current !== "paused") {
        addEvent({ type: "system", content: "Nothing to resume." });
        return;
      }

      if (!threadIdRef.current) {
        addEvent({ type: "system", content: "No thread to resume." });
        setRunState("idle");
        return;
      }

      if (value) {
        addEvent({ type: "user", content: value });
      }
      addEvent({ type: "system", content: "Resuming..." });

      const abortController = new AbortController();
      abortRef.current = abortController;

      const runResume = async () => {
        const client = clientRef.current;
        setError(null);

        // Sync lastCountRef with server state before resuming
        try {
          const state = await client.threads.getState(threadIdRef.current!);
          const msgs = (state.values as { messages?: unknown[] })?.messages;
          if (msgs) lastCountRef.current = msgs.length;
        } catch {
          // Proceed with current count — may cause some duplicate events
        }

        if (abortController.signal.aborted) return;

        setRunState("streaming");
        setPendingTool(null);
        setActiveAgent("decepticon");
        setStreamStats({ startTime: Date.now(), totalTokens: 0, promptTokens: 0, completionTokens: 0 });

        try {
          const stream = client.runs.stream(
            threadIdRef.current!,
            ASSISTANT_ID,
            {
              command: { resume: value ?? true },
              ...STREAM_OPTIONS,
              onDisconnect: "continue",
              signal: abortController.signal,
            },
          );

          await processStream(stream, abortController);
        } catch (err) {
          if (abortController.signal.aborted) return;
          const msg =
            err instanceof Error ? err.message : "Resume failed";
          setError(msg);
        }

        handleStreamComplete(abortController);
      };

      runResume().catch((err) => {
        if (abortController.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Resume error");
        abortRef.current = null;
        runIdRef.current = null;
        resetStreamState();
      });
    },
    [addEvent, processStream, handleStreamComplete, resetStreamState],
  );

  return {
    submit,
    interrupt,
    cancel,
    resume,
    enqueue,
    clearQueuedMessage,
    events,
    runState,
    isStreaming,
    pendingTool,
    streamStats,
    activeAgent,
    queuedMessage,
    error,
    clearEvents,
    addSystemEvent,
  };
}
