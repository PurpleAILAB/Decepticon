"use client";

/**
 * useThreadSync — polls LangGraph thread state for cross-client sync.
 *
 * Unlike useChat (which only receives events from its own submissions),
 * this hook polls the LangGraph server for thread state changes regardless
 * of which client (CLI or Web) triggered the run.
 *
 * Architecture:
 *   CLI ──submit──→ LangGraph Server ←──poll──── useThreadSync (Web)
 *                      (shared thread)
 *
 * The graph visualization consumes messages from this hook to show
 * agent activity started by any client.
 */

import { useState, useEffect, useRef } from "react";
import { Client } from "@langchain/langgraph-sdk";
import type { ChatMessage } from "@/lib/chat/types";
import { extractText, stripResultTags } from "@decepticon/streaming";

const POLL_INTERVAL = 2000; // 2s

interface Message {
  type: string;
  id?: string;
  content: string | Array<{ type: string; text?: string }>;
  name?: string;
  tool_calls?: Array<{ id: string; name: string; args: Record<string, unknown> }>;
}

interface ThreadState {
  values: {
    messages?: Message[];
  };
}

interface UseThreadSyncOptions {
  engagementId: string;
}

interface UseThreadSyncReturn {
  messages: ChatMessage[];
  isRunning: boolean;
  threadId: string | null;
}

function loadThreadId(engagementId: string): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(`decepticon:thread:${engagementId}`) ?? null;
}

export function useThreadSync({
  engagementId,
}: UseThreadSyncOptions): UseThreadSyncReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const prevCountRef = useRef(0);

  const apiUrl = typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_LANGGRAPH_API_URL ?? "http://localhost:2024")
    : (process.env.LANGGRAPH_API_URL ?? "http://localhost:2024");

  const clientRef = useRef(new Client({ apiUrl }));

  // Watch for thread ID changes (CLI might create one)
  useEffect(() => {
    const check = () => {
      const tid = loadThreadId(engagementId);
      if (tid && tid !== threadId) setThreadId(tid);
    };
    check();
    const interval = setInterval(check, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [engagementId, threadId]);

  // Poll thread state
  useEffect(() => {
    if (!threadId) return;

    let active = true;
    const client = clientRef.current;

    const poll = async () => {
      if (!active) return;
      try {
        // Get thread state
        const state = await client.threads.getState(threadId) as ThreadState;
        const serverMessages = state?.values?.messages ?? [];

        // Only update if message count changed
        if (serverMessages.length !== prevCountRef.current) {
          prevCountRef.current = serverMessages.length;
          const chatMessages = serverMessagesToChatMessages(serverMessages);
          setMessages(chatMessages);
        }

        // Check for active runs
        const runs = await client.runs.list(threadId, { limit: 1 });
        const hasActiveRun = runs.some(
          (r: { status: string }) => r.status === "pending" || r.status === "running",
        );
        setIsRunning(hasActiveRun);
      } catch {
        // Thread might not exist yet or server unreachable — ignore
      }
    };

    poll();
    const interval = setInterval(poll, POLL_INTERVAL);
    return () => { active = false; clearInterval(interval); };
  }, [threadId]);

  return { messages, isRunning, threadId };
}

function serverMessagesToChatMessages(messages: Message[]): ChatMessage[] {
  const result: ChatMessage[] = [];

  for (const msg of messages) {
    const ts = Date.now();

    if (msg.type === "human") {
      result.push({
        id: msg.id ?? `user-${result.length}`,
        role: "user",
        content: extractText(msg.content),
        timestamp: ts,
      });
    } else if (msg.type === "ai") {
      const text = stripResultTags(extractText(msg.content));
      if (text) {
        result.push({
          id: msg.id ?? `assistant-${result.length}`,
          role: "assistant",
          content: text,
          timestamp: ts,
        });
      }
      // Emit tool calls as system messages for graph tracking
      if (msg.tool_calls?.length) {
        for (const tc of msg.tool_calls) {
          if (tc.name === "task") {
            // "task" tool = sub-agent delegation
            const agentName = (tc.args?.agent as string) ?? "";
            if (agentName) {
              result.push({
                id: tc.id ?? `system-${result.length}`,
                role: "system",
                content: `Agent **${agentName}** started`,
                agent: agentName,
                timestamp: ts,
              });
            }
          } else {
            result.push({
              id: tc.id ?? `tool-${result.length}`,
              role: "tool",
              content: "",
              toolName: tc.name,
              toolArgs: tc.args,
              agent: (msg as unknown as { name?: string }).name ?? undefined,
              timestamp: ts,
            });
          }
        }
      }
    } else if (msg.type === "tool") {
      const toolMsg = msg as Message & { name?: string };
      if (toolMsg.name === "task") continue;
      result.push({
        id: msg.id ?? `result-${result.length}`,
        role: "tool",
        content: extractText(msg.content),
        toolName: toolMsg.name ?? "",
        toolArgs: {},
        timestamp: ts,
      });
    }
  }

  return result;
}
