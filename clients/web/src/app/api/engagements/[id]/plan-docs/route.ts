import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

const WORKSPACE = process.env.WORKSPACE_PATH ?? path.join(process.env.HOME ?? "", ".decepticon", "workspace");

const PLAN_DOCS = ["opplan", "conops", "roe", "deconfliction"] as const;

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

  const wsPath = path.join(WORKSPACE, engagement.name);
  const planDir = path.join(wsPath, "plan");

  const docs: Record<string, unknown> = {};

  for (const name of PLAN_DOCS) {
    try {
      const content = await fs.readFile(path.join(planDir, `${name}.json`), "utf-8");
      docs[name] = JSON.parse(content);
    } catch {
      // File doesn't exist yet
    }
  }

  return NextResponse.json(docs);
}
