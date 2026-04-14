"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { AGENTS, type AgentConfig } from "@/lib/agents";
import { AgentCard } from "@/components/agents/agent-card";
import { AgentSpline } from "@/components/agents/agent-spline";
import { DocumentPanel } from "@/components/panels/document-panel";
import { LangGraphChatService } from "@/lib/chat/langgraph-service";
import { defaultRenderer } from "@/lib/chat/markdown-renderer";
import type { ChatMessage, DocumentRef } from "@/lib/chat/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import {
  Send,
  Bot,
  Wrench,
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
    local_path: "Local Path",
    git_url: "Git Repository URL",
    file_upload: "Uploaded Archive",
    web_url: "Web Application URL",
    ip_range: "IP Range / Network",
    github_repo: "GitHub Repository",
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

  const [selectedAgent, setSelectedAgent] = useState<AgentConfig | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [input, setInput] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<DocumentRef | null>(null);
  const [docPanelOpen, setDocPanelOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const chatService = useMemo(() => new LangGraphChatService(), []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Auto-select Soundwave for new engagements
  useEffect(() => {
    if (isNew && !selectedAgent) {
      const soundwave = AGENTS.find((a) => a.id === "soundwave");
      if (soundwave) setSelectedAgent(soundwave);
    }
  }, [isNew, selectedAgent]);

  const sendMessage = useCallback(
    async (content: string, showInChat = true) => {
      if (showInChat) {
        setMessages((prev) => [
          ...prev,
          { id: `user-${Date.now()}`, role: "user", content, timestamp: Date.now() },
        ]);
      }
      setIsStreaming(true);

      await chatService.sendMessage(
        {
          engagementId,
          message: content,
          assistantId: selectedAgent?.id ?? "soundwave",
        },
        {
          onMessage: (msg) => {
            setMessages((prev) => {
              const idx = prev.findIndex((m) => m.id === msg.id);
              if (idx >= 0) {
                const updated = [...prev];
                updated[idx] = msg;
                return updated;
              }
              return [...prev, msg];
            });
          },
          onToolCall: (msg) => setMessages((prev) => [...prev, msg]),
          onError: (error) => {
            setMessages((prev) => [
              ...prev,
              { id: `error-${Date.now()}`, role: "system", content: `Error: ${error}`, timestamp: Date.now() },
            ]);
            setIsStreaming(false);
          },
          onDone: () => setIsStreaming(false),
        }
      );
    },
    [chatService, engagementId, selectedAgent]
  );

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
    if (!input.trim() || isStreaming) return;
    sendMessage(input.trim(), true);
    setInput("");
  }

  function handleAgentClick(agent: AgentConfig) {
    if (selectedAgent?.id === agent.id) {
      setSelectedAgent(null); // toggle off
    } else {
      setSelectedAgent(agent);
      setMessages([]); // clear chat when switching agents
    }
  }

  const renderer = defaultRenderer;
  const isEmpty = messages.length === 0 && !isStreaming;

  // Group agents by role
  const roleGroups = AGENTS.reduce<Record<string, AgentConfig[]>>((acc, agent) => {
    (acc[agent.role] ??= []).push(agent);
    return acc;
  }, {});

  return (
    <div className="relative flex h-full">
      {/* Left: Agent Grid */}
      <div className={cn("flex-1 overflow-auto p-4 transition-all duration-300", selectedAgent && "pr-[420px]")}>
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">Live</h1>
          <p className="text-sm text-muted-foreground">
            Select an agent to interact with in real-time
          </p>
        </div>

        {Object.entries(roleGroups).map(([role, agents]) => (
          <div key={role} className="mb-6">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground/60">
              {role}
            </h2>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
              {agents.map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  selected={selectedAgent?.id === agent.id}
                  onClick={() => handleAgentClick(agent)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Right: Glassmorphism Floating Panel */}
      {selectedAgent && (
        <div className="absolute right-4 top-4 bottom-4 w-[420px] flex flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0d0d1a]/80 shadow-2xl backdrop-blur-xl">
          {/* Gradient glow effects */}
          <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-2xl">
            <div className="absolute -left-20 -top-20 h-40 w-40 rounded-full blur-[80px]" style={{ backgroundColor: `${selectedAgent.color}15` }} />
            <div className="absolute -right-20 -bottom-20 h-40 w-40 rounded-full bg-purple-600/10 blur-[80px]" />
          </div>

          {/* Header */}
          <div className="relative flex items-center gap-3 px-5 py-4">
            <Sparkles className="h-5 w-5" style={{ color: selectedAgent.color }} />
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-semibold text-white">
                Running {selectedAgent.name} Agent
              </h3>
            </div>
            <button
              onClick={() => setSelectedAgent(null)}
              className="flex h-7 w-7 items-center justify-center rounded-lg text-zinc-500 hover:bg-white/5 hover:text-zinc-300 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Steps / Messages — vertical step list */}
          <ScrollArea className="relative flex-1" ref={scrollRef}>
            <div className="space-y-2 px-5 py-3">
              {isEmpty && (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <AgentSpline agent={selectedAgent} size={56} />
                  <h3 className="mt-3 text-sm font-medium text-white">{selectedAgent.name}</h3>
                  <p className="mt-1 max-w-xs text-xs text-zinc-500">
                    {selectedAgent.description}
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

              {isStreaming && messages[messages.length - 1]?.role !== "assistant" && (
                <div className="flex items-center gap-3 rounded-xl bg-white/[0.03] px-4 py-3 ring-1 ring-white/[0.06]">
                  <Loader2 className="h-4 w-4 animate-spin" style={{ color: selectedAgent.color }} />
                  <span className="text-xs text-zinc-400">Processing...</span>
                </div>
              )}
            </div>
          </ScrollArea>

          {/* Progress indicator */}
          {messages.length > 0 && (
            <div className="relative px-5 py-2">
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
          <div className="relative px-5 pb-4 pt-2">
            <div className="flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                placeholder={`Message ${selectedAgent.name}...`}
                disabled={isStreaming}
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white placeholder-zinc-600 outline-none transition-colors focus:border-white/20 focus:ring-1 focus:ring-white/10 disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isStreaming}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white transition-all disabled:opacity-30"
                style={{ backgroundColor: selectedAgent.color }}
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      <DocumentPanel
        open={docPanelOpen}
        onClose={() => setDocPanelOpen(false)}
        document={selectedDoc}
      />
    </div>
  );
}

/* ── Step card — glassmorphism style like reference image ──────── */

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

  // System messages — small inline badge
  if (message.role === "system") {
    return (
      <div className="flex items-center gap-2 py-1">
        <Circle className="h-2 w-2 fill-zinc-600 text-zinc-600" />
        <span className="text-[11px] text-zinc-500">{message.content}</span>
      </div>
    );
  }

  // User messages — right-aligned bubble
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5" style={{ backgroundColor: `${agentColor}25` }}>
          <p className="text-sm leading-relaxed text-white whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  // Tool calls — step card with icon
  if (message.role === "tool") {
    const isDone = !!message.content;
    return (
      <div
        className={cn(
          "rounded-xl px-4 py-3 ring-1 transition-all",
          isDone
            ? "bg-white/[0.04] ring-white/[0.08]"
            : "bg-white/[0.02] ring-white/[0.05]"
        )}
      >
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
              <p className="mt-0.5 truncate text-xs text-zinc-500">
                {message.content.slice(0, 100)}
              </p>
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

  // Assistant messages — step card with status
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
