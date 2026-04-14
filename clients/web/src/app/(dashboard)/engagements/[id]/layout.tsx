"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { GitBranch, Globe, Server } from "lucide-react";
interface Engagement {
  id: string;
  name: string;
  targetType: string;
  targetValue: string;
  status: string;
}

const statusColors: Record<string, string> = {
  draft: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  planning: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  running: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  completed: "bg-green-500/10 text-green-400 border-green-500/20",
  failed: "bg-red-500/10 text-red-400 border-red-500/20",
};

const targetIcons: Record<string, typeof GitBranch> = {
  github_repo: GitBranch,
  web_url: Globe,
  ip_range: Server,
};

export default function EngagementLayout({ children }: { children: React.ReactNode }) {
  const params = useParams();
  const id = params.id as string;
  const [engagement, setEngagement] = useState<Engagement | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/engagements/${id}`)
      .then((res) => {
        if (!res.ok) throw new Error("fetch failed");
        return res.json();
      })
      .then((data: Engagement) => setEngagement(data))
      .catch(() => setEngagement(null))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-[500px] w-full" />
      </div>
    );
  }

  if (!engagement) {
    return <div className="text-sm text-muted-foreground">Engagement not found</div>;
  }

  const Icon = targetIcons[engagement.targetType] ?? Globe;

  return (
    <div className="space-y-4">
      {/* Engagement header */}
      <div className="flex items-center gap-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold tracking-tight">{engagement.name}</h1>
            <Badge variant="outline" className={statusColors[engagement.status] ?? ""}>
              {engagement.status}
            </Badge>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Icon className="h-3 w-3" />
            {engagement.targetValue}
          </div>
        </div>
      </div>

      {/* Page content */}
      {children}
    </div>
  );
}
