"use client";

/**
 * AgentGraphCanvas — force-directed graph visualization of agent execution.
 *
 * Replaces the 3D model panel in the Live page. Shows all agents as nodes
 * in a physics-based layout with the orchestrator (Decepticon) at center.
 * Active agents glow and edges animate with flowing dots.
 *
 * Includes:
 * - Toolbar with fit-to-view
 * - Waiting notification bars for blocked agents
 * - Pan/zoom via mouse
 */

import { useCallback, useEffect, useMemo, useRef } from "react";
import { Maximize2 } from "lucide-react";
import type { AgentConfig } from "@/lib/agents";
import type { SubagentCustomEvent } from "@decepticon/streaming";
import type { GraphNode } from "@/lib/graph/types";
import { isWaitingState } from "@/lib/graph/types";
import { useForceSimulation } from "@/hooks/useForceSimulation";
import { useCanvasTransform } from "@/hooks/useCanvasTransform";
import { useAgentActivity } from "@/hooks/useAgentActivity";
import { AgentNode } from "./agent-node";
import { SessionNode } from "./session-node";
import { GraphEdgeComponent } from "./graph-edge";
import "@/styles/canvas-graph.css";

interface AgentGraphCanvasProps {
  agents: AgentConfig[];
  events: SubagentCustomEvent[];
  selectedAgent: AgentConfig | null;
  onAgentClick: (agent: AgentConfig) => void;
}

