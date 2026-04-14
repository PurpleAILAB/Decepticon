"use client";

import { useEffect, useRef, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { ChatMessage, DocumentRef, MessageRenderer } from "@/lib/chat/types";
import { defaultRenderer } from "@/lib/chat/markdown-renderer";
import {
  Bot,
  Send,
  Wrench,
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatViewProps {
  messages: ChatMessage[];
  onSend?: (message: string) => void;
  onDocumentClick?: (doc: DocumentRef) => void;
  isStreaming?: boolean;
  agentName?: string;
  renderer?: MessageRenderer;
}

export function ChatView({
  messages,
  onSend,
  onDocumentClick,
  isStreaming = false,
  agentName = "Soundwave",
  renderer = defaultRenderer,
}: ChatViewProps) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  function handleSend() {
    if (!input.trim() || !onSend) return;
    onSend(input.trim());
    setInput("");
  }

  const isEmpty = messages.length === 0 && !isStreaming;

  return (
    <div className="flex h-full flex-col bg-[#0a0a14]">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-white/5 px-5 py-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-red-500/20 to-red-900/20 ring-1 ring-red-500/20">
          <Sparkles className="h-4 w-4 text-red-400" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-white">{agentName}</h3>
          <p className="text-xs text-zinc-500">
            {isStreaming ? (
              <span className="flex items-center gap-1.5 text-emerald-400">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                Responding...
              </span>
            ) : (
              "AI Security Agent"
            )}
          </p>
        </div>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1" ref={scrollRef}>
        <div className="mx-auto max-w-3xl space-y-1 px-5 py-5">
          {isEmpty && (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-red-500/10 to-red-900/10 ring-1 ring-red-500/10">
                <Sparkles className="h-6 w-6 text-red-400/60" />
              </div>
              <h3 className="text-base font-medium text-white">Start a conversation</h3>
              <p className="mt-1 max-w-sm text-sm text-zinc-500">
                Describe your target and I&apos;ll conduct a threat assessment interview to generate
                your engagement documents (RoE, CONOPS, OPPLAN).
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              renderer={renderer}
              onDocumentClick={onDocumentClick}
            />
          ))}

          {isStreaming && messages[messages.length - 1]?.role !== "assistant" && (
            <div className="flex items-start gap-3 py-3">
              <AgentAvatar />
              <div className="flex items-center gap-2 rounded-xl bg-white/[0.03] px-4 py-3 ring-1 ring-white/5">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-red-400" />
                <span className="text-xs text-zinc-500">Thinking...</span>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input */}
      {onSend && (
        <div className="border-t border-white/5 p-4">
          <div className="mx-auto flex max-w-3xl items-center gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder={isEmpty ? "Describe your target..." : `Message ${agentName}...`}
              disabled={isStreaming}
              className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white placeholder-zinc-600 outline-none transition-colors focus:border-red-500/50 focus:ring-1 focus:ring-red-500/20 disabled:opacity-50"
            />
            <Button
              size="icon"
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              className="h-11 w-11 shrink-0 rounded-xl bg-red-600 hover:bg-red-500"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function AgentAvatar() {
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-red-500/20 to-red-900/20 ring-1 ring-red-500/10">
      <Bot className="h-3.5 w-3.5 text-red-400" />
    </div>
  );
}

function ToolCallBlock({ message, renderer }: { message: ChatMessage; renderer: MessageRenderer }) {
  const [expanded, setExpanded] = useState(false);
  const hasOutput = !!message.content;

  return (
    <div className="ml-10 my-1 overflow-hidden rounded-xl ring-1 ring-white/5">
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
        {message.toolArgs && (
          <span className="truncate font-mono text-zinc-600">
            {Object.values(message.toolArgs).map(String).join(" ").slice(0, 50)}
          </span>
        )}
        <span className="flex-1" />
        {hasOutput && (
          expanded
            ? <ChevronDown className="h-3 w-3 text-zinc-600" />
            : <ChevronRight className="h-3 w-3 text-zinc-600" />
        )}
      </button>
      {expanded && message.content && (
        <div className="border-t border-white/5 bg-black/30 p-3">
          {renderer.renderToolOutput(message.content)}
        </div>
      )}
    </div>
  );
}

function MessageBubble({
  message,
  renderer,
  onDocumentClick,
}: {
  message: ChatMessage;
  renderer: MessageRenderer;
  onDocumentClick?: (doc: DocumentRef) => void;
}) {
  const isUser = message.role === "user";
  const isTool = message.role === "tool";
  const isSystem = message.role === "system";

  if (isTool) return <ToolCallBlock message={message} renderer={renderer} />;

  if (isSystem) {
    return (
      <div className="my-2 flex justify-center">
        <span className="rounded-full bg-white/[0.03] px-3 py-1 text-[11px] text-zinc-500 ring-1 ring-white/5">
          {renderer.renderAssistantContent(message.content)}
        </span>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="flex justify-end py-2">
        <div className="max-w-[75%] rounded-2xl rounded-br-md bg-red-600 px-4 py-2.5">
          <p className="text-sm leading-relaxed text-white whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="py-3">
      <div className="mb-1.5 flex items-center gap-2 pl-10">
        {message.agent && (
          <span className="text-[11px] font-medium text-red-400/70">{message.agent}</span>
        )}
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
        <AgentAvatar />
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
