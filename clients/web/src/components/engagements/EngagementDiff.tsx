"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ArrowLeftRight,
  Plus,
  Minus,
  Equal,
  Shield,
  Bug,
  Server,
  RotateCcw,
  ChevronDown,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Engagement {
  id: string;
  name: string;
  status: string;
}

interface FindingDelta {
  title: string;
  severity: string;
  location: "a_only" | "b_only" | "both";
  cvssA?: number;
  cvssB?: number;
}

interface AssetDelta {
  asset: string;
  location: "a_only" | "b_only" | "both";
}

interface MitreDelta {
  techniqueId: string;
  techniqueName: string;
  location: "a_only" | "b_only" | "both";
}

interface DiffStats {
  findingsOnlyA: number;
  findingsOnlyB: number;
  findingsCommon: number;
  assetsOnlyA: number;
  assetsOnlyB: number;
  assetsCommon: number;
  mitreOnlyA: number;
  mitreOnlyB: number;
  mitreCommon: number;
}

interface DiffPayload {
  engagementA: string;
  engagementB: string;
  stats: DiffStats;
  findings: FindingDelta[];
  assets: AssetDelta[];
  mitre: MitreDelta[];
}

type DiffTab = "findings" | "assets" | "mitre";

interface EngagementDiffProps {
  /** Pre-select engagement A */
  engagementA?: string;
  /** Pre-select engagement B */
  engagementB?: string;
}

// ---------------------------------------------------------------------------
// Severity ordering for sort
// ---------------------------------------------------------------------------

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  informational: 4,
};

const SEVERITY_CLASSES: Record<string, string> = {
  critical: "bg-red-500/20 text-red-400",
  high: "bg-orange-500/20 text-orange-400",
  medium: "bg-yellow-500/20 text-yellow-400",
  low: "bg-blue-500/20 text-blue-400",
  informational: "bg-zinc-500/20 text-zinc-400",
};

