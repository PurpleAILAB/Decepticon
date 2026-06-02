"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { ShieldAlert, Check, X, Loader2, Pencil } from "lucide-react";

// Matches the `approval_request` wire format written by
// decepticon/middleware/hitl.py (ApprovalRequest.to_jsonl).
interface ApprovalRequest {
  request_id: string;
  engagement_name: string;
  agent_name: string;
  tool_name: string;
  tool_args_redacted: Record<string, unknown>;
  reason: string;
  created_at: number;
}

interface ApprovalGateProps {
  engagementId: string;
  className?: string;
}

const POLL_INTERVAL_MS = 3000;

export function ApprovalGate({ engagementId, className }: ApprovalGateProps) {
  const [requests, setRequests] = useState<ApprovalRequest[]>([]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const res = await fetch(`/api/engagements/${engagementId}/approvals`, {
          signal,
        });
        if (!res.ok) return;
        const data = (await res.json()) as ApprovalRequest[];
        setRequests(Array.isArray(data) ? data : []);
      } catch {
        // Transient — keep prior state, retry next tick.
      }
    },
    [engagementId],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    const interval = setInterval(() => load(controller.signal), POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      clearInterval(interval);
    };
  }, [load]);

  const onDecided = useCallback(
    (requestId: string) => {
      // Optimistically drop the resolved gate, then re-sync with the server.
      setRequests((prev) => prev.filter((r) => r.request_id !== requestId));
      void load();
    },
    [load],
  );

  if (requests.length === 0) return null;

  return (
    <div className={cn("space-y-2", className)}>
      {requests.map((req) => (
        <ApprovalCard key={req.request_id} request={req} engagementId={engagementId} onDecided={onDecided} />
      ))}
    </div>
  );
}

interface ApprovalCardProps {
  request: ApprovalRequest;
  engagementId: string;
  onDecided: (requestId: string) => void;
}

function ApprovalCard({ request, engagementId, onDecided }: ApprovalCardProps) {
  const [note, setNote] = useState("");
  const [argsText, setArgsText] = useState("");
  const [submitting, setSubmitting] = useState<"allow" | "deny" | "redirect" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const noteRef = useRef(note);
  noteRef.current = note;

  async function decide(action: "allow" | "deny" | "redirect") {
    if (submitting) return;

    let redirectArgs: Record<string, unknown> | undefined;
    if (action === "redirect") {
      try {
        redirectArgs = JSON.parse(argsText) as Record<string, unknown>;
      } catch {
        setError("Redirect args must be valid JSON");
        return;
      }
    }

    setSubmitting(action);
    setError(null);
    try {
      const res = await fetch(`/api/engagements/${engagementId}/approvals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: request.request_id,
          action,
          operator_note: noteRef.current.trim(),
          ...(action === "redirect" ? { redirect_args: redirectArgs } : {}),
        }),
      });
      if (!res.ok) {
        setError("Failed to submit decision");
        setSubmitting(null);
        return;
      }
      onDecided(request.request_id);
    } catch {
      setError("Network error");
      setSubmitting(null);
    }
  }

  const argEntries = Object.entries(request.tool_args_redacted ?? {});

  return (
    <Card className="border-amber-500/40 bg-amber-500/5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm text-amber-300">
          <ShieldAlert className="h-4 w-4 shrink-0" />
          <span className="flex-1">Approval required</span>
          <Badge variant="outline" className="border-amber-500/40 text-amber-300">
            {request.agent_name}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-muted-foreground">Tool</span>
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground">
            {request.tool_name}
          </code>
        </div>

        {request.reason && (
          <p className="text-muted-foreground">{request.reason}</p>
        )}

        {argEntries.length > 0 && (
          <div className="rounded-md border border-white/[0.08] bg-background/40 p-2">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Arguments (redacted)
            </div>
            <dl className="space-y-0.5">
              {argEntries.map(([key, value]) => (
                <div key={key} className="flex gap-2 font-mono text-[11px]">
                  <dt className="shrink-0 text-muted-foreground">{key}</dt>
                  <dd className="min-w-0 flex-1 break-all text-foreground">
                    {typeof value === "string" ? value : JSON.stringify(value)}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <Textarea
          aria-label="Operator note"
          placeholder="Optional note…"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={submitting !== null}
          className="min-h-[2.5rem] text-xs"
        />

        <Textarea
          aria-label="Redirect arguments (JSON)"
          placeholder='Redirect args as JSON, e.g. {"cmd": "ls -la"}'
          value={argsText}
          onChange={(e) => setArgsText(e.target.value)}
          disabled={submitting !== null}
          className="min-h-[2.5rem] font-mono text-xs"
        />

        {error && <p className="text-destructive">{error}</p>}

        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            onClick={() => decide("allow")}
            disabled={submitting !== null}
            className="flex-1 bg-emerald-600 text-white hover:bg-emerald-500"
          >
            {submitting === "allow" ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Check />
            )}
            Allow
          </Button>
          <Button
            type="button"
            size="sm"
            variant="destructive"
            onClick={() => decide("deny")}
            disabled={submitting !== null}
            className="flex-1"
          >
            {submitting === "deny" ? <Loader2 className="animate-spin" /> : <X />}
            Deny
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => decide("redirect")}
            disabled={submitting !== null}
            className="flex-1"
          >
            {submitting === "redirect" ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Pencil />
            )}
            Redirect
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
