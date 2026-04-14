"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  Panel,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Network } from "lucide-react";
import { GraphNode } from "./graph-node";

const nodeTypes = { custom: GraphNode };

interface AttackGraphCanvasProps {
  engagementId: string;
  mockNodes?: Node[];
  mockEdges?: Edge[];
}

function styleEdges(edges: Edge[]): Edge[] {
  return edges.map((e) => ({
    ...e,
    animated: true,
    style: { stroke: "#525252" },
    labelStyle: { fill: "#a1a1aa", fontSize: 10 },
  }));
}

export function AttackGraphCanvas({ engagementId, mockNodes, mockEdges }: AttackGraphCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(mockNodes ?? []);
  const [edges, setEdges, onEdgesChange] = useEdgesState(
    mockEdges ? styleEdges(mockEdges) : []
  );
  const [loading, setLoading] = useState(!mockNodes || mockNodes.length === 0);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  useEffect(() => {
    if (mockNodes && mockNodes.length > 0) return;

    fetch(`/api/engagements/${engagementId}/graph`)
      .then((res) => {
        if (!res.ok) throw new Error("fetch failed");
        return res.json();
      })
      .then((data) => {
        const fetchedNodes: Node[] = data.nodes ?? [];
        const fetchedEdges: Edge[] = data.edges ?? [];
        setNodes(fetchedNodes.length > 0 ? fetchedNodes : (mockNodes ?? []));
        setEdges(styleEdges(fetchedEdges.length > 0 ? fetchedEdges : (mockEdges ?? [])));
      })
      .catch(() => {
        setNodes(mockNodes ?? []);
        setEdges(styleEdges(mockEdges ?? []));
      })
      .finally(() => setLoading(false));
  }, [engagementId, mockNodes, mockEdges, setNodes, setEdges]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
  }, []);

  if (loading) {
    return <Skeleton className="h-[600px] w-full rounded-lg" />;
  }

  if (nodes.length === 0) {
    return (
      <Card className="min-h-[600px]">
        <CardContent className="flex items-center justify-center py-24">
          <div className="text-center text-sm text-muted-foreground">
            <Network className="mx-auto mb-3 h-8 w-8 opacity-50" />
            <p>No graph data available.</p>
            <p className="mt-1 text-xs">
              Run an engagement to populate the knowledge graph.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex gap-4">
      <div className="min-h-[600px] flex-1 overflow-hidden rounded-lg border border-border">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
          colorMode="dark"
          defaultEdgeOptions={{
            type: "smoothstep",
          }}
        >
          <Background color="#27272a" gap={20} />
          <Controls className="[&>button]:bg-card [&>button]:border-border [&>button]:text-foreground" />
          <MiniMap
            className="rounded-lg border border-border"
            nodeColor={(node) => {
              const colors: Record<string, string> = {
                Host: "#3b82f6",
                Service: "#22c55e",
                Vulnerability: "#ef4444",
                CVE: "#f97316",
                User: "#a855f7",
                Credential: "#eab308",
                Finding: "#ec4899",
                AttackPath: "#06b6d4",
                DefenseAction: "#10b981",
              };
              const nodeType = String((node.data as Record<string, unknown>)?.nodeType ?? "");
              return colors[nodeType] ?? "#71717a";
            }}
          />
          <Panel position="top-left">
            <Badge variant="secondary">
              {nodes.length} nodes / {edges.length} edges
            </Badge>
          </Panel>
        </ReactFlow>
      </div>

      {/* Detail panel */}
      {selectedNode && (
        <Card className="w-80 shrink-0">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">
                {String(selectedNode.data?.label ?? "Node")}
              </CardTitle>
              <Badge variant="outline" className="text-xs">
                {String(selectedNode.data?.nodeType ?? "Unknown")}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(
                ((selectedNode.data as Record<string, unknown>)?.properties ?? {}) as Record<string, unknown>
              ).map(([key, value]) => (
                <div key={key} className="text-xs">
                  <span className="font-medium text-muted-foreground">
                    {key}:
                  </span>{" "}
                  <span className="break-all text-foreground">
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
