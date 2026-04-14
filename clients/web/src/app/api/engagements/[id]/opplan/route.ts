import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

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

  // Try to read opplan from workspace
  if (engagement.workspacePath) {
    const opplanPath = path.join(
      engagement.workspacePath,
      "plan",
      "opplan.json"
    );
    try {
      const content = await fs.readFile(opplanPath, "utf-8");
      return NextResponse.json(JSON.parse(content));
    } catch {
      // File not found or invalid — return empty
    }
  }

  return NextResponse.json({ objectives: [] });
}
