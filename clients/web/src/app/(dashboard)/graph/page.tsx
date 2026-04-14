"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Network } from "lucide-react";
import { AttackGraphCanvas } from "@/components/graph/attack-graph-canvas";

export default function GraphPage() {
  const [engagementId, setEngagementId] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Attack Graph</h1>
        <p className="text-sm text-muted-foreground">
          Visualize attack paths and knowledge graph from Neo4j
        </p>
      </div>

      <div className="flex items-end gap-3">
        <div className="space-y-2">
          <Label htmlFor="engId">Engagement ID</Label>
          <Input
            id="engId"
            placeholder="Enter engagement ID..."
            value={engagementId}
            onChange={(e) => setEngagementId(e.target.value)}
            className="w-80"
          />
        </div>
        <Button
          onClick={() => setActiveId(engagementId)}
          disabled={!engagementId.trim()}
        >
          Load Graph
        </Button>
      </div>

      {activeId ? (
        <AttackGraphCanvas engagementId={activeId} />
      ) : (
        <Card className="min-h-[600px]">
          <CardContent className="flex items-center justify-center py-24">
            <div className="text-center text-sm text-muted-foreground">
              <Network className="mx-auto mb-3 h-8 w-8 opacity-50" />
              <p>Enter an engagement ID to load its attack graph.</p>
              <p className="mt-1 text-xs">
                Or view the graph from an engagement&apos;s detail page.
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
