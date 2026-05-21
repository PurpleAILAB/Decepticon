"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import type { SubagentCustomEvent } from "@decepticon/streaming";

interface EngagementContextValue {
  engagementId: string;
  engagementSlug: string;
  agentId: "soundwave" | "decepticon";
  threadId: string | null;
  setThreadId: (id: string) => void;
  events: SubagentCustomEvent[];
  isRunning: boolean;
  activeRunId: string | null;
}

const EngagementContext = createContext<EngagementContextValue | null>(null);

export function useEngagementContext(): EngagementContextValue {
  const ctx = useContext(EngagementContext);
  if (!ctx) throw new Error("useEngagementContext must be used within EngagementProvider");
  return ctx;
}

interface EngagementProviderProps {
  children: ReactNode;
  engagementId: string;
  engagementSlug: string;
  agentId: "soundwave" | "decepticon";
  events: SubagentCustomEvent[];
  isRunning: boolean;
  activeRunId: string | null;
}

export function EngagementProvider({
  children,
  engagementId,
  engagementSlug,
  agentId,
  events,
  isRunning,
  activeRunId,
}: EngagementProviderProps) {
  const [threadId, setThreadId] = useState<string | null>(null);

  const handleSetThreadId = useCallback((id: string) => {
    setThreadId(id);
  }, []);

  return (
    <EngagementContext.Provider
      value={{
        engagementId,
        engagementSlug,
        agentId,
        threadId,
        setThreadId: handleSetThreadId,
        events,
        isRunning,
        activeRunId,
      }}
    >
      {children}
    </EngagementContext.Provider>
  );
}
