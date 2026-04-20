"use client";

/**
 * SessionNode — small SVG node for active tool calls.
 *
 * One node per unique tool name per agent.
 * Active: pulse animation. Completed: dimmed.
 */

import type { GraphNode } from "@/lib/graph/types";

interface SessionNodeProps {
  node: GraphNode;
  x: number;
  y: number;
}

export function SessionNode({ node, x, y }: SessionNodeProps) {
  const r = node.radius;
  const isActive = node.type === "tool-session";
  const color = isActive ? node.color : "#6b7280";

  return (
    <g transform={`translate(${x}, ${y})`}>
      <circle
        r={r}
        fill={`${color}${isActive ? "60" : "30"}`}
        stroke={color}
        strokeWidth={1}
        className={isActive ? "agent-card-pulse" : undefined}
      />

      <text
        y={r + 12}
        textAnchor="middle"
        fill={isActive ? "#d1d5db" : "#6b7280"}
        fontSize={9}
        className="canvas-node-label"
      >
        {node.label}
      </text>
    </g>
  );
}
