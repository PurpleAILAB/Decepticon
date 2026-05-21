"use client";

/**
 * AgentDetailPanel — Slide-in panel showing detailed activity for a selected agent.
 *
 * Filters the global SubagentCustomEvent stream to the selected agent,
 * derives current status, and renders a mini-feed of recent tool calls and messages.
 */

import { useEffect, useMemo, useRef } from "react";
import type { SubagentCustomEvent } from "@decepticon/streaming";
import type { AgentConfig } from "@/lib/agents";
import { AGENT_DISPLAY_CONFIG } from "@/lib/agents";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { X, Wrench, MessageSquare, Clock } from "lucide-react";
import ReactMarkdown from "react-markdown";

// ── Types ──────────────────────────────────────────────────────────

interface AgentDetailPanelProps {
  agent: AgentConfig | null;
  events: SubagentCustomEvent[];
  onClose: () => void;
  className?: string;
}

// ── Helpers ────────────────────────────────────────────────────────

type AgentStatus = "idle" | "processing" | "completed";

const STALENESS_THRESHOLD_MS = 15_000; // Agent idle if no recent event

function deriveStatus(agentEvents: SubagentCustomEvent[]): AgentStatus {
  if (agentEvents.length === 0) return "idle";

  const last = agentEvents[agentEvents.length - 1];
  if (last.type === "subagent_end") return "completed";

  // Stale events: if most recent event is older than threshold, agent is
  // no longer active — likely finished while observer was disconnected
  if (last.elapsed != null && last.elapsed * 1000 > STALENESS_THRESHOLD_MS) {
    return "idle";
  }

  if (
    last.type === "subagent_start" ||
    last.type === "subagent_tool_call" ||
    last.type === "subagent_message"
  ) {
    return "processing";
  }

  return "processing";
}

const STATUS_META: Record<
  AgentStatus,
  { label: string; dotClass: string }
> = {
  idle: {
    label: "Idle",
    dotClass: "bg-zinc-500",
  },
  processing: {
    label: "Processing",
    dotClass: "bg-amber-400 animate-pulse",
  },
  completed: {
    label: "Completed",
    dotClass: "bg-emerald-400",
  },
};

function formatElapsed(ms: number): string {
  if (ms < 1000) return "just now";
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "…";
}

// ── Component ──────────────────────────────────────────────────────

