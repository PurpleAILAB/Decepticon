"use client";

/**
 * AgentNode — SVG node for the force-directed graph.
 *
 * - Orchestrator (Decepticon): Custom mascot image
 * - Sub-agents: Initial avatar circle with agent color
 * - Active state: Pulse animation on border
 * - Completed: Checkmark badge
 */

import type { GraphNode } from "@/lib/graph/types";
import { isWaitingState } from "@/lib/graph/types";

const AMBER = "#f59e0b";

interface AgentNodeProps {
  node: GraphNode;
  x: number;
  y: number;
  onDragStart?: (node: GraphNode, e: React.MouseEvent) => void;
}

export function AgentNode({ node, x, y, onDragStart }: AgentNodeProps) {
  const isOrchestrator = node.type === "orchestrator";
  const { runtimeState } = node;

  const isProcessing = runtimeState === "processing";
  const isWaiting = isWaitingState(runtimeState);
  const isCompleted = runtimeState === "completed";
  const isFailed = runtimeState === "failed";
  const isIdle = runtimeState === "idle";
  const isActive = isProcessing || isWaiting;

  const color = isWaiting ? AMBER : node.color;

  // State-based pulse CSS class
  const pulseClass = isProcessing
    ? "agent-pulse-processing"
    : isWaiting
      ? "agent-pulse-waiting"
      : isCompleted
        ? "agent-pulse-completed"
        : isFailed
          ? "agent-pulse-failed"
          : undefined;
  const r = isOrchestrator ? 36 : 24;
  const initial = node.label.charAt(0).toUpperCase();

  const pillText = runtimeState === "waiting_for_permission"
    ? (node.waitingToolName?.slice(0, 14) ?? "PERMISSION")
    : runtimeState === "waiting_for_user"
      ? "WAITING"
      : null;
  const pillWidth = pillText ? pillText.length * 5.5 + 14 : 0;

  return (
    <g
      transform={`translate(${x}, ${y})`}
      className="cursor-pointer"
      onMouseDown={(e) => { e.stopPropagation(); onDragStart?.(node, e); }}
    >
      {/* Invisible hit area for reliable drag */}
      <circle r={r + 8} fill="transparent" />

      {isOrchestrator ? (
        <>
          {/* Orchestrator: mascot image */}
          <image
            href="/agents/decepticon.png"
            x={-r}
            y={-r}
            width={r * 2}
            height={r * 2}
            className={pulseClass}
            style={{ pointerEvents: "none", opacity: isIdle ? 0.5 : 1 }}
          />
        </>
      ) : (
        <>
          {/* Sub-agent: initial avatar */}
          <circle
            r={r}
            fill={`${color}${isIdle ? "10" : "20"}`}
            stroke={color}
            strokeWidth={1.5}
            className={pulseClass}
            style={{ pointerEvents: "none", opacity: isIdle ? 0.4 : 1 }}
          />
          <text
            textAnchor="middle"
            dominantBaseline="central"
            fill={color}
            fontSize={r * 0.9}
            fontWeight={700}
            className="select-none pointer-events-none"
            style={{ fontFamily: "system-ui, sans-serif" }}
          >
            {initial}
          </text>
        </>
      )}

      {/* Completed checkmark badge */}
      {isCompleted && (
        <g transform={`translate(${r * 0.7}, ${-r * 0.7})`}>
          <circle r={8} fill="#10b981" />
          <path
            d="M-3,0 L-1,3 L4,-2"
            fill="none"
            stroke="white"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </g>
      )}

      {/* Agent name below */}
      <text
        y={r + 14}
        textAnchor="middle"
        fill="#d1d5db"
        fontSize={11}
        fontWeight={isActive ? 600 : 400}
        opacity={isIdle ? 0.4 : 1}
        className="canvas-node-label"
      >
        {node.label}
      </text>

      {/* Waiting pill */}
      {pillText && (
        <g transform={`translate(0, ${r + 28})`}>
          <rect
            x={-pillWidth / 2}
            y={0}
            width={pillWidth}
            height={16}
            rx={8}
            fill={AMBER}
            className="canvas-waiting-pill"
          />
          <text
            textAnchor="middle"
            y={12}
            fill="#0a0e14"
            fontSize={9}
            fontWeight={700}
            className="select-none pointer-events-none"
          >
            {pillText}
          </text>
        </g>
      )}
    </g>
  );
}
