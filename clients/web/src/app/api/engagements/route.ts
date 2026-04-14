import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { NextRequest, NextResponse } from "next/server";

export async function GET() {
  try {
    const { userId } = await requireAuth();

    const engagements = await prisma.engagement.findMany({
      where: { userId },
      orderBy: { createdAt: "desc" },
    });

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

    const validTypes = [
      "local_path", "git_url", "file_upload", "web_url", "ip_range", "github_repo",
    ];
    if (!validTypes.includes(targetType)) {
      return NextResponse.json(
        { error: `Invalid targetType. Must be one of: ${validTypes.join(", ")}` },
        { status: 400 }
      );
    }

    const engagement = await prisma.engagement.create({
      data: {
        name,
        targetType,
        targetValue,
        userId,
      },
    });

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
