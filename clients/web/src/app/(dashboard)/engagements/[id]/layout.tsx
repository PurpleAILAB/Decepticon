"use client";

import { useState, useEffect } from "react";
import { useParams, usePathname } from "next/navigation";
import { EngagementProvider } from "@/lib/engagement-context";
import { useRunObserver } from "@/hooks/useRunObserver";
import { WebTerminal } from "@/components/terminal/web-terminal";
import { cn } from "@/lib/utils";

const REQUIRED_PLAN_DOCS = ["roe", "conops", "deconfliction"] as const;

function pickAssistant(planDocs: Record<string, unknown>): "soundwave" | "decepticon" {
  for (const name of REQUIRED_PLAN_DOCS) {
    if (planDocs[name] == null) return "soundwave";
  }
  return "decepticon";
}

export default function EngagementLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const params = useParams();
  const pathname = usePathname();
  const engagementId = params.id as string;

  const [engagement, setEngagement] = useState<{ name: string } | null>(null);
  const [agentId, setAgentId] = useState<"soundwave" | "decepticon" | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);

  // Resolve engagement metadata — determines agentId and slug for WS
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [engRes, planRes] = await Promise.all([
          fetch(`/api/engagements/${engagementId}`),
          fetch(`/api/engagements/${engagementId}/plan-docs`),
        ]);
        if (!engRes.ok) return;
        const eng = (await engRes.json()) as { name: string };
        const planDocs = planRes.ok ? ((await planRes.json()) as Record<string, unknown>) : {};
        if (cancelled) return;
        setEngagement(eng);
        setAgentId(pickAssistant(planDocs));
      } catch (err) {
        console.error("[EngagementLayout] Failed to resolve engagement:", err);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [engagementId]);

  // Persistent observer — survives tab navigation
  const { events, isRunning, activeRunId } = useRunObserver({ threadId });

  const isLivePath = pathname.endsWith("/live");

  // Don't render terminal until we know the slug and assistant
  const terminalReady = engagement != null && agentId != null;

  return (
    <EngagementProvider
      engagementId={engagementId}
      engagementSlug={engagement?.name ?? ""}
      agentId={agentId ?? "soundwave"}
      events={events}
      isRunning={isRunning}
      activeRunId={activeRunId}
    >
      <div className="flex h-full overflow-hidden">
        <div className="flex-1 min-w-0 overflow-auto">
          {children}
        </div>
        {/* Terminal: always mounted, visibility controlled by route */}
        <div
          className={cn(
            "shrink-0 overflow-hidden border-l border-white/[0.08] transition-[width] duration-200",
            isLivePath ? "w-[35%] min-w-[350px]" : "w-0 min-w-0",
          )}
        >
          {terminalReady && (
            <WebTerminal
              engagementId={engagementId}
              engagementSlug={engagement!.name}
              agentId={agentId!}
              className="h-full"
              onThreadId={setThreadId}
            />
          )}
        </div>
      </div>
    </EngagementProvider>
  );
}
