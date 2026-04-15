"use client";

import { Suspense, useState, useEffect } from "react";
import type { AgentConfig } from "@/lib/agents";

interface AgentSplineProps {
  agent: AgentConfig;
  size?: number;
  interactive?: boolean;
}

// Track which models exist
const checkedModels = new Map<string, boolean>();

function useModelExists(agentId: string): boolean {
  const [exists, setExists] = useState(() => checkedModels.get(agentId) ?? false);

  useEffect(() => {
    if (checkedModels.has(agentId)) {
      setExists(checkedModels.get(agentId)!);
      return;
    }
    fetch(`/models/${agentId}.glb`, { method: "HEAD" })
      .then((res) => {
        checkedModels.set(agentId, res.ok);
        setExists(res.ok);
      })
      .catch(() => {
        checkedModels.set(agentId, false);
        setExists(false);
      });
  }, [agentId]);

  return exists;
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
 * Place models at public/models/[agent-id].glb
 */
export function AgentSpline({ agent, size = 64, interactive = false }: AgentSplineProps) {
  const hasModel = useModelExists(agent.id);
  const [Scene, setScene] = useState<React.ComponentType<{
    agentId: string;
    color: string;
    size: number;
    interactive: boolean;
  }> | null>(null);

  // Lazy load the 3D scene only when model exists (avoids loading Three.js for emoji-only agents)
  useEffect(() => {
    if (!hasModel) return;
    import("./agent-scene").then((mod) => setScene(() => mod.AgentScene));
  }, [hasModel]);

  if (!hasModel || !Scene) {
    return <EmojiAvatar emoji={agent.mascotEmoji} mascot={agent.mascot} size={size} />;
  }

  return (
    <Suspense fallback={<EmojiAvatar emoji={agent.mascotEmoji} mascot={agent.mascot} size={size} />}>
      <Scene agentId={agent.id} color={agent.color} size={size} interactive={interactive} />
    </Suspense>
  );
}
