import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

interface TimelineEvent {
  timestamp: string;
  type: "plan_created" | "objective_changed" | "finding_discovered" | "file_created";
  title: string;
  detail: string;
  severity?: string;
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

  const WORKSPACE = process.env.WORKSPACE_PATH ?? "/workspace";
  const wsPath = path.join(WORKSPACE, engagement.name);
  const events: TimelineEvent[] = [];

  // Engagement creation
  events.push({
    timestamp: engagement.createdAt.toISOString(),
    type: "plan_created",
    title: "Engagement created",
    detail: `${engagement.name} (${engagement.targetType}: ${engagement.targetValue})`,
  });

  // Scan plan docs for creation timestamps
  const planDir = path.join(wsPath, "plan");
  for (const doc of ["roe.json", "conops.json", "deconfliction.json", "opplan.json"]) {
    try {
      const stat = await fs.stat(path.join(planDir, doc));
      events.push({
        timestamp: stat.mtime.toISOString(),
        type: "plan_created",
        title: `${doc.replace(".json", "").toUpperCase()} created`,
        detail: doc,
      });
    } catch {
      // File doesn't exist
    }
  }

  // Scan findings for creation timestamps
  const findingsDir = path.join(wsPath, "findings");
  try {
    const files = await fs.readdir(findingsDir);
    for (const file of files) {
      if (!file.startsWith("FIND-") || !file.endsWith(".md")) continue;
      try {
        const stat = await fs.stat(path.join(findingsDir, file));
        const content = await fs.readFile(path.join(findingsDir, file), "utf-8");
        const titleMatch = content.match(/^# (.+)$/m);
        const sevMatch = content.toLowerCase().match(/severity[:\s]*\**(critical|high|medium|low|informational)/);
        events.push({
          timestamp: stat.mtime.toISOString(),
          type: "finding_discovered",
          title: titleMatch?.[1] ?? file.replace(".md", ""),
          detail: file.replace(".md", ""),
          severity: sevMatch?.[1],
        });
      } catch {
        // skip
      }
    }
  } catch {
    // No findings dir
  }

  // Scan workspace files for activity
  const scanDirs = ["recon", "exploit", "post-exploit"];
  for (const dir of scanDirs) {
    try {
      const files = await fs.readdir(path.join(wsPath, dir));
      for (const file of files.slice(0, 20)) {
        if (file.startsWith(".")) continue;
        try {
          const stat = await fs.stat(path.join(wsPath, dir, file));
          events.push({
            timestamp: stat.mtime.toISOString(),
            type: "file_created",
            title: `${dir}/${file}`,
            detail: `${(stat.size / 1024).toFixed(1)} KB`,
          });
        } catch {
          // skip
        }
      }
    } catch {
      // Dir doesn't exist
    }
  }

  // Sort by timestamp descending (most recent first)
  events.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  return NextResponse.json(events);
}
