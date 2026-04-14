"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MessageSquare, Target, FileWarning, Network, Play, ArrowRight } from "lucide-react";

const quickStats = [
  {
    label: "Objectives",
    value: 0,
    subValue: "0 completed",
    icon: Target,
    href: "opplan",
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
  const id = params.id as string;

  return (
    <div className="space-y-6">
      {/* Action buttons */}
      <div className="flex gap-3">
        <Link href={`/engagements/${id}/chat`}>
          <Button className="gap-2">
            <MessageSquare className="h-4 w-4" />
            Open Chat
          </Button>
        </Link>
        <Link href={`/engagements/${id}/opplan`}>
          <Button variant="outline" className="gap-2">
            <Target className="h-4 w-4" />
            View OPPLAN
          </Button>
        </Link>
      </div>

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
