"use client";

/**
 * useForceSimulation — d3-force physics layout for the agent graph.
 *
 * Runs a force simulation with repulsion, linking, centering, and collision
 * avoidance. Returns a snapshot of node positions on each tick so React
 * can re-render the SVG.
 */

import { useEffect, useMemo, useRef, useCallback, useState } from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceX,
  forceY,
  forceCollide,
  type Simulation,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import type { GraphNode, GraphEdge } from "@/lib/graph/types";

interface ForceNode extends SimulationNodeDatum {
  id: string;
  radius: number;
  pinned: boolean;
}

interface ForceParams {
  repelStrength: number;
  repelDistanceMax: number;
  linkDistance: number;
  linkStrength: number;
  positionStrength: number;
  collisionPadding: number;
  velocityDecay: number;
  alphaDecay: number;
}

const DEFAULT_FORCE_PARAMS: ForceParams = {
  repelStrength: -350,
  repelDistanceMax: 500,
  linkDistance: 120,
  linkStrength: 0.3,
  positionStrength: 0.05,
  collisionPadding: 40,
  velocityDecay: 0.4,
  alphaDecay: 0.02,
};

interface UseForceSimulationOptions {
  nodes: GraphNode[];
  edges: GraphEdge[];
  params?: Partial<ForceParams>;
}

interface UseForceSimulationReturn {
  /** Current node positions snapshot (triggers re-render on tick). */
  positions: Map<string, { x: number; y: number }>;
  /** Pin a node at its current position (for dragging). */
  pinNode: (id: string, x: number, y: number) => void;
  /** Unpin a node and let forces resume. */
  unpinNode: (id: string) => void;
  /** Reheat the simulation (e.g. after topology changes). */
  reheat: () => void;
}

export function useForceSimulation({
  nodes,
  edges,
  params: userParams,
}: UseForceSimulationOptions): UseForceSimulationReturn {
  const p = { ...DEFAULT_FORCE_PARAMS, ...userParams };
  const simRef = useRef<Simulation<ForceNode, SimulationLinkDatum<ForceNode>> | null>(null);
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map());
  // Preserve positions and pinned state across simulation rebuilds
  const prevPositionsRef = useRef<Map<string, { x: number; y: number; fx: number | null; fy: number | null }>>(new Map());
  const posMapRef = useRef(new Map<string, { x: number; y: number }>());

  // Stable keys for topology change detection
  const nodeKey = useMemo(() => nodes.map((n) => n.id).join(","), [nodes]);
  const edgeKey = useMemo(() => edges.map((e) => `${e.source}-${e.target}`).join(","), [edges]);

  // Build / rebuild simulation when topology changes
  useEffect(() => {
    // prevPositionsRef is populated by the PREVIOUS effect's cleanup (see below)
    const forceNodes: ForceNode[] = nodes.map((n) => {
      const prev = prevPositionsRef.current.get(n.id);
      return {
        id: n.id,
        x: prev?.x ?? n.x,
        y: prev?.y ?? n.y,
        vx: 0,
        vy: 0,
        radius: n.radius,
        pinned: n.pinned || (prev?.fx != null),
        // Restore pinned position if node was previously pinned
        ...(prev?.fx != null ? { fx: prev.fx, fy: prev.fy } : {}),
      };
    });

    const forceEdges: SimulationLinkDatum<ForceNode>[] = edges.map((e) => ({
      source: e.source,
      target: e.target,
    }));

    const sim = forceSimulation<ForceNode>(forceNodes)
      .force(
        "link",
        forceLink<ForceNode, SimulationLinkDatum<ForceNode>>(forceEdges)
          .id((d) => d.id)
          .distance(p.linkDistance)
          .strength(p.linkStrength),
      )
      .force(
        "charge",
        forceManyBody<ForceNode>()
          .strength(p.repelStrength)
          .distanceMax(p.repelDistanceMax),
      )
      .force("x", forceX<ForceNode>(0).strength(p.positionStrength))
      .force("y", forceY<ForceNode>(0).strength(p.positionStrength))
      .force(
        "collide",
        forceCollide<ForceNode>((d) => d.radius + p.collisionPadding),
      )
      .velocityDecay(p.velocityDecay)
      .alphaDecay(p.alphaDecay)
      .on("tick", () => {
        posMapRef.current.clear();
        for (const n of forceNodes) {
          if (n.pinned && n.fx == null) {
            n.fx = n.x;
            n.fy = n.y;
          }
          posMapRef.current.set(n.id, { x: n.x ?? 0, y: n.y ?? 0 });
        }
        setPositions(new Map(posMapRef.current));
      });

    simRef.current = sim;

    return () => {
      // Save positions + pinned state BEFORE destroying — next effect reads prevPositionsRef
      const prev = new Map<string, { x: number; y: number; fx: number | null; fy: number | null }>();
      for (const n of sim.nodes()) {
        prev.set(n.id, { x: n.x ?? 0, y: n.y ?? 0, fx: n.fx ?? null, fy: n.fy ?? null });
      }
      prevPositionsRef.current = prev;
      sim.stop();
      simRef.current = null;
    };
    // Re-run when node/edge IDs change (serialized for stable deps)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeKey, edgeKey]);

  const pinNode = useCallback((id: string, x: number, y: number) => {
    const sim = simRef.current;
    if (!sim) return;
    const node = sim.nodes().find((n) => n.id === id);
    if (node) {
      node.fx = x;
      node.fy = y;
      node.pinned = true;
      sim.alpha(0.3).restart();
    }
  }, []);

  const unpinNode = useCallback((id: string) => {
    const sim = simRef.current;
    if (!sim) return;
    const node = sim.nodes().find((n) => n.id === id);
    if (node) {
      node.fx = null;
      node.fy = null;
      node.pinned = false;
      sim.alpha(0.3).restart();
    }
  }, []);

  const reheat = useCallback(() => {
    simRef.current?.alpha(0.5).restart();
  }, []);

  return { positions, pinNode, unpinNode, reheat };
}
