"use client";

import { groupByKillChain, type AgentConfig } from "@/lib/agents";
import { AgentSpline } from "./agent-spline";

interface AgentGridProps {
  agents: AgentConfig[];
  onAgentClick: (agent: AgentConfig) => void;
}

export function AgentGrid({ agents, onAgentClick }: AgentGridProps) {
  const groups = groupByKillChain(agents);

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {groups.map((group) => (
        <section key={group.role}>
          {/* Section header — centered divider with label */}
          <div className="flex items-center gap-3 mb-3 px-1">
            <div className="h-px flex-1 bg-white/[0.06]" />
            <h2 className="text-[11px] font-medium uppercase tracking-widest text-zinc-500 shrink-0">
              {group.label}
            </h2>
            <div className="h-px flex-1 bg-white/[0.06]" />
          </div>

          {/* Agent buttons */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            {group.agents.map((agent, i) => (
              <button
                key={agent.id}
                onClick={() => onAgentClick(agent)}
                className="group flex flex-col items-center gap-2 rounded-2xl p-5 transition-all duration-300 hover:bg-white/[0.04] hover:scale-105"
              >
                <div
                  className="transition-transform duration-300 group-hover:scale-110"
                  style={{
                    animation: `float ${3 + (i % 3) * 0.5}s ease-in-out infinite`,
                    animationDelay: `${i * 0.2}s`,
                  }}
                >
                  <AgentSpline agent={agent} size={56} />
                </div>
                <h3 className="text-sm font-semibold text-white">{agent.name}</h3>
                <p className="text-[11px] text-zinc-500 text-center leading-relaxed line-clamp-2">
                  {agent.description}
                </p>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
