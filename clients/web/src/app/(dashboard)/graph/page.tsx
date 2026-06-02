"use client";

import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Network, Loader2 } from "lucide-react";
import { AttackGraphCanvas } from "@/components/graph/attack-graph-canvas";

interface Engagement {
  id: string;
  name: string;
  status: string;
}

export default function GraphPage() {
  const [engagements, setEngagements] = useState<Engagement[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    fetch("/api/engagements")
      .then((res) => {
        if (!res.ok) throw new Error("fetch failed");
        return res.json();
      })
      .then((data: Engagement[]) => {
        if (!active) return;
        const engagements = Array.isArray(data) ? data : [];
        setEngagements(engagements);
        const selected =
          engagements.find((e) => e.status === "running") ??
          engagements.find((e) => e.status === "completed") ??
          engagements[0];
        if (selected) setSelectedId(selected.id);
      })
      .catch(() => {
        if (!active) return;
        setEngagements([]);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Attack Graph</h1>
          <p className="text-sm text-muted-foreground">
            Visualize attack paths and knowledge graph from Neo4j
          </p>
        </div>

        {engagements.length > 1 && (
          <select
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(e.target.value || null)}
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
          >
            {engagements.map((eng) => (
              <option key={eng.id} value={eng.id}>
                {eng.name} ({eng.status})
              </option>
            ))}
          </select>
        )}
      </div>

      {selectedId ? (
        <AttackGraphCanvas engagementId={selectedId} />
      ) : (
        <Card className="min-h-[600px]">
          <CardContent className="flex items-center justify-center py-24">
            <div className="text-center text-sm text-muted-foreground">
              <Network className="mx-auto mb-3 h-8 w-8 opacity-50" />
              <p>No engagements found.</p>
              <p className="mt-1 text-xs">Create an engagement to start building an attack graph.</p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
