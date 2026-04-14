"use client";

import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Terminal, MessageSquare, Wrench, Bot } from "lucide-react";

interface StreamEvent {
  id: string;
  type: string;
  agent?: string;
  tool?: string;
  args?: Record<string, unknown>;
  content?: string;
  text?: string;
  prompt?: string;
  status?: string;
  elapsed?: number;
  timestamp: number;
}

interface StreamingViewProps {
  engagementId: string;
  isRunning: boolean;
  mockEvents?: StreamEvent[];
}

export function StreamingView({ engagementId, isRunning, mockEvents }: StreamingViewProps) {
  const [events, setEvents] = useState<StreamEvent[]>(() => mockEvents ?? []);
  const [connected, setConnected] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const eventIdRef = useRef(0);

  useEffect(() => {
    if (mockEvents && mockEvents.length > 0) return;
    if (!isRunning) return;

    const eventSource = new EventSource(
      `/api/engagements/${engagementId}/stream`
    );

    eventSource.onopen = () => setConnected(true);

    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        const event: StreamEvent = {
          ...data,
          id: String(eventIdRef.current++),
          timestamp: Date.now(),
        };
        setEvents((prev) => [...prev, event]);
      } catch {
        // Skip malformed events
      }
    };

    eventSource.onerror = () => {
      setConnected(false);
      eventSource.close();
    };

    return () => {
      eventSource.close();
      setConnected(false);
    };
  }, [engagementId, isRunning, mockEvents]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  if (!isRunning && events.length === 0 && (!mockEvents || mockEvents.length === 0)) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-16">
          <div className="text-center text-sm text-muted-foreground">
            <Terminal className="mx-auto mb-3 h-8 w-8 opacity-50" />
            <p>Click &quot;Run&quot; to start the engagement.</p>
            <p className="mt-1 text-xs">
              Soundwave will interview you, generate an OPPLAN, then execute
              objectives.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="text-base">Live Stream</CardTitle>
        <div className="flex items-center gap-2">
          {connected && (
            <Badge variant="outline" className="gap-1 text-green-400">
              <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
              Connected
            </Badge>
          )}
          <Badge variant="secondary">{events.length} events</Badge>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[500px]" ref={scrollRef}>
          <div className="space-y-1 p-4 font-mono text-xs">
            {events.map((event) => (
              <EventLine key={event.id} event={event} />
            ))}
            {isRunning && connected && (
              <div className="flex items-center gap-2 py-1 text-muted-foreground">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400" />
                Streaming...
              </div>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function EventLine({ event }: { event: StreamEvent }) {
  switch (event.type) {
    case "subagent_start":
      return (
        <div className="flex items-center gap-2 py-1 text-blue-400">
          <Bot className="h-3.5 w-3.5" />
          <span className="font-medium">[{event.agent}]</span>
          <span className="text-muted-foreground">started</span>
          {event.prompt && (
            <span className="truncate text-muted-foreground/70">
              — {event.prompt}
            </span>
          )}
        </div>
      );

    case "subagent_tool_call":
      return (
        <div className="flex items-start gap-2 py-1 text-yellow-400">
          <Wrench className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span className="font-medium">{event.tool}</span>
          {event.args && (
            <span className="truncate text-muted-foreground">
              {JSON.stringify(event.args).slice(0, 120)}
            </span>
          )}
        </div>
      );

    case "subagent_tool_result":
      return (
        <div className="border-l-2 border-border py-1 pl-6">
          <pre className="max-h-32 overflow-hidden whitespace-pre-wrap text-muted-foreground">
            {(event.content ?? "").slice(0, 500)}
            {(event.content ?? "").length > 500 && "..."}
          </pre>
        </div>
      );

    case "subagent_message":
      return (
        <div className="flex items-start gap-2 py-1 text-foreground">
          <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 text-green-400" />
          <span className="whitespace-pre-wrap">{event.text}</span>
        </div>
      );

    case "subagent_end":
      return (
        <div className="flex items-center gap-2 py-1 text-blue-400/70">
          <Bot className="h-3.5 w-3.5" />
          <span>[{event.agent}]</span>
          <span className="text-muted-foreground">
            completed in {event.elapsed?.toFixed(1)}s
          </span>
        </div>
      );

    default:
      return (
        <div className="py-1 text-muted-foreground">
          {JSON.stringify(event)}
        </div>
      );
  }
}
