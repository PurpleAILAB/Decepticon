"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Panel,
} from "@xyflow/react";
import type { Node, Edge, NodeMouseHandler } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Network,
  Search,
  RotateCcw,
  Filter,
  X,
  ChevronDown,
} from "lucide-react";
import { GraphNode } from "../graph/graph-node";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface KGNodeData {
  label: string;
  nodeType: string;
  properties: Record<string, unknown>;
  [key: string]: unknown;
}

interface GraphPayload {
  nodes: Node<KGNodeData>[];
  edges: Edge[];
}

interface AttackGraphProps {
  /** Scope to a single engagement. Omit for cross-engagement view. */
  engagementId?: string;
  /** Pre-filter to specific node labels. */
  labelFilter?: string[];
}

// ---------------------------------------------------------------------------
// Force-directed layout (simple spring-electric model)
// ---------------------------------------------------------------------------

interface Vec2 {
  x: number;
  y: number;
}

function forceLayout(
  positions: Vec2[],
  edgePairs: [number, number][],
  iterations: number = 300,
): Vec2[] {
  const n = positions.length;
  if (n === 0) return [];

  const pos = positions.map((p) => ({ x: p.x, y: p.y }));
  const vel = Array.from<unknown, Vec2>({ length: n }, () => ({ x: 0, y: 0 }));

  const repulsion = 8000;
  const springK = 0.005;
  const springLen = 180;
  const damping = 0.9;
  const gravity = 0.01;

  for (let iter = 0; iter < iterations; iter++) {
    const temperature = 1 - iter / iterations;

    // Repulsion between all pairs (Barnes–Hut would be O(n log n) but n < 500 here)
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = pos[i].x - pos[j].x;
        let dy = pos[i].y - pos[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (repulsion / (dist * dist)) * temperature;
        dx = (dx / dist) * force;
        dy = (dy / dist) * force;
        vel[i].x += dx;
        vel[i].y += dy;
        vel[j].x -= dx;
        vel[j].y -= dy;
      }
    }

    // Spring attraction along edges
    for (const [si, ti] of edgePairs) {
      const dx = pos[ti].x - pos[si].x;
      const dy = pos[ti].y - pos[si].y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const displacement = dist - springLen;
      const force = springK * displacement * temperature;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      vel[si].x += fx;
      vel[si].y += fy;
      vel[ti].x -= fx;
      vel[ti].y -= fy;
    }

    // Center gravity
    for (let i = 0; i < n; i++) {
      vel[i].x -= pos[i].x * gravity;
      vel[i].y -= pos[i].y * gravity;
    }

    // Integrate
    for (let i = 0; i < n; i++) {
      vel[i].x *= damping;
      vel[i].y *= damping;
      pos[i].x += vel[i].x;
      pos[i].y += vel[i].y;
    }
  }

  return pos;
}

// ---------------------------------------------------------------------------
// Edge styling
// ---------------------------------------------------------------------------

function styleEdges(edges: Edge[]): Edge[] {
  return edges.map((e) => ({
    ...e,
    animated: true,
    style: { stroke: "hsl(var(--muted-foreground))", strokeWidth: 1.5 },
  }));
}

// ---------------------------------------------------------------------------
// Custom node types
// ---------------------------------------------------------------------------

const nodeTypes = { custom: GraphNode };

// ---------------------------------------------------------------------------
// Label colours for the filter panel
// ---------------------------------------------------------------------------

const LABEL_COLORS: Record<string, string> = {
  Host: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  Service: "bg-green-500/20 text-green-400 border-green-500/30",
  Vulnerability: "bg-red-500/20 text-red-400 border-red-500/30",
  CVE: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  User: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  Credential: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  Finding: "bg-pink-500/20 text-pink-400 border-pink-500/30",
  AttackPath: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
};

