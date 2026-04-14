import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Crosshair, FileWarning, Shield, AlertTriangle, TrendingUp, TrendingDown } from "lucide-react";

const metrics = [
  {
    title: "Active Engagements",
    value: "0",
    change: null,
    icon: Crosshair,
    gradient: "from-violet-500/20 to-purple-500/20",
    iconColor: "text-violet-400",
    borderGlow: "hover:border-violet-500/30",
  },
  {
    title: "Total Findings",
    value: "0",
    change: null,
    icon: FileWarning,
    gradient: "from-amber-500/20 to-orange-500/20",
    iconColor: "text-amber-400",
    borderGlow: "hover:border-amber-500/30",
  },
  {
    title: "Critical Vulnerabilities",
    value: "0",
    change: null,
    icon: AlertTriangle,
    gradient: "from-red-500/20 to-rose-500/20",
    iconColor: "text-red-400",
    borderGlow: "hover:border-red-500/30",
  },
  {
    title: "Defenses Verified",
    value: "0",
    change: null,
    icon: Shield,
    gradient: "from-emerald-500/20 to-green-500/20",
    iconColor: "text-emerald-400",
    borderGlow: "hover:border-emerald-500/30",
  },
];

const severityData = [
  { label: "Critical", count: 0, color: "bg-red-500", barColor: "bg-red-500/80" },
  { label: "High", count: 0, color: "bg-orange-500", barColor: "bg-orange-500/80" },
  { label: "Medium", count: 0, color: "bg-yellow-500", barColor: "bg-yellow-500/80" },
  { label: "Low", count: 0, color: "bg-blue-500", barColor: "bg-blue-500/80" },
  { label: "Info", count: 0, color: "bg-slate-500", barColor: "bg-slate-500/80" },
];

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Overview of your security testing operations
        </p>
      </div>

      {/* Metric Cards — CTEM style with gradient backgrounds */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map((metric) => (
          <Card
            key={metric.title}
            className={`group relative overflow-hidden transition-colors duration-200 ${metric.borderGlow}`}
          >
            {/* Gradient background overlay */}
            <div className={`absolute inset-0 bg-gradient-to-br ${metric.gradient} opacity-0 transition-opacity duration-300 group-hover:opacity-100`} />
            <CardHeader className="relative flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {metric.title}
              </CardTitle>
              <div className={`flex h-8 w-8 items-center justify-center rounded-lg bg-white/5 ${metric.iconColor}`}>
                <metric.icon className="h-4 w-4" />
              </div>
            </CardHeader>
            <CardContent className="relative">
              <div className="flex items-end gap-2">
                <span className="text-4xl font-bold tracking-tight">{metric.value}</span>
                {metric.change !== null && (
                  <span className={`mb-1 flex items-center gap-0.5 text-xs font-medium ${(metric.change as number) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {(metric.change as number) >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                    {Math.abs(metric.change as number)}%
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Severity Distribution — horizontal bar chart style */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Severity Distribution</CardTitle>
          <CardDescription>Findings breakdown by severity level</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {severityData.map((severity) => (
              <div key={severity.label} className="flex items-center gap-3">
                <div className="flex w-20 items-center gap-2">
                  <div className={`h-2.5 w-2.5 rounded-full ${severity.color}`} />
                  <span className="text-sm text-muted-foreground">{severity.label}</span>
                </div>
                <div className="flex-1">
                  <div className="h-2 overflow-hidden rounded-full bg-secondary">
                    <div
                      className={`h-full rounded-full ${severity.barColor} transition-all duration-500`}
                      style={{ width: "0%" }}
                    />
                  </div>
                </div>
                <Badge variant="secondary" className="min-w-[2rem] justify-center font-mono text-xs">
                  {severity.count}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Recent Activity Grid */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent Engagements</CardTitle>
            <CardDescription>Your latest red team operations</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
              No engagements yet
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Latest Findings</CardTitle>
            <CardDescription>Recently discovered vulnerabilities</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
              No findings yet
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