export function AgentDetailPanel({
  agent,
  events,
  onClose,
  className,
}: AgentDetailPanelProps) {
  // Escape key handler
  useEffect(() => {
    if (!agent) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [agent, onClose]);

  // Filter events for this agent
  const agentEvents = useMemo(() => {
    if (!agent) return [];
    return events.filter((e) => e.agent === agent.id);
  }, [agent, events]);

  // Last 20 events for the mini-feed
  const recentEvents = useMemo(
    () => agentEvents.slice(-20),
    [agentEvents],
  );

  // Elapsed time since last event
  const feedRef = useRef<HTMLDivElement>(null);

  // Derive status
  const status = useMemo(() => deriveStatus(agentEvents), [agentEvents]);
  const statusMeta = STATUS_META[status];

  // Latest subagent_message content
  const latestMessage = useMemo(() => {
    const messages = agentEvents.filter((e) => e.type === "subagent_message");
    if (messages.length === 0) return null;
    return messages[messages.length - 1];
  }, [agentEvents]);


  if (!agent) return null;

  const displayMeta = AGENT_DISPLAY_CONFIG[agent.id];
  const agentColor = agent.color ?? displayMeta?.color ?? "#6b7280";

  return (
    <div
      className={cn(
        "flex h-full w-[360px] shrink-0 flex-col bg-zinc-950 border-l border-white/[0.08]",
        className,
      )}
    >
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-white/[0.08]">
        <span className="text-lg leading-none">{agent.mascotEmoji}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white truncate">
              {agent.name}
            </span>
            <Badge
              variant="outline"
              className="text-[10px] shrink-0"
              style={{ borderColor: agentColor, color: agentColor }}
            >
              {agent.role}
            </Badge>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 text-zinc-500 transition-colors hover:bg-white/[0.06] hover:text-zinc-300"
          aria-label="Close agent detail panel"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* ── Status ─────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/[0.08]">
        <span
          className={cn("h-2 w-2 rounded-full shrink-0", statusMeta.dotClass)}
        />
        <span className="text-xs text-zinc-400">{statusMeta.label}</span>
        {agentEvents.length > 0 && (
          <span className="ml-auto text-[10px] text-zinc-600">
            {agentEvents.length} event{agentEvents.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* ── Recent Activity ────────────────────────────────── */}
      <div className="flex-1 min-h-0 flex flex-col">
        <div className="px-4 pt-3 pb-1.5">
          <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-600">
            Recent Activity
          </span>
        </div>

        <ScrollArea className="flex-1 min-h-0">
          <div ref={feedRef} className="space-y-1 px-4 pb-3">
            {recentEvents.length === 0 ? (
              agent.id === "decepticon" ? (
                <div className="py-4 text-center text-xs text-zinc-500 space-y-2">
                  <p className="font-medium text-zinc-400">Orchestrator</p>
                  <p>Decepticon coordinates sub-agents via task() delegation.</p>
                  <p>Activity appears on the sub-agent nodes, not here.</p>
                  <p className="text-zinc-600 mt-2">Click a sub-agent node in the graph to see its activity.</p>
                </div>
              ) : (
                <p className="py-6 text-center text-xs text-zinc-600">
                  No activity yet
                </p>
              )
            ) : (
              recentEvents.map((event, i) => (
                <ActivityRow
                  key={`${event.type}-${event.agent}-${i}`}
                  event={event}
                  agentColor={agentColor}
                />
              ))
            )}
          </div>
        </ScrollArea>

        {/* ── Latest Message ─────────────────────────────── */}
        {latestMessage && latestMessage.content && (
          <>
            <Separator className="bg-white/[0.08]" />
            <div className="px-4 pt-3 pb-1.5">
              <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-600">
                Latest Message
              </span>
            </div>
            <ScrollArea className="max-h-[200px]">
              <div className="px-4 pb-4 text-xs leading-relaxed text-zinc-300 prose prose-invert prose-xs max-w-none">
                <ReactMarkdown>{latestMessage.content}</ReactMarkdown>
              </div>
            </ScrollArea>
          </>
        )}
      </div>
    </div>
  );
}

// ── Activity Row ───────────────────────────────────────────────────

function ActivityRow({
  event,
  agentColor,
}: {
  event: SubagentCustomEvent;
  agentColor: string;
}) {
  const elapsed = event.elapsed != null ? event.elapsed * 1000 : undefined;

  switch (event.type) {
    case "subagent_tool_call":
      return (
        <div className="flex items-start gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-white/[0.03]">
          <Wrench
            className="mt-0.5 h-3 w-3 shrink-0 text-amber-400/70"
          />
          <div className="min-w-0 flex-1">
            <code className="text-[11px] font-mono text-white/80">
              {event.tool ?? "unknown"}
            </code>
            {event.content && (
              <p className="mt-0.5 text-[10px] text-zinc-500 truncate">
                {truncate(event.content, 80)}
              </p>
            )}
          </div>
          {elapsed != null && (
            <span className="shrink-0 text-[10px] text-zinc-600 flex items-center gap-0.5">
              <Clock className="h-2.5 w-2.5" />
              {formatElapsed(elapsed)}
            </span>
          )}
        </div>
      );

    case "subagent_tool_result":
      return (
        <div className="flex items-start gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-white/[0.03]">
          <Wrench className="mt-0.5 h-3 w-3 shrink-0 text-emerald-400/70" />
          <div className="min-w-0 flex-1">
            <span className="text-[11px] text-zinc-400">
              Result:{" "}
              <code className="font-mono text-white/60">
                {event.tool ?? "tool"}
              </code>
            </span>
            {event.content && (
              <p className="mt-0.5 text-[10px] text-zinc-600 truncate">
                {truncate(event.content, 80)}
              </p>
            )}
          </div>
          {elapsed != null && (
            <span className="shrink-0 text-[10px] text-zinc-600 flex items-center gap-0.5">
              <Clock className="h-2.5 w-2.5" />
              {formatElapsed(elapsed)}
            </span>
          )}
        </div>
      );

    case "subagent_message":
      return (
        <div className="flex items-start gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-white/[0.03]">
          <MessageSquare
            className="mt-0.5 h-3 w-3 shrink-0"
            style={{ color: agentColor }}
          />
          <p className="min-w-0 flex-1 text-[11px] text-zinc-400 truncate">
            {truncate(event.content ?? event.text ?? "", 100)}
          </p>
        </div>
      );

    case "subagent_start":
      return (
        <div className="flex items-center gap-2 rounded-md px-2 py-1.5">
          <span
            className="h-1.5 w-1.5 rounded-full shrink-0"
            style={{ backgroundColor: agentColor }}
          />
          <span className="text-[11px] text-zinc-500">Started</span>
        </div>
      );

    case "subagent_end":
      return (
        <div className="flex items-center gap-2 rounded-md px-2 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full shrink-0 bg-emerald-400" />
          <span className="text-[11px] text-zinc-500">
            Completed
            {event.status ? ` — ${event.status}` : ""}
          </span>
          {elapsed != null && (
            <span className="ml-auto shrink-0 text-[10px] text-zinc-600 flex items-center gap-0.5">
              <Clock className="h-2.5 w-2.5" />
              {formatElapsed(elapsed)}
            </span>
          )}
        </div>
      );

    case "ask_user_question":
      return (
        <div className="flex items-start gap-2 rounded-md bg-amber-400/5 px-2 py-1.5 ring-1 ring-amber-400/10">
          <MessageSquare className="mt-0.5 h-3 w-3 shrink-0 text-amber-400" />
          <p className="min-w-0 flex-1 text-[11px] text-amber-300/80 truncate">
            {truncate(event.question ?? event.content ?? "Awaiting input", 100)}
          </p>
        </div>
      );

    default:
      return null;
  }
}
