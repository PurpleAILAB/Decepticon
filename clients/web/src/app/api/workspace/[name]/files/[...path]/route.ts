import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { resolveEngagementDir } from "@/lib/workspace";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

const WORKSPACE = process.env.WORKSPACE_PATH ?? path.join(process.env.HOME ?? "", ".decepticon", "workspace");

const FOLDERS = ["recon", "exploit", "post-exploit", "findings", "report"];

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ name: string; path: string[] }> }
) {
  let userId: string;
  try {
    ({ userId } = await requireAuth());
  } catch (e) {
    if (e instanceof AuthError) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    throw e;
  }

  const { name, path: segments } = await params;
  const engagement = await prisma.engagement.findFirst({
    where: { name, userId },
  });

  if (!engagement) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  if (!segments || segments.length === 0) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  let engagementDir: string;
  try {
    engagementDir = resolveEngagementDir(engagement.name, WORKSPACE);
  } catch {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  if (!FOLDERS.includes(segments[0])) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const target = path.resolve(engagementDir, ...segments);
  if (target !== engagementDir && !target.startsWith(engagementDir + path.sep)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  let content: string;
  try {
    const stat = await fs.stat(target);
    if (!stat.isFile()) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    content = await fs.readFile(target, "utf-8");
  } catch {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const isJson = target.endsWith(".json");
  return new NextResponse(content, {
    headers: { "Content-Type": isJson ? "application/json" : "text/plain; charset=utf-8" },
  });
}
