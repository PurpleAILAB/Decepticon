"use client";

import { useState, useCallback } from "react";
import { useParams } from "next/navigation";
import type { AgentConfig } from "@/lib/agents";
import { AgentGraphCanvas } from "@/components/agents/agent-graph-canvas";
import { WebTerminal } from "@/components/terminal/web-terminal";
import { useRunObserver } from "@/hooks/useRunObserver";
import { useAgents } from "@/hooks/useAgents";

export default function LivePage() {
  const params = useParams();
  const engagementId = params.id as string;

  const { agents } = useAgents();
  const [selectedAgent, setSelectedAgent] = useState<AgentConfig | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);

  const { events } = useRunObserver({ threadId });

  const handleThreadId = useCallback((tid: string) => {
    console.log("[LivePage] Thread ID received:", tid);
    setThreadId(tid);
  }, []);

  function handleAgentClick(agent: AgentConfig) {
    setSelectedAgent(
      selectedAgent?.id === agent.id ? null : agent,
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: Agent Execution Graph */}
      <div className="w-1/2 overflow-hidden border-r border-white/[0.08]">
        <AgentGraphCanvas
          agents={agents}
          events={events}
          selectedAgent={selectedAgent}
          onAgentClick={handleAgentClick}
        />
      </div>

      {/* Right: CLI Terminal */}
      <div className="w-1/2 overflow-hidden">
        <WebTerminal
          engagementId={engagementId}
          agentId="decepticon"
          className="h-full"
          onThreadId={handleThreadId}
        />
      </div>
    </div>
  );
}
