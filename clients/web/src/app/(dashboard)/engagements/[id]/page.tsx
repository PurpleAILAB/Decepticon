"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileWarning, Network, Play, ArrowRight, ClipboardList, Loader2 } from "lucide-react";

const quickStats = [
  {
    label: "Objectives",
    value: 0,
    subValue: "0 completed",
    icon: ClipboardList,
    href: "plan",
    color: "text-emerald-400",
  },
  {
    label: "Findings",
    value: 0,
    subValue: "0 critical",
    icon: FileWarning,
    href: "findings",
    color: "text-red-400",
  },
];

export default function EngagementOverviewPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;
  const [loading, setLoading] = useState(true);

  // Check if engagement has documents — if not, redirect to Live for Soundwave interview
  useEffect(() => {
    let active = true;
    async function checkDocs() {
      try {
        const res = await fetch(`/api/engagements/${id}/opplan`);
        if (!active) return;
        if (!res.ok) {
          router.replace(`/engagements/${id}/live?new=true`);
          return;
        }
        const data = await res.json();
        if (!active) return;
        // If opplan has no objectives, documents haven't been created yet
        if (!data.objectives || data.objectives.length === 0) {
          router.replace(`/engagements/${id}/live?new=true`);
          return;
        }
      } catch {
        if (!active) return;
        router.replace(`/engagements/${id}/live?new=true`);
        return;
      }
      if (!active) return;
      setLoading(false);
    }
    checkDocs();
    return () => {
      active = false;
    };
  }, [id, router]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {quickStats.map((stat) => (
          <Link key={stat.label} href={`/engagements/${id}/${stat.href}`}>
            <Card className="group cursor-pointer transition-colors hover:border-primary/30">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {stat.label}
                </CardTitle>
                <stat.icon className={`h-4 w-4 ${stat.color}`} />
              </CardHeader>
              <CardContent>
                <div className="flex items-end justify-between">
                  <div>
                    <span className="text-3xl font-bold">{stat.value}</span>
                    <p className="mt-0.5 text-xs text-muted-foreground">{stat.subValue}</p>
                  </div>
                  <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}

        <Link href={`/engagements/${id}/graph`}>
          <Card className="group cursor-pointer transition-colors hover:border-primary/30">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Attack Graph
              </CardTitle>
              <Network className="h-4 w-4 text-cyan-400" />
            </CardHeader>
            <CardContent>
              <div className="flex items-end justify-between">
                <div>
                  <span className="text-3xl font-bold">0</span>
                  <p className="mt-0.5 text-xs text-muted-foreground">nodes discovered</p>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
            </CardContent>
          </Card>
        </Link>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Progress
            </CardTitle>
            <Play className="h-4 w-4 text-amber-400" />
          </CardHeader>
          <CardContent>
            <div>
              <span className="text-3xl font-bold">0%</span>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-secondary">
                <div className="h-full rounded-full bg-primary transition-all" style={{ width: "0%" }} />
              </div>
              <p className="mt-1 text-xs text-muted-foreground">Run engagement to see data</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent activity */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Findings</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
            Run engagement to see data
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
