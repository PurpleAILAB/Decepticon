"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { AGENTS, type AgentConfig } from "@/lib/agents";
import { AgentSpline } from "@/components/agents/agent-spline";
import { AgentCanvasProvider } from "@/components/agents/agent-canvas-provider";
import { AgentGrid } from "@/components/agents/agent-grid";
import { DocumentPanel } from "@/components/panels/document-panel";
import { StreamError } from "@/components/chat/streaming-activity";
import { useChat } from "@/hooks/useChat";
import { useAgents } from "@/hooks/useAgents";
import { defaultRenderer } from "@/lib/chat/markdown-renderer";
import type { ChatMessage, DocumentRef } from "@/lib/chat/types";

import { Badge } from "@/components/ui/badge";
import {
  Send,
  Bot,
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  X,
  Sparkles,
  Circle,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface Engagement {
  id: string;
  name: string;
  targetType: string;
  targetValue: string;
  status: string;
}

function buildInitialPrompt(eng: Engagement): string {
  const targetLabels: Record<string, string> = {
    web_url: "Web Application URL",
    ip_range: "IP Range / Network",
  };
  return [
    `New engagement: **${eng.name}**`,
    `Target type: ${targetLabels[eng.targetType] ?? eng.targetType}`,
    `Target: ${eng.targetValue}`,
    "",
    "Please begin the Socratic interview to generate the engagement documents (RoE, CONOPS, OPPLAN).",
  ].join("\n");
}

export default function LivePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const engagementId = params.id as string;
  const isNew = searchParams.get("new") === "true";
  const initSent = useRef(false);

  const { agents } = useAgents();
  const [selectedAgent, setSelectedAgent] = useState<AgentConfig | null>(
    () => isNew ? (AGENTS.find((a) => a.id === "soundwave") ?? null) : null,
  );
  const [input, setInput] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<DocumentRef | null>(null);
  const [docPanelOpen, setDocPanelOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isUserScrolledRef = useRef(false);
  const prevMsgCountRef = useRef(0);

  const {
    messages, isStreaming, runState, error: chatError,
    sendMessage, interrupt, resume,
  } = useChat({
    engagementId,
    assistantId: selectedAgent?.id ?? "soundwave",
  });

  // Smart auto-scroll: don't interrupt when user is reading earlier messages
  useEffect(() => {
    const container = scrollRef.current;
    if (!container || isUserScrolledRef.current) return;
    const isNewMessage = messages.length > prevMsgCountRef.current;
    prevMsgCountRef.current = messages.length;
    // Small delay for new messages (smoother UX), immediate for content updates
    const delay = isNewMessage ? 250 : 0;
    setTimeout(() => {
      container.scrollTop = container.scrollHeight;
    }, delay);
  }, [messages]);

  // Pre-fill initial prompt for new engagements (user must click send)
  useEffect(() => {
    if (!isNew || initSent.current || !selectedAgent) return;
    initSent.current = true;
    fetch(`/api/engagements/${engagementId}`)
      .then((res) => { if (!res.ok) throw new Error("fail"); return res.json(); })
      .then((eng: Engagement) => setInput(buildInitialPrompt(eng)))
      .catch(() => {});
  }, [isNew, engagementId, selectedAgent]);

  function handleSend() {
    if (!input.trim()) return;
    sendMessage(input.trim());
    setInput("");
  }

  function handleAgentClick(agent: AgentConfig) {
    if (selectedAgent?.id === agent.id) {
      setSelectedAgent(null);
    } else {
      setSelectedAgent(agent);
    }
  }

  const renderer = defaultRenderer;
  const isEmpty = messages.length === 0 && !isStreaming;
  const panelOpen = !!selectedAgent;

  return (
    <AgentCanvasProvider>
    <div className="flex h-full overflow-hidden">
      {/* Left: Agent Characters */}
      <div className={cn(
        "flex-1 overflow-auto transition-all duration-500 ease-out",
        panelOpen ? "w-1/2" : "w-full"
      )}>
        {/* Selected agent hero view */}
        {selectedAgent ? (
          <div className="flex h-full flex-col items-center justify-center p-8">
            {/* Enlarged 3D character with glow */}
            <div className="relative">
              {/* Glow ring */}
              <div
                className="absolute inset-0 -m-8 rounded-full blur-[60px] opacity-30 animate-pulse"
                style={{ backgroundColor: selectedAgent.color }}
              />
              {/* Character — no box, blends with background */}
              <div className="relative animate-[float_3s_ease-in-out_infinite]">
                <AgentSpline agent={selectedAgent} size={160} />
              </div>
            </div>

            <h2 className="mt-6 text-xl font-bold text-white">{selectedAgent.name}</h2>
            <p className="mt-3 max-w-sm text-center text-sm text-zinc-400 leading-relaxed">
              {selectedAgent.description}
            </p>

            {/* Other agents — small row at bottom */}
            <div className="mt-8 flex flex-wrap justify-center gap-2">
              {agents.filter((a) => a.id !== selectedAgent.id).map((agent) => (
                <button
                  key={agent.id}
                  onClick={() => handleAgentClick(agent)}
                  className="group flex h-12 w-12 items-center justify-center rounded-xl bg-white/[0.04] ring-1 ring-white/[0.06] transition-all hover:bg-white/[0.08] hover:ring-white/[0.12] hover:scale-110"
                  title={agent.name}
                >
                  <span className="text-lg group-hover:scale-110 transition-transform">
                    {agent.mascotEmoji}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* Agent selection grid — grouped by kill chain phase */
          <div className="p-6">
            <div className="mb-8 text-center">
              <h1 className="text-2xl font-bold tracking-tight">Live</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Select an agent to start a conversation
              </p>
            </div>

            <AgentGrid agents={agents} onAgentClick={handleAgentClick} />
          </div>
        )}
      </div>

      {/* Right: Chat sidebar panel — slides in at 50% width */}
      <aside
        className={cn(
          "flex flex-col overflow-hidden border-l border-white/[0.08] bg-[#0d0d1a]/95 backdrop-blur-xl transition-all duration-500 ease-out",
          panelOpen ? "w-1/2" : "w-0 border-l-0"
        )}
      >
        {selectedAgent && (
          <>
            {/* Header */}
            <div className="flex items-center gap-3 px-5 py-4 shrink-0 border-b border-white/[0.06]">
              <Sparkles className="h-5 w-5" style={{ color: selectedAgent.color }} />
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-semibold text-white">
                  {selectedAgent.name}
                </h3>
                <p className="text-[11px] text-zinc-500">
                  {chatError ? (
                    <span className="flex items-center gap-1.5 text-red-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
                      {chatError}
                    </span>
                  ) : isStreaming ? (
                    <span className="flex items-center gap-1.5 text-emerald-400">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                      Processing...
                    </span>
                  ) : (
                    selectedAgent.description
                  )}
                </p>
              </div>
              <button
                onClick={() => setSelectedAgent(null)}
                className="flex h-7 w-7 items-center justify-center rounded-lg text-zinc-500 hover:bg-white/5 hover:text-zinc-300 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Messages */}
            <div
              className="flex-1 overflow-y-auto min-h-0"
              ref={scrollRef}
              onScroll={(e) => {
                const el = e.currentTarget;
                const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
                isUserScrolledRef.current = !atBottom;
              }}
            >
              <div className="space-y-2 px-5 py-4">
                {isEmpty && (
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/[0.04] ring-1 ring-white/[0.08]">
                      <AgentSpline agent={selectedAgent} size={48} />
                    </div>
                    <p className="mt-4 text-sm text-zinc-400">
                      Start a conversation with {selectedAgent.name}
                    </p>
                  </div>
                )}

                {messages.map((msg) => (
                  <StepCard
                    key={msg.id}
                    message={msg}
                    renderer={renderer}
                    agentColor={selectedAgent.color}
                    onDocumentClick={(doc) => { setSelectedDoc(doc); setDocPanelOpen(true); }}
                  />
                ))}

                {chatError && (
                  <StreamError
                    error={chatError}
                    onRetry={() => {
                      const lastUserMsg = [...messages].reverse().find((m) => m.role === "user");
                      if (lastUserMsg) sendMessage(lastUserMsg.content);
                    }}
                  />
                )}

                {isStreaming && messages[messages.length - 1]?.role !== "assistant" && (
                  <div className="flex items-center gap-3 rounded-xl bg-white/[0.03] px-4 py-3 ring-1 ring-white/[0.06]">
                    <Loader2 className="h-4 w-4 animate-spin" style={{ color: selectedAgent.color }} />
                    <span className="text-xs text-zinc-400">Processing...</span>
                  </div>
                )}
              </div>
            </div>

            {/* Progress */}
            {messages.length > 0 && (
              <div className="px-5 py-2 shrink-0">
                <div className="h-1 overflow-hidden rounded-full bg-white/5">
                  <div
                    className="h-full rounded-full transition-all duration-1000"
                    style={{
                      backgroundColor: selectedAgent.color,
                      width: isStreaming ? "60%" : "100%",
                    }}
                  />
                </div>
              </div>
            )}

            {/* Input */}
            <div className="px-5 pb-4 pt-2 shrink-0">
              <div className="flex items-center gap-2">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                  placeholder={`Message ${selectedAgent.name}...`}
                  className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white placeholder-zinc-600 outline-none transition-colors focus:border-white/20 focus:ring-1 focus:ring-white/10 disabled:opacity-50"
                />
                {isStreaming ? (
                  <button
                    onClick={() => interrupt()}
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-yellow-600 text-white transition-all hover:bg-yellow-500"
                    title="Pause"
                  >
                    <X className="h-4 w-4" />
                  </button>
                ) : runState === "paused" ? (
                  <button
                    onClick={() => resume()}
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white transition-all hover:bg-emerald-500"
                    title="Resume"
                  >
                    <Send className="h-4 w-4" />
                  </button>
                ) : (
                  <button
                    onClick={handleSend}
                    disabled={!input.trim()}
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white transition-all disabled:opacity-30"
                    style={{ backgroundColor: selectedAgent.color }}
                  >
                    <Send className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
          </>
        )}
      </aside>

      <DocumentPanel
        open={docPanelOpen}
        onClose={() => setDocPanelOpen(false)}
        document={selectedDoc}
      />
    </div>
    </AgentCanvasProvider>
  );
}

/* ── Step card ────────────────────────────────────────────────── */

function StepCard({
  message,
  renderer,
  agentColor,
  onDocumentClick,
}: {
  message: ChatMessage;
  renderer: { renderAssistantContent: (c: string) => React.ReactNode; renderToolOutput: (c: string) => React.ReactNode };
  agentColor: string;
  onDocumentClick?: (doc: DocumentRef) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  if (message.role === "system") {
    return (
      <div className="flex items-center gap-2 py-1">
        <Circle className="h-2 w-2 fill-zinc-600 text-zinc-600" />
        <span className="text-[11px] text-zinc-500">{message.content}</span>
      </div>
    );
  }

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5" style={{ backgroundColor: `${agentColor}25` }}>
          <p className="text-sm leading-relaxed text-white whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  if (message.role === "tool") {
    const isDone = !!message.content;
    return (
      <div className={cn(
        "rounded-xl px-4 py-3 ring-1 transition-all",
        isDone ? "bg-white/[0.04] ring-white/[0.08]" : "bg-white/[0.02] ring-white/[0.05]"
      )}>
        <button
          type="button"
          onClick={() => isDone && setExpanded(!expanded)}
          className="flex w-full items-center gap-3 text-left"
        >
          {isDone ? (
            <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400" />
          ) : (
            <Loader2 className="h-5 w-5 shrink-0 animate-spin text-zinc-500" />
          )}
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-white">{message.toolName}</p>
            {isDone && message.content && (
              <p className="mt-0.5 truncate text-xs text-zinc-500">{message.content.slice(0, 100)}</p>
            )}
          </div>
          {isDone && (
            expanded
              ? <ChevronDown className="h-4 w-4 shrink-0 text-zinc-600" />
              : <ChevronRight className="h-4 w-4 shrink-0 text-zinc-600" />
          )}
        </button>
        {expanded && message.content && (
          <div className="mt-2 rounded-lg bg-black/30 p-3 text-xs">
            {renderer.renderToolOutput(message.content)}
          </div>
        )}
      </div>
    );
  }

  // Assistant
  const hasStatus = message.status === "passed" || message.status === "blocked";
  return (
    <div className="rounded-xl bg-white/[0.04] px-4 py-3 ring-1 ring-white/[0.08]">
      <div className="flex items-start gap-3">
        {hasStatus ? (
          message.status === "passed" ? (
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
          ) : (
            <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
          )
        ) : (
          <Bot className="mt-0.5 h-5 w-5 shrink-0" style={{ color: agentColor }} />
        )}
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="text-sm text-zinc-200 leading-relaxed">
            {renderer.renderAssistantContent(message.content)}
          </div>
          {message.documents && message.documents.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {message.documents.map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => onDocumentClick?.(doc)}
                  className="flex items-center gap-1.5 rounded-lg bg-white/[0.05] px-2.5 py-1.5 text-[11px] ring-1 ring-white/[0.08] transition-all hover:bg-white/[0.08]"
                >
                  <FileText className="h-3 w-3" style={{ color: agentColor }} />
                  <span className="text-zinc-300">{doc.title}</span>
                  <Badge variant="secondary" className="h-4 bg-white/5 px-1 text-[9px] text-zinc-500">{doc.type}</Badge>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
