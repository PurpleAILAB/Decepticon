"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  Search,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Shield,
  FileWarning,
  ArrowUpDown,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TriageStatus = "open" | "confirmed" | "false_positive" | "remediated" | "accepted_risk";
type Severity = "critical" | "high" | "medium" | "low" | "informational";
type SortField = "title" | "severity" | "engagement" | "status" | "cvssScore";
type SortDir = "asc" | "desc";

interface Finding {
  id: string;
  title: string;
  severity: Severity;
  description: string;
  evidence: string;
  attackVector: string;
  affectedAssets: string[];
  cvssScore?: number;
  cvssVector?: string;
  cwe?: string[];
  mitre?: string[];
  remediation?: string;
  engagementId: string;
  engagementName: string;
  triageStatus: TriageStatus;
  triageNote?: string;
}

interface FindingTriageProps {
  engagementId?: string;
}

// ---------------------------------------------------------------------------
// Severity helpers
// ---------------------------------------------------------------------------

const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  informational: 4,
};

const SEVERITY_CLASSES: Record<Severity, string> = {
  critical: "bg-red-500/20 text-red-400 border-red-500/30",
  high: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  medium: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  low: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  informational: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
};

const STATUS_LABELS: Record<TriageStatus, { label: string; icon: typeof CheckCircle; className: string }> = {
  open: {
    label: "Open",
    icon: FileWarning,
    className: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
  },
  confirmed: {
    label: "Confirmed",
    icon: AlertTriangle,
    className: "bg-red-500/20 text-red-400 border-red-500/30",
  },
  false_positive: {
    label: "False Positive",
    icon: XCircle,
    className: "bg-zinc-500/20 text-zinc-500 border-zinc-500/30",
  },
  remediated: {
    label: "Remediated",
    icon: CheckCircle,
    className: "bg-green-500/20 text-green-400 border-green-500/30",
  },
  accepted_risk: {
    label: "Accepted Risk",
    icon: Shield,
    className: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  },
};

