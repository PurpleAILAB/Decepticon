"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { DocumentPanel } from "@/components/panels/document-panel";
import { LangGraphChatService } from "@/lib/chat/langgraph-service";
import { defaultRenderer } from "@/lib/chat/markdown-renderer";
import type { ChatMessage, DocumentRef } from "@/lib/chat/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import {
  Sparkles,
  Send,
  Bot,
  Wrench,
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
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
    github_repo: "GitHub Repository",
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

export default function ChatPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const engagementId = params.id as string;
  const isNew = searchParams.get("new") === "true";
  const initSent = useRef(false);

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
        { engagementId, message: content, assistantId: "soundwave" },
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
    [chatService, engagementId]
  );

  useEffect(() => {
    if (!isNew || initSent.current) return;
    initSent.current = true;
    fetch(`/api/engagements/${engagementId}`)
      .then((res) => { if (!res.ok) throw new Error("fail"); return res.json(); })
      .then((eng: Engagement) => sendMessage(buildInitialPrompt(eng), true))
      .catch(() => {});
  }, [isNew, engagementId, sendMessage]);

  function handleSend() {
    if (!input.trim() || isStreaming) return;
    sendMessage(input.trim(), true);
    setInput("");
  }

  const renderer = defaultRenderer;
  const isEmpty = messages.length === 0 && !isStreaming;

  return (
    <>
      {/* Blurred background overlay — only covers main content area, not sidebar */}
      <div className="absolute inset-0 z-30 bg-background/70 backdrop-blur-md" />

      {/* Gradient glow effects */}
      <div className="absolute inset-0 z-30 overflow-hidden pointer-events-none">
        <div className="absolute left-1/4 top-1/3 h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-red-600/10 blur-[120px]" />
        <div className="absolute right-1/4 bottom-1/3 h-[400px] w-[400px] translate-x-1/2 translate-y-1/2 rounded-full bg-rose-600/8 blur-[100px]" />
      </div>

      {/* Floating chat card */}
      <div className="absolute inset-0 z-40 flex items-center justify-center p-8">
        <div className="flex h-[78vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-white/[0.06] bg-[#0d0d1a]/90 shadow-2xl shadow-red-500/10 backdrop-blur-sm">

          {/* Header */}
          <div className="flex items-center gap-3 border-b border-white/5 px-6 py-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-red-500/20 to-red-900/20 ring-1 ring-red-500/20">
              <Sparkles className="h-5 w-5 text-red-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-white">Soundwave</h3>
              <p className="text-xs text-zinc-500">
                {isStreaming ? (
                  <span className="flex items-center gap-1.5 text-emerald-400">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                    Responding...
                  </span>
                ) : (
                  "Threat Assessment & Document Generation"
                )}
              </p>
            </div>
            {/* Phase indicator */}
            <div className="flex items-center gap-1.5">
              {["RoE", "CONOPS", "OPPLAN"].map((phase, i) => (
                <span
                  key={phase}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-medium ring-1",
                    i === 0
                      ? "bg-violet-500/10 text-red-400 ring-red-500/20"
                      : "bg-white/[0.02] text-zinc-600 ring-white/5"
                  )}
                >
                  {phase}
                </span>
              ))}
            </div>
          </div>

          {/* Messages area */}
          <ScrollArea className="flex-1" ref={scrollRef}>
            <div className="space-y-4 px-6 py-5">
              {isEmpty && (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/10 to-purple-500/10 ring-1 ring-red-500/10">
                    <Sparkles className="h-6 w-6 text-red-400/60" />
                  </div>
                  <h3 className="text-base font-medium text-white">Engagement Interview</h3>
                  <p className="mt-1 max-w-md text-sm text-zinc-500">
                    Describe your target and I&apos;ll conduct a threat assessment interview
                    to generate RoE, CONOPS, and OPPLAN documents.
                  </p>
                </div>
              )}

              {messages.map((msg) => (
                <FloatingMessage
                  key={msg.id}
                  message={msg}
                  renderer={renderer}
                  onDocumentClick={(doc) => { setSelectedDoc(doc); setDocPanelOpen(true); }}
                />
              ))}

              {isStreaming && messages[messages.length - 1]?.role !== "assistant" && (
                <div className="flex items-start gap-3">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-red-500/20 to-red-900/20 ring-1 ring-red-500/10">
                    <Bot className="h-3.5 w-3.5 text-red-400" />
                  </div>
                  <div className="flex items-center gap-2 rounded-xl bg-white/[0.03] px-4 py-3 ring-1 ring-white/5">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-red-400" />
                    <span className="text-xs text-zinc-500">Analyzing...</span>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>

          {/* Input */}
          <div className="border-t border-white/5 px-6 py-4">
            <div className="flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                placeholder={isEmpty ? "Describe your target..." : "Reply to Soundwave..."}
                disabled={isStreaming}
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white placeholder-zinc-600 outline-none transition-colors focus:border-red-500/50 focus:ring-1 focus:ring-red-500/20 disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isStreaming}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-red-600 text-white transition-colors hover:bg-red-500 disabled:opacity-30"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <DocumentPanel
        open={docPanelOpen}
        onClose={() => setDocPanelOpen(false)}
        document={selectedDoc}
      />
    </>
  );
}