function labelBadgeClass(label: string): string {
  return LABEL_COLORS[label] ?? "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AttackGraph({
  engagementId,
  labelFilter: initialLabels,
}: AttackGraphProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<KGNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node<KGNodeData> | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [activeLabels, setActiveLabels] = useState<Set<string>>(
    new Set(initialLabels ?? []),
  );
  const [availableLabels, setAvailableLabels] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(false);

  // Raw graph data kept for re-filtering without refetching
  const rawRef = useRef<GraphPayload>({ nodes: [], edges: [] });

  // ------------------------------------------------------------------
  // Fetch
  // ------------------------------------------------------------------

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (engagementId) params.set("engagement", engagementId);
      if (activeLabels.size > 0) {
        params.set("labels", Array.from(activeLabels).join(","));
      }
      const url = `/api/graph${params.toString() ? `?${params}` : ""}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: GraphPayload = await res.json() as GraphPayload;

      // Extract unique labels
      const labels = Array.from(
        new Set(data.nodes.map((n) => String(n.data.nodeType))),
      ).sort();
      setAvailableLabels(labels);

      // Apply force layout
      const idxMap = new Map<string, number>();
      data.nodes.forEach((n, i) => idxMap.set(n.id, i));
      const initialPositions = data.nodes.map(() => ({
        x: (Math.random() - 0.5) * 600,
        y: (Math.random() - 0.5) * 600,
      }));
      const edgePairs: [number, number][] = data.edges
        .map((e) => [idxMap.get(e.source), idxMap.get(e.target)] as const)
        .filter(
          (pair): pair is [number, number] =>
            pair[0] !== undefined && pair[1] !== undefined,
        );
      const laid = forceLayout(initialPositions, edgePairs);
      const positioned = data.nodes.map((n, i) => ({
        ...n,
        position: { x: laid[i].x, y: laid[i].y },
      }));

      rawRef.current = { nodes: positioned, edges: data.edges };
      setNodes(positioned);
      setEdges(styleEdges(data.edges));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [engagementId, activeLabels, setNodes, setEdges]);

  useEffect(() => {
    void fetchGraph();
  }, [fetchGraph]);

  // ------------------------------------------------------------------
  // Client-side search filtering
  // ------------------------------------------------------------------

  const filteredNodes = useMemo(() => {
    if (!searchTerm.trim()) return rawRef.current.nodes;
    const term = searchTerm.toLowerCase();
    return rawRef.current.nodes.filter(
      (n) =>
        String(n.data.label).toLowerCase().includes(term) ||
        String(n.data.nodeType).toLowerCase().includes(term),
    );
  }, [searchTerm]);

  useEffect(() => {
    if (!searchTerm.trim()) {
      setNodes(rawRef.current.nodes);
      setEdges(styleEdges(rawRef.current.edges));
      return;
    }
    const visibleIds = new Set(filteredNodes.map((n) => n.id));
    setNodes(
      rawRef.current.nodes.map((n) => ({
        ...n,
        hidden: !visibleIds.has(n.id),
      })),
    );
    setEdges(
      styleEdges(
        rawRef.current.edges.filter(
          (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
        ),
      ),
    );
  }, [filteredNodes, searchTerm, setNodes, setEdges]);

  // ------------------------------------------------------------------
  // Handlers
  // ------------------------------------------------------------------

  const onNodeClick: NodeMouseHandler<Node<KGNodeData>> = useCallback(
    (_evt, node) => setSelectedNode(node),
    [],
  );

  const toggleLabel = useCallback((label: string) => {
    setActiveLabels((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }, []);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  if (loading) {
    return <Skeleton className="h-[600px] w-full rounded-lg" />;
  }

  if (error) {
    return (
      <Card className="border-destructive/40">
        <CardContent className="flex items-center gap-3 p-6">
          <Network className="h-5 w-5 text-destructive" />
          <div>
            <p className="text-sm font-medium text-destructive">
              Knowledge Graph Unavailable
            </p>
            <p className="text-xs text-muted-foreground">{error}</p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={() => void fetchGraph()}
          >
            <RotateCcw className="mr-1 h-3 w-3" />
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (nodes.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center p-12 text-center">
          <Network className="mb-4 h-10 w-10 text-muted-foreground" />
          <p className="text-sm font-medium">No graph data</p>
          <p className="text-xs text-muted-foreground">
            Run an engagement to populate the knowledge graph.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex gap-4">
      {/* Main graph */}
      <div className="relative h-[700px] flex-1 rounded-lg border bg-background">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} size={1} />
          <Controls />
          <MiniMap
            nodeStrokeWidth={2}
            className="!bg-background/80 !border-border"
          />

          {/* Search + Filter panel */}
          <Panel position="top-left" className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search nodes…"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="h-8 w-56 bg-background/90 pl-8 text-xs backdrop-blur"
                />
                {searchTerm && (
                  <button
                    onClick={() => setSearchTerm("")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
              <Button
                variant={showFilters ? "secondary" : "outline"}
                size="sm"
                onClick={() => setShowFilters((v) => !v)}
                className="h-8 gap-1 text-xs"
              >
                <Filter className="h-3 w-3" />
                Labels
                <ChevronDown className="h-3 w-3" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void fetchGraph()}
                className="h-8 text-xs"
              >
                <RotateCcw className="h-3 w-3" />
              </Button>
            </div>

            {showFilters && availableLabels.length > 0 && (
              <div className="flex flex-wrap gap-1 rounded-md border bg-background/90 p-2 backdrop-blur">
                {availableLabels.map((label) => (
                  <button
                    key={label}
                    onClick={() => toggleLabel(label)}
                    className={`rounded-md border px-2 py-0.5 text-[10px] font-medium transition-colors ${
                      activeLabels.size === 0 || activeLabels.has(label)
                        ? labelBadgeClass(label)
                        : "border-border bg-muted/30 text-muted-foreground opacity-40"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}

            {/* Stats */}
            <div className="flex gap-2">
              <Badge variant="secondary" className="text-[10px]">
                {nodes.filter((n) => !n.hidden).length} nodes
              </Badge>
              <Badge variant="secondary" className="text-[10px]">
                {edges.length} edges
              </Badge>
            </div>
          </Panel>
        </ReactFlow>
      </div>

      {/* Node detail sidebar */}
      {selectedNode && (
        <Card className="w-80 shrink-0">
          <CardHeader className="p-4 pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">
                {String(selectedNode.data.label)}
              </CardTitle>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <Badge
              variant="outline"
              className={`w-fit text-[10px] ${labelBadgeClass(String(selectedNode.data.nodeType))}`}
            >
              {String(selectedNode.data.nodeType)}
            </Badge>
          </CardHeader>
          <CardContent className="space-y-2 p-4 pt-0">
            <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Properties
            </p>
            <div className="max-h-[400px] space-y-1 overflow-y-auto">
              {Object.entries(
                selectedNode.data.properties as Record<string, unknown>,
              ).map(([key, value]) => (
                <div
                  key={key}
                  className="flex justify-between gap-2 rounded px-2 py-1 text-xs odd:bg-muted/30"
                >
                  <span className="shrink-0 font-medium text-muted-foreground">
                    {key}
                  </span>
                  <span className="truncate text-right text-foreground">
                    {String(value)}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
