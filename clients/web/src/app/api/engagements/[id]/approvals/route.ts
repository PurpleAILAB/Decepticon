import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { isValidEngagementSlug } from "@/lib/engagement-slug";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

// Wire format mirrors decepticon/middleware/hitl.py: requests.jsonl holds
// `approval_request` records (ApprovalRequest.to_jsonl), decisions.jsonl holds
// `approval_decision` records consumed by FileBackedApprovalTransport.
interface MatchedRule {
  technique_tag: string | null;
  tool_pattern: string | null;
  timeout_seconds: number;
  default_on_timeout: string;
}

interface ApprovalRequest {
  kind: "approval_request";
  request_id: string;
  engagement_name: string;
  agent_name: string;
  tool_name: string;
  tool_args_redacted: Record<string, unknown>;
  matched_rule: MatchedRule;
  reason: string;
  created_at: number;
  metadata: Record<string, unknown>;
}

const ACTIONS = new Set(["allow", "deny", "redirect"]);

function workspaceFor(name: string) {
  const WORKSPACE = process.env.WORKSPACE_PATH ?? path.join(process.env.HOME ?? "", ".decepticon", "workspace");
  const dir = path.join(WORKSPACE, name, "approvals");
  return {
    dir,
    requests: path.join(dir, "requests.jsonl"),
    decisions: path.join(dir, "decisions.jsonl"),
  };
}

// Read a JSONL file into parsed objects, skipping blank/malformed lines.
// Returns [] when the file is absent.
async function readJsonl(file: string): Promise<Record<string, unknown>[]> {
  let raw: string;
  try {
    raw = await fs.readFile(file, "utf-8");
  } catch {
    return [];
  }
  const out: Record<string, unknown>[] = [];
  for (const line of raw.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const obj = JSON.parse(trimmed);
      if (obj && typeof obj === "object") out.push(obj as Record<string, unknown>);
    } catch {
      // Skip malformed line.
    }
  }
  return out;
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  let userId: string;
  try {
    ({ userId } = await requireAuth());
  } catch (e) {
    if (e instanceof AuthError) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    throw e;
  }

  const { id } = await params;
  const engagement = await prisma.engagement.findFirst({
    where: { id, userId },
  });
  if (!engagement) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  // Defense-in-depth: engagement.name is joined into a filesystem path by
  // workspaceFor(). The PATCH route already enforces the slug rule, but never
  // trust a stored name — re-validate so a malformed/legacy/tampered value can
  // never escape WORKSPACE (path traversal) when reading approvals.
  if (!isValidEngagementSlug(engagement.name)) {
    return NextResponse.json({ error: "Engagement name is not a valid workspace slug" }, { status: 400 });
  }

  const { requests, decisions } = workspaceFor(engagement.name);

  const decided = new Set<string>();
  for (const d of await readJsonl(decisions)) {
    if (d.kind === "approval_decision" && typeof d.request_id === "string") {
      decided.add(d.request_id);
    }
  }

  const pending: ApprovalRequest[] = [];
  for (const r of await readJsonl(requests)) {
    if (r.kind !== "approval_request") continue;
    const requestId = r.request_id;
    if (typeof requestId !== "string" || decided.has(requestId)) continue;
    pending.push(r as unknown as ApprovalRequest);
  }

  // Newest-first.
  pending.sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0));

  return NextResponse.json(pending);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  let userId: string;
  try {
    ({ userId } = await requireAuth());
  } catch (e) {
    if (e instanceof AuthError) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    throw e;
  }

  const { id } = await params;
  const engagement = await prisma.engagement.findFirst({
    where: { id, userId },
  });
  if (!engagement) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  // Defense-in-depth: re-validate before workspaceFor() joins the name into a
  // filesystem path that this handler writes to (mkdir + appendFile). Closes
  // path traversal even if a malformed name reached the DB.
  if (!isValidEngagementSlug(engagement.name)) {
    return NextResponse.json({ error: "Engagement name is not a valid workspace slug" }, { status: 400 });
  }

  let body: {
    request_id?: unknown;
    action?: unknown;
    operator_note?: unknown;
    redirect_args?: unknown;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const requestId = body.request_id;
  const action = body.action;
  if (typeof requestId !== "string" || !requestId) {
    return NextResponse.json({ error: "request_id required" }, { status: 400 });
  }
  if (typeof action !== "string" || !ACTIONS.has(action)) {
    return NextResponse.json({ error: "action must be one of allow, deny, redirect" }, { status: 400 });
  }

  const operatorNote =
    typeof body.operator_note === "string" ? body.operator_note : "";
  const redirectArgs =
    body.redirect_args !== undefined && body.redirect_args !== null
      ? body.redirect_args
      : null;

  const { dir, decisions } = workspaceFor(engagement.name);

  // Decision line shape consumed by FileBackedApprovalTransport._scan_decisions.
  const line =
    JSON.stringify({
      kind: "approval_decision",
      request_id: requestId,
      action,
      operator_note: operatorNote,
      redirect_args: redirectArgs,
      decided_at: Date.now() / 1000,
    }) + "\n";

  await fs.mkdir(dir, { recursive: true });
  await fs.appendFile(decisions, line, "utf-8");

  return NextResponse.json({ ok: true });
}