export function AgentGraphCanvas({
  agents,
  events,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  selectedAgent,
  onAgentClick,
}: AgentGraphCanvasProps) {
  const containerRef = useRef<SVGSVGElement>(null);
  const hasFitted = useRef(false);

  const { nodes, edges } = useAgentActivity({
    agents,
    events,
  });

  const { positions, pinNode } = useForceSimulation({ nodes, edges });
  const {
    transformAttr,
    onWheel,
    onMouseDown: onPanStart,
    onMouseMove: onPanMove,
    onMouseUp: onPanEnd,
    isPanning,
    fitToViewport,
    transform,
  } = useCanvasTransform();

  const nodeById = useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const n of nodes) map.set(n.id, n);
    return map;
  }, [nodes]);

  useEffect(() => {
    hasFitted.current = false;
  }, [agents]);

  const positionsRef = useRef(positions);
  positionsRef.current = positions;

  const fitNow = useCallback(() => {
    const svg = containerRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const posArray = Array.from(positionsRef.current.values());
    if (posArray.length > 0) {
      fitToViewport(posArray, rect.width, rect.height);
    }
  }, [fitToViewport]);

  useEffect(() => {
    if (hasFitted.current || positions.size === 0) return;
    const timer = setTimeout(() => {
      fitNow();
      hasFitted.current = true;
    }, 800);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positions.size > 0, fitNow]);

  useEffect(() => {
    const svg = containerRef.current;
    if (!svg) return;
    let prevWidth = svg.getBoundingClientRect().width;
    let resizeTimer: ReturnType<typeof setTimeout>;
    const observer = new ResizeObserver(() => {
      const newWidth = svg.getBoundingClientRect().width;
      if (Math.abs(newWidth - prevWidth) < 10) return;
      prevWidth = newWidth;
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(fitNow, 550);
    });
    observer.observe(svg);
    return () => { observer.disconnect(); clearTimeout(resizeTimer); };
  }, [fitNow]);

  // Register wheel listener as non-passive so preventDefault works (zoom)
  useEffect(() => {
    const svg = containerRef.current;
    if (!svg) return;
    const handler = (e: WheelEvent) => onWheel(e as unknown as React.WheelEvent);
    svg.addEventListener("wheel", handler, { passive: false });
    return () => svg.removeEventListener("wheel", handler);
  }, [onWheel]);

  // Global mouse move/up for panning
  useEffect(() => {
    if (!isPanning) return;
    const handleMove = (e: MouseEvent) => onPanMove(e);
    const handleUp = () => onPanEnd();
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
  }, [isPanning, onPanMove, onPanEnd]);

  // Node drag state — tracks graph-space position directly to avoid stale closures
  const DRAG_THRESHOLD = 5; // px — distinguish click from drag
  const dragRef = useRef<{
    nodeId: string;
    screenX: number;
    screenY: number;
    originScreenX: number;
    originScreenY: number;
    nodeX: number;
    nodeY: number;
    didDrag: boolean;
  } | null>(null);
  const dragCleanupRef = useRef<(() => void) | null>(null);
  // Refs for values needed inside drag handlers (avoids stale closures)
  const transformRef = useRef(transform);
  transformRef.current = transform;

  useEffect(() => {
    return () => { dragCleanupRef.current?.(); };
  }, []);

  const handleNodeDragStart = useCallback((node: GraphNode, e: React.MouseEvent) => {
    const currentPos = positionsRef.current.get(node.id);
    if (!currentPos) return;

    dragRef.current = {
      nodeId: node.id,
      screenX: e.clientX,
      screenY: e.clientY,
      originScreenX: e.clientX,
      originScreenY: e.clientY,
      nodeX: currentPos.x,
      nodeY: currentPos.y,
      didDrag: false,
    };

    const handleDragMove = (me: MouseEvent) => {
      const drag = dragRef.current;
      if (!drag) return;

      // Check if movement exceeds threshold
      const totalDx = me.clientX - drag.originScreenX;
      const totalDy = me.clientY - drag.originScreenY;
      if (!drag.didDrag && Math.sqrt(totalDx * totalDx + totalDy * totalDy) < DRAG_THRESHOLD) {
        return; // Not a drag yet
      }
      drag.didDrag = true;

      const scale = transformRef.current.scale || 1;
      const dx = (me.clientX - drag.screenX) / scale;
      const dy = (me.clientY - drag.screenY) / scale;
      drag.screenX = me.clientX;
      drag.screenY = me.clientY;
      drag.nodeX += dx;
      drag.nodeY += dy;
      pinNode(drag.nodeId, drag.nodeX, drag.nodeY);
    };

    const handleDragEnd = () => {
      const wasDrag = dragRef.current?.didDrag ?? false;
      const nodeId = dragRef.current?.nodeId;
      dragRef.current = null;
      window.removeEventListener("mousemove", handleDragMove);
      window.removeEventListener("mouseup", handleDragEnd);
      dragCleanupRef.current = null;

      if (!wasDrag && nodeId) {
        const clickedNode = nodeById.get(nodeId);
        if (clickedNode) {
          const agent = agents.find((a) => a.id === clickedNode.agentId);
          if (agent) onAgentClick(agent);
        }
      }
    };

    window.addEventListener("mousemove", handleDragMove);
    window.addEventListener("mouseup", handleDragEnd);
    dragCleanupRef.current = handleDragEnd;
  }, [pinNode, nodeById, agents, onAgentClick]);

  const handleNodeClick = useCallback((node: GraphNode) => {
    const agent = agents.find((a) => a.id === node.agentId);
    if (agent) onAgentClick(agent);
  }, [agents, onAgentClick]);

  const handleFit = useCallback(() => {
    fitNow();
  }, [fitNow]);

  const waitingNodes = nodes.filter((n) => isWaitingState(n.runtimeState));

  return (
    <div className="relative h-full w-full">
      <div className="canvas-toolbar">
        <button
          className="canvas-toolbar-btn"
          onClick={handleFit}
          title="Fit to view"
        >
          <Maximize2 className="h-4 w-4" />
        </button>
      </div>

      {waitingNodes.length > 0 && (
        <div className="absolute left-4 top-[72px] z-10 flex flex-col gap-1">
          {waitingNodes.map((node) => (
            <button
              key={node.id}
              className="canvas-waiting-bar"
              onClick={() => handleNodeClick(node)}
            >
              <span className="canvas-waiting-bar-prefix">
                {node.runtimeState === "waiting_for_permission"
                  ? `${node.waitingToolName ?? "PERMISSION"}: `
                  : "Waiting: "}
              </span>
              {node.label}
            </button>
          ))}
        </div>
      )}

      <svg
        ref={containerRef}
        className="agent-graph-canvas h-full w-full"
        style={{ cursor: isPanning ? "grabbing" : "grab" }}
        onMouseDown={onPanStart}
      >
        <defs>
          <radialGradient id="nodeInnerGlow">
            <stop offset="0%" stopColor="white" stopOpacity={0.15} />
            <stop offset="100%" stopColor="white" stopOpacity={0} />
          </radialGradient>
        </defs>

        <g transform={transformAttr}>
          {edges.map((edge) => {
            const sourcePos = positions.get(edge.source);
            const targetPos = positions.get(edge.target);
            if (!sourcePos || !targetPos) return null;
            const sourceNode = nodeById.get(edge.source);
            const targetNode = nodeById.get(edge.target);
            return (
              <GraphEdgeComponent
                key={`${edge.source}-${edge.target}`}
                edgeId={`${edge.source}-${edge.target}`}
                sourceX={sourcePos.x}
                sourceY={sourcePos.y}
                targetX={targetPos.x}
                targetY={targetPos.y}
                active={edge.active}
                color={targetNode?.color ?? "#6b7280"}
                sourceRadius={sourceNode?.radius ?? 48}
                targetRadius={targetNode?.radius ?? 32}
              />
            );
          })}

          {nodes.map((node) => {
            const pos = positions.get(node.id);
            if (!pos) return null;

            if (node.type === "tool-session" || node.type === "completed-session") {
              return (
                <SessionNode
                  key={node.id}
                  node={node}
                  x={pos.x}
                  y={pos.y}
                />
              );
            }

            return (
              <AgentNode
                key={node.id}
                node={node}
                x={pos.x}
                y={pos.y}
                onDragStart={handleNodeDragStart}
              />
            );
          })}
        </g>
      </svg>
    </div>
  );
}
