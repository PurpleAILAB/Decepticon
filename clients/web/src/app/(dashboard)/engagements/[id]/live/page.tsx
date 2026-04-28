"use client";

import { useState, useCallback, useEffect } from "react";
import { useParams } from "next/navigation";
import type { AgentConfig } from "@/lib/agents";
import { AgentGraphCanvas } from "@/components/agents/agent-graph-canvas";
import { WebTerminal } from "@/components/terminal/web-terminal";
import { useRunObserver } from "@/hooks/useRunObserver";
import { useAgents } from "@/hooks/useAgents";

interface EngagementMeta {
  name: string;
}

const REQUIRED_PLAN_DOCS = ["roe", "conops", "deconfliction"] as const;

/** Decide which assistant the CLI should connect to.
 *
 * The launcher's engagement.Select makes the same choice for the CLI: an
 * engagement with all three planning docs is "ready" and routes to
 * decepticon; anything missing means soundwave still has an interview to
 * run. plan-docs is the source of truth — engagement.status drifts when
 * the operator switches between web and CLI.
 */
function pickAssistant(planDocs: Record<string, unknown>): "soundwave" | "decepticon" {
  for (const name of REQUIRED_PLAN_DOCS) {
    if (planDocs[name] == null) return "soundwave";
  }
  return "decepticon";
}

export default function LivePage() {
  const params = useParams();
  const engagementId = params.id as string;

  const { agents } = useAgents();
  const [selectedAgent, setSelectedAgent] = useState<AgentConfig | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [engagement, setEngagement] = useState<EngagementMeta | null>(null);
  const [agentId, setAgentId] = useState<"soundwave" | "decepticon" | null>(null);

  // Resolve the slug + assistant before mounting the terminal. Mounting it
  // earlier would spawn the PTY with wrong env (defaulting to soundwave with
  // an empty slug), forcing a reconnect once the data lands.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [engRes, planRes] = await Promise.all([
          fetch(`/api/engagements/${engagementId}`),
          fetch(`/api/engagements/${engagementId}/plan-docs`),
        ]);
        if (!engRes.ok) return;
        const eng = (await engRes.json()) as EngagementMeta;
        const planDocs = planRes.ok ? ((await planRes.json()) as Record<string, unknown>) : {};
        if (cancelled) return;
        setEngagement(eng);
        setAgentId(pickAssistant(planDocs));
      } catch (err) {
        console.error("[LivePage] Failed to resolve engagement:", err);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [engagementId]);

  const { events } = useRunObserver({ threadId });

  const handleThreadId = useCallback((tid: string) => {
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
        {engagement && agentId ? (
          <WebTerminal
            engagementId={engagementId}
            engagementSlug={engagement.name}
            agentId={agentId}
            className="h-full"
            onThreadId={handleThreadId}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-white/40 text-sm">
            Loading engagement…
          </div>
        )}
      </div>
    </div>
  );
}
