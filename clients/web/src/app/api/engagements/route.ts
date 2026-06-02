import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { SLUG_RE, VALID_TARGET_TYPES } from "@/lib/workspace";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

const WORKSPACE = process.env.WORKSPACE_PATH ?? path.join(process.env.HOME ?? "", ".decepticon", "workspace");

const WORKSPACE_SUBDIRS = ["plan"];

function isEngagementWorkspaceDir(name: string) {
  return SLUG_RE.test(name) && !name.startsWith(".");
}

export async function GET() {
  try {
    const { userId } = await requireAuth();

    const engagements = (await prisma.engagement.findMany({
      where: { userId },
      orderBy: { createdAt: "desc" },
    })).filter((eng) => isEngagementWorkspaceDir(eng.name));

    // Auto-import workspace dirs created by CLI that are not yet in DB
    try {
      const entries = await fs.readdir(WORKSPACE, { withFileTypes: true });
      const wsDirs = entries
        .filter((e) => e.isDirectory() && isEngagementWorkspaceDir(e.name))
        .map((e) => e.name);
      const knownNames = new Set(engagements.map((e) => e.name));

      for (const dir of wsDirs) {
        if (!knownNames.has(dir)) {
          const wsPath = path.join(WORKSPACE, dir);
          const imported = await prisma.engagement.create({
            data: {
              name: dir,
              targetType: "web_url",
              targetValue: "imported from CLI",
              status: "running",
              userId,
              workspacePath: wsPath,
            },
          });
          engagements.unshift(imported);
        }
      }
    } catch {
      // Workspace dir may not exist yet — skip
    }

    return NextResponse.json(engagements);
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("GET /api/engagements error:", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal server error" },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const { userId } = await requireAuth();

    const body = await req.json();
    const { name, targetType, targetValue } = body;

    if (!name || !targetType || !targetValue) {
      return NextResponse.json(
        { error: "Missing required fields: name, targetType, targetValue" },
        { status: 400 }
      );
    }

    if (!VALID_TARGET_TYPES.includes(targetType)) {
      return NextResponse.json(
        { error: `Invalid targetType. Must be one of: ${VALID_TARGET_TYPES.join(", ")}` },
        { status: 400 }
      );
    }

    // Engagement name doubles as the workspace slug. Enforce the same regex
    // the launcher uses so a name created here works as a folder name and a
    // future "Resume <slug>" picker entry without further escaping.
    if (!SLUG_RE.test(name)) {
      return NextResponse.json(
        {
          error:
            "Invalid engagement name — must be 3-64 chars, lowercase letters / digits / internal hyphens",
        },
        { status: 400 }
      );
    }
    const existing = await prisma.engagement.findFirst({
      where: { name, userId },
    });
    if (existing) {
      return NextResponse.json(
        { error: `An engagement named '${name}' already exists` },
        { status: 409 },
      );
    }
    const wsPath = path.join(WORKSPACE, name);

    const engagement = await prisma.engagement.create({
      data: {
        name,
        targetType,
        targetValue,
        userId,
        workspacePath: wsPath,
      },
    });

    // Create only the planning root. Phase artifact directories are created
    // lazily when an agent writes a real artifact there.
    try {
      await Promise.all(
        WORKSPACE_SUBDIRS.map((sub) => fs.mkdir(path.join(wsPath, sub), { recursive: true }))
      );
    } catch {
      // Non-fatal — workspace creation failure doesn't block engagement creation
    }

    return NextResponse.json(engagement, { status: 201 });
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("POST /api/engagements error:", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal server error" },
      { status: 500 }
    );
  }
}
