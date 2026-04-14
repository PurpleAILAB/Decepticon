"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Target,
} from "lucide-react";

interface Objective {
  id: string;
  title: string;
  phase: string;
  status: string;
  priority: number;
}

interface OpplanTrackerProps {
  engagementId: string;
  mockObjectives?: Objective[];
}

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
  in_progress: {
    icon: Loader2,
    color: "text-amber-400",
    label: "Running",
  },
  pending: {
    icon: Clock,
    color: "text-muted-foreground",
    label: "Pending",
  },
};

export function OpplanTracker({ engagementId, mockObjectives }: OpplanTrackerProps) {
  const [objectives, setObjectives] = useState<Objective[]>(() => mockObjectives ?? []);
  const [loading, setLoading] = useState(!mockObjectives || mockObjectives.length === 0);

  useEffect(() => {
    if (mockObjectives && mockObjectives.length > 0) return;

    fetch(`/api/engagements/${engagementId}/opplan`)
      .then((res) => {
        if (!res.ok) throw new Error("fetch failed");
        return res.json();
      })
      .then((data) => {
        const fetched: Objective[] = data.objectives ?? [];
        setObjectives(fetched.length > 0 ? fetched : (mockObjectives ?? []));
      })
      .catch(() => setObjectives(mockObjectives ?? []))
      .finally(() => setLoading(false));
  }, [engagementId, mockObjectives]);

  const total = objectives.length;
  const completed = objectives.filter(
    (o) => o.status === "completed"
  ).length;
  const blocked = objectives.filter((o) => o.status === "blocked").length;
  const progress = total > 0 ? ((completed + blocked) / total) * 100 : 0;

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (objectives.length === 0) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12 text-sm text-muted-foreground">
          <div className="text-center">
            <Target className="mx-auto mb-3 h-8 w-8 opacity-50" />
            <p>No OPPLAN generated yet.</p>
            <p className="mt-1 text-xs">
              Run the engagement to generate objectives via Soundwave interview.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Progress bar */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              Progress: {completed + blocked}/{total} objectives
            </span>
            <span className="font-medium">{Math.round(progress)}%</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="mt-2 flex gap-4 text-xs text-muted-foreground">
            <span className="text-green-400">{completed} passed</span>
            <span className="text-red-400">{blocked} blocked</span>
            <span>
              {total - completed - blocked} remaining
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Objectives list */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Objectives</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {objectives.map((obj) => {
            const config = statusConfig[obj.status] ?? statusConfig.pending;
            const StatusIcon = config.icon;
            return (
              <div
                key={obj.id}
                className="flex items-center gap-3 rounded-lg border border-border p-3"
              >
                <StatusIcon
                  className={`h-5 w-5 shrink-0 ${config.color} ${
                    obj.status === "in_progress" ? "animate-spin" : ""
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{obj.title}</span>
                    <Badge variant="outline" className="text-xs">
                      {obj.phase}
                    </Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {obj.id}
                  </span>
                </div>
                <Badge
                  variant="secondary"
                  className={`shrink-0 text-xs ${config.color}`}
                >
                  {config.label}
                </Badge>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
