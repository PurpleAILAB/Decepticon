"use client";

import { useState, useEffect } from "react";
import { useParams, usePathname } from "next/navigation";
import { EngagementProvider } from "@/lib/engagement-context";
import { useRunObserver } from "@/hooks/useRunObserver";
import { WebTerminal } from "@/components/terminal/web-terminal";
import type { ModelOverrides } from "@/components/engagement/engagement-model-picker";
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

  const [engagement, setEngagement] = useState<{
    name: string;
    modelOverride?: string | null;
    modelOverrides?: ModelOverrides | null;
  } | null>(null);
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
        const eng = (await engRes.json()) as {
          name: string;
          threadId?: string | null;
          modelOverride?: string | null;
          modelOverrides?: ModelOverrides | null;
        };
        const planDocs = planRes.ok ? ((await planRes.json()) as Record<string, unknown>) : {};
        if (cancelled) return;
        setEngagement(eng);
        setAgentId(pickAssistant(planDocs));
        // Seed the observer from the persisted thread so the dashboard attaches
        // to the engagement's real thread on load, not a brand-new empty one.
        if (eng.threadId) setThreadId(eng.threadId);
      } catch (err) {
        console.error("[EngagementLayout] Failed to resolve engagement:", err);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [engagementId]);

  useEffect(() => {
    function handleModelsUpdated(event: Event) {
      const detail = (event as CustomEvent<{
        engagementId?: string;
        modelOverride?: string | null;
        modelOverrides?: ModelOverrides | null;
      }>).detail;
      if (detail?.engagementId !== engagementId) return;
      setEngagement((current) =>
        current
          ? {
              ...current,
              modelOverride: detail.modelOverride || null,
              modelOverrides: detail.modelOverrides ?? null,
            }
          : current,
      );
    }

    window.addEventListener("decepticon:engagement-models-updated", handleModelsUpdated);
    return () => window.removeEventListener("decepticon:engagement-models-updated", handleModelsUpdated);
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
      threadId={threadId}
      setThreadId={setThreadId}
      events={events}
      isRunning={isRunning}
      activeRunId={activeRunId}
    >
      <div className="flex h-full min-w-0 flex-col overflow-hidden">
        <div
          className={cn(
            "min-h-0 min-w-0 flex-1",
            isLivePath ? "flex flex-col overflow-hidden xl:flex-row" : "overflow-auto",
          )}
        >
          <div className={cn("min-h-0 min-w-0 flex-1", isLivePath ? "overflow-hidden" : "")}>
            {children}
          </div>
          {/* Terminal: always mounted, visibility controlled by route */}
          <div
            className={cn(
              "overflow-hidden transition-[height,width] duration-200",
              isLivePath
                ? "h-[42dvh] min-h-64 shrink-0 border-t border-white/[0.08] xl:h-auto xl:w-[clamp(460px,32vw,620px)] xl:border-l xl:border-t-0"
                : "h-0 min-h-0",
            )}
          >
            {terminalReady && (
              <WebTerminal
                engagementId={engagementId}
                engagementSlug={engagement!.name}
                agentId={agentId!}
                modelOverride={engagement.modelOverride || ""}
                modelOverrides={engagement.modelOverrides ?? undefined}
                threadId={threadId ?? undefined}
                className="h-full"
                onThreadId={setThreadId}
              />
            )}
          </div>
        </div>
      </div>
    </EngagementProvider>
  );
}