/* ── Message components ─────────────────────────────────────────── */

function FloatingMessage({
  message,
  renderer,
  onDocumentClick,
}: {
  message: ChatMessage;
  renderer: { renderAssistantContent: (c: string) => React.ReactNode; renderToolOutput: (c: string) => React.ReactNode };
  onDocumentClick?: (doc: DocumentRef) => void;
}) {
  if (message.role === "tool") return <ToolBlock message={message} renderer={renderer} />;
  if (message.role === "system") {
    return (
      <div className="flex justify-center">
        <span className="rounded-full bg-white/[0.03] px-3 py-1 text-[11px] text-zinc-500 ring-1 ring-white/5">
          {message.content}
        </span>
      </div>
    );
  }
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-md bg-red-600 px-4 py-2.5">
          <p className="text-sm leading-relaxed text-white whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  // Assistant
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2 pl-10">
        {message.agent && <span className="text-[11px] font-medium text-red-400/70">{message.agent}</span>}
        {message.status === "passed" && (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400 ring-1 ring-emerald-500/20">
            <CheckCircle2 className="h-2.5 w-2.5" /> PASSED
          </span>
        )}
        {message.status === "blocked" && (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-400 ring-1 ring-red-500/20">
            <XCircle className="h-2.5 w-2.5" /> BLOCKED
          </span>
        )}
      </div>
      <div className="flex items-start gap-3">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-red-500/20 to-red-900/20 ring-1 ring-red-500/10">
          <Bot className="h-3.5 w-3.5 text-red-400" />
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="rounded-2xl rounded-tl-md bg-white/[0.04] px-4 py-3 ring-1 ring-white/[0.06]">
            {renderer.renderAssistantContent(message.content)}
          </div>
          {message.documents && message.documents.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pl-1">
              {message.documents.map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => onDocumentClick?.(doc)}
                  className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-white/[0.03] px-2.5 py-1.5 text-xs ring-1 ring-white/[0.06] transition-all hover:bg-red-500/10 hover:ring-red-500/20"
                >
                  <FileText className="h-3 w-3 text-red-400" />
                  <span className="text-zinc-300">{doc.title}</span>
                  <Badge variant="secondary" className="h-4 bg-white/5 px-1 text-[10px] text-zinc-500">
                    {doc.type}
                  </Badge>
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
    <div className="ml-10 overflow-hidden rounded-xl ring-1 ring-white/5">
      <button
        type="button"
        onClick={() => hasOutput && setExpanded(!expanded)}
        className={cn(
          "flex w-full items-center gap-2 bg-white/[0.02] px-3 py-2 text-xs",
          hasOutput && "cursor-pointer hover:bg-white/[0.04]"
        )}
      >
        <Wrench className="h-3 w-3 shrink-0 text-amber-400/70" />
        <span className="font-mono font-medium text-amber-400/90">{message.toolName}</span>
        <span className="flex-1" />
        {hasOutput && (expanded ? <ChevronDown className="h-3 w-3 text-zinc-600" /> : <ChevronRight className="h-3 w-3 text-zinc-600" />)}
      </button>
      {expanded && message.content && (
        <div className="border-t border-white/5 bg-black/30 p-3">
          {renderer.renderToolOutput(message.content)}
        </div>
      )}
    </div>
  );
}
