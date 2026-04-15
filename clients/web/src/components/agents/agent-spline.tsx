"use client";

import { Suspense } from "react";
import type { AgentConfig } from "@/lib/agents";
import { AgentScene } from "./agent-scene";

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

function ModelSkeleton({ size }: { size: number }) {
  return (
    <div
      className="animate-pulse rounded-2xl bg-white/[0.06]"
      style={{ width: size, height: size }}
    />
  );
}

/**
 * 3D GLB model viewer with shimmer skeleton fallback.
 * Agents without models (hasModel: false) render emoji instantly.
 * Agents with models render via the shared Canvas (AgentCanvasProvider).
 */
export function AgentSpline({ agent, size = 64, interactive = false }: AgentSplineProps) {
  if (!agent.hasModel) {
    return <EmojiAvatar emoji={agent.mascotEmoji} mascot={agent.mascot} size={size} />;
  }

  return (
    <Suspense fallback={<ModelSkeleton size={size} />}>
      <AgentScene agentId={agent.id} color={agent.color} size={size} interactive={interactive} />
    </Suspense>
  );
}