const LOCATION_ICON = {
  a_only: { icon: Minus, label: "Only in A", className: "text-red-400" },
  b_only: { icon: Plus, label: "Only in B", className: "text-green-400" },
  both: { icon: Equal, label: "Both", className: "text-zinc-400" },
} as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EngagementDiff({
  engagementA: initA,
  engagementB: initB,
}: EngagementDiffProps) {
  const [engagements, setEngagements] = useState<Engagement[]>([]);
  const [engA, setEngA] = useState(initA ?? "");
  const [engB, setEngB] = useState(initB ?? "");
  const [diff, setDiff] = useState<DiffPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<DiffTab>("findings");
  const [showPickerA, setShowPickerA] = useState(false);
  const [showPickerB, setShowPickerB] = useState(false);

  // ------------------------------------------------------------------
  // Fetch engagement list
  // ------------------------------------------------------------------

  useEffect(() => {
    let active = true;
    fetch("/api/engagements")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: Engagement[]) => {
        if (active) setEngagements(data);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setLoadingList(false);
      });
    return () => {
      active = false;
    };
  }, []);

  // ------------------------------------------------------------------
  // Fetch diff
  // ------------------------------------------------------------------

  const fetchDiff = useCallback(async () => {
    if (!engA || !engB || engA === engB) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ a: engA, b: engB });
      const res = await fetch(`/api/engagements/diff?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = (await res.json()) as DiffPayload;
      setDiff(payload);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [engA, engB]);

  // ------------------------------------------------------------------
  // Engagement picker
  // ------------------------------------------------------------------

  function EngagementPicker({
    value,
    onChange,
    label,
    open,
    setOpen,
    excludeId,
  }: {
    value: string;
    onChange: (id: string) => void;
    label: string;
    open: boolean;
    setOpen: (v: boolean) => void;
    excludeId?: string;
  }) {
    const selected = engagements.find((e) => e.id === value);
    return (
      <div className="relative">
        <button
          onClick={() => setOpen(!open)}
          className="flex h-10 w-full items-center justify-between rounded-lg border border-border bg-background px-3 text-sm transition-colors hover:bg-muted"
        >
          <span className={selected ? "text-foreground" : "text-muted-foreground"}>
            {selected ? selected.name : label}
          </span>
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </button>
        {open && (
          <div className="absolute z-50 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border bg-background shadow-lg">
            {engagements
              .filter((e) => e.id !== excludeId)
              .map((e) => (
                <button
                  key={e.id}
                  onClick={() => {
                    onChange(e.id);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors hover:bg-muted ${
                    e.id === value ? "bg-muted" : ""
                  }`}
                >
                  <span>{e.name}</span>
                  <Badge variant="outline" className="text-[10px] capitalize">
                    {e.status}
                  </Badge>
                </button>
              ))}
            {engagements.filter((e) => e.id !== excludeId).length === 0 && (
              <div className="p-3 text-xs text-muted-foreground">
                No engagements available
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Render helpers
  // ------------------------------------------------------------------

  function DeltaIcon({ location }: { location: "a_only" | "b_only" | "both" }) {
    const cfg = LOCATION_ICON[location];
    const Icon = cfg.icon;
    return (
      <span className={`flex items-center gap-1 text-xs ${cfg.className}`}>
        <Icon className="h-3 w-3" />
        {cfg.label}
      </span>
    );
  }

  function StatCard({
    icon: Icon,
    title,
    onlyA,
    onlyB,
    common,
  }: {
    icon: typeof Bug;
    title: string;
    onlyA: number;
    onlyB: number;
    common: number;
  }) {
    return (
      <Card>
        <CardContent className="flex items-center gap-3 p-4">
          <Icon className="h-5 w-5 text-muted-foreground" />
          <div>
            <div className="text-xs font-medium">{title}</div>
            <div className="mt-1 flex gap-2 text-[10px]">
              <span className="text-red-400">−{onlyA}</span>
              <span className="text-green-400">+{onlyB}</span>
              <span className="text-zinc-400">={common}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  // ------------------------------------------------------------------
  // Main render
  // ------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Engagement selector */}
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <ArrowLeftRight className="h-4 w-4" />
            Compare Engagements
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-2">
          {loadingList ? (
            <div className="flex gap-4">
              <Skeleton className="h-10 flex-1" />
              <Skeleton className="h-10 flex-1" />
            </div>
          ) : (
            <div className="flex items-end gap-4">
              <div className="flex-1 space-y-1">
                <label className="text-xs font-medium text-muted-foreground">
                  Engagement A
                </label>
                <EngagementPicker
                  value={engA}
                  onChange={setEngA}
                  label="Select baseline…"
                  open={showPickerA}
                  setOpen={setShowPickerA}
                  excludeId={engB}
                />
              </div>
              <ArrowLeftRight className="mb-2 h-5 w-5 shrink-0 text-muted-foreground" />
              <div className="flex-1 space-y-1">
                <label className="text-xs font-medium text-muted-foreground">
                  Engagement B
                </label>
                <EngagementPicker
                  value={engB}
                  onChange={setEngB}
                  label="Select comparison…"
                  open={showPickerB}
                  setOpen={setShowPickerB}
                  excludeId={engA}
                />
              </div>
              <Button
                size="sm"
                disabled={!engA || !engB || engA === engB || loading}
                onClick={() => void fetchDiff()}
                className="mb-0"
              >
                {loading ? "Comparing…" : "Compare"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Card className="border-destructive/40">
          <CardContent className="flex items-center gap-3 p-4">
            <ArrowLeftRight className="h-5 w-5 text-destructive" />
            <p className="text-xs text-destructive">{error}</p>
            <Button
              variant="outline"
              size="sm"
              className="ml-auto"
              onClick={() => void fetchDiff()}
            >
              <RotateCcw className="mr-1 h-3 w-3" />
              Retry
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-4">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
          <Skeleton className="h-64" />
        </div>
      )}

      {/* Results */}
      {diff && !loading && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-3 gap-4">
            <StatCard
              icon={Bug}
              title="Findings"
              onlyA={diff.stats.findingsOnlyA}
              onlyB={diff.stats.findingsOnlyB}
              common={diff.stats.findingsCommon}
            />
            <StatCard
              icon={Server}
              title="Assets"
              onlyA={diff.stats.assetsOnlyA}
              onlyB={diff.stats.assetsOnlyB}
              common={diff.stats.assetsCommon}
            />
            <StatCard
              icon={Shield}
              title="MITRE Techniques"
              onlyA={diff.stats.mitreOnlyA}
              onlyB={diff.stats.mitreOnlyB}
              common={diff.stats.mitreCommon}
            />
          </div>

          {/* Tabs */}
          <div className="flex gap-1 rounded-lg border bg-muted/30 p-1">
            {(["findings", "assets", "mitre"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                  activeTab === tab
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {tab === "mitre" ? "MITRE Techniques" : tab}
              </button>
            ))}
          </div>

          {/* Table content */}
          {activeTab === "findings" && (
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Finding</TableHead>
                    <TableHead className="w-24">Severity</TableHead>
                    <TableHead className="w-20">CVSS A</TableHead>
                    <TableHead className="w-20">CVSS B</TableHead>
                    <TableHead className="w-28">Delta</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {diff.findings
                    .sort(
                      (a, b) =>
                        (SEVERITY_ORDER[a.severity] ?? 5) -
                        (SEVERITY_ORDER[b.severity] ?? 5),
                    )
                    .map((f, i) => (
                      <TableRow key={`${f.title}-${i}`}>
                        <TableCell className="text-sm font-medium">
                          {f.title}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={`capitalize ${SEVERITY_CLASSES[f.severity] ?? ""}`}
                          >
                            {f.severity}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs tabular-nums">
                          {f.cvssA?.toFixed(1) ?? "—"}
                        </TableCell>
                        <TableCell className="font-mono text-xs tabular-nums">
                          {f.cvssB?.toFixed(1) ?? "—"}
                        </TableCell>
                        <TableCell>
                          <DeltaIcon location={f.location} />
                        </TableCell>
                      </TableRow>
                    ))}
                  {diff.findings.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-xs text-muted-foreground">
                        No findings to compare.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          )}

          {activeTab === "assets" && (
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Asset</TableHead>
                    <TableHead className="w-28">Delta</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {diff.assets.map((a, i) => (
                    <TableRow key={`${a.asset}-${i}`}>
                      <TableCell className="font-mono text-sm">{a.asset}</TableCell>
                      <TableCell>
                        <DeltaIcon location={a.location} />
                      </TableCell>
                    </TableRow>
                  ))}
                  {diff.assets.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={2} className="py-8 text-center text-xs text-muted-foreground">
                        No assets to compare.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          )}

          {activeTab === "mitre" && (
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-28">Technique ID</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead className="w-28">Delta</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {diff.mitre.map((m, i) => (
                    <TableRow key={`${m.techniqueId}-${i}`}>
                      <TableCell className="font-mono text-xs">
                        {m.techniqueId}
                      </TableCell>
                      <TableCell className="text-sm">{m.techniqueName}</TableCell>
                      <TableCell>
                        <DeltaIcon location={m.location} />
                      </TableCell>
                    </TableRow>
                  ))}
                  {diff.mitre.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={3} className="py-8 text-center text-xs text-muted-foreground">
                        No MITRE technique differences.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}

      {/* Empty state — no comparison yet */}
      {!diff && !loading && !error && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center p-12 text-center">
            <ArrowLeftRight className="mb-4 h-10 w-10 text-muted-foreground" />
            <p className="text-sm font-medium">Select two engagements to compare</p>
            <p className="text-xs text-muted-foreground">
              View differences in findings, assets, and MITRE coverage.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
