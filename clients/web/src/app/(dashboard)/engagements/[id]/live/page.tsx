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
    <div className="flex h-full overflow-hidden">
      {/* Left: Activity Feed */}
      <div className="relative w-1/4 min-w-[280px] overflow-hidden border-r border-white/[0.08]">
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
      <div className="relative flex-1 min-w-[400px] overflow-hidden">
        <AgentGraphCanvas
          agents={agents}
          events={events}
          selectedAgent={selectedAgent}
          onAgentClick={handleAgentClick}
        />
        <div className="absolute right-4 top-4 z-10">
          <OpplanLiveOverlay engagementId={engagementId} />
        </div>
      </div>

      {/* Right column (terminal) is rendered by the engagement layout.
           It persists across tab switches — no more reset on navigation. */}
    </div>
  );
}
