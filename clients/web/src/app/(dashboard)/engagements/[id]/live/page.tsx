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

  // Auto-send initial prompt for new engagements
  useEffect(() => {
    if (!isNew || initSent.current || !selectedAgent) return;
    initSent.current = true;
    fetch(`/api/engagements/${engagementId}`)
      .then((res) => { if (!res.ok) throw new Error("fail"); return res.json(); })
      .then((eng: Engagement) => sendMessage(buildInitialPrompt(eng), true))
      .catch(() => {});
  }, [isNew, engagementId, sendMessage, selectedAgent]);

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

      {/* Right: Floating Chat Panel */}
      {selectedAgent && (
        <div className="absolute right-0 top-0 bottom-0 w-[400px] border-l border-border/50 bg-background shadow-xl flex flex-col">
          {/* Chat header */}
          <div className="flex items-center gap-3 border-b border-border/50 px-4 py-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/50">
              <AgentSpline agent={selectedAgent} size={32} />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-semibold truncate">{selectedAgent.name}</h3>
              <p className="text-xs text-muted-foreground truncate">
                {isStreaming ? (
                  <span className="flex items-center gap-1.5 text-emerald-400">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                    Responding...
                  </span>
                ) : (
                  selectedAgent.mascot
                )}
              </p>
            </div>
            <button
              onClick={() => setSelectedAgent(null)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Messages */}
          <ScrollArea className="flex-1" ref={scrollRef}>
            <div className="space-y-4 p-4">
              {isEmpty && (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <div className="mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent/50">
                    <AgentSpline agent={selectedAgent} size={48} />
                  </div>
                  <h3 className="text-sm font-medium">{selectedAgent.name}</h3>
                  <p className="mt-1 max-w-xs text-xs text-muted-foreground">
                    {selectedAgent.description}
                  </p>
                </div>
              )}

              {messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  renderer={renderer}
                  agentColor={selectedAgent.color}
                  onDocumentClick={(doc) => { setSelectedDoc(doc); setDocPanelOpen(true); }}
                />
              ))}

              {isStreaming && messages[messages.length - 1]?.role !== "assistant" && (
                <div className="flex items-start gap-2">
                  <div
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg"
                    style={{ backgroundColor: `${selectedAgent.color}20` }}
                  >
                    <Bot className="h-3 w-3" style={{ color: selectedAgent.color }} />
                  </div>
                  <div className="flex items-center gap-2 rounded-xl bg-accent/50 px-3 py-2">
                    <Loader2 className="h-3 w-3 animate-spin" style={{ color: selectedAgent.color }} />
                    <span className="text-xs text-muted-foreground">Thinking...</span>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>

          {/* Input */}
          <div className="border-t border-border/50 p-3">
            <div className="flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                placeholder={`Message ${selectedAgent.name}...`}
                disabled={isStreaming}
                className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm outline-none transition-colors focus:border-primary/50 focus:ring-1 focus:ring-primary/20 disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isStreaming}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white transition-colors disabled:opacity-30"
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

/* ── Message components ─────────────────────────────────────────── */

function MessageBubble({
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
  if (message.role === "tool") return <ToolBlock message={message} renderer={renderer} />;
  if (message.role === "system") {
    return (
      <div className="flex justify-center">
        <span className="rounded-full bg-accent/50 px-3 py-1 text-[10px] text-muted-foreground">
          {message.content}
        </span>
      </div>
    );
  }
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-3 py-2">
          <p className="text-sm leading-relaxed text-primary-foreground whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {message.status && (
        <div className="mb-1 pl-8">
          {message.status === "passed" && (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
              <CheckCircle2 className="h-2.5 w-2.5" /> PASSED
            </span>
          )}
          {message.status === "blocked" && (
            <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-400">
              <XCircle className="h-2.5 w-2.5" /> BLOCKED
            </span>
          )}
        </div>
      )}
      <div className="flex items-start gap-2">
        <div
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg"
          style={{ backgroundColor: `${agentColor}20` }}
        >
          <Bot className="h-3 w-3" style={{ color: agentColor }} />
        </div>
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="rounded-2xl rounded-tl-md bg-accent/30 px-3 py-2 ring-1 ring-border/30">
            {renderer.renderAssistantContent(message.content)}
          </div>
          {message.documents && message.documents.length > 0 && (
            <div className="flex flex-wrap gap-1 pl-0.5">
              {message.documents.map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => onDocumentClick?.(doc)}
                  className="flex items-center gap-1 rounded-lg bg-accent/30 px-2 py-1 text-[11px] ring-1 ring-border/30 transition-all hover:bg-primary/10"
                >
                  <FileText className="h-2.5 w-2.5 text-primary" />
                  <span>{doc.title}</span>
                  <Badge variant="secondary" className="h-3.5 px-1 text-[9px]">{doc.type}</Badge>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ToolBlock({
  message,
  renderer,
}: {
  message: ChatMessage;
  renderer: { renderToolOutput: (c: string) => React.ReactNode };
}) {
  const [expanded, setExpanded] = useState(false);
  const hasOutput = !!message.content;

  return (
    <div className="ml-8 overflow-hidden rounded-xl ring-1 ring-border/30">
      <button
        type="button"
        onClick={() => hasOutput && setExpanded(!expanded)}
        className={cn(
          "flex w-full items-center gap-2 bg-accent/20 px-3 py-1.5 text-[11px]",
          hasOutput && "cursor-pointer hover:bg-accent/40"
        )}
      >
        <Wrench className="h-2.5 w-2.5 shrink-0 text-amber-400/70" />
        <span className="font-mono font-medium text-amber-400/90">{message.toolName}</span>
        <span className="flex-1" />
        {hasOutput && (expanded ? <ChevronDown className="h-2.5 w-2.5 text-muted-foreground" /> : <ChevronRight className="h-2.5 w-2.5 text-muted-foreground" />)}
      </button>
      {expanded && message.content && (
        <div className="border-t border-border/30 bg-background/50 p-2">
          {renderer.renderToolOutput(message.content)}
        </div>
      )}
    </div>
  );
}
