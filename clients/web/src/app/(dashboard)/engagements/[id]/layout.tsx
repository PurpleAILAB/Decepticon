"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Skeleton } from "@/components/ui/skeleton";

interface Engagement {
  id: string;
  name: string;
}

export default function EngagementLayout({ children }: { children: React.ReactNode }) {
  const params = useParams();
  const id = params.id as string;
  const [engagement, setEngagement] = useState<Engagement | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    fetch(`/api/engagements/${id}`)
      .then((res) => {
        if (!res.ok) throw new Error("fetch failed");
        return res.json();
      })
      .then((data: Engagement) => {
        if (!active) return;
        setEngagement(data);
      })
      .catch(() => {
        if (!active) return;
        setEngagement(null);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-[500px] w-full" />
      </div>
    );
  }

  if (!engagement) {
    return <div className="text-sm text-muted-foreground">Engagement not found</div>;
  }

  return <>{children}</>;
}
