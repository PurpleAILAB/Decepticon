"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Activity,
  Database,
  Server,
  Network,
  Bot,
  Box,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentConfig } from "@/lib/agents";

interface ServiceStatus {
  name: string;
  status: "ok" | "error" | "loading";
  detail: string;
  icon: typeof Server;
}

interface Engagement {
  id: string;
  name: string;
  status: string;
}

function StatusDot({ status }: { status: "ok" | "error" | "loading" }) {
  if (status === "loading") return <Loader2 className="h-3 w-3 animate-spin text-amber-400" />;
  if (status === "ok") return <div className="h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50" />;
  return <div className="h-2.5 w-2.5 rounded-full bg-red-400 shadow-sm shadow-red-400/50" />;
}

export default function SettingsPage() {
  const [services, setServices] = useState<ServiceStatus[]>([
    { name: "LangGraph API", status: "loading", detail: "Checking...", icon: Activity },
    { name: "LiteLLM Proxy", status: "loading", detail: "Checking...", icon: Server },
    { name: "Neo4j", status: "loading", detail: "Checking...", icon: Network },
    { name: "PostgreSQL", status: "ok", detail: "Connected", icon: Database },
    { name: "Sandbox", status: "ok", detail: "decepticon-sandbox", icon: Box },
  ]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [engagements, setEngagements] = useState<Engagement[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);
  // Check all services via server-side health API
  useEffect(() => {
    fetch("/api/health", { signal: AbortSignal.timeout(10000) })
      .then(async (res) => {
        if (!res.ok) throw new Error("Health API failed");
        const data = await res.json();
        setServices((prev) =>
          prev.map((s) => {
            const match = (data.services ?? []).find((r: { name: string }) =>
              s.name.toLowerCase().includes(r.name) || r.name.includes(s.name.toLowerCase().split(" ")[0])
            );
            if (match) return { ...s, status: match.status as "ok" | "error", detail: match.detail ?? "" };
            return s;
          })
        );
      })
      .catch(() => {
        setServices((prev) =>
          prev.map((s) => s.status === "loading" ? { ...s, status: "error" as const, detail: "Unreachable" } : s)
        );
      });
  }, []);

  // Fetch agents
  useEffect(() => {
    fetch("/api/agents")
      .then((res) => res.json())
      .then((data: AgentConfig[]) => setAgents(data))
      .catch(() => {})
      .finally(() => setLoadingAgents(false));
  }, []);

  // Fetch engagements
  useEffect(() => {
    fetch("/api/engagements")
      .then((res) => res.json())
      .then((data: Engagement[]) => setEngagements(data))
      .catch(() => {});
  }, []);

  const statusCounts = {
    total: engagements.length,
    running: engagements.filter((e) => e.status === "running").length,
    completed: engagements.filter((e) => e.status === "completed").length,
    draft: engagements.filter((e) => e.status === "draft").length,
    planning: engagements.filter((e) => e.status === "planning").length,
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">System status and configuration</p>
      </div>

      {/* System Health */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Server className="h-4 w-4" />
            System Health
          </CardTitle>
          <CardDescription>Infrastructure component status</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2">
            {services.map((svc) => (
              <div key={svc.name} className="flex items-center gap-3 rounded-lg border border-border/50 p-3">
                <StatusDot status={svc.status} />
                <svc.icon className="h-4 w-4 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{svc.name}</p>
                  <p className="text-xs text-muted-foreground truncate">{svc.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Engagement Stats */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Engagement Statistics</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-5 gap-4 text-center">
            {([
              ["Total", statusCounts.total, "text-foreground"],
              ["Running", statusCounts.running, "text-amber-400"],
              ["Completed", statusCounts.completed, "text-emerald-400"],
              ["Planning", statusCounts.planning, "text-violet-400"],
              ["Draft", statusCounts.draft, "text-zinc-400"],
            ] as const).map(([label, count, color]) => (
              <div key={label}>
                <p className={cn("text-2xl font-bold", color)}>{count}</p>
                <p className="text-xs text-muted-foreground">{label}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Agent Registry */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Bot className="h-4 w-4" />
            Agent Registry
          </CardTitle>
          <CardDescription>{agents.length} agents registered</CardDescription>
        </CardHeader>
        <CardContent>
          {loadingAgents ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {agents.map((agent) => (
                <div key={agent.id} className="flex items-center gap-3 rounded-lg border border-border/50 p-3">
                  <div
                    className="h-3 w-3 shrink-0 rounded-full"
                    style={{ backgroundColor: agent.color }}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{agent.name}</p>
                    <p className="text-xs text-muted-foreground truncate">{agent.description}</p>
                  </div>
                  <Badge variant="outline" className="shrink-0 text-[10px]">
                    {agent.role}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Configuration</CardTitle>
          <CardDescription>Read-only system configuration</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 text-sm">
            {[
              ["Edition", "Open Source (OSS)"],
              ["LangGraph API (internal)", process.env.NEXT_PUBLIC_LANGGRAPH_API_URL ?? "http://localhost:2024"],
              ["Model Profile", "eco (per-agent tier)"],
              ["C2 Framework", "Sliver"],
            ].map(([label, value]) => (
              <div key={label} className="flex items-center justify-between rounded-lg border border-border/50 px-3 py-2">
                <span className="text-muted-foreground">{label}</span>
                <span className="font-mono text-xs">{value}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
