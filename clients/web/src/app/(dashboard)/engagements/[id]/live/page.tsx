"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { DocumentPanel } from "@/components/panels/document-panel";
import { LangGraphChatService } from "@/lib/chat/langgraph-service";
import { defaultRenderer } from "@/lib/chat/markdown-renderer";
import type { ChatMessage, DocumentRef } from "@/lib/chat/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  Radio,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface Engagement {
  id: string;
  name: string;
  targetType: string;
  targetValue: string;
  status: string;
}

interface StreamEvent {
  id: string;
  type: "tool_call" | "tool_result" | "text" | "status" | "error" | "complete";
  content: string;
  toolName?: string;
  timestamp: number;
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

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [input, setInput] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<DocumentRef | null>(null);
  const [docPanelOpen, setDocPanelOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("chat");
  const scrollRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<HTMLDivElement>(null);

  const chatService = useMemo(() => new LangGraphChatService(), []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [streamEvents]);

  // Connect to agent execution stream
  useEffect(() => {
    const evtSource = new EventSource(`/api/engagements/${engagementId}/stream`);
    evtSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        const event: StreamEvent = {
          id: `stream-${Date.now()}-${Math.random()}`,
          type: data.type ?? "text",
          content: data.content ?? JSON.stringify(data),
          toolName: data.tool_name,
          timestamp: Date.now(),
        };
        setStreamEvents((prev) => [...prev.slice(-500), event]);
      } catch {
        // skip unparseable
      }
    };
    evtSource.onerror = () => evtSource.close();
    return () => evtSource.close();
  }, [engagementId]);

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
    <div className="flex h-full flex-col">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-border/50 px-1">
          <TabsList className="bg-transparent">
            <TabsTrigger value="chat" className="gap-2 data-[state=active]:bg-accent">
              <Sparkles className="h-3.5 w-3.5" />
              Soundwave Chat
            </TabsTrigger>
            <TabsTrigger value="stream" className="gap-2 data-[state=active]:bg-accent">
              <Radio className="h-3.5 w-3.5" />
              Agent Stream
            </TabsTrigger>
          </TabsList>
          {isStreaming && (
            <span className="flex items-center gap-1.5 pr-3 text-xs text-emerald-400">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
              Live
            </span>
          )}
        </div>

        {/* Chat tab */}
        <TabsContent value="chat" className="flex-1 overflow-hidden mt-0">
          <div className="flex h-full flex-col">
            <ScrollArea className="flex-1" ref={scrollRef}>
              <div className="space-y-4 p-4">
                {isEmpty && (
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/10 to-purple-500/10 ring-1 ring-red-500/10">
                      <Sparkles className="h-6 w-6 text-red-400/60" />
                    </div>
                    <h3 className="text-base font-medium">Engagement Interview</h3>
                    <p className="mt-1 max-w-md text-sm text-muted-foreground">
                      Describe your target and Soundwave will conduct a threat assessment
                      interview to generate RoE, CONOPS, and OPPLAN documents.
                    </p>
                  </div>
                )}

                {messages.map((msg) => (
                  <MessageBubble
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
                    <div className="flex items-center gap-2 rounded-xl bg-accent/50 px-4 py-3">
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-red-400" />
                      <span className="text-xs text-muted-foreground">Analyzing...</span>
                    </div>
                  </div>
                )}
              </div>
            </ScrollArea>

            {/* Input */}
            <div className="border-t border-border/50 p-4">
              <div className="flex items-center gap-2">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                  placeholder={isEmpty ? "Describe your target..." : "Reply to Soundwave..."}
                  disabled={isStreaming}
                  className="w-full rounded-xl border border-border bg-background px-4 py-3 text-sm outline-none transition-colors focus:border-primary/50 focus:ring-1 focus:ring-primary/20 disabled:opacity-50"
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || isStreaming}
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-30"
                >
                  <Send className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* Agent Stream tab */}
        <TabsContent value="stream" className="flex-1 overflow-hidden mt-0">
          <ScrollArea className="h-full" ref={streamRef}>
            <div className="space-y-1 p-4 font-mono text-xs">
              {streamEvents.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <Radio className="mb-3 h-8 w-8 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">No agent activity yet</p>
                  <p className="mt-1 text-xs text-muted-foreground/60">
                    Start an engagement to see real-time agent execution
                  </p>
                </div>
              ) : (
                streamEvents.map((evt) => (
                  <div key={evt.id} className="flex gap-2">
                    <span className="shrink-0 text-muted-foreground/50">
                      {new Date(evt.timestamp).toLocaleTimeString()}
                    </span>
                    {evt.type === "tool_call" && (
                      <>
                        <Wrench className="mt-0.5 h-3 w-3 shrink-0 text-amber-400" />
                        <span className="text-amber-400">{evt.toolName}</span>
                      </>
                    )}
                    {evt.type === "tool_result" && (
                      <span className="whitespace-pre-wrap text-muted-foreground">{evt.content}</span>
                    )}
                    {evt.type === "text" && (
                      <span className="whitespace-pre-wrap text-foreground">{evt.content}</span>
                    )}
                    {evt.type === "error" && (
                      <span className="text-destructive">{evt.content}</span>
                    )}
                    {evt.type === "status" && (
                      <span className="text-emerald-400">{evt.content}</span>
                    )}
                    {evt.type === "complete" && (
                      <span className="text-emerald-400">Execution complete</span>
                    )}
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </TabsContent>
      </Tabs>

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
        <span className="rounded-full bg-accent/50 px-3 py-1 text-[11px] text-muted-foreground">
          {message.content}
        </span>
      </div>
    );
  }
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5">
          <p className="text-sm leading-relaxed text-primary-foreground whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

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
          <div className="rounded-2xl rounded-tl-md bg-accent/30 px-4 py-3 ring-1 ring-border/50">
            {renderer.renderAssistantContent(message.content)}
          </div>
          {message.documents && message.documents.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pl-1">
              {message.documents.map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => onDocumentClick?.(doc)}
                  className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-accent/30 px-2.5 py-1.5 text-xs ring-1 ring-border/50 transition-all hover:bg-primary/10 hover:ring-primary/20"
                >
                  <FileText className="h-3 w-3 text-primary" />
                  <span className="text-foreground">{doc.title}</span>
                  <Badge variant="secondary" className="h-4 px-1 text-[10px]">
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
    <div className="ml-10 overflow-hidden rounded-xl ring-1 ring-border/50">
      <button
        type="button"
        onClick={() => hasOutput && setExpanded(!expanded)}
        className={cn(
          "flex w-full items-center gap-2 bg-accent/20 px-3 py-2 text-xs",
          hasOutput && "cursor-pointer hover:bg-accent/40"
        )}
      >
        <Wrench className="h-3 w-3 shrink-0 text-amber-400/70" />
        <span className="font-mono font-medium text-amber-400/90">{message.toolName}</span>
        <span className="flex-1" />
        {hasOutput && (expanded ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 text-muted-foreground" />)}
      </button>
      {expanded && message.content && (
        <div className="border-t border-border/50 bg-background/50 p-3">
          {renderer.renderToolOutput(message.content)}
        </div>
      )}
    </div>
  );
}
