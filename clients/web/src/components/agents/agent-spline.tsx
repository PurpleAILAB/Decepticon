"use client";

import { lazy, Suspense } from "react";
import type { AgentConfig } from "@/lib/agents";

const Spline = lazy(() => import("@splinetool/react-spline"));

interface AgentSplineProps {
  agent: AgentConfig;
  size?: number;
}

/**
 * Renders a Spline 3D scene for the agent when splineUrl is available.
 * Falls back to a large mascot emoji when no Spline scene is configured.
 *
 * To add a Spline scene for an agent:
 * 1. Design the 3D mascot in Spline (spline.design)
 * 2. Publish the scene and copy the production URL
 * 3. Set the splineUrl in src/lib/agents.ts
 */
export function AgentSpline({ agent, size = 64 }: AgentSplineProps) {
  if (agent.splineUrl) {
    return (
      <Suspense
        fallback={
          <span style={{ fontSize: size * 0.6 }} role="img" aria-label={agent.mascot}>
            {agent.mascotEmoji}
          </span>
        }
      >
        <div style={{ width: size, height: size }} className="overflow-hidden rounded-xl">
          <Spline scene={agent.splineUrl} />
        </div>
      </Suspense>
    );
  }

  return (
    <span
      className="select-none"
      style={{ fontSize: size * 0.6 }}
      role="img"
      aria-label={agent.mascot}
    >
      {agent.mascotEmoji}
    </span>
  );
}
