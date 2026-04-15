"use client";

/**
 * StreamingActivity — Real-time agent execution feedback.
 *
 * Shows sub-agent activity (tool calls, progress, errors) during streaming.
 * Inspired by the reference LangGraph Chat UI's ActivityStream pattern.
 */

import { useState } from "react";
import type { ChatMessage } from "@/lib/chat/types";
import {
  Loader2,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Wrench,
  Bot,
  AlertTriangle,
  RotateCcw,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Error Recovery ──────────────────────────────────────────────

interface StreamErrorProps {
  error: string;
  onRetry?: () => void;
}

function categorizeError(error: string): { title: string; description: string } {
  const lower = error.toLowerCase();
  if (lower.includes("network") || lower.includes("fetch") || lower.includes("econnrefused")) {
    return { title: "Network Error", description: "Could not reach the server. Check your connection." };
  }
  if (lower.includes("401") || lower.includes("unauthorized") || lower.includes("auth")) {
    return { title: "Authentication Error", description: "Your session may have expired. Try refreshing." };
  }
  if (lower.includes("429") || lower.includes("rate limit")) {
    return { title: "Rate Limited", description: "Too many requests. Please wait a moment." };
  }
  if (lower.includes("500") || lower.includes("internal server")) {
    return { title: "Server Error", description: "The server encountered an error. Try again." };
  }
  if (lower.includes("timeout") || lower.includes("timed out")) {
    return { title: "Timeout", description: "The request took too long. Try again." };
  }
  return { title: "Error", description: error };
}

export function StreamError({ error, onRetry }: StreamErrorProps) {
  const [showDetails, setShowDetails] = useState(false);
  const { title, description } = categorizeError(error);

  return (
    <div className="rounded-xl bg-red-500/5 px-4 py-3 ring-1 ring-red-500/20">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-red-300">{title}</p>
          <p className="mt-0.5 text-xs text-red-400/70">{description}</p>

          <div className="mt-2 flex items-center gap-2">
            {onRetry && (
              <button
                onClick={onRetry}
                className="flex items-center gap-1.5 rounded-lg bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-300 transition-colors hover:bg-red-500/20"
              >
                <RotateCcw className="h-3 w-3" />
                Retry
              </button>
            )}
            <button
              onClick={() => setShowDetails(!showDetails)}
              className="text-[11px] text-red-400/50 hover:text-red-400/70"
            >
              {showDetails ? "Hide" : "Show"} details
            </button>
          </div>

          {showDetails && (
            <pre className="mt-2 overflow-x-auto rounded-lg bg-black/30 p-2 text-[11px] text-red-400/60">
              {error}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Activity Item ───────────────────────────────────────────────

interface ActivityItemProps {
  message: ChatMessage;
  agentColor?: string;
}

export function ActivityItem({ message, agentColor = "#ef4444" }: ActivityItemProps) {
  const [expanded, setExpanded] = useState(false);

  // System messages (agent start/end)
  if (message.role === "system") {
    const isEnd = message.content.includes("completed");
    return (
      <div className="flex items-center gap-2 py-1">
        {isEnd ? (
          <CheckCircle2 className="h-3 w-3 text-emerald-400/70" />
        ) : (
          <Bot className="h-3 w-3" style={{ color: agentColor }} />
        )}
        <span className="text-[11px] text-zinc-500">{message.content.replace(/\*\*/g, "")}</span>
      </div>
    );
  }

  // Tool calls
  if (message.role === "tool") {
    const isDone = !!message.content;
    return (
      <div
        className={cn(
          "rounded-lg px-3 py-2 ring-1 transition-all",
          isDone ? "bg-white/[0.03] ring-white/[0.06]" : "bg-white/[0.02] ring-white/[0.04]"
        )}
      >
        <button
          type="button"
          onClick={() => isDone && setExpanded(!expanded)}
          className="flex w-full items-center gap-2 text-left"
        >
          {isDone ? (
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
          ) : (
            <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-zinc-500" />
          )}
          <Wrench className="h-3 w-3 shrink-0 text-amber-400/70" />
          <span className="text-xs font-medium text-white">{message.toolName}</span>
          {message.agent && (
            <span className="text-[10px] text-zinc-600">{message.agent}</span>
          )}
          <span className="flex-1" />
          {isDone && (
            expanded
              ? <ChevronDown className="h-3 w-3 text-zinc-600" />
              : <ChevronRight className="h-3 w-3 text-zinc-600" />
          )}
        </button>
        {expanded && message.content && (
          <div className="mt-2 rounded-lg bg-black/30 p-2 text-[11px] font-mono text-zinc-400 max-h-40 overflow-auto">
            {message.content.slice(0, 500)}
            {message.content.length > 500 && "..."}
          </div>
        )}
      </div>
    );
  }

  return null;
}

// ── Streaming Activity Container ────────────────────────────────

interface StreamingActivityProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  agentColor?: string;
}

export function StreamingActivity({ messages, isStreaming, agentColor }: StreamingActivityProps) {
  // Filter to only system + tool messages (activity, not content)
  const activityMessages = messages.filter(
    (m) => m.role === "system" || (m.role === "tool" && m.toolName)
  );

  if (activityMessages.length === 0 && !isStreaming) return null;

  return (
    <div className="space-y-1">
      {activityMessages.map((msg) => (
        <ActivityItem key={msg.id} message={msg} agentColor={agentColor} />
      ))}
      {isStreaming && activityMessages.length === 0 && (
        <div className="flex items-center gap-2 py-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin" style={{ color: agentColor }} />
          <span className="text-xs text-zinc-400">Thinking...</span>
        </div>
      )}
    </div>
  );
}
