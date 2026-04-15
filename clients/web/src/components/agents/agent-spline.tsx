"use client";

import { Suspense, useState, useEffect } from "react";
import type { AgentConfig } from "@/lib/agents";

interface AgentSplineProps {
  agent: AgentConfig;
  size?: number;
  interactive?: boolean;
}

function EmojiAvatar({ emoji, mascot, size }: { emoji: string; mascot: string; size: number }) {
  return (
    <span
      className="select-none"
      style={{ fontSize: size * 0.6 }}
      role="img"
      aria-label={mascot}
    >
      {emoji}
    </span>
  );
}

/**
 * 3D GLB model viewer with emoji fallback.
 * Place models at public/models/[agent-id].glb and set hasModel: true in agents.ts
 */
export function AgentSpline({ agent, size = 64, interactive = false }: AgentSplineProps) {
  const [Scene, setScene] = useState<React.ComponentType<{
    agentId: string;
    color: string;
    size: number;
    interactive: boolean;
  }> | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (!agent.hasModel) return;
    import("./agent-scene")
      .then((mod) => setScene(() => mod.AgentScene))
      .catch(() => setLoadError(true));
  }, [agent.hasModel]);

  if (!agent.hasModel || loadError || !Scene) {
    return <EmojiAvatar emoji={agent.mascotEmoji} mascot={agent.mascot} size={size} />;
  }

  return (
    <Suspense fallback={<EmojiAvatar emoji={agent.mascotEmoji} mascot={agent.mascot} size={size} />}>
      <Scene agentId={agent.id} color={agent.color} size={size} interactive={interactive} />
    </Suspense>
  );
}