const TRIAGE_ACTIONS: TriageStatus[] = [
  "confirmed",
  "false_positive",
  "remediated",
  "accepted_risk",
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FindingTriage({ engagementId }: FindingTriageProps) {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [severityFilter, setSeverityFilter] = useState<Set<Severity>>(new Set());
  const [statusFilter, setStatusFilter] = useState<Set<TriageStatus>>(new Set());
  const [sortField, setSortField] = useState<SortField>("severity");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Triage dialog state
  const [triageTarget, setTriageTarget] = useState<Finding | null>(null);
  const [triageAction, setTriageAction] = useState<TriageStatus>("confirmed");
  const [triageNote, setTriageNote] = useState("");
  const [triaging, setTriaging] = useState(false);

  // ------------------------------------------------------------------
  // Fetch
  // ------------------------------------------------------------------

  const fetchFindings = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (engagementId) params.set("engagementId", engagementId);
      const url = `/api/findings${params.toString() ? `?${params}` : ""}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Finding[] = await res.json() as Finding[];
      setFindings(data);
    } catch {
      // Silently fail — empty state will show
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  useEffect(() => {
    void fetchFindings();
  }, [fetchFindings]);

  // ------------------------------------------------------------------
  // Filtering + sorting
  // ------------------------------------------------------------------

  const filtered = useMemo(() => {
    let list = findings;

    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      list = list.filter(
        (f) =>
          f.title.toLowerCase().includes(term) ||
          f.description.toLowerCase().includes(term) ||
          f.engagementName.toLowerCase().includes(term) ||
          f.affectedAssets.some((a) => a.toLowerCase().includes(term)),
      );
    }

    if (severityFilter.size > 0) {
      list = list.filter((f) => severityFilter.has(f.severity));
    }

    if (statusFilter.size > 0) {
      list = list.filter((f) => statusFilter.has(f.triageStatus));
    }

    list = [...list].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "severity":
          cmp = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
          break;
        case "title":
          cmp = a.title.localeCompare(b.title);
          break;
        case "engagement":
          cmp = a.engagementName.localeCompare(b.engagementName);
          break;
        case "status":
          cmp = a.triageStatus.localeCompare(b.triageStatus);
          break;
        case "cvssScore":
          cmp = (b.cvssScore ?? 0) - (a.cvssScore ?? 0);
          break;
      }
      return sortDir === "desc" ? -cmp : cmp;
    });

    return list;
  }, [findings, searchTerm, severityFilter, statusFilter, sortField, sortDir]);

  // ------------------------------------------------------------------
  // Sort toggle
  // ------------------------------------------------------------------

  const toggleSort = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortField(field);
        setSortDir("asc");
      }
    },
    [sortField],
  );

  function SortIcon({ field }: { field: SortField }) {
    if (sortField !== field) return <ArrowUpDown className="ml-1 h-3 w-3 opacity-30" />;
    return sortDir === "asc" ? (
      <ChevronUp className="ml-1 h-3 w-3" />
    ) : (
      <ChevronDown className="ml-1 h-3 w-3" />
    );
  }

  // ------------------------------------------------------------------
  // Triage action
  // ------------------------------------------------------------------

  const submitTriage = useCallback(async () => {
    if (!triageTarget) return;
    setTriaging(true);
    try {
      const res = await fetch("/api/findings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          findingId: triageTarget.id,
          engagementId: triageTarget.engagementId,
          triageStatus: triageAction,
          triageNote,
        }),
      });
      if (res.ok) {
        setFindings((prev) =>
          prev.map((f) =>
            f.id === triageTarget.id
              ? { ...f, triageStatus: triageAction, triageNote }
              : f,
          ),
        );
        setTriageTarget(null);
        setTriageNote("");
      }
    } finally {
      setTriaging(false);
    }
  }, [triageTarget, triageAction, triageNote]);

  // ------------------------------------------------------------------
  // Toggle helpers
  // ------------------------------------------------------------------

  const toggleSeverity = useCallback((s: Severity) => {
    setSeverityFilter((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  }, []);

  const toggleStatus = useCallback((s: TriageStatus) => {
    setStatusFilter((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  }, []);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search findings…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-9"
          />
        </div>

        <div className="flex gap-1">
          {(Object.keys(SEVERITY_ORDER) as Severity[]).map((s) => (
            <button
              key={s}
              onClick={() => toggleSeverity(s)}
              className={`rounded-md border px-2 py-1 text-[10px] font-medium capitalize transition-colors ${
                severityFilter.size === 0 || severityFilter.has(s)
                  ? SEVERITY_CLASSES[s]
                  : "border-border bg-muted/30 text-muted-foreground opacity-40"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="flex gap-1">
          {(Object.keys(STATUS_LABELS) as TriageStatus[]).map((s) => {
            const cfg = STATUS_LABELS[s];
            return (
              <button
                key={s}
                onClick={() => toggleStatus(s)}
                className={`rounded-md border px-2 py-1 text-[10px] font-medium transition-colors ${
                  statusFilter.size === 0 || statusFilter.has(s)
                    ? cfg.className
                    : "border-border bg-muted/30 text-muted-foreground opacity-40"
                }`}
              >
                {cfg.label}
              </button>
            );
          })}
        </div>

        <Badge variant="secondary" className="text-xs">
          {filtered.length} / {findings.length}
        </Badge>
      </div>

      {/* Findings table */}
      {filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center p-12 text-center">
            <ShieldAlert className="mb-4 h-10 w-10 text-muted-foreground" />
            <p className="text-sm font-medium">No findings match</p>
            <p className="text-xs text-muted-foreground">
              Adjust your filters or run a new engagement.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead
                  className="w-[300px] cursor-pointer"
                  onClick={() => toggleSort("title")}
                >
                  <span className="flex items-center">
                    Title <SortIcon field="title" />
                  </span>
                </TableHead>
                <TableHead
                  className="w-24 cursor-pointer"
                  onClick={() => toggleSort("severity")}
                >
                  <span className="flex items-center">
                    Severity <SortIcon field="severity" />
                  </span>
                </TableHead>
                <TableHead
                  className="w-20 cursor-pointer"
                  onClick={() => toggleSort("cvssScore")}
                >
                  <span className="flex items-center">
                    CVSS <SortIcon field="cvssScore" />
                  </span>
                </TableHead>
                <TableHead
                  className="cursor-pointer"
                  onClick={() => toggleSort("engagement")}
                >
                  <span className="flex items-center">
                    Engagement <SortIcon field="engagement" />
                  </span>
                </TableHead>
                <TableHead
                  className="w-32 cursor-pointer"
                  onClick={() => toggleSort("status")}
                >
                  <span className="flex items-center">
                    Status <SortIcon field="status" />
                  </span>
                </TableHead>
                <TableHead className="w-28 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((f) => {
                const statusCfg = STATUS_LABELS[f.triageStatus];
                const StatusIcon = statusCfg.icon;
                const isExpanded = expandedId === f.id;

                return (
                  <TableRow
                    key={f.id}
                    className="group cursor-pointer"
                  >
                    <TableCell>
                      <button
                        onClick={() => setExpandedId(isExpanded ? null : f.id)}
                        className="text-left"
                      >
                        <div className="font-medium text-sm">{f.title}</div>
                        {isExpanded && (
                          <div className="mt-2 space-y-2 text-xs text-muted-foreground">
                            <p>{f.description}</p>
                            {f.affectedAssets.length > 0 && (
                              <div className="flex flex-wrap gap-1">
                                {f.affectedAssets.map((a) => (
                                  <Badge
                                    key={a}
                                    variant="outline"
                                    className="text-[10px]"
                                  >
                                    {a}
                                  </Badge>
                                ))}
                              </div>
                            )}
                            {f.mitre && f.mitre.length > 0 && (
                              <div className="flex flex-wrap gap-1">
                                {f.mitre.map((t) => (
                                  <Badge
                                    key={t}
                                    variant="secondary"
                                    className="text-[10px]"
                                  >
                                    {t}
                                  </Badge>
                                ))}
                              </div>
                            )}
                            {f.remediation && (
                              <p className="rounded border border-green-500/20 bg-green-500/5 p-2 text-green-400">
                                {f.remediation}
                              </p>
                            )}
                          </div>
                        )}
                      </button>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={`capitalize ${SEVERITY_CLASSES[f.severity]}`}
                      >
                        {f.severity}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs tabular-nums">
                      {f.cvssScore?.toFixed(1) ?? "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {f.engagementName}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={`gap-1 ${statusCfg.className}`}
                      >
                        <StatusIcon className="h-3 w-3" />
                        {statusCfg.label}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Dialog>
                        <DialogTrigger
                          onClick={() => {
                            setTriageTarget(f);
                            setTriageAction(
                              f.triageStatus === "open" ? "confirmed" : f.triageStatus,
                            );
                            setTriageNote(f.triageNote ?? "");
                          }}
                        >
                          <Button variant="ghost" size="sm" className="h-7 text-xs">
                            Triage
                          </Button>
                        </DialogTrigger>
                        <DialogContent>
                          <DialogHeader>
                            <DialogTitle className="text-sm">
                              Triage: {f.title}
                            </DialogTitle>
                            <DialogDescription className="text-xs">
                              Set finding status and add notes.
                            </DialogDescription>
                          </DialogHeader>
                          <div className="space-y-4 py-2">
                            <div className="grid grid-cols-2 gap-2">
                              {TRIAGE_ACTIONS.map((action) => {
                                const acfg = STATUS_LABELS[action];
                                const AIcon = acfg.icon;
                                return (
                                  <button
                                    key={action}
                                    onClick={() => setTriageAction(action)}
                                    className={`flex items-center gap-2 rounded-lg border p-3 text-left text-xs transition-colors ${
                                      triageAction === action
                                        ? acfg.className + " border-current"
                                        : "border-border hover:bg-muted/50"
                                    }`}
                                  >
                                    <AIcon className="h-4 w-4 shrink-0" />
                                    {acfg.label}
                                  </button>
                                );
                              })}
                            </div>
                            <Textarea
                              placeholder="Triage notes (optional)"
                              value={triageNote}
                              onChange={(e) => setTriageNote(e.target.value)}
                              className="min-h-[80px] text-xs"
                            />
                          </div>
                          <DialogFooter>
                            <Button
                              size="sm"
                              disabled={triaging}
                              onClick={() => void submitTriage()}
                            >
                              {triaging ? "Saving…" : "Save"}
                            </Button>
                          </DialogFooter>
                        </DialogContent>
                      </Dialog>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
