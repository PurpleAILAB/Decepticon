"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { RotateCcw, Shield, Grid3X3 } from "lucide-react";

// ---------------------------------------------------------------------------
// ATT&CK Enterprise Tactics (column headers)
// ---------------------------------------------------------------------------

interface Tactic {
  id: string;
  name: string;
  shortName: string;
}

const TACTICS: Tactic[] = [
  { id: "TA0043", name: "Reconnaissance", shortName: "Recon" },
  { id: "TA0042", name: "Resource Development", shortName: "Res Dev" },
  { id: "TA0001", name: "Initial Access", shortName: "Init Acc" },
  { id: "TA0002", name: "Execution", shortName: "Exec" },
  { id: "TA0003", name: "Persistence", shortName: "Persist" },
  { id: "TA0004", name: "Privilege Escalation", shortName: "Priv Esc" },
  { id: "TA0005", name: "Defense Evasion", shortName: "Def Evas" },
  { id: "TA0006", name: "Credential Access", shortName: "Cred Acc" },
  { id: "TA0007", name: "Discovery", shortName: "Discov" },
  { id: "TA0008", name: "Lateral Movement", shortName: "Lat Mov" },
  { id: "TA0009", name: "Collection", shortName: "Collect" },
  { id: "TA0011", name: "Command and Control", shortName: "C2" },
  { id: "TA0010", name: "Exfiltration", shortName: "Exfil" },
  { id: "TA0040", name: "Impact", shortName: "Impact" },
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TechniqueHit {
  techniqueId: string;
  techniqueName: string;
  tacticId: string;
  count: number;
  engagements: string[];
}

interface MitrePayload {
  techniques: TechniqueHit[];
  totalEngagements: number;
}

interface MitreHeatmapProps {
  engagementId?: string;
}

// ---------------------------------------------------------------------------
// Colour scale
// ---------------------------------------------------------------------------

function heatColor(count: number, maxCount: number): string {
  if (count === 0) return "bg-zinc-800/30";
  const intensity = Math.min(count / Math.max(maxCount, 1), 1);
  if (intensity <= 0.25) return "bg-yellow-500/20 text-yellow-400";
  if (intensity <= 0.5) return "bg-orange-500/30 text-orange-400";
  if (intensity <= 0.75) return "bg-red-500/40 text-red-400";
  return "bg-red-600/60 text-red-300";
}

function heatBorder(count: number, maxCount: number): string {
  if (count === 0) return "border-zinc-700/30";
  const intensity = Math.min(count / Math.max(maxCount, 1), 1);
  if (intensity <= 0.25) return "border-yellow-500/30";
  if (intensity <= 0.5) return "border-orange-500/30";
  if (intensity <= 0.75) return "border-red-500/30";
  return "border-red-600/40";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MitreHeatmap({ engagementId }: MitreHeatmapProps) {
  const [data, setData] = useState<MitrePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredTechnique, setHoveredTechnique] = useState<TechniqueHit | null>(null);

  // ------------------------------------------------------------------
  // Fetch
  // ------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (engagementId) params.set("engagement", engagementId);
      const url = `/api/mitre${params.toString() ? `?${params}` : ""}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = (await res.json()) as MitrePayload;
      setData(payload);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // ------------------------------------------------------------------
  // Group techniques by tactic
  // ------------------------------------------------------------------

  const { tacticMap, maxCount, totalTechniques, coveredTactics } = useMemo(() => {
    const tMap = new Map<string, TechniqueHit[]>();
    let maxC = 0;
    let total = 0;
    const covered = new Set<string>();

    if (data) {
      for (const t of data.techniques) {
        const list = tMap.get(t.tacticId) ?? [];
        list.push(t);
        tMap.set(t.tacticId, list);
        if (t.count > maxC) maxC = t.count;
        total++;
        covered.add(t.tacticId);
      }
      // Sort by count descending within each tactic
      for (const [, list] of tMap) {
        list.sort((a, b) => b.count - a.count);
      }
    }

    return {
      tacticMap: tMap,
      maxCount: maxC,
      totalTechniques: total,
      coveredTactics: covered.size,
    };
  }, [data]);

  // ------------------------------------------------------------------
  // Loading / error states
  // ------------------------------------------------------------------

  if (loading) {
    return <Skeleton className="h-[500px] w-full rounded-lg" />;
  }

  if (error) {
    return (
      <Card className="border-destructive/40">
        <CardContent className="flex items-center gap-3 p-6">
          <Grid3X3 className="h-5 w-5 text-destructive" />
          <div>
            <p className="text-sm font-medium text-destructive">
              MITRE Data Unavailable
            </p>
            <p className="text-xs text-muted-foreground">{error}</p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={() => void fetchData()}
          >
            <RotateCcw className="mr-1 h-3 w-3" />
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!data || data.techniques.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center p-12 text-center">
          <Shield className="mb-4 h-10 w-10 text-muted-foreground" />
          <p className="text-sm font-medium">No MITRE ATT&CK coverage</p>
          <p className="text-xs text-muted-foreground">
            Findings with mapped ATT&CK techniques will appear here.
          </p>
        </CardContent>
      </Card>
    );
  }

  // ------------------------------------------------------------------
  // Render matrix
  // ------------------------------------------------------------------

  return (
    <div className="space-y-4">
      {/* Summary stats */}
      <div className="flex flex-wrap gap-3">
        <Badge variant="secondary" className="text-xs">
          {totalTechniques} techniques observed
        </Badge>
        <Badge variant="secondary" className="text-xs">
          {coveredTactics} / {TACTICS.length} tactics covered
        </Badge>
        <Badge variant="secondary" className="text-xs">
          {data.totalEngagements} engagement{data.totalEngagements !== 1 ? "s" : ""}
        </Badge>
        <div className="ml-auto flex items-center gap-2 text-[10px] text-muted-foreground">
          <span>Low</span>
          <div className="flex gap-0.5">
            <div className="h-3 w-6 rounded-sm bg-yellow-500/20" />
            <div className="h-3 w-6 rounded-sm bg-orange-500/30" />
            <div className="h-3 w-6 rounded-sm bg-red-500/40" />
            <div className="h-3 w-6 rounded-sm bg-red-600/60" />
          </div>
          <span>High</span>
        </div>
      </div>

      {/* Heatmap grid */}
      <TooltipProvider delayDuration={100}>
        <div className="overflow-x-auto rounded-lg border bg-background">
          <div className="inline-grid min-w-full" style={{ gridTemplateColumns: `repeat(${TACTICS.length}, minmax(100px, 1fr))` }}>
            {/* Tactic header row */}
            {TACTICS.map((tactic) => {
              const techniques = tacticMap.get(tactic.id) ?? [];
              const tacticTotal = techniques.reduce((s, t) => s + t.count, 0);
              return (
                <div
                  key={tactic.id}
                  className="border-b border-r border-border p-2 text-center last:border-r-0"
                >
                  <div className="text-[10px] font-semibold text-foreground">
                    {tactic.shortName}
                  </div>
                  <div className="text-[9px] text-muted-foreground">
                    {tactic.id}
                  </div>
                  {tacticTotal > 0 && (
                    <Badge variant="outline" className="mt-1 text-[9px]">
                      {techniques.length} / {tacticTotal} hits
                    </Badge>
                  )}
                </div>
              );
            })}

            {/* Technique cells */}
            {TACTICS.map((tactic) => {
              const techniques = tacticMap.get(tactic.id) ?? [];
              return (
                <div
                  key={`col-${tactic.id}`}
                  className="border-r border-border last:border-r-0"
                >
                  {techniques.length === 0 ? (
                    <div className="flex h-16 items-center justify-center p-2">
                      <span className="text-[10px] text-muted-foreground/40">—</span>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-0.5 p-1">
                      {techniques.map((tech) => (
                        <Tooltip key={tech.techniqueId}>
                          <TooltipTrigger asChild>
                            <button
                              className={`rounded border px-1.5 py-1 text-left transition-colors ${heatColor(tech.count, maxCount)} ${heatBorder(tech.count, maxCount)} hover:brightness-125`}
                              onMouseEnter={() => setHoveredTechnique(tech)}
                              onMouseLeave={() => setHoveredTechnique(null)}
                            >
                              <div className="truncate text-[9px] font-medium">
                                {tech.techniqueId}
                              </div>
                              <div className="truncate text-[8px] opacity-70">
                                {tech.techniqueName}
                              </div>
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-xs">
                            <div className="space-y-1">
                              <div className="text-xs font-semibold">
                                {tech.techniqueId}: {tech.techniqueName}
                              </div>
                              <div className="text-[10px] text-muted-foreground">
                                {tech.count} hit{tech.count !== 1 ? "s" : ""} across{" "}
                                {tech.engagements.length} engagement
                                {tech.engagements.length !== 1 ? "s" : ""}
                              </div>
                              <div className="flex flex-wrap gap-1">
                                {tech.engagements.slice(0, 5).map((e) => (
                                  <Badge
                                    key={e}
                                    variant="outline"
                                    className="text-[9px]"
                                  >
                                    {e}
                                  </Badge>
                                ))}
                                {tech.engagements.length > 5 && (
                                  <Badge variant="secondary" className="text-[9px]">
                                    +{tech.engagements.length - 5} more
                                  </Badge>
                                )}
                              </div>
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </TooltipProvider>

      {/* Hovered technique detail panel */}
      {hoveredTechnique && (
        <Card className="border-muted">
          <CardHeader className="p-3 pb-1">
            <CardTitle className="text-xs">
              {hoveredTechnique.techniqueId}: {hoveredTechnique.techniqueName}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-4 p-3 pt-0 text-xs text-muted-foreground">
            <span>
              <strong className="text-foreground">{hoveredTechnique.count}</strong> observations
            </span>
            <span>
              <strong className="text-foreground">{hoveredTechnique.engagements.length}</strong> engagements
            </span>
            <div className="flex gap-1">
              {hoveredTechnique.engagements.slice(0, 8).map((e) => (
                <Badge key={e} variant="outline" className="text-[9px]">
                  {e}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
