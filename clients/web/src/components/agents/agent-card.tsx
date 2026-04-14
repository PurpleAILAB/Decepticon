"use client";

import type { AgentConfig } from "@/lib/agents";
import { cn } from "@/lib/utils";
import { AgentSpline } from "./agent-spline";

interface AgentCardProps {
  agent: AgentConfig;
  selected?: boolean;
  onClick?: () => void;
}

export function AgentCard({ agent, selected, onClick }: AgentCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative flex flex-col items-center gap-3 rounded-2xl border p-5 text-left transition-all duration-200",
        selected
          ? "border-transparent ring-2 shadow-lg shadow-primary/10"
          : "border-border/50 hover:border-border hover:shadow-md hover:shadow-black/10",
      )}
      style={{
        ...(selected ? { ringColor: agent.color, borderColor: agent.color } : {}),
      }}
    >
      {/* Colored accent top bar */}
      <div
        className="absolute inset-x-0 top-0 h-1 rounded-t-2xl transition-opacity"
        style={{ backgroundColor: agent.color, opacity: selected ? 1 : 0.3 }}
      />

      {/* Mascot area */}
      <div className={cn(
        "flex h-20 w-20 items-center justify-center rounded-2xl transition-transform duration-200",
        "bg-accent/50 group-hover:scale-105",
        selected && "scale-110"
      )}>
        <AgentSpline agent={agent} size={64} />
      </div>

      {/* Info */}
      <div className="text-center">
        <h3 className="text-sm font-semibold">{agent.name}</h3>
        <span
          className="mt-0.5 inline-block rounded-full px-2 py-0.5 text-[10px] font-medium"
          style={{ backgroundColor: `${agent.color}15`, color: agent.color }}
        >
          {agent.role}
        </span>
      </div>

      <p className="text-center text-xs text-muted-foreground leading-relaxed">
        {agent.description}
      </p>

      {/* Selection indicator */}
      {selected && (
        <div
          className="absolute -bottom-1 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full"
          style={{ backgroundColor: agent.color }}
        />
      )}
    </button>
  );
}
