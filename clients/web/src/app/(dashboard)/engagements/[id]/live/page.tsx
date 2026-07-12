"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import type { AgentConfig } from "@/lib/agents";
import { AgentGraphCanvas } from "@/components/agents/agent-graph-canvas";
import { useEngagementContext } from "@/lib/engagement-context";
import { useAgents } from "@/hooks/useAgents";
import { LiveActivityFeed } from "@/components/streaming/live-activity-feed";
import { OpplanLiveOverlay } from "@/components/streaming/opplan-live-overlay";
import { AgentDetailPanel } from "@/components/streaming/agent-detail-panel";
import { ApprovalGate } from "@/components/streaming/approval-gate";

export default function LivePage() {
  const params = useParams();
  const engagementId = params.id as string;

  const { agents } = useAgents();
  const [selectedAgent, setSelectedAgent] = useState<AgentConfig | null>(null);

  // Observer + terminal are managed by the engagement layout — they persist
  // across tab switches so events and PTY connection survive navigation.
  const { events } = useEngagementContext();

  function handleAgentClick(agent: AgentConfig) {
    setSelectedAgent(
      selectedAgent?.id === agent.id ? null : agent,
    );
  }

  return (
    <div className="grid h-full min-h-0 min-w-0 grid-rows-[minmax(420px,1fr)_240px] overflow-hidden xl:grid-cols-[320px_minmax(520px,1fr)] xl:grid-rows-1">
      {/* Left: Activity Feed */}
      <div className="relative order-2 min-h-0 overflow-hidden border-t border-white/[0.08] xl:order-none xl:border-r xl:border-t-0">
        <LiveActivityFeed events={events} engagementId={engagementId} />
        {selectedAgent && (
          <div className="absolute inset-0 z-20">
            <AgentDetailPanel
              agent={selectedAgent}
              events={events}
              onClose={() => setSelectedAgent(null)}
            />
          </div>
        )}
      </div>

      {/* Center: Agent Execution Graph + OPPLAN overlay */}
      <div className="relative order-1 min-h-0 min-w-0 overflow-hidden xl:order-none">
        <AgentGraphCanvas
          agents={agents}
          events={events}
          selectedAgent={selectedAgent}
          onAgentClick={handleAgentClick}
        />
        <div className="absolute inset-x-3 bottom-3 z-10 md:inset-auto md:right-4 md:top-4">
          <OpplanLiveOverlay engagementId={engagementId} />
        </div>
        {/* HITL approval gates — surface prominently during a run */}
        <div className="absolute left-3 top-3 z-30 w-[min(360px,calc(100%-1.5rem))] sm:left-4 sm:top-4 sm:max-w-[calc(100%-2rem)]">
          <ApprovalGate engagementId={engagementId} />
        </div>
      </div>

      {/* Right column (terminal) is rendered by the engagement layout.
           It persists across tab switches — no more reset on navigation. */}
    </div>
  );
}
