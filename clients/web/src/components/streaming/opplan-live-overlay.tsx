"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  ChevronDown,
  ChevronRight,
  Target,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ───────────────────────────────────────────────────────

interface Objective {
  id: string;
  title: string;
  phase: string;
  status: string;
  priority: number;
  description?: string;
  acceptanceCriteria?: string[];
}

interface OpplanLiveOverlayProps {
  engagementId: string;
  className?: string;
}

// ── Status config (mirrors opplan-tracker.tsx) ──────────────────

const statusConfig: Record<
  string,
  { icon: typeof CheckCircle2; color: string; label: string }
> = {
  completed: {
    icon: CheckCircle2,
    color: "text-green-400",
    label: "Passed",
  },
  blocked: {
    icon: XCircle,
    color: "text-red-400",
    label: "Blocked",
  },
  "in-progress": {
    icon: Loader2,
    color: "text-amber-400",
    label: "Running",
  },
  "in_progress": {
    icon: Loader2,
    color: "text-amber-400",
    label: "Running",
  },
  pending: {
    icon: Clock,
    color: "text-muted-foreground",
    label: "Pending",
  },
  cancelled: {
    icon: XCircle,
    color: "text-zinc-600",
    label: "Cancelled",
  },
};

// ── Objective Row ────────────────────────────────────────────────

interface ObjectiveRowProps {
  obj: Objective;
  expandedObjectiveId: string | null;
  onToggleExpand: (id: string | null) => void;
}

function ObjectiveRow({ obj, expandedObjectiveId, onToggleExpand }: ObjectiveRowProps) {
  const config = statusConfig[obj.status] ?? statusConfig.pending;
  const StatusIcon = config.icon;
  const isInProgress = obj.status === "in-progress" || obj.status === "in_progress";
  const isExpanded = expandedObjectiveId === obj.id;
  const hasDetails = obj.description || (obj.acceptanceCriteria && obj.acceptanceCriteria.length > 0);

  return (
    <div
      className={cn(
        "border-l-2 transition-colors",
        isInProgress ? "border-l-amber-400/60" : "border-l-transparent",
      )}
    >
      <button
        type="button"
        onClick={() =>
          onToggleExpand(isExpanded ? null : obj.id)
        }
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-white/[0.03]"
      >
        <StatusIcon
          className={cn(
            "h-3.5 w-3.5 shrink-0",
            config.color,
            isInProgress && "animate-spin",
          )}
        />
        <Badge
          variant="outline"
          className="shrink-0 px-1.5 py-0 font-mono text-[10px]"
        >
          {obj.id}
        </Badge>
        <span className="min-w-0 flex-1 truncate text-xs text-zinc-300">
          {obj.title}
        </span>
        {hasDetails && (
          isExpanded ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-zinc-600" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-zinc-600" />
          )
        )}
      </button>

      {/* Expanded detail */}
      <div
        className={cn(
          "grid transition-all duration-200 ease-in-out",
          isExpanded && hasDetails
            ? "grid-rows-[1fr] opacity-100"
            : "grid-rows-[0fr] opacity-0",
        )}
      >
        <div className="overflow-hidden">
          <div className="px-3 pb-2 pl-[2.125rem]">
            {obj.description && (
              <p className="text-[11px] leading-relaxed text-zinc-500">
                {obj.description}
              </p>
            )}
            {obj.acceptanceCriteria &&
              obj.acceptanceCriteria.length > 0 && (
                <ul className="mt-1.5 space-y-0.5">
                  {obj.acceptanceCriteria.map((c, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-1.5 text-[11px] text-zinc-500"
                    >
                      <span className="mt-px shrink-0 text-zinc-600">•</span>
                      <span>{c}</span>
                    </li>
                  ))}
                </ul>
              )}
          </div>
        </div>
      </div>
    </div>
  );
}


// ── Component ───────────────────────────────────────────────────

export function OpplanLiveOverlay({
  engagementId,
  className,
}: OpplanLiveOverlayProps) {
  const [objectives, setObjectives] = useState<Objective[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [expandedObjectiveId, setExpandedObjectiveId] = useState<string | null>(
    null,
  );
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchObjectives = useCallback(async () => {
    try {
      const res = await fetch(
        `/api/engagements/${engagementId}/opplan`,
      );
      if (!res.ok) return;
      const data = await res.json();
      const fetched: Objective[] = data.objectives ?? [];
      setObjectives(fetched);
    } catch {
      // Silently ignore — stale data is acceptable for an overlay
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  useEffect(() => {
    fetchObjectives();
    intervalRef.current = setInterval(fetchObjectives, 5_000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchObjectives]);

  // ── Derived state ──

  const total = objectives.length;
  const completed = objectives.filter((o) => o.status === "completed").length;
  const blocked = objectives.filter((o) => o.status === "blocked").length;
  const resolved = completed + blocked;
  const progress = total > 0 ? (resolved / total) * 100 : 0;

  // ── Loading state ──

  if (loading) {
    return (
      <div
        className={cn(
          "overflow-hidden rounded-xl bg-zinc-950/90 ring-1 ring-white/[0.08] backdrop-blur-sm",
          className,
        )}
      >
        <div className="flex items-center gap-2 px-3 py-2.5">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
          <span className="text-xs text-zinc-500">Loading OPPLAN…</span>
        </div>
      </div>
    );
  }

  // ── Empty state ──

  if (total === 0) {
    return (
      <div
        className={cn(
          "overflow-hidden rounded-xl bg-zinc-950/90 ring-1 ring-white/[0.08] backdrop-blur-sm",
          className,
        )}
      >
        <div className="flex items-center gap-2 px-3 py-2.5">
          <Target className="h-3.5 w-3.5 text-zinc-600" />
          <span className="text-xs text-zinc-500">No OPPLAN objectives</span>
        </div>
      </div>
    );
  }

  // ── Main render ──

  // ── Main render ──

  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl bg-zinc-950/90 ring-1 ring-white/[0.08] backdrop-blur-sm",
        className,
      )}
    >
      {/* Progress bar — 4px, always visible */}
      <div className="h-1 w-full bg-zinc-800/60">
        <div
          className={cn(
            "h-full transition-all duration-500 ease-out",
            blocked > 0 && completed === 0
              ? "bg-red-500"
              : progress >= 100
                ? "bg-green-500"
                : "bg-amber-400",
          )}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Header — collapsed summary + toggle */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-white/[0.03]"
      >
        <Target className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
        <span className="flex-1 text-xs text-zinc-400">
          <span className="font-medium text-zinc-200">
            {resolved}/{total}
          </span>{" "}
          objectives
        </span>
        <span className="text-[10px] text-zinc-600">
          {Math.round(progress)}%
        </span>
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-600" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-zinc-600" />
        )}
      </button>

      {/* Expanded objective list */}
      <div
        className={cn(
          "grid transition-all duration-300 ease-in-out",
          expanded
            ? "grid-rows-[1fr] opacity-100"
            : "grid-rows-[0fr] opacity-0",
        )}
      >
        <div className="overflow-hidden">
          <div className="border-t border-white/[0.06]">
            <ScrollArea className="max-h-[300px]">
              <div className="divide-y divide-white/[0.04]">
                {objectives.map((obj) => (
                  <ObjectiveRow key={obj.id} obj={obj} expandedObjectiveId={expandedObjectiveId} onToggleExpand={setExpandedObjectiveId} />
                ))}
              </div>
            </ScrollArea>
          </div>
        </div>
      </div>
    </div>
  );
}
